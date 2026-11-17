# @AI_GENERATED
"""pv_fault 领域桥：把 pv_projects 的候选**接进对应诊断路径 slot 的模型治理存储**。

**目标（用户意图）**：模型部署 / 精度运营 / 工作流模板 / 项目 四个模块互通、互相显示。
本桥负责把「项目工作台产出的候选」送到「模型部署」页真正读的那套存储。

**槽位不能接错**：前端 `slotProductConfig.ts` 把三路径定义为独立产品 slot
（pv_day / pv_point / pv_tsc）；「模型部署 / 精度运营」页在它们下面读
`data/slot_governance/{slot}/{registry.json, model_candidates.json}`。

三步（缺一不可，否则页面看不到）：
1. **镜像执行**：`slot_governance` 的 provenance 校验查的是统一执行历史
   （`services/execution_history/store.py`），而项目侧执行只在 `data/pv_projects/...`。
   先把执行补进统一历史，校验才可能过。
2. **进候选池**：`register_model_candidate` → `model_candidates.json`。
   页面「已登记模型（N）— 生产 / 候选」读的就是这个池（`SlotDeployedModelPanel` 调
   `listModelCandidates`），**不是** registry.challenger。
3. **设挑战者**：`set_candidate_model`（现在带 candidate_id）→ `registry.json` 的 challenger。

红线：只写 challenger / 候选池，绝不触碰 champion / production_path / 滚动指针。
"""

from __future__ import annotations

from typing import Any, Optional

from services.pv_projects.domain_bridge import set_domain_bridge
from services.pv_projects.scope import PRODUCT_SLOTS


