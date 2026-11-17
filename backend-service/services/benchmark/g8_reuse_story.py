"""G8 cross-path reuse story: product pv_day/pv_point + labeled/unlabeled benchmarks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.benchmark.reuse_report import (
    DEFAULT_BENCHMARK_SLOTS,
    build_g6_reuse_report,
    extract_profile_evidence,
)

G8_BENCHMARK_SLOTS = (
    *DEFAULT_BENCHMARK_SLOTS,
    "benchmark_pvdaq_system683",
)

G8_SLOT_PROFILES = {
    "benchmark_nasa_smap_msl": "benchmark-nasa-smap-msl-demo",
    "benchmark_fhc_twin_plant": "benchmark-fhc-twin-plant-demo",
    "benchmark_pvdaq_system683": "benchmark-pvdaq-system683-demo",
}

PRODUCT_SLOTS = ("pv_day", "pv_point")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_g8_reuse_story(
    *,
    benchmark_slots: Optional[list[str]] = None,
    persist: bool = False,
) -> dict[str, Any]:
    slot_list = list(benchmark_slots or G8_BENCHMARK_SLOTS)
    g6_report = build_g6_reuse_report(
        slots=slot_list,
        slot_profiles=G8_SLOT_PROFILES,
        persist=False,
    )

    profiles = {slot: extract_profile_evidence(G8_SLOT_PROFILES[slot]) for slot in slot_list}

    pvdaq = profiles.get("benchmark_pvdaq_system683") or {}
    fields = pvdaq.get("profile_fields") or {}
    unlabeled_ok = (
        pvdaq.get("label_semantics") == "unlabeled"
        and fields.get("label_column") is None
    )

    story = {
        "story_id": f"g8-story-{uuid.uuid4().hex[:12]}",
        "generated_at": _now_iso(),
        "product_slots": list(PRODUCT_SLOTS),
        "benchmark_slots": slot_list,
        "g6_graph_evidence": g6_report["workflow_comparison"],
        "profiles": profiles,
        "governance_evidence": g6_report["governance_evidence"],
        "reuse_conclusion": {
            **g6_report["reuse_conclusion"],
            "pvdaq_unlabeled_no_fake_metrics": unlabeled_ok,
            "labeled_benchmarks": [
                s for s in slot_list if profiles.get(s, {}).get("label_semantics") == "benchmark_ground_truth"
            ],
            "unlabeled_benchmarks": [
                s for s in slot_list if profiles.get(s, {}).get("label_semantics") == "unlabeled"
            ],
            "day_point_product_paths": PRODUCT_SLOTS,
        },
    }

    if persist:
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parents[2]
        out_dir = backend_dir / "data" / "benchmark" / "reuse_stories"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{story['story_id']}.json"
        import json

        path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
        story["persisted_path"] = str(path.relative_to(backend_dir)).replace("\\", "/")

    return story
