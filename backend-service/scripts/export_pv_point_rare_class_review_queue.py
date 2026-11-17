"""Phase B: export rare label 9/10/16 manual gold review queue for pv_point."""

from __future__ import annotations

from services.slot_datasets.rare_class_review_queue import (
    build_rare_class_review_queue,
    save_rare_class_review_queue,
    sync_review_queue_to_annotation_candidates,
)


def main() -> None:
    payload = build_rare_class_review_queue()
    rel = save_rare_class_review_queue(payload)
    sync = sync_review_queue_to_annotation_candidates(payload)
    print(f"queue saved: {rel}")
    print(f"summary: {payload.get('summary')}")
    print(f"annotation candidates sync: {sync}")
    for item in payload.get("items") or []:
        print(
            f"  label {item['label_id']} {item['date']} {item['entity_key']} "
            f"role={item['annotation_role_recommended']} points={item['point_count']}"
        )


if __name__ == "__main__":
    main()
