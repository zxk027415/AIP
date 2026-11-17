"""Tests for G13.1 operator implementation_status annotation."""

from __future__ import annotations

from services.operator_catalog_aliases import catalog_has_backend, resolve_backend_operator_id
from services.operator_implementation_status import (
    enrich_function,
    implementation_status_for,
)
from models.function import DataType, FunctionDefinition


def _sample_function(function_id: str) -> FunctionDefinition:
    return FunctionDefinition(
        id=function_id,
        name=function_id,
        category="test",
        description="test",
        parameters=[],
        return_type=DataType.ANY,
    )


def test_resolve_backend_alias_for_kmeans_cluster():
    assert resolve_backend_operator_id("kmeans_cluster") == "kmeans"


def test_catalog_has_backend_via_alias():
    registered = {"kmeans", "load_csv"}
    assert catalog_has_backend("kmeans_cluster", registered) is True
    assert catalog_has_backend("load_mqtt", registered) is False


def test_implementation_status_for_known_backend():
    assert implementation_status_for("load_csv") == "available"


def test_implementation_status_for_planned_catalog_entry():
    assert implementation_status_for("load_mqtt") == "planned"


def test_enrich_function_sets_fields():
    enriched = enrich_function(_sample_function("load_csv"))
    assert enriched.implementation_status == "available"
    assert enriched.implementation_verified in (True, False)

    planned = enrich_function(_sample_function("load_mqtt"))
    assert planned.implementation_status == "planned"
    assert planned.implementation_verified is False
