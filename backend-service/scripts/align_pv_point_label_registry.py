"""Phase A: align pv_point label registry to pv_fault (13-class business names)."""

from __future__ import annotations

from services.iterative_labeling.label_registry import LabelRegistryService


def main() -> None:
    service = LabelRegistryService(slot="pv_point")
    before = service.get_current()
    before_ids = sorted(int(item["label_id"]) for item in before.get("labels", []))
    result = service.align_from_reference_slot(
        "pv_fault",
        migration_source="pv_point_align_pv_fault_v1",
    )
    after_ids = sorted(int(item["label_id"]) for item in result.get("labels", []))
    print(
        f"pv_point registry aligned: {before.get('label_space_version')} -> "
        f"{result.get('label_space_version')} ids {before_ids} -> {after_ids}"
    )
    for item in result.get("labels", []):
        print(f"  {item['label_id']}: {item['label_name']}")


if __name__ == "__main__":
    main()
