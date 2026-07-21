from copy import deepcopy

import pytest

from services.iterative_labeling.label_registry import LabelRegistryService


class InMemoryRegistryRepository:
    def __init__(self):
        self.current = {
            "label_space_version": "ls-v1",
            "labels": [
                {"label_id": 0, "label_name": "正常", "created_at": "2026-07-20T00:00:00"},
                {"label_id": 1, "label_name": "组串遮挡", "created_at": "2026-07-20T00:00:00"},
            ],
            "label_map": {"正常": 0, "组串遮挡": 1},
            "history": [],
        }
        self.save_count = 0

    def load_current(self, slot):
        return deepcopy(self.current)

    def save_new_version(self, slot, registry):
        self.current = deepcopy(registry)
        self.save_count += 1


def test_reconcile_labels_preserves_snapshot_ids_and_versions_registry():
    repository = InMemoryRegistryRepository()
    service = LabelRegistryService(slot="pv_fault", registry_repo=repository)

    result = service.reconcile_labels({2: "待确认故障A", 10: "待确认故障B"})

    assert result["label_space_version"] == "ls-v2"
    assert result["label_map"]["待确认故障A"] == 2
    assert result["label_map"]["待确认故障B"] == 10
    assert [item["label_id"] for item in result["labels"]] == [0, 1, 2, 10]
    assert result["history"][0]["label_ids"] == [0, 1]


def test_reconcile_allows_renaming_placeholder_names():
    repository = InMemoryRegistryRepository()
    service = LabelRegistryService(slot="pv_fault", registry_repo=repository)
    service.reconcile_labels({2: "待命名-故障码2"})
    renamed = service.reconcile_labels({2: "组串隐裂"})
    assert renamed["label_map"]["组串隐裂"] == 2
    assert "待命名-故障码2" not in renamed["label_map"]
    assert renamed["label_space_version"] == "ls-v3"


def test_reconcile_labels_is_idempotent_and_rejects_conflicts():
    repository = InMemoryRegistryRepository()
    service = LabelRegistryService(slot="pv_fault", registry_repo=repository)
    service.reconcile_labels({2: "待确认故障A"})
    first_save_count = repository.save_count

    same = service.reconcile_labels({2: "待确认故障A"})
    assert same["label_space_version"] == "ls-v2"
    assert repository.save_count == first_save_count

    with pytest.raises(ValueError, match="已登记"):
        service.reconcile_labels({2: "另一个名称"})
    with pytest.raises(ValueError, match="已绑定"):
        service.reconcile_labels({3: "待确认故障A"})
