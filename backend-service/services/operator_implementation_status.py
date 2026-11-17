"""Dynamic implementation_status annotation for function catalog (G13.1)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Iterable, List

from models.function import FunctionDefinition
from services.operator_catalog_aliases import catalog_has_backend, resolve_backend_operator_id


@lru_cache(maxsize=1)
def _registered_operator_ids() -> frozenset[str]:
    from services.operator_execution.router import OperatorRouter

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backends_dir = os.path.join(backend_dir, "services", "operator_backends")
    router = OperatorRouter()
    router.auto_discover(backends_dir)
    return frozenset(router.list_operators())


@lru_cache(maxsize=1)
def _verified_operator_ids() -> frozenset[str]:
    from services.operator_verification import filter_verified_registered

    return frozenset(filter_verified_registered(list(_registered_operator_ids())))


def implementation_status_for(catalog_id: str) -> str:
    registered = set(_registered_operator_ids())
    return "available" if catalog_has_backend(catalog_id, registered) else "planned"


def implementation_verified_for(catalog_id: str) -> bool:
    if implementation_status_for(catalog_id) != "available":
        return False
    verified = set(_verified_operator_ids())
    backend_id = resolve_backend_operator_id(catalog_id)
    return catalog_id in verified or backend_id in verified


def enrich_function(function: FunctionDefinition) -> FunctionDefinition:
    status = implementation_status_for(function.id)
    verified = implementation_verified_for(function.id) if status == "available" else False
    return function.model_copy(
        update={
            "implementation_status": status,
            "implementation_verified": verified,
        }
    )


def enrich_functions(functions: Iterable[FunctionDefinition]) -> List[FunctionDefinition]:
    return [enrich_function(item) for item in functions]
