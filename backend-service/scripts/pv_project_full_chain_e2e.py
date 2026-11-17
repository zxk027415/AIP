# @AI_GENERATED
#!/usr/bin/env python
"""项目工作台完整链路 E2E：创建项目 → 挂载数据集 → 训练 → 喂数 → 按日精度。

**这是「项目能不能完整跑完」的唯一可执行判据**，也是交接文档的可执行附件。

链路九步（每步都有独立断言，失败即停并打印原因码）：

    1. 发布累计快照到平台数据集目录（幂等；已发布则命中）
    2. 创建项目并在创建时挂载该快照（先选数据集，再推导路径）
    3. 校验挂载副产物：模型继承 baseline（共享原工件，不复制二进制）
    4. 发布项目级不可变数据版本（资产 → 画像 → 版本）
    5. 审核 → 逐条裁定 → 完成并准入（产 admission 事件；冻结的唯一前置）
    6. 冻结快照（产 snap-*；候选登记的硬门）
    7. 建 training 项目工作流（绑数据版本 + 绑冻结快照）并跑 training 执行
    8. finalize 带模型工件 → 自动登记候选 → 领域桥进 slot 候选池
    9. 选喂数源 → 按日回放 → 产出真精度

用法（backend-service/ 下，无需启动后端；用 TestClient 直连 ASGI app）：

    $env:PYTHONPATH="."
    python scripts/pv_project_full_chain_e2e.py                # 隔离临时存储，不碰真实 data/
    python scripts/pv_project_full_chain_e2e.py --live         # 打真实 data/（会写入真实项目）
    python scripts/pv_project_full_chain_e2e.py --slot pv_point

默认 `--slot pv_day`。默认隔离模式：`repo.set_storage_base(tmp)` 重定向项目存储，
证据写 `data/e2e/`，跑完自动清理临时目录。

**重要：隔离模式只隔离项目存储，第 9 步一定会写真实 data/slot_datasets/<slot>/。**
`services/slot_datasets/{feed_sources,loop_demo}.py` 用各自的模块级 `_BACKEND_DIR`，
不受 `repo.set_storage_base` 影响。第 9 步会：
  - 改写 `data/slot_datasets/<slot>/feed_source.json`（切换该路径喂数源）
  - 换源时清空并重建该路径的 `loop_demo/`（arrived / outcomes / daily_accuracy）
不想动真实回放进度就别跑第 9 步（用 `--skip-feed`）。

**已知边界（不是脚本缺陷，是系统现状）**：
- 项目执行是记账壳，不触发算法计算。`--model-artifact` 复用平台已有工件；
  真训练要走平台 enhanced workflow 或离线脚本。
- 按日精度默认用内置规则检测（`model_id=loop_demo_rule`），归属不到项目。
  加 `--use-real-model` 才会走 `resolve_slot_scheduler_model` 的真实模型，
  此时 `model_id` 是 `mc-*`，与继承 baseline 的 `source_model_candidate_id` 对齐。
- 项目 Promote 写项目 registry，按日回放读 slot registry，两者是不同 store：
  **项目 Promote 不改变回放实际用哪个模型**。
- `loop_demo/outcomes.json` 是单个 JSON 全量读写。实测 pv_day 那份已经
  **132 MB / 316,104 条 / 只覆盖 8 个业务日**，一次 `json.load` 要 3.49 s、
  Python 堆峰值 0.61 GB。`load_outcomes()` / `outcomes_for_window()` /
  `run_next_demo_day()` 全是整读整写，所以推进一天至少付两次这个代价，
  任何窗口查询也付一次。这是已知伸缩性问题，建议按业务日分片。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND_DIR / "data" / "e2e"

#: 每条路径的默认复用模型工件（项目内不产工件，只能引平台已有的）。
DEFAULT_ARTIFACT_BY_SLOT: dict[str, str] = {
    "pv_day": "data/models/pv_fault_rfc_20260825T093215Z_2d79bc.pkl",
    "pv_point": "data/models/timeseries_point/rtpoint-tcn-last_point-20260827073808-a3d1d118",
    "pv_tsc": "data/models/tsc/tsc-minirocket-20260901101632-171fcd4f",
}

#: 审核单元粒度：pv_point 冻结会排除整日盒，必须用 point。
GRANULARITY_BY_SLOT: dict[str, str] = {
    "pv_day": "device_day",
    "pv_point": "point",
    "pv_tsc": "device_day",
}

MAPPING = {"time_col": "time", "device_col": "device_id", "value_col": "value"}


class StepFailed(RuntimeError):
    """某一步断言失败；带上原因码便于对照后端 reason_code。"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ChainRunner:
    def __init__(
        self,
        client: Any,
        *,
        slot: str,
        artifact: str,
        days: int = 3,
        use_real_model: bool = False,
        skip_feed: bool = False,
    ) -> None:
        self.c = client
        self.slot = slot
        self.artifact = artifact
        self.days = max(1, int(days))
        self.use_real_model = bool(use_real_model)
        self.skip_feed = bool(skip_feed)
        self.granularity = GRANULARITY_BY_SLOT[slot]
        self.steps: list[dict[str, Any]] = []
        self.project_id: Optional[str] = None
        self.entry_id: Optional[str] = None
        self.dataset_version_id: Optional[str] = None
        self.snapshot_id: Optional[str] = None
        self.workflow_id: Optional[str] = None
        self.execution_id: Optional[str] = None
        self.candidate_id: Optional[str] = None
        self.pool_candidate_id: Optional[str] = None
        self.dataset_ref: Optional[str] = None

    # -- 工具 ---------------------------------------------------------------

    def _record(self, name: str, ok: bool, detail: Any) -> None:
        self.steps.append({"step": name, "ok": bool(ok), "detail": detail, "at": _now()})
        flag = "OK  " if ok else "FAIL"
        print(f"[{flag}] {name}")
        if not ok:
            print(json.dumps(detail, ensure_ascii=False, indent=2, default=str)[:1600])

    def _post(self, path: str, payload: Any = None, **kw: Any) -> Any:
        return self.c.post(path, json=payload, **kw)

    def _need(self, resp: Any, name: str) -> dict[str, Any]:
        """要求 2xx；否则记账并抛出（带 reason_code，便于定位门禁）。"""
        if resp.status_code >= 400:
            body: Any
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = resp.text
            detail = {"status": resp.status_code, "body": body}
            self._record(name, False, detail)
            reason = ""
            if isinstance(body, dict):
                reason = str((body.get("detail") or {}).get("reason_code") or "")
            raise StepFailed(f"{name} 失败：HTTP {resp.status_code} {reason}")
        return resp.json()

    # -- 步骤 ---------------------------------------------------------------

    def step1_publish_snapshot(self) -> None:
        """发布该路径的累计冻结快照到平台目录（幂等）。"""
        sources = self._need(
            self.c.get("/api/pv-projects/catalog/available-sources"), "1.列出可检测来源"
        )
        cumulative = [
            s for s in (sources.get("path_cumulative") or [])
            if str(s.get("origin_slot")) == self.slot
        ]
        if not cumulative:
            self._record("1.发布累计快照", False, {"reason": f"{self.slot} 无累计冻结快照可发布"})
            raise StepFailed("没有累计快照；先在该路径冻结出 snapshots/*.parquet")
        src = cumulative[0]
        entry = self._need(
            self._post(
                "/api/pv-projects/catalog/publish",
                {
                    "dataset_ref": src["dataset_ref"],
                    "mapping": MAPPING,
                    "label_policy": {"granularity": self.granularity},
                    "origin_slot": self.slot,
                    "origin": src.get("origin"),
                    "display_name": src.get("display_name"),
                },
            ),
            "1.发布累计快照",
        )
        self.entry_id = entry["entry_id"]
        self.dataset_ref = entry["dataset_ref"]
        # 路径累计快照必须只归自己那条路径。
        applicable = [
            s for s, info in (entry.get("applicable_paths") or {}).items()
            if isinstance(info, dict) and info.get("applicable") is True
        ]
        if applicable != [self.slot]:
            self._record("1.发布累计快照", False,
                         {"applicable": applicable, "expect": [self.slot]})
            raise StepFailed("累计快照适用路径不唯一，路径归属收敛失效")
        self._record("1.发布累计快照", True, {
            "entry_id": self.entry_id,
            "dataset_ref": self.dataset_ref,
            "applicable": applicable,
            "idempotent_hit": entry.get("idempotent_hit"),
        })

    def step2_create_project_with_mount(self) -> None:
        """创建项目并在创建时挂载数据集（先选数据集，再推导路径）。"""
        created = self._need(
            self._post(
                "/api/pv-projects",
                {
                    "project_name": f"E2E 全链 {self.slot} {uuid.uuid4().hex[:6]}",
                    "solution_id": "pv_fault",
                    "scenario_id": "renewable-energy",
                    "catalog_entry_id": self.entry_id,
                },
            ),
            "2.创建项目并挂载",
        )
        self.project_id = created["project_id"]
        if created.get("mount_slot") != self.slot:
            self._record("2.创建项目并挂载", False, {"mount_slot": created.get("mount_slot")})
            raise StepFailed("挂载路径推导错误")
        self._record("2.创建项目并挂载", True, {
            "project_id": self.project_id,
            "mount_slot": created.get("mount_slot"),
            "dataset_ref": (created.get("mounted") or {}).get("dataset_ref"),
        })

    def step3_check_inheritance(self) -> None:
        """挂载副产物：模型继承 baseline（共享工件，不复制二进制，不可 Promote）。"""
        reg = self._need(
            self.c.get(f"/api/pv-projects/{self.project_id}/slots/{self.slot}/registry"),
            "3.校验模型继承",
        )
        inherited = reg.get("inherited_baseline")
        mi = reg.get("model_inheritance") or {}
        if not inherited:
            # 该 slot 平台侧没有可解析模型时，这一步允许为空但要如实记录。
            self._record("3.校验模型继承", True, {
                "inherited": None,
                "status": mi.get("status"),
                "note": "平台该路径无可解析模型或工件缺失；不阻断链路",
            })
            return
        problems = []
        if inherited.get("promotable") is not False:
            problems.append("promotable 必须为 false")
        if inherited.get("governance_effect") != "none":
            problems.append("governance_effect 必须为 none")
        if inherited.get("binary_copied") is not False:
            problems.append("binary_copied 必须为 false")
        if problems:
            self._record("3.校验模型继承", False, {"problems": problems, "inherited": inherited})
            raise StepFailed("继承 baseline 语义越界")
        self._record("3.校验模型继承", True, {
            "source_model_candidate_id": inherited.get("source_model_candidate_id"),
            "source_role": inherited.get("source_role"),
            "model_artifact_ref": inherited.get("model_artifact_ref"),
            "promotable": inherited.get("promotable"),
        })

    def step4_publish_dataset_version(self) -> None:
        """发布项目级不可变数据版本：资产 → 画像 → 版本。"""
        asset = self._need(
            self._post(
                f"/api/pv-projects/{self.project_id}/datasets",
                {
                    "source_kind": "platform_asset",
                    "asset_id": f"e2e-{self.slot}-{uuid.uuid4().hex[:8]}",
                    "logical_object": f"{self.slot}.cumulative",
                    "logical_description": "E2E 全链数据版本来源（逻辑引用）",
                },
            ),
            "4.登记数据资产",
        )
        profile = self._need(
            self._post(
                f"/api/pv-projects/{self.project_id}/datasets/{asset['dataset_id']}/profile",
                {
                    "mapping": MAPPING,
                    "label_policy": {"granularity": self.granularity},
                    "facts": {"sufficient_coverage": True},
                },
            ),
            "4.保存画像",
        )
        version = self._need(
            self._post(
                f"/api/pv-projects/{self.project_id}/dataset-versions/publish",
                {
                    "dataset_id": asset["dataset_id"],
                    "dataset_profile_id": profile["dataset_profile_id"],
                },
            ),
            "4.发布数据版本",
        )
        self.dataset_version_id = version["dataset_version_id"]
        self._record("4.发布数据版本", True, {
            "dataset_id": asset["dataset_id"],
            "dataset_version_id": self.dataset_version_id,
        })

    def step5_review_and_admit(self) -> None:
        """审核 → 裁定 → 完成并准入。这是冻结快照的唯一前置，没有旁路。"""
        base = f"/api/pv-projects/{self.project_id}/slots/{self.slot}/reviews"
        items = [
            {
                "item_id": f"it-{idx}",
                # unit_ref 约定 device=..;date=..;label=..，冻结时按片段解析分布。
                "unit_ref": f"device=DEV{idx};date=2026-01-0{idx};label=fault",
                "proposed_label": "fault",
            }
            for idx in (1, 2, 3)
        ]
        review = self._need(
            self._post(base, {
                "source_kind": "label_proposal",
                "unit_granularity": self.granularity,
                "items": items,
                "dataset_version_id": self.dataset_version_id,
            }),
            "5.登记审核会话",
        )["review"]
        rid = review["review_id"]

        saved = self._need(
            self._post(f"{base}/{rid}/verdict", {
                "expected_review_version": review["review_version"],
                "item_verdicts": [
                    {"item_id": it["item_id"], "verdict": "accept", "verdict_label": "fault"}
                    for it in items
                ],
            }),
            "5.保存裁定",
        )
        version_after = (saved.get("review") or {}).get("review_version", review["review_version"])

        admitted = self._need(
            self._post(f"{base}/{rid}/complete-and-admit", {
                "expected_review_version": version_after,
                "idempotency_key": f"e2e-admit-{rid}",
                "operator": "e2e-script",
            }),
            "5.完成并准入",
        )
        count = int((admitted.get("admission") or {}).get("admitted_count") or 0)
        if count <= 0:
            self._record("5.审核准入", False, {"admitted": admitted})
            raise StepFailed("准入条数为 0，无法冻结")
        self._record("5.审核准入", True, {"review_id": rid, "admitted_count": count})

    def step6_freeze_snapshot(self) -> None:
        """冻结快照，拿 snap-*。候选登记的硬门。"""
        base = f"/api/pv-projects/{self.project_id}/slots/{self.slot}/cumulative"
        plan = self._need(self._post(f"{base}/freeze-plan", {}), "6.冻结计划")
        if int(plan.get("included_count") or 0) <= 0:
            self._record("6.冻结快照", False, {"plan": plan})
            raise StepFailed("冻结计划 included_count=0（pv_point 注意整日盒会被排除）")
        frozen = self._need(
            self._post(f"{base}/freeze", {
                "idempotency_key": f"e2e-freeze-{self.project_id}-{self.slot}",
                "operator": "e2e-script",
            }),
            "6.冻结快照",
        )
        snap = frozen["snapshot"]
        self.snapshot_id = snap["snapshot_id"]
        self._record("6.冻结快照", True, {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": snap.get("snapshot_type"),
            "included_count": snap.get("included_count"),
        })

    def step7_training_workflow_and_run(self) -> None:
        """建 training 工作流（绑数据版本 + 绑快照）并跑 training 执行。"""
        wf = self._need(
            self._post(f"/api/pv-projects/{self.project_id}/project-workflows", {
                "slot": self.slot,
                "mode": "blank",
                "name": f"E2E {self.slot} 训练",
                "workflow_kind": "training",
                "dataset_version_id": self.dataset_version_id,
                "source_snapshot_id": self.snapshot_id,
                "nodes": [{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            }),
            "7.创建训练工作流",
        )
        self.workflow_id = wf["project_workflow_id"]

        pre = self._need(
            self._post(f"/api/pv-projects/{self.project_id}/preflight", {
                "slot": self.slot,
                "project_workflow_id": self.workflow_id,
            }),
            "7.执行前预检",
        )
        if pre.get("overall") == "blocked":
            self._record("7.执行前预检", False, {"checks": pre.get("checks")})
            raise StepFailed("预检 blocked，无法创建执行")

        ex = self._need(
            self._post(f"/api/pv-projects/{self.project_id}/executions", {
                "slot": self.slot,
                "project_workflow_id": self.workflow_id,
                "run_mode": "training",
                "run_domain": "project",
            }),
            "7.创建训练执行",
        )
        self.execution_id = ex["execution_id"]
        if ex.get("governance_eligible") is not True:
            self._record("7.创建训练执行", False, {"execution": ex})
            raise StepFailed("training 执行未取得治理资格")
        self._record("7.训练工作流与执行", True, {
            "project_workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "preflight_overall": pre.get("overall"),
            "experiment_only": pre.get("experiment_only"),
            "governance_eligible": ex.get("governance_eligible"),
        })

    def step8_finalize_and_register(self) -> None:
        """finalize 带模型工件 → 自动登记候选 → 领域桥进 slot 候选池。"""
        done = self._need(
            self._post(
                f"/api/pv-projects/{self.project_id}/executions/{self.execution_id}/finalize",
                {
                    "slot": self.slot,
                    "status": "success",
                    "result_destination": "governable_candidate",
                    "model_artifact_ref": self.artifact,
                    "node_results": {
                        "n1": {"outputSummary": {"model_artifact_ref": self.artifact}}
                    },
                },
            ),
            "8.finalize 执行",
        )
        auto = done.get("auto_candidate") or {}
        if not auto.get("registered"):
            self._record("8.自动登记候选", False, {"auto_candidate": auto})
            raise StepFailed(f"候选未登记：{auto.get('reason')}")
        self.candidate_id = auto.get("model_candidate_id")
        self.pool_candidate_id = auto.get("pool_candidate_id")

        gov = self._need(
            self.c.get(
                f"/api/pv-projects/{self.project_id}/slots/{self.slot}/governance-overview"
            ),
            "8.读治理视图",
        )
        pending_ids = {c.get("model_candidate_id") for c in (gov.get("pending_candidates") or [])}
        if self.candidate_id not in pending_ids:
            self._record("8.候选进待复验区", False, {
                "candidate_id": self.candidate_id,
                "pending": sorted(x for x in pending_ids if x),
                "experiment_results": len(gov.get("experiment_results") or []),
            })
            raise StepFailed("候选未进入待复验候选（可能 provenance 不完整）")
        self._record("8.候选登记与进池", True, {
            "project_candidate_id": self.candidate_id,
            "pool_registered": auto.get("pool_registered"),
            "pool_candidate_id": self.pool_candidate_id,
            "domain_sync_reason": auto.get("domain_sync_reason"),
            "pending_candidates": len(pending_ids),
        })

    def step9_feed_and_accuracy(self) -> None:
        """选喂数源 → 按日回放 → 产出真精度。"""
        feeds = self._need(
            self.c.get("/api/slot-datasets/feed-sources", params={"limit": 400}),
            "9.列喂数候选",
        )
        refs = {str(c.get("dataset_ref")) for c in (feeds.get("candidates") or [])}
        if self.dataset_ref not in refs:
            self._record("9.喂数候选可见性", False, {
                "expect": self.dataset_ref,
                "candidate_count": len(refs),
                "note": "累计快照不在候选里 → DATASET_UNIT_SPECS 缺 slot_datasets 规则",
            })
            raise StepFailed("项目数据集不在喂数候选清单里（前端下拉将选不到）")

        selected = self._need(
            self._post("/api/slot-datasets/feed-sources/select", {
                "slot": self.slot,
                "dataset_ref": self.dataset_ref,
                "operator": "e2e-script",
            }),
            "9.选中喂数源",
        )

        # pv_tsc 生产观测只读，回放走独立通道；pv_day / pv_point 走水位推进。
        if self.slot == "pv_tsc":
            advance_path = "/api/slot-datasets/observability/pv-tsc/replay-advance"
            advance_body: dict[str, Any] = {
                "operator": "e2e-script",
                "use_real_model": self.use_real_model,
            }
        else:
            advance_path = "/api/slot-datasets/observability/advance-day"
            advance_body = {
                "slot": self.slot,
                "operator": "e2e-script",
                "use_real_model": self.use_real_model,
            }

        fed_days: list[dict[str, Any]] = []
        last: dict[str, Any] = {}
        for _ in range(self.days):
            last = self._need(self._post(advance_path, advance_body), "9.推进业务日")
            cycle = last.get("cycle") if isinstance(last.get("cycle"), dict) else last
            day = cycle.get("fed_day")
            if day:
                acc = cycle.get("accuracy") or {}
                fed_days.append({
                    "day": day,
                    "counted_units": acc.get("counted_units"),
                    "classifier_accuracy": acc.get("classifier_accuracy"),
                    "model_id": cycle.get("model_id"),
                })
            if cycle.get("exhausted"):
                break

        evaluated = [d for d in fed_days if int(d.get("counted_units") or 0) > 0]
        if not evaluated:
            self._record("9.按日精度", False, {
                "fed_days": fed_days,
                "selected": selected.get("selection"),
                "note": "喂了日但没有计入真值的评估单元；确认喂数源含 label 列",
            })
            raise StepFailed("没有产出可用精度")

        overview = self._need(self.c.get("/api/slot-datasets/overview"), "9.读三路径总览")
        row = next((r for r in overview.get("paths") or [] if r.get("slot") == self.slot), {})
        att = row.get("accuracy_attribution") or {}
        # 精度是否归属项目：内置规则（loop_demo_rule）不可能归属；真实模型模式下
        # model_id 应等于继承 baseline 的 source_model_candidate_id。
        reg = self._need(
            self.c.get(f"/api/pv-projects/{self.project_id}/slots/{self.slot}/registry"),
            "9.读项目模型登记",
        )
        inherited_mc = str((reg.get("inherited_baseline") or {}).get("source_model_candidate_id") or "")
        acc_model = str(att.get("model_id") or "")
        self._record("9.喂数与按日精度", True, {
            "dataset_ref": self.dataset_ref,
            "used_real_model": self.use_real_model,
            "fed_days": fed_days,
            "evaluated_days": len(evaluated),
            "cumulative_accuracy": row.get("classifier_accuracy"),
            "latest_accuracy": att.get("latest_accuracy"),
            "latest_counted_units": att.get("latest_counted_units"),
            "accuracy_model_id": acc_model or None,
            "inherited_model_candidate_id": inherited_mc or None,
            "accuracy_attributable_to_project": bool(
                acc_model and inherited_mc and acc_model == inherited_mc
            ),
            "attribution_note": (
                "内置规则检测，精度不归属任何模型（加 --use-real-model 才归属）"
                if acc_model == "loop_demo_rule"
                else None
            ),
        })

    def run(self) -> dict[str, Any]:
        self.step1_publish_snapshot()
        self.step2_create_project_with_mount()
        self.step3_check_inheritance()
        self.step4_publish_dataset_version()
        self.step5_review_and_admit()
        self.step6_freeze_snapshot()
        self.step7_training_workflow_and_run()
        self.step8_finalize_and_register()
        if self.skip_feed:
            self._record("9.喂数与按日精度", True, {"skipped": "--skip-feed（不动真实回放进度）"})
        else:
            self.step9_feed_and_accuracy()
        return self.summary(passed=True)

    def summary(self, *, passed: bool) -> dict[str, Any]:
        return {
            "passed": bool(passed),
            "slot": self.slot,
            "project_id": self.project_id,
            "catalog_entry_id": self.entry_id,
            "dataset_ref": self.dataset_ref,
            "dataset_version_id": self.dataset_version_id,
            "snapshot_id": self.snapshot_id,
            "project_workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "project_candidate_id": self.candidate_id,
            "pool_candidate_id": self.pool_candidate_id,
            "model_artifact_ref": self.artifact,
            "steps": self.steps,
            "finished_at": _now(),
        }


def _build_client() -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.pv_projects import router as pv_router
    from api.slot_datasets import router as slot_router

    app = FastAPI()
    app.include_router(pv_router)
    app.include_router(slot_router)
    # raise_server_exceptions=False：让 5xx 以响应形式返回，脚本能记录原因而不是崩栈。
    return TestClient(app, raise_server_exceptions=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="项目工作台完整链路 E2E")
    parser.add_argument("--slot", default="pv_day", choices=sorted(DEFAULT_ARTIFACT_BY_SLOT))
    parser.add_argument("--model-artifact", default=None,
                        help="复用的模型工件相对引用；缺省按 slot 取平台已有工件")
    parser.add_argument("--live", action="store_true",
                        help="打真实 data/（会写入真实项目）；缺省用隔离临时存储")
    parser.add_argument("--days", type=int, default=3,
                        help="第 9 步推进几个业务日（默认 3；outcomes.json 全量读写，越多越慢）")
    parser.add_argument("--use-real-model", action="store_true",
                        help="按日检测用真实模型而非内置规则；精度才可能归属到项目模型")
    parser.add_argument("--skip-feed", action="store_true",
                        help="跳过第 9 步；不改写真实 data/slot_datasets/<slot>/")
    args = parser.parse_args()

    sys.path.insert(0, str(BACKEND_DIR))
    from services.pv_projects import repositories as repo

    artifact = args.model_artifact or DEFAULT_ARTIFACT_BY_SLOT[args.slot]
    tmp: Optional[str] = None
    if not args.live:
        tmp = tempfile.mkdtemp(prefix="pv_chain_e2e_")
        repo.set_storage_base(tmp)
        print(f"隔离模式：项目存储重定向到 {tmp}")
    else:
        print("LIVE 模式：将写入真实 data/")

    if not args.skip_feed:
        print(f"注意：第 9 步会改写真实 data/slot_datasets/{args.slot}/"
              f"（feed_source.json + loop_demo/）。加 --skip-feed 可跳过。")

    runner = ChainRunner(
        _build_client(),
        slot=args.slot,
        artifact=artifact,
        days=args.days,
        use_real_model=args.use_real_model,
        skip_feed=args.skip_feed,
    )
    try:
        report = runner.run()
    except StepFailed as exc:
        report = runner.summary(passed=False)
        report["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 — 未预期异常也要留证据
        report = runner.summary(passed=False)
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if tmp:
            repo.set_storage_base(None)
            shutil.rmtree(tmp, ignore_errors=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out = OUT_DIR / f"pv_project_full_chain_{args.slot}_{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("")
    print("=" * 62)
    print(f"链路结果：{'PASS' if report['passed'] else 'FAIL'}    slot={args.slot}")
    if not report["passed"]:
        print(f"失败原因：{report.get('error')}")
    print(f"证据：{out.relative_to(BACKEND_DIR)}")
    print("=" * 62)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
# @AI_GENERATED: end
