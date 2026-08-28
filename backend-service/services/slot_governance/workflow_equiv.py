"""Extract comparable workflow graph signatures for equivalence tests."""

from __future__ import annotations

from typing import Any


def _node_config_dict(config: Any) -> dict[str, Any]:
    if config is None:
        return {}
    if hasattr(config, "model_dump"):
        return dict(config.model_dump())
    if hasattr(config, "dict"):
        return dict(config.dict())
    if isinstance(config, dict):
        return dict(config)
    return {}


def workflow_graph_signature(workflow) -> dict[str, Any]:
    """
    Build a deterministic signature of operator graph topology + configs.

    Ignores workflow id/name/metadata slot fields — only compares executable graph.
    """
    nodes: list[dict[str, Any]] = []
    for node in sorted(workflow.nodes, key=lambda item: item.id):
        cfg = _node_config_dict(getattr(node.data, "config", None))
        nodes.append(
            {
                "functionId": cfg.get("functionId"),
                "config": {k: v for k, v in sorted(cfg.items()) if k != "functionId"},
            }
        )

    edges = sorted(
        {
            (
                edge.source,
                edge.target,
                getattr(edge, "sourceHandle", None),
                getattr(edge, "targetHandle", None),
            )
            for edge in workflow.edges
        }
    )
    return {"nodes": nodes, "edges": edges}


def metadata_product_fields(metadata: dict[str, Any] | None) -> dict[str, Any]:
    meta = metadata if isinstance(metadata, dict) else {}
    return {
        "slot": meta.get("slot"),
        "template_role": meta.get("template_role"),
        "slot_config_ref": meta.get("slot_config_ref"),
        "template_type": meta.get("template_type"),
    }
