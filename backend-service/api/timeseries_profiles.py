"""Timeseries profile registry and preflight HTTP API."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.timeseries_profiles.models import UsePurpose
from services.timeseries_profiles.preflight import run_dataset_profile_preflight
from services.timeseries_profiles.store import TimeseriesProfileStore

router = APIRouter(prefix="/api/timeseries/profiles", tags=["timeseries-profiles"])
_store = TimeseriesProfileStore()
_store.ensure_seed_layout()


class PreflightRequest(BaseModel):
    use_purpose: UsePurpose = Field(default="local_validation")


@router.get("/dataset", summary="List dataset profiles")
async def list_dataset_profiles():
    return {"success": True, "items": _store.list_dataset_profiles()}


@router.get("/dataset/{profile_id}", summary="Get dataset profile")
async def get_dataset_profile(profile_id: str, version: Optional[str] = Query(default=None)):
    try:
        profile = _store.get_dataset_profile(profile_id, version=version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "profile": profile.model_dump()}


@router.get("/domain", summary="List domain profiles")
async def list_domain_profiles():
    return {"success": True, "items": _store.list_domain_profiles()}


@router.get("/domain/{profile_id}", summary="Get domain profile")
async def get_domain_profile(profile_id: str, version: Optional[str] = Query(default=None)):
    try:
        profile = _store.get_domain_profile(profile_id, version=version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "profile": profile.model_dump()}


@router.get("/manifests/{manifest_id}", summary="Get acquisition manifest")
async def get_acquisition_manifest(manifest_id: str):
    try:
        manifest = _store.get_manifest(manifest_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "manifest": manifest.model_dump()}


@router.post("/dataset/{profile_id}/preflight", summary="Run dataset profile preflight")
async def preflight_dataset_profile(
    profile_id: str,
    body: PreflightRequest,
    version: Optional[str] = Query(default=None),
):
    try:
        profile = _store.get_dataset_profile(profile_id, version=version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report = run_dataset_profile_preflight(profile, use_purpose=body.use_purpose)
    return {"success": True, "report": report.model_dump()}
