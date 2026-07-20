# @AI_GENERATED: copy a complete iterative-labeling slot while preserving the source slot for rollback
"""Copy one iterative-labeling slot into another with path-aware JSON rewrites.

Run from ``backend-service``:
  conda run -n cp_web python scripts/migrate_iterative_labeling_slot.py \
    --source-slot default --target-slot pv_fault --dry-run
  conda run -n cp_web python scripts/migrate_iterative_labeling_slot.py \
    --source-slot default --target-slot pv_fault

The utility never removes or modifies source-slot assets. It refuses to overwrite
an existing target slot so a failed or partial migration remains recoverable.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_DIR.parent
_ITERATIVE_ROOT = _BACKEND_DIR / "data" / "iterative_labeling"
_SLOT_COMPONENTS = (
    "cumulative_training",
    "prediction_batches",
    "prediction_inputs",
    "pv_scheduler",
    "review_results",
    "ground_truth",
    "iterations",
)
_SLOT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Non-destructively copy an iterative-labeling slot."
    )
    parser.add_argument("--source-slot", required=True, help="Existing source slot.")
    parser.add_argument("--target-slot", required=True, help="New target slot.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the migration plan without creating files.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Validate an existing target slot without copying files.",
    )
    return parser.parse_args()


def _validate_slot(slot: str, argument_name: str) -> str:
    normalized = str(slot or "").strip()
    if not _SLOT_NAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{argument_name} 必须是 1-64 位字母、数字、下划线或连字符，且不能以符号开头"
        )
    return normalized


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", text=True
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (path for path in root.rglob("*") if path.is_file())


def _file_count(root: Path) -> int:
    return sum(1 for _ in _iter_files(root))


def _slot_path_replacements(source_slot: str, target_slot: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            f"data/iterative_labeling/{component}/{source_slot}/",
            f"data/iterative_labeling/{component}/{target_slot}/",
        )
        for component in _SLOT_COMPONENTS
    )


def _rewrite_slot_paths(value: Any, source_slot: str, target_slot: str) -> Any:
    replacements = _slot_path_replacements(source_slot, target_slot)
    if isinstance(value, dict):
        return {
            key: _rewrite_slot_paths(item, source_slot, target_slot)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_slot_paths(item, source_slot, target_slot) for item in value]
    if isinstance(value, str):
        rewritten = value
        for source_fragment, target_fragment in replacements:
            rewritten = rewritten.replace(source_fragment, target_fragment)
        return rewritten
    return value


def _all_strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_strings(item)
    elif isinstance(value, str):
        yield value


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_digests(source_slot: str) -> dict[str, str]:
    """Fingerprint source assets without treating a new target registry slot as a source change."""
    digests: dict[str, str] = {}
    for component in _SLOT_COMPONENTS:
        source_dir = _ITERATIVE_ROOT / component / source_slot
        for file_path in _iter_files(source_dir):
            digests[file_path.relative_to(_ITERATIVE_ROOT).as_posix()] = _digest(file_path)
    registry_path = _ITERATIVE_ROOT / "label_registry.json"
    if registry_path.exists():
        registry = _read_json(registry_path)
        source_registry = registry.get("slots", {}).get(source_slot)
        serialized = json.dumps(
            source_registry,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digests[f"label_registry.json#slots.{source_slot}"] = hashlib.sha256(serialized).hexdigest()
    return digests


def _assert_source_exists(source_slot: str) -> None:
    state_path = _ITERATIVE_ROOT / "cumulative_training" / source_slot / "state.json"
    registry_path = _ITERATIVE_ROOT / "label_registry.json"
    if not state_path.is_file():
        raise FileNotFoundError(f"源累计训练状态不存在: {state_path}")
    if not registry_path.is_file():
        raise FileNotFoundError(f"标签注册表不存在: {registry_path}")
    registry = _read_json(registry_path)
    if source_slot not in registry.get("slots", {}):
        raise ValueError(f"标签注册表不存在源槽位: {source_slot}")


def _assert_target_is_empty(target_slot: str) -> None:
    occupied = [
        str(_ITERATIVE_ROOT / component / target_slot)
        for component in _SLOT_COMPONENTS
        if (_ITERATIVE_ROOT / component / target_slot).exists()
    ]
    registry_path = _ITERATIVE_ROOT / "label_registry.json"
    if registry_path.is_file():
        registry = _read_json(registry_path)
        if target_slot in registry.get("slots", {}):
            occupied.append(f"{registry_path}#slots.{target_slot}")
    if occupied:
        raise FileExistsError(
            "目标槽位已存在，拒绝覆盖；请先人工核对或改用其他槽位: "
            + ", ".join(occupied)
        )


def _copy_component(source_slot: str, target_slot: str, component: str) -> int:
    source_dir = _ITERATIVE_ROOT / component / source_slot
    target_dir = _ITERATIVE_ROOT / component / target_slot
    if not source_dir.exists():
        return 0
    shutil.copytree(source_dir, target_dir)
    for json_path in target_dir.rglob("*.json"):
        payload = _rewrite_slot_paths(_read_json(json_path), source_slot, target_slot)
        if component == "cumulative_training" and json_path.name == "state.json":
            payload["slot"] = target_slot
        _atomic_write_json(json_path, payload)
    return _file_count(target_dir)


def _copy_label_registry(source_slot: str, target_slot: str) -> None:
    registry_path = _ITERATIVE_ROOT / "label_registry.json"
    registry = _read_json(registry_path)
    slots = registry.setdefault("slots", {})
    slots[target_slot] = copy.deepcopy(slots[source_slot])
    _atomic_write_json(registry_path, registry)


def _verify_paths(payload: Any, source_slot: str, target_slot: str, owner: Path) -> list[str]:
    errors: list[str] = []
    source_fragments = [source for source, _ in _slot_path_replacements(source_slot, target_slot)]
    for string_value in _all_strings(payload):
        if any(fragment in string_value for fragment in source_fragments):
            errors.append(f"{owner}: 仍引用源槽位路径: {string_value}")
        if string_value.startswith("backend-service/data/iterative_labeling/"):
            absolute_path = _PROJECT_ROOT / string_value
            if not absolute_path.exists():
                errors.append(f"{owner}: 相对路径不存在: {string_value}")
    return errors


def _verify_target(source_slot: str, target_slot: str) -> dict[str, int]:
    errors: list[str] = []
    counts: dict[str, int] = {}
    for component in _SLOT_COMPONENTS:
        source_dir = _ITERATIVE_ROOT / component / source_slot
        target_dir = _ITERATIVE_ROOT / component / target_slot
        source_count = _file_count(source_dir)
        target_count = _file_count(target_dir)
        counts[component] = target_count
        if source_count != target_count:
            errors.append(
                f"{component}: 源文件数 {source_count} 与目标文件数 {target_count} 不一致"
            )
        for json_path in target_dir.rglob("*.json"):
            errors.extend(_verify_paths(_read_json(json_path), source_slot, target_slot, json_path))

    state_path = _ITERATIVE_ROOT / "cumulative_training" / target_slot / "state.json"
    state = _read_json(state_path)
    if state.get("slot") != target_slot:
        errors.append(f"{state_path}: state.slot 不是 {target_slot}")

    registry = _read_json(_ITERATIVE_ROOT / "label_registry.json")
    if target_slot not in registry.get("slots", {}):
        errors.append(f"label_registry.json: 缺少 slots.{target_slot}")
    elif registry["slots"][target_slot] != registry["slots"].get(source_slot):
        errors.append("label_registry.json: 目标标签空间与源槽位不一致")

    if errors:
        raise RuntimeError("槽位迁移校验失败:\n- " + "\n- ".join(errors))
    return counts


def main() -> None:
    args = _parse_args()
    source_slot = _validate_slot(args.source_slot, "source-slot")
    target_slot = _validate_slot(args.target_slot, "target-slot")
    if source_slot == target_slot:
        raise ValueError("source-slot 与 target-slot 不能相同")
    if args.dry_run and args.verify_only:
        raise ValueError("--dry-run 与 --verify-only 不能同时使用")

    _assert_source_exists(source_slot)
    if args.verify_only:
        counts = _verify_target(source_slot, target_slot)
        print(json.dumps({"verified": True, "target_slot": target_slot, "file_counts": counts}, ensure_ascii=False))
        return

    _assert_target_is_empty(target_slot)
    source_digests = _source_digests(source_slot)
    planned_counts = {
        component: _file_count(_ITERATIVE_ROOT / component / source_slot)
        for component in _SLOT_COMPONENTS
    }
    plan = {
        "source_slot": source_slot,
        "target_slot": target_slot,
        "component_file_counts": planned_counts,
        "label_registry_copy": f"slots.{source_slot} -> slots.{target_slot}",
        "source_preserved": True,
    }
    if args.dry_run:
        print(json.dumps({"dry_run": True, **plan}, ensure_ascii=False, indent=2))
        return

    copied_counts = {
        component: _copy_component(source_slot, target_slot, component)
        for component in _SLOT_COMPONENTS
    }
    _copy_label_registry(source_slot, target_slot)
    verified_counts = _verify_target(source_slot, target_slot)
    if _source_digests(source_slot) != source_digests:
        raise RuntimeError("源槽位文件在迁移期间发生变化，已停止；请人工核对")

    print(
        json.dumps(
            {
                "migrated": True,
                **plan,
                "copied_file_counts": copied_counts,
                "verified_file_counts": verified_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
