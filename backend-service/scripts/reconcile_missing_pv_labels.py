"""补登记训练快照中缺失的故障码到 pv_fault / default 标签注册表（占位名，可后续改名）。"""

from __future__ import annotations

from services.iterative_labeling.label_registry import LabelRegistryService

# 快照/parquet 共 13 类；注册表原先缺 2/3/6/9/10
MISSING = {
    2: "待命名-故障码2",
    3: "待命名-故障码3",
    6: "待命名-故障码6",
    9: "待命名-故障码9",
    10: "待命名-故障码10",
}


def main() -> None:
    for slot in ("pv_fault", "default"):
        service = LabelRegistryService(slot=slot)
        before = service.get_current()
        result = service.reconcile_labels(MISSING)
        after_ids = sorted(int(x["label_id"]) for x in result["labels"])
        print(
            f"slot={slot} {before.get('label_space_version')} -> {result['label_space_version']} "
            f"n={len(after_ids)} ids={after_ids}"
        )


if __name__ == "__main__":
    main()
