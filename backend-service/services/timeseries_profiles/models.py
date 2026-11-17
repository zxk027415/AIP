"""Dataset and domain profile data models."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

ClockMode = Literal["event_time", "index"]
SourceKind = Literal["file", "directory", "manifest", "connection"]
LicenseStatus = Literal["verified", "unverified", "prohibited"]
UsePurpose = Literal["local_validation", "product_workflow", "distribution", "production", "benchmark_reuse"]


class DatasetProfile(BaseModel):
    profile_id: str
    profile_version: str
    slot: str = Field(description="Allowed slot partition, e.g. pv_point")
    source_kind: SourceKind = "file"
    source_ref: str = Field(description="Relative path or registered connector ID")
    path_root_alias: str = "backend_service"
    format: str = "parquet"
    clock_mode: ClockMode = "event_time"
    time_column: Optional[str] = "time"
    index_column: Optional[str] = Field(
        default=None,
        description="Monotonic ordering column when clock_mode=index",
    )
    simulation_step: Optional[int] = Field(
        default=1,
        description="Explicit index step size for index-clock replay (no wall time)",
    )
    entity_keys: list[str] = Field(default_factory=list)
    feature_columns: list[str] = Field(default_factory=list)
    label_column: Optional[str] = None
    label_semantics: Optional[str] = None
    sampling_interval: Optional[str] = "PT5M"
    timezone: str = "UTC"
    split_policy: dict[str, Any] = Field(default_factory=dict)
    license_ref: Optional[str] = None
    license_status: LicenseStatus = "verified"
    redistribution_allowed: bool = False
    allowed_use_purposes: list[str] = Field(default_factory=lambda: ["local_validation", "product_workflow"])
    adapter_id: Optional[str] = None
    quality_rules: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "published"] = "published"
    description: Optional[str] = None

    @field_validator("time_column")
    @classmethod
    def _validate_time_column(cls, value: Optional[str], info):
        clock_mode = info.data.get("clock_mode")
        if clock_mode == "event_time" and not value:
            raise ValueError("time_column is required when clock_mode=event_time")
        if clock_mode == "index" and value:
            raise ValueError("time_column must be empty when clock_mode=index")
        return value

    @field_validator("index_column")
    @classmethod
    def _validate_index_column(cls, value: Optional[str], info):
        clock_mode = info.data.get("clock_mode")
        if clock_mode == "index" and not value:
            raise ValueError("index_column is required when clock_mode=index")
        if clock_mode == "event_time" and value:
            raise ValueError("index_column must be empty when clock_mode=event_time")
        return value


class DomainProfile(BaseModel):
    domain_profile_id: str
    profile_version: str
    slot: str
    label_space_ref: Optional[str] = None
    field_aliases: dict[str, str] = Field(default_factory=dict)
    display_names: dict[str, str] = Field(default_factory=dict)
    candidate_policy_defaults: dict[str, Any] = Field(default_factory=dict)
    alarm_policy_defaults: dict[str, Any] = Field(default_factory=dict)
    role_permissions: dict[str, Any] = Field(default_factory=dict)
    slot_defaults: dict[str, Any] = Field(default_factory=dict)
    entity_key_display: dict[str, str] = Field(default_factory=dict)
    allowed_point_sources: list[str] = Field(default_factory=list)
    status: Literal["draft", "published"] = "published"
    description: Optional[str] = None


class AcquisitionManifestEntry(BaseModel):
    role: Literal["train", "validation", "test", "replay", "reference"]
    dataset_profile_ref: str
    source_digest: Optional[str] = None
    notes: Optional[str] = None


class AcquisitionManifest(BaseModel):
    manifest_id: str
    manifest_version: str
    slot: str
    entries: list[AcquisitionManifestEntry]
    placeholder_external: list[dict[str, Any]] = Field(default_factory=list)
    description: Optional[str] = None


class ProfilePreflightIssue(BaseModel):
    code: str
    severity: Literal["error", "warning"] = "error"
    field: Optional[str] = None
    message: str
    sample_count: Optional[int] = None
    hint: Optional[str] = None


class ProfilePreflightReport(BaseModel):
    profile_id: str
    profile_version: str
    use_purpose: str
    ready: bool
    blocked_by_license: bool = False
    resolved_source_ref: Optional[str] = None
    source_digest: Optional[str] = None
    row_count: Optional[int] = None
    entity_count: Optional[int] = None
    time_range_start: Optional[str] = None
    time_range_end: Optional[str] = None
    duplicate_point_count: int = 0
    missing_required_columns: list[str] = Field(default_factory=list)
    issues: list[ProfilePreflightIssue] = Field(default_factory=list)