class PvFaultCandidateBridge:
    """把项目侧候选接进对应 slot 的候选池与模型登记。"""

    # ------------------------------------------------------------------
    # 步骤 1：把项目侧执行补进统一执行历史（幂等）
    # ------------------------------------------------------------------

    def _mirror_execution(self, *, project_id: str, slot: str, execution_id: str) -> Optional[str]:
        """返回该执行的 workflow_id（成功镜像或已存在）；无法镜像时返回 None。"""
        if not execution_id:
            return None
        from services.execution_history.store import (  # noqa: PLC0415
            load_execution_record,
            persist_execution_record,
        )
        from services.pv_projects.scope import ScopeContext  # noqa: PLC0415
        from services.pv_projects.stores import executions as project_executions  # noqa: PLC0415

        scope = ScopeContext.create(project_id, slot, require_slot=True, allow_legacy=False)
        rec = project_executions.find(scope, execution_id)
        if not rec:
            return None
        workflow_id = str(rec.get("project_workflow_id") or "").strip()
        if not workflow_id:
            return None
        if load_execution_record(workflow_id, execution_id) is not None:
            return workflow_id  # 已在统一历史里，幂等返回

        # 统一执行历史用 `workflow_id` / `nodeResults` 命名（与项目侧不同），这里做形状适配。
        persist_execution_record(
            {
                "workflow_id": workflow_id,
                "execution_id": execution_id,
                "status": rec.get("status"),
                "slot": rec.get("slot"),
                "governance_eligible": rec.get("governance_eligible"),
                "started_at": rec.get("started_at"),
                "finished_at": rec.get("finished_at"),
                "nodeResults": rec.get("node_results") or {},
            }
        )
        return workflow_id

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def sync_candidate(
        self, *, project_id: str, slot: str, candidate: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        slot_name = str(slot or "").strip()
        if slot_name not in PRODUCT_SLOTS:
            # 不属三路径产品槽位（load_forecast / benchmark_*）：交给别的桥，或无人处理。
            return None

        candidate_id = str(candidate.get("model_candidate_id") or "")
        artifact_ref = str(candidate.get("model_artifact_ref") or "")
        execution_id = str(candidate.get("source_execution_id") or "")
        if not candidate_id or not artifact_ref:
            return {"skipped": "missing_candidate_id_or_model_ref"}

        workflow_id = self._mirror_execution(
            project_id=project_id, slot=slot_name, execution_id=execution_id
        )

        from services.slot_governance.model_candidates import register_model_candidate  # noqa: PLC0415

        # 保真搬运：此前只传 5 个字段，快照 / 评测契约 / 工作流版本在池里全丢了，
        # 导致「模型部署」页上项目来源的候选没有指标也说不出出身。这些形参本来就存在。
        contract = candidate.get("evaluation_contract")
        try:
            mc = register_model_candidate(
                slot=slot_name,
                source_workflow_id=workflow_id or "",
                source_execution_id=execution_id,
                model_artifact_ref=artifact_ref,
                model_ref=candidate_id,
                source_kind="project_workflow",
                source_workflow_version=candidate.get("source_workflow_version"),
                source_snapshot_id=candidate.get("source_snapshot_id"),
                evaluation_contract=dict(contract) if isinstance(contract, dict) and contract else None,
                project_id=project_id,
                source_project_candidate_id=candidate_id,
            )
        except Exception as exc:  # noqa: BLE001 — 进池失败要如实回显，不阻断项目侧登记
            # 带上 code（ProvenanceError 等自带 .code），否则只剩 message，事后不好按原因归类。
            code = getattr(exc, "code", None)
            return {
                "bridge": "pv_fault",
                "pool_registered": False,
                "pool_error": f"{code or type(exc).__name__}: {exc}",
            }

        # **只进池，不授予挑战者身份**。挑战者身份由「考察（复验）通过」触发
        # （`sync_verification_passed`）—— 这是「一套逻辑」必须保住的那道门：
        # 候选 ≠ 挑战者，只有考察通过的才去和生产竞争。
        return {
            "bridge": "pv_fault",
            "registry_slot": slot_name,
            "pool_registered": True,
            "pool_candidate_id": mc.get("model_candidate_id"),
        }

    # ------------------------------------------------------------------
    # 考察通过 → 升级为挑战者（与生产竞争）
    # ------------------------------------------------------------------

    def sync_verification_passed(
        self,
        *,
        project_id: str,
        slot: str,
        candidate: dict[str, Any],
        verification: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        slot_name = str(slot or "").strip()
        if slot_name not in PRODUCT_SLOTS:
            return None

        artifact_ref = str(candidate.get("model_artifact_ref") or "")
        # 池内 candidate_id 来自候选登记时桥写回的 domain_sync（那才是在 slot_governance 池里的 ID）。
        pool_candidate_id = str(
            (candidate.get("domain_sync") or {}).get("pool_candidate_id")
            or candidate.get("pool_candidate_id")
            or ""
        )
        if not artifact_ref:
            return {"skipped": "missing_model_artifact_ref"}
        if not pool_candidate_id:
            # 复验通过但还没进槽位候选池（例如桥在候选登记时未装配）→ 不臆造 ID。
            return {"skipped": "candidate_not_in_slot_pool"}

        from services.slot_governance.registry import set_candidate_model  # noqa: PLC0415

        view = set_candidate_model(
            slot_name,
            model_candidate_id=pool_candidate_id,
            model_artifact_ref=artifact_ref,
            operator="pv_projects",
            reason=(
                f"项目 {project_id} 的候选经正式复验（{verification.get('verification_id')}）通过，"
                "升级为挑战者，与生产（champion）竞争；不直接改写生产身份。"
            ),
        )
        return {
            "bridge": "pv_fault",
            "registry_slot": slot_name,
            "registry_version": view.get("registry_version"),
            "challenger_candidate_id": (view.get("challenger") or {}).get(
                "challenger_model_candidate_id"
            ),
        }


def install() -> PvFaultCandidateBridge:
    """装配 pv_fault 桥（幂等）。由应用启动或测试显式调用。"""
    bridge = PvFaultCandidateBridge()
    set_domain_bridge(bridge)
    return bridge


# @AI_GENERATED: end
