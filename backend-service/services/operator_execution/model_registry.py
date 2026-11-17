"""
Shared in-memory model registry for operator backends.

This keeps model artifact handling decoupled from a single industry workflow and
allows train/predict/backtest chains to exchange model references consistently.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_model(
    model_ref: str,
    model: Any,
    feature_list: Optional[list] = None,
    metadata: Optional[dict] = None,
) -> str:
    _REGISTRY[model_ref] = {
        "model": model,
        "feature_list": list(feature_list or []),
        "metadata": dict(metadata or {}),
    }
    return model_ref


def get_model(model_ref: str) -> Optional[Dict[str, Any]]:
    return _REGISTRY.get(model_ref)


def has_model(model_ref: str) -> bool:
    return model_ref in _REGISTRY


def list_model_refs() -> list:
    return sorted(_REGISTRY.keys())

