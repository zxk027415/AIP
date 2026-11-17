"""Copy pv_fault label registry onto pv_day. Source slot is kept intact."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.iterative_labeling.storage.file_backend import FileLabelRegistryRepository


def main() -> None:
    repo = FileLabelRegistryRepository()
    registry_path = repo.registry_path
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    slots = payload.setdefault("slots", {})
    source = slots.get("pv_fault")
    if not isinstance(source, dict) or not source.get("labels"):
        raise SystemExit("pv_fault 标签注册表为空，无法切到 pv_day")
    slots["pv_day"] = copy.deepcopy(source)
    repo.save_new_version("pv_day", slots["pv_day"])
    copied = repo.load_current("pv_day")
    print(
        json.dumps(
            {
                "slot": "pv_day",
                "label_space_version": copied.get("label_space_version"),
                "n_labels": len(copied.get("labels") or []),
                "label_ids": [item.get("label_id") for item in (copied.get("labels") or [])],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
