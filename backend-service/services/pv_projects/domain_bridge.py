# @AI_GENERATED
"""领域桥：把 pv_projects 的治理产出同步到**领域侧**的模型登记。

为什么需要一层桥，而不是在壳里直接 import 领域存储：

- `pv_projects` 是**领域无关的项目壳**（同一套「项目 × 路径 × 门禁 × 候选」要复用到其它领域，
  见 `services/pv_projects/` 与前端 `pv-fault/adapters/solutionCapabilityAdapter`）；
- `PVModelRegistry`（`data/pv_dual_path/model_registry/<slot>.json`）与
  iterative_labeling 的 slot 存储是**本领域（pv_fault）**的落地形态。

壳若直接依赖某个领域的存储，复用时就会被绑死。所以这里只定义**协议 + 可注入实现**：
领域侧在启动时注册自己的桥；未注册时是 no-op，壳仍可独立工作与测试。

同步失败**不阻断**候选登记（登记是主链路，同步是派发）：异常被记录并吞掉，
但结果会在候选上以 `domain_sync` 字段如实回显（成功 / 未注册 / 失败），不静默。
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable

_logger = logging.getLogger(__name__)


@runtime_checkable
class CandidateGovernanceBridge(Protocol):
    """候选 / 复验 → 领域模型登记的同步协议。"""

    def sync_candidate(
        self, *, project_id: str, slot: str, candidate: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """把一条候选同步到领域存储（**只登记为候选，不授予挑战者身份**）。"""
        ...

    def sync_verification_passed(
        self,
        *,
        project_id: str,
        slot: str,
        candidate: dict[str, Any],
        verification: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """**考察通过**时把该候选升级为对应槽位的挑战者（challenger）。

        这是「一套逻辑」的关键一环：模型在项目里被考察（复验）通过后，才升级成 challenger，
        再与在岗的 champion 竞争 —— 而不是一登记就上位。
        """
        ...


_bridge: Optional[CandidateGovernanceBridge] = None


def set_domain_bridge(bridge: Optional[CandidateGovernanceBridge]) -> None:
    """注册 / 清除领域桥（传 None 复位；主要供测试与启动装配使用）。"""
    global _bridge
    _bridge = bridge


def get_domain_bridge() -> Optional[CandidateGovernanceBridge]:
    return _bridge


def sync_candidate_to_domain(
    *, project_id: str, slot: str, candidate: dict[str, Any]
) -> dict[str, Any]:
    """壳内唯一的同步调用点；**永不抛错**，结果如实回显。

    返回形状：
    - `{"synced": False, "reason": "no_bridge"}` —— 未注册桥（壳独立运行，正常）
    - `{"synced": False, "reason": "not_handled"}` —— 桥不处理该路径
    - `{"synced": True, ...}` —— 同步成功，附桥返回的摘要
    - `{"synced": False, "reason": "error", "error": "..."}` —— 同步抛错（已记日志）
    """
    bridge = _bridge
    if bridge is None:
        return {"synced": False, "reason": "no_bridge"}
    try:
        result = bridge.sync_candidate(project_id=project_id, slot=slot, candidate=candidate)
    except Exception as exc:  # noqa: BLE001 — 派发失败不阻断登记，但必须可见
        _logger.exception("领域桥同步候选失败 project=%s slot=%s", project_id, slot)
        return {"synced": False, "reason": "error", "error": f"{type(exc).__name__}: {exc}"}
    if result is None:
        return {"synced": False, "reason": "not_handled"}
    if result.get("skipped"):
        # 桥**明确跳过**了这次同步（如缺稳定幂等键）：这不是"已同步"。
        # 早先把 skipped 也打成 synced=True，任何按 synced 判断的消费端都会得到假阳性。
        return {"synced": False, "reason": "skipped", "skipped": result["skipped"]}
    return {"synced": True, **result}


def sync_verification_passed_to_domain(
    *, project_id: str, slot: str, candidate: dict[str, Any], verification: dict[str, Any]
) -> dict[str, Any]:
    """**考察通过 → 升级 challenger** 的派发点；永不抛错，结果如实回显（形状同 sync_candidate_to_domain）。

    与 `sync_candidate_to_domain` 分开是刻意的：候选登记只让模型进池，
    **只有复验通过**才授予挑战者身份 —— 这正是「一套逻辑」要保住的那道门。
    """
    bridge = _bridge
    if bridge is None:
        return {"synced": False, "reason": "no_bridge"}
    handler = getattr(bridge, "sync_verification_passed", None)
    if handler is None:
        return {"synced": False, "reason": "unsupported"}
    try:
        result = handler(
            project_id=project_id, slot=slot, candidate=candidate, verification=verification
        )
    except Exception as exc:  # noqa: BLE001 — 派发失败不阻断复验落库，但必须可见
        _logger.exception("领域桥同步复验失败 project=%s slot=%s", project_id, slot)
        return {"synced": False, "reason": "error", "error": f"{type(exc).__name__}: {exc}"}
    if result is None:
        return {"synced": False, "reason": "not_handled"}
    if result.get("skipped"):
        return {"synced": False, "reason": "skipped", "skipped": result["skipped"]}
    return {"synced": True, **result}


# @AI_GENERATED: end
