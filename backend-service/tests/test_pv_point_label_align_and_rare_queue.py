from copy import deepcopy

import pytest

from services.iterative_labeling.label_registry import LabelRegistryService


class MultiSlotRegistryRepository:
    def __init__(self) -> None:
        self.slots: dict[str, dict] = {
            "pv_fault": {
                "label_space_version": "ls-v2",
                "labels": [
                    {"label_id": 0, "label_name": "正常", "created_at": "2026-01-01"},
                    {"label_id": 1, "label_name": "组串遮挡", "created_at": "2026-01-01"},
                    {"label_id": 16, "label_name": "其他故障", "created_at": "2026-01-01"},
                ],
                "label_map": {"正常": 0, "组串遮挡": 1, "其他故障": 16},
                "history": [],
            },
            "pv_point": {
                "label_space_version": "ls-v10",
                "labels": [
                    {"label_id": 0, "label_name": "g10_e2e_c0", "created_at": "2026-08-25"},
                    {"label_id": 1, "label_name": "g10_e2e_c1", "created_at": "2026-08-25"},
                ],
                "label_map": {"g10_e2e_c0": 0, "g10_e2e_c1": 1},
                "history": [],
            },
        }

    def load_current(self, slot: str):
        return deepcopy(self.slots[slot])

    def save_new_version(self, slot: str, registry: dict) -> None:
        self.slots[slot] = deepcopy(registry)


def test_align_from_reference_slot_replaces_poc_names_and_keeps_history():
    repo = MultiSlotRegistryRepository()
    service = LabelRegistryService(slot="pv_point", registry_repo=repo)
    result = service.align_from_reference_slot("pv_fault", migration_source="test_align")
    assert result["label_space_version"] == "ls-v11"
    names = {int(item["label_id"]): item["label_name"] for item in result["labels"]}
    assert names[0] == "正常"
    assert names[16] == "其他故障"
    assert result["history"][-1]["label_ids"] == [0, 1]
    assert result["alignment_meta"]["reference_slot"] == "pv_fault"


def test_rare_class_review_queue_finds_nine_ten_sixteen():
    from services.slot_datasets.rare_class_review_queue import build_rare_class_review_queue

    payload = build_rare_class_review_queue()
    assert payload["summary"]["total_items"] == 11
    label_ids = sorted({int(item["label_id"]) for item in payload["items"]})
    assert label_ids == [9, 10, 16]
    holdout = [item for item in payload["items"] if item["annotation_role_recommended"] == "locked_holdout"]
    assert len(holdout) == 3
