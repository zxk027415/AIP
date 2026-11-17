# @AI_GENERATED
"""ScopedWorkflowRunner：把 scope、数据版本、运行模式 / 域和评测合同写入持久化 execution 的执行服务。

设计依据：`design.md` D-RUN-01 / D-STATE-01；`requirements.md` R2.2–R2.13、R7.1–R7.3、R7.11–R7.12、NFR4.1–NFR4.5。

职责（scoped 持久化层，不替代既有 pipeline 执行引擎）：
- 每次 run 落库：project / slot / data version / workflow / run_mode / run_domain / node 状态 / 治理资格。
- 节点时间线（node timeline），而非单一"运行中"标签；覆盖 pending/running/success/failed/cancelled、
  刷新恢复、长静默、后端记录缺失。
- 成功时给出结果去向：仅实验工件 / 验证执行 / 可治理候选 / 打标提案 / 预测批次 + 待审核会话。
- 区分"用原输入重试"（新尝试）与"改后重跑"（新 execution）；**绝不覆盖历史失败证据**。

治理资格红线：`experiment` 与 `validation` 执行**恒为非可治理**（governance_eligible=False）；
仅 `training` 运行域非 sandbox 时可作为候选来源。Sandbox 域一律非可治理。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from services.pv_projects import stores
from services.pv_projects.errors import ScopeError
from services.pv_projects.scope import ScopeContext
from services.pv_projects.workflows import (
    DEFAULT_WORKFLOW_KIND,
    assert_run_mode_allowed,
    run_preflight,
)

RUN_MODES = ("experiment", "validation", "training", "prediction", "replay")
RUN_DOMAINS = ("project", "sandbox")

# 结果去向枚举（成功时展示）
RESULT_DESTINATIONS = (
    "experiment_artifact_only",
    "validation_execution",
    "governable_candidate",
    "labeling_proposal",
    "prediction_batch_and_pending_review",
)

TERMINAL_STATES = ("success", "failed", "cancelled")
NODE_STATES = ("pending", "running", "success", "failed", "cancelled")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _checks_digest(checks: list[dict[str, Any]]) -> str:
    """对预检逐项结果求稳定摘要，供执行记录固化。

    只摘 key / status / governance_impact 三个稳定字段，使执行记录可回溯
    "当时依据的是哪一份预检结论"，而不必保存整份 checks。
    """
    import hashlib
    import json as _json

    canonical = _json.dumps(
        [{k: c.get(k) for k in ("key", "status", "governance_impact")} for c in checks],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_governance_eligible(workflow_kind: str, run_mode: str, run_domain: str) -> bool:
    """治理资格：仅 **training 用途** 的工作流 + `run_mode=training` + 非 sandbox 可治理。

    `workflow_kind` 必须来自**持久化工作流**，不接受请求体声明；否则客户端可用
    labeling 工作流以 `run_mode=training` 执行，凭空取得治理资格（P0-1 第 5 条）。
    """
    if run_domain == "sandbox":
        return False
    if str(workflow_kind or "") != "training":
        return False
    return run_mode == "training"


class ScopedWorkflowRunner:
    """按 scope 持久化 execution 的运行服务。"""

    def start_execution(
        self,
        scope: ScopeContext,
        *,
        project_workflow_id: str,
        run_mode: str,
        run_domain: str = "project",
        dataset_version_id: Optional[str] = None,
        node_ids: Optional[list[str]] = None,
        evaluation_contract: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        origin_execution_id: Optional[str] = None,
        origin_kind: Optional[str] = None,
    ) -> dict[str, Any]:
        """登记一次 run（初始 running），写入 scope / 版本 / 模式 / 域 / 治理资格 + 节点时间线。

        三道门禁（P0-1）：
        1. `project_workflow_id` 必须**在当前 scope 真实存在**（修复前只是原样落库的字符串，
           跨 scope / 不存在的 ID 也能执行）。
        2. `run_mode` 必须与**持久化工作流**的用途合同一致（`assert_run_mode_allowed`）。
        3. 执行前必须 `run_preflight`；`overall == blocked` 时拒绝创建执行。

        执行记录同时**固化血缘**（workflow_kind / version / 绑定数据版本 / 绑定快照 / 预检摘要），
        使下游（候选登记、stage 投影、UI）只需读执行记录，不必相信调用方传入。

        `idempotency_key` 命中已存在记录时直接返回（防重复提交）。
        `origin_execution_id` + `origin_kind`（retry / modify_rerun）记录来历，不覆盖原记录。
        """
        scope.assert_writable()
        rm = str(run_mode or "").strip()
        rd = str(run_domain or "project").strip()
        if rm not in RUN_MODES:
            raise ValueError(f"未知 run_mode：{run_mode!r}")
        if rd not in RUN_DOMAINS:
            raise ValueError(f"未知 run_domain：{run_domain!r}")

        # 门禁 1：项目工作流必须在当前 scope 真实存在（store 天然按 scope 隔离）。
        pwf = stores.project_workflows.find(scope, project_workflow_id)
        if pwf is None:
            raise ScopeError(
                "unknown_project_workflow",
                f"当前项目 / 路径下找不到项目工作流 {project_workflow_id!r}，拒绝创建执行。",
                next_action="在工作流阶段创建或选择一个属于当前项目 / 路径的项目工作流",
                scope=scope.echo(),
            )

        # 门禁 2：run_mode 必须与持久化工作流的用途合同一致。
        kind = str(pwf.get("workflow_kind") or DEFAULT_WORKFLOW_KIND)
        assert_run_mode_allowed(kind, rm)

        if idempotency_key:
            for existing in stores.executions.list(scope):
                if str(existing.get("idempotency_key") or "") == str(idempotency_key):
                    return existing

        # 门禁 3：执行前预检；blocked 必须拒绝。
        effective_version_id = str(dataset_version_id).strip() if dataset_version_id else None
        if not effective_version_id:
            effective_version_id = str(pwf.get("bound_dataset_version_id") or "").strip() or None
        preflight = run_preflight(
            scope,
            project_workflow_id=project_workflow_id,
            dataset_version_id=effective_version_id,
        )
        if str(preflight.get("overall") or "") == "blocked":
            blocked = [
                c["key"] for c in (preflight.get("checks") or []) if c.get("status") == "blocked"
            ]
            raise ScopeError(
                "preflight_blocked",
                f"执行前预检阻断，拒绝创建执行；阻断项：{blocked}。",
                next_action="修复上述阻断项后重新预检",
                scope=scope.echo(),
            )

        timeline = [
            {"node_id": nid, "status": "pending", "updated_at": _now_iso()}
            for nid in (node_ids or [])
        ]
        record = {
            "execution_id": _new_id("exec"),
            "project_workflow_id": project_workflow_id,
            # 固化工作流血缘：执行记录自带可核验的用途 / 版本 / 绑定对象。
            "workflow_kind": kind,
            "workflow_version": pwf.get("version"),
            "workflow_version_group_id": pwf.get("version_group_id"),
            "bound_dataset_version_id": pwf.get("bound_dataset_version_id"),
            "bound_snapshot_id": pwf.get("bound_snapshot_id"),
            "bound_snapshot_type": pwf.get("bound_snapshot_type"),
            "preflight": {
                "overall": preflight.get("overall"),
                "experiment_only": bool(preflight.get("experiment_only")),
                "evaluated_at": preflight.get("evaluated_at"),
                "checks_digest": _checks_digest(preflight.get("checks") or []),
            },
            "dataset_version_id": effective_version_id,
            "run_mode": rm,
            "run_domain": rd,
            "evaluation_contract": evaluation_contract or {},
            "governance_eligible": compute_governance_eligible(kind, rm, rd),
            "status": "running",
            "node_timeline": timeline,
            "result_destination": None,
            "failure_reason": None,
            "idempotency_key": idempotency_key,
            "origin_execution_id": origin_execution_id,
            "origin_kind": origin_kind,
            "started_at": _now_iso(),
            "updated_at": _now_iso(),
            "finished_at": None,
        }
        return stores.executions.append(scope, record)

    def update_node_status(
        self, scope: ScopeContext, execution_id: str, node_id: str, status: str,
        *, error: Optional[str] = None,
    ) -> dict[str, Any]:
        """更新节点时间线中的某个节点状态。"""
        scope.assert_writable()
        if status not in NODE_STATES:
            raise ValueError(f"未知节点状态：{status!r}")
        rec = self._require(scope, execution_id)
        timeline = list(rec.get("node_timeline") or [])
        found = False
        for entry in timeline:
            if str(entry.get("node_id")) == str(node_id):
                entry["status"] = status
                entry["updated_at"] = _now_iso()
                if error:
                    entry["error"] = error
                found = True
                break
        if not found:
            timeline.append({"node_id": node_id, "status": status, "updated_at": _now_iso(),
                             **({"error": error} if error else {})})
        rec["node_timeline"] = timeline
        rec["updated_at"] = _now_iso()
        return stores.executions.replace(scope, execution_id, rec)

    def finalize(
        self, scope: ScopeContext, execution_id: str, *, status: str,
        result_destination: Optional[str] = None, failure_reason: Optional[str] = None,
        model_artifact_ref: Optional[str] = None,
        node_results: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """终态落库；成功时写结果去向。绝不覆盖其他 execution 的失败证据。

        `model_artifact_ref`（训练产出的模型工件相对引用）与 `node_results`
        （节点产出摘要，形如 `{node_id: {"outputSummary": {...}}}`）都是可选的：
        **一旦给出工件，且本次执行成功且可治理，就自动登记候选**，候选再由领域桥
        进对应 slot 的候选池，从而在「模型部署 / 精度运营」页可见。

        为什么做成"给工件才登记"而不是"成功就登记"：项目执行是记账壳，工件路径只有
        调用方知道（此前 `node_results` 从未被写入，恒为 None，无从推断）。不传工件时
        行为与改动前完全一致——这是既有调用方的兼容底线。

        自动登记**不阻断**终态落库：登记是派发，落库是主链路。结果如实写进
        `auto_candidate` 字段（成功 / 跳过原因 / 失败原因），不静默。
        """
        scope.assert_writable()
        if status not in TERMINAL_STATES:
            raise ValueError(f"终态必须是 {TERMINAL_STATES}，收到 {status!r}")
        rec = self._require(scope, execution_id)
        rec["status"] = status
        rec["finished_at"] = _now_iso()
        rec["updated_at"] = _now_iso()
        if isinstance(node_results, dict) and node_results:
            # 落 node_results：领域桥镜像执行、provenance 提取工件都读这一份。
            rec["node_results"] = node_results
        if status == "success":
            if result_destination and result_destination not in RESULT_DESTINATIONS:
                raise ValueError(f"未知结果去向：{result_destination!r}")
            rec["result_destination"] = result_destination
        if status == "failed":
            rec["failure_reason"] = failure_reason or "unknown"
        saved = stores.executions.replace(scope, execution_id, rec)

        # 候选登记必须在执行以 success 落盘**之后**：register_candidate 会重新读执行记录
        # 并要求 status == "success"。
        auto = self._auto_register_candidate(
            scope, saved, model_artifact_ref=model_artifact_ref
        )
        if auto is None:
            return saved
        return stores.executions.replace(
            scope, execution_id, {**saved, "auto_candidate": auto}
        )

    def _auto_register_candidate(
        self, scope: ScopeContext, execution: dict[str, Any], *,
        model_artifact_ref: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """成功且可治理的训练执行 → 自动登记候选。返回 None 表示"本次不适用，不必记账"。

        跳过与失败都返回结构化原因，供页面解释"为什么模型没出现在部署页"。
        """
        if str(execution.get("status") or "") != "success":
            return None
        if execution.get("governance_eligible") is not True:
            # experiment / validation / sandbox 恒非可治理：这是设计红线，不是异常。
            return None

        from services.slot_governance.provenance import extract_model_artifact_ref  # noqa: PLC0415

        artifact = str(model_artifact_ref or "").strip() or (
            extract_model_artifact_ref(execution.get("node_results")) or ""
        )
        if not artifact:
            return {
                "registered": False,
                "reason": "missing_model_artifact_ref",
                "note": "执行成功且可治理，但未提供模型工件引用，无法登记候选；"
                        "请在 finalize 时带 model_artifact_ref 或 node_results。",
            }

        from services.pv_projects import governance as governance_service  # noqa: PLC0415

        execution_id = str(execution.get("execution_id") or "")
        # 幂等：finalize 可能被重复调用（刷新 / 重试 / 外部编排重放），而
        # register_candidate 自身**不去重**，直接登记会在候选池里堆同一个模型。
        # 判据用 (来源执行, 工件) 而不是只看执行——同一次训练可能产出多个工件。
        try:
            for existing in governance_service.list_candidates(scope):
                if (
                    str(existing.get("source_execution_id") or "") == execution_id
                    and str(existing.get("model_artifact_ref") or "").replace("\\", "/")
                    == artifact.replace("\\", "/")
                ):
                    sync_prev = existing.get("domain_sync") or {}
                    return {
                        "registered": True,
                        "idempotent_hit": True,
                        "model_candidate_id": existing.get("model_candidate_id"),
                        "model_artifact_ref": artifact,
                        "pool_registered": bool(sync_prev.get("pool_registered")),
                        "pool_candidate_id": sync_prev.get("pool_candidate_id"),
                    }
        except Exception:  # noqa: BLE001 — 去重探测失败就走正常登记，不因此拒绝主动作
            pass

        try:
            candidate = governance_service.register_candidate(
                scope,
                source_execution_id=execution_id,
                model_artifact_ref=artifact,
            )
        except Exception as exc:  # noqa: BLE001 — 登记失败不阻断终态落库，但必须可见
            return {
                "registered": False,
                "reason": getattr(exc, "code", None) or type(exc).__name__,
                "error": str(exc),
            }
        sync = candidate.get("domain_sync") or {}
        return {
            "registered": True,
            "idempotent_hit": False,
            "model_candidate_id": candidate.get("model_candidate_id"),
            "model_artifact_ref": artifact,
            # 进池才等于"部署页看得见"：synced=True 不代表进池（桥可能回了 pool_error）。
            "pool_registered": bool(sync.get("pool_registered")),
            "pool_candidate_id": sync.get("pool_candidate_id"),
            "domain_sync_reason": sync.get("reason") or sync.get("pool_error"),
        }

    def retry_with_original_input(self, scope: ScopeContext, execution_id: str) -> dict[str, Any]:
        """用原输入重试：产生一条**新** execution，保留原失败证据。"""
        origin = self._require(scope, execution_id)
        return self.start_execution(
            scope,
            project_workflow_id=str(origin.get("project_workflow_id")),
            run_mode=str(origin.get("run_mode")),
            run_domain=str(origin.get("run_domain") or "project"),
            dataset_version_id=origin.get("dataset_version_id"),
            node_ids=[e.get("node_id") for e in (origin.get("node_timeline") or [])],
            evaluation_contract=origin.get("evaluation_contract"),
            origin_execution_id=execution_id,
            origin_kind="retry",
        )

    def modify_and_rerun(
        self, scope: ScopeContext, execution_id: str, *,
        run_mode: Optional[str] = None, dataset_version_id: Optional[str] = None,
        node_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """改后重跑：产生一条**新** execution（可换模式 / 版本 / 节点），保留原记录。"""
        origin = self._require(scope, execution_id)
        return self.start_execution(
            scope,
            project_workflow_id=str(origin.get("project_workflow_id")),
            run_mode=str(run_mode or origin.get("run_mode")),
            run_domain=str(origin.get("run_domain") or "project"),
            dataset_version_id=dataset_version_id or origin.get("dataset_version_id"),
            node_ids=node_ids if node_ids is not None else [e.get("node_id") for e in (origin.get("node_timeline") or [])],
            evaluation_contract=origin.get("evaluation_contract"),
            origin_execution_id=execution_id,
            origin_kind="modify_rerun",
        )

    def get_execution(self, scope: ScopeContext, execution_id: str) -> Optional[dict[str, Any]]:
        return stores.executions.find(scope, execution_id)

    def list_executions(self, scope: ScopeContext) -> list[dict[str, Any]]:
        return stores.executions.list(scope)

    def _require(self, scope: ScopeContext, execution_id: str) -> dict[str, Any]:
        rec = stores.executions.find(scope, execution_id)
        if rec is None:
            # 后端记录缺失：显式失败，不臆造
            raise LookupError(f"execution 记录缺失：{execution_id}")
        return dict(rec)


_runner = ScopedWorkflowRunner()


def get_runner() -> ScopedWorkflowRunner:
    return _runner

# @AI_GENERATED: end
