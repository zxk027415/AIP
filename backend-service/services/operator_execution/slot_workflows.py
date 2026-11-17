"""Map product slots to published workflow template IDs."""

from __future__ import annotations

SLOT_TRAIN_WORKFLOW: dict[str, str] = {
    "pv_day": "workflow-pv-day-train-eval-v1",
    "pv_point": "workflow-pv-point-train-eval-v1",
    # @AI_GENERATED: pv_tsc uses its own strict MultiRocket product workflow.
    "pv_tsc": "workflow-pv-tsc-train-eval-v1",
    # @AI_GENERATED: end
    "default": "workflow-pv-fault-diag-quickval-cv-v1",
}

SLOT_PREDICT_WORKFLOW: dict[str, str] = {
    "pv_day": "workflow-pv-day-predict-v1",
    "pv_point": "workflow-pv-point-predict-replay-v1",
    # @AI_GENERATED: pv_tsc preserves device-day/window-evidence semantics.
    "pv_tsc": "workflow-pv-tsc-predict-v1",
    # @AI_GENERATED: end
    "default": "workflow-pv-fault-diag-quickval-predict-v1",
}

SLOT_REPLAY_WORKFLOW: dict[str, str] = {
    "pv_point": "workflow-pv-point-predict-replay-v1",
}


def resolve_train_workflow_id(slot: str | None) -> str:
    key = (slot or "default").strip()
    if key.startswith("benchmark_"):
        return SLOT_TRAIN_WORKFLOW["pv_point"]
    return SLOT_TRAIN_WORKFLOW.get(key, SLOT_TRAIN_WORKFLOW["default"])


def resolve_predict_workflow_id(slot: str | None) -> str:
    key = (slot or "default").strip()
    if key.startswith("benchmark_"):
        return SLOT_PREDICT_WORKFLOW["pv_point"]
    return SLOT_PREDICT_WORKFLOW.get(key, SLOT_PREDICT_WORKFLOW["default"])


# @AI_GENERATED
# 回退到 pv_point replay 模板是**有意**的：benchmark_* 槽复用点路径 replay 图，
# `tests/test_g6_reuse_report.py` 对此有断言，`services/benchmark/reuse_report.py`
# 也依赖它为任意 slot 产出 predict_replay 字段。这里把 benchmark_ 分支写显式，
# 与 resolve_train_workflow_id / resolve_predict_workflow_id 保持同构。
# 注意：pv_day / pv_tsc 目前没有自己的 replay 模板，若将来新增必须先登记到
# SLOT_REPLAY_WORKFLOW，否则会静默拿到点路径模板。
def resolve_replay_workflow_id(slot: str | None) -> str:
    key = (slot or "pv_point").strip()
    if key.startswith("benchmark_"):
        return SLOT_REPLAY_WORKFLOW["pv_point"]
    return SLOT_REPLAY_WORKFLOW.get(key, "workflow-pv-point-predict-replay-v1")
# @AI_GENERATED: end
