"""HTTP API for G6 benchmark reuse evidence reports."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from services.benchmark.reuse_report import DEFAULT_BENCHMARK_SLOTS, build_g6_reuse_report
from services.benchmark.g8_reuse_story import build_g8_reuse_story

router = APIRouter(prefix="/api/benchmark", tags=["benchmark-reuse"])


@router.get("/reuse-report", summary="Build G6.5 graph reuse evidence report")
async def get_reuse_report(
    slots: Optional[str] = Query(
        default=None,
        description="Comma-separated benchmark slots; defaults to NASA + FHC",
    ),
    persist: bool = Query(default=False, description="Write report JSON under data/benchmark/reuse_reports/"),
) -> dict[str, Any]:
    slot_list = [s.strip() for s in slots.split(",") if s.strip()] if slots else list(DEFAULT_BENCHMARK_SLOTS)
    try:
        report = build_g6_reuse_report(slots=slot_list, persist=persist)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "report": report}


@router.get("/reuse-story", summary="Build G8 cross-path reuse story (incl. PVDAQ unlabeled)")
async def get_reuse_story(
    persist: bool = Query(default=False, description="Write story JSON under data/benchmark/reuse_stories/"),
) -> dict[str, Any]:
    try:
        story = build_g8_reuse_story(persist=persist)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "story": story}
