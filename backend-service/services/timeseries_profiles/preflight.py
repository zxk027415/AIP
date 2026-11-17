"""Read-only dataset profile preflight."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import pandas as pd

from .models import DatasetProfile, ProfilePreflightIssue, ProfilePreflightReport, UsePurpose
from .path_guard import PathGuardError, resolve_profile_source_path
from .loader import load_dataset_from_profile
from services.benchmark.governance import BENCHMARK_EXECUTION_PURPOSE, is_benchmark_slot


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _purpose_allowed(profile: DatasetProfile, use_purpose: UsePurpose) -> tuple[bool, Optional[str]]:
    if use_purpose in profile.allowed_use_purposes:
        return True, None
    if profile.license_status == "prohibited":
        return False, "license_status=prohibited"
    if use_purpose == "local_validation" and profile.license_status == "unverified":
        return True, None
    if use_purpose in {"distribution", "production"} and not profile.redistribution_allowed:
        return False, "redistribution_allowed=false"
    return False, f"use_purpose {use_purpose!r} not in allowed_use_purposes"


def run_dataset_profile_preflight(
    profile: DatasetProfile,
    use_purpose: UsePurpose = "local_validation",
) -> ProfilePreflightReport:
    issues: list[ProfilePreflightIssue] = []
    resolved_path: Optional[Path] = None
    blocked_by_license = False

    if is_benchmark_slot(profile.slot) and use_purpose == "product_workflow":
        blocked_by_license = True
        issues.append(
            ProfilePreflightIssue(
                code="benchmark_product_purpose_forbidden",
                field="slot",
                message=f"benchmark slot {profile.slot!r} cannot use product_workflow preflight",
                hint="Use benchmark_reuse or local_validation",
            )
        )
    if not is_benchmark_slot(profile.slot) and use_purpose == BENCHMARK_EXECUTION_PURPOSE:
        blocked_by_license = True
        issues.append(
            ProfilePreflightIssue(
                code="benchmark_purpose_requires_benchmark_slot",
                field="use_purpose",
                message="benchmark_reuse preflight requires a benchmark_* slot profile",
            )
        )

    allowed, license_reason = _purpose_allowed(profile, use_purpose)
    if not allowed:
        blocked_by_license = True
        issues.append(
            ProfilePreflightIssue(
                code="license_blocked",
                field="allowed_use_purposes",
                message=f"Profile blocked for use_purpose={use_purpose}",
                hint=license_reason or "Check license_status and redistribution_allowed",
            )
        )

    if profile.source_kind == "connection":
        issues.append(
            ProfilePreflightIssue(
                code="connector_not_implemented",
                message="Connection-backed profiles are not implemented in G1",
                hint="Use file-backed profile for PV snapshot",
            )
        )
        return ProfilePreflightReport(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            use_purpose=use_purpose,
            ready=False,
            blocked_by_license=blocked_by_license,
            issues=issues,
        )

    try:
        resolved_path = resolve_profile_source_path(profile.source_ref, profile.path_root_alias)
    except PathGuardError as exc:
        issues.append(
            ProfilePreflightIssue(
                code=exc.code,
                field="source_ref",
                message=exc.message,
                hint="Use a relative path under backend_service or project_root",
            )
        )
        return ProfilePreflightReport(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            use_purpose=use_purpose,
            ready=False,
            blocked_by_license=blocked_by_license,
            issues=issues,
        )

    if not resolved_path.exists():
        issues.append(
            ProfilePreflightIssue(
                code="source_not_found",
                field="source_ref",
                message=f"Source file not found: {profile.source_ref}",
            )
        )
        return ProfilePreflightReport(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            use_purpose=use_purpose,
            ready=False,
            blocked_by_license=blocked_by_license,
            resolved_source_ref=profile.source_ref,
            issues=issues,
        )

    required_columns = list(profile.entity_keys)
    if profile.time_column:
        required_columns.append(profile.time_column)
    if profile.clock_mode == "index" and profile.index_column:
        required_columns.append(profile.index_column)
    required_columns.extend(profile.feature_columns)
    if profile.label_column:
        required_columns.append(profile.label_column)

    try:
        if profile.adapter_id:
            df = load_dataset_from_profile(profile)
        elif profile.format == "parquet":
            df = pd.read_parquet(resolved_path, columns=None)
        elif profile.format in {"csv", "tsv"}:
            df = pd.read_csv(resolved_path)
        else:
            issues.append(
                ProfilePreflightIssue(
                    code="unsupported_format",
                    field="format",
                    message=f"Preflight does not support format={profile.format!r} without adapter_id",
                )
            )
            df = None
    except Exception as exc:
        issues.append(
            ProfilePreflightIssue(
                code="read_failed",
                message=f"Failed to read source: {exc}",
            )
        )
        df = None

    row_count = entity_count = duplicate_point_count = None
    time_range_start = time_range_end = None
    missing_required: list[str] = []
    source_digest = _file_digest(resolved_path)

    if df is not None:
        row_count = int(len(df))
        missing_required = [col for col in required_columns if col not in df.columns]
        if missing_required:
            issues.append(
                ProfilePreflightIssue(
                    code="missing_columns",
                    field=",".join(missing_required),
                    message=f"Missing required columns: {missing_required}",
                    sample_count=len(missing_required),
                    hint="Update profile feature_columns/entity_keys or fix dataset",
                )
            )

        if profile.clock_mode == "event_time" and profile.time_column in df.columns:
            ts = pd.to_datetime(df[profile.time_column], errors="coerce", utc=True)
            invalid_ts = int(ts.isna().sum())
            if invalid_ts:
                issues.append(
                    ProfilePreflightIssue(
                        code="invalid_timestamps",
                        field=profile.time_column,
                        message=f"{invalid_ts} rows have unparseable timestamps",
                        sample_count=invalid_ts,
                    )
                )
            else:
                time_range_start = ts.min().isoformat()
                time_range_end = ts.max().isoformat()

            if profile.entity_keys:
                entity_cols = [c for c in profile.entity_keys if c in df.columns]
                if entity_cols and profile.time_column in df.columns:
                    dup_mask = df.duplicated(subset=entity_cols + [profile.time_column], keep=False)
                    duplicate_point_count = int(dup_mask.sum())
                    if duplicate_point_count:
                        issues.append(
                            ProfilePreflightIssue(
                                code="duplicate_points",
                                message=f"Found {duplicate_point_count} duplicate entity+time rows",
                                sample_count=duplicate_point_count,
                                hint="Deduplicate source or fix entity_keys/time_column mapping",
                            )
                        )
                    entity_count = int(df[entity_cols].drop_duplicates().shape[0])

        elif profile.clock_mode == "index" and profile.index_column and profile.index_column in df.columns:
            idx = pd.to_numeric(df[profile.index_column], errors="coerce")
            invalid_idx = int(idx.isna().sum())
            if invalid_idx:
                issues.append(
                    ProfilePreflightIssue(
                        code="invalid_index_values",
                        field=profile.index_column,
                        message=f"{invalid_idx} rows have invalid index values",
                        sample_count=invalid_idx,
                    )
                )
            else:
                time_range_start = str(int(idx.min()))
                time_range_end = str(int(idx.max()))

            if profile.entity_keys:
                entity_cols = [c for c in profile.entity_keys if c in df.columns]
                if entity_cols:
                    dup_mask = df.duplicated(subset=entity_cols + [profile.index_column], keep=False)
                    duplicate_point_count = int(dup_mask.sum())
                    if duplicate_point_count:
                        issues.append(
                            ProfilePreflightIssue(
                                code="duplicate_points",
                                message=f"Found {duplicate_point_count} duplicate entity+index rows",
                                sample_count=duplicate_point_count,
                            )
                        )
                    entity_count = int(df[entity_cols].drop_duplicates().shape[0])

    ready = not blocked_by_license and not any(i.severity == "error" for i in issues)
    return ProfilePreflightReport(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        use_purpose=use_purpose,
        ready=ready,
        blocked_by_license=blocked_by_license,
        resolved_source_ref=profile.source_ref,
        source_digest=source_digest,
        row_count=row_count,
        entity_count=entity_count,
        time_range_start=time_range_start,
        time_range_end=time_range_end,
        duplicate_point_count=duplicate_point_count or 0,
        missing_required_columns=missing_required,
        issues=issues,
    )
