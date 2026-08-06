# @AI_GENERATED
"""完整 LF 故事线：带 AR patch 的预上线 → 喂 1 日 → pull → 日滚 → 回填 → 系列/对比。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from services.deployment.experiment_patch import (
        experiment_patch_fingerprint,
        load_experiment_patch_from_candidate_id,
        normalize_experiment_patch,
    )
    from services.deployment.store import DeploymentSlotStore
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from services.db.datasources.local_db_mock import (
        LocalDbMockDataSource,
        build_default_mock_feeder,
    )
    from services.db.repositories.load_forecast import LoadForecastRepository
    from services.scheduler.tasks.load_forecast_tasks import (
        make_accuracy_backfill_task,
        make_daily_rolling_task,
        make_data_pull_task,
    )

    slot = "load_forecast"
    store = DeploymentSlotStore()
    slot_obj = store.get(slot)
    assert slot_obj is not None, "slot missing"

    # ---- 1) 确保有一条带真实 patch 的预上线 ----
    cand_id = "cand-369ed87351eb"
    patch = load_experiment_patch_from_candidate_id(cand_id)
    if not patch:
        # 兜底：手工构造与候选一致的 patch
        patch = normalize_experiment_patch(
            {
                "challenger_override": {"ensemble_mode": "all_adaptive", "train_days": 75},
                "effective_parameter_patch": {"ensemble_mode": "all_adaptive"},
                "node_param_patches": [
                    {
                        "node_id": "tpl-ensemble_forecast-20",
                        "functionId": "ensemble_forecast",
                        "param_patch": {"weight_mode": "auto_rmse"},
                    }
                ],
            }
        )
    print("[patch]", experiment_patch_fingerprint(patch), json.dumps(patch, ensure_ascii=False)[:240])

    from api.deployment import PrelaunchEnterBody, enter_prelaunch
    from fastapi import HTTPException

    version_tag = f"e2e-prelaunch-{cand_id[5:17]}"
    # 清出配额：取消/保留旧 demo，尽量腾出位置
    active = [m for m in slot_obj.prelaunch_models if m.status == "prelaunch"]
    print("[prelaunch_before]", [(m.version_tag, bool(m.experiment_patch)) for m in active])
    if len(active) >= slot_obj.max_prelaunch_slots:
        # 直接从 store 去掉最旧的一条（故事线演示）
        drop = active[0]
        slot_obj.prelaunch_models = [
            m for m in slot_obj.prelaunch_models
            if not (m.version_tag == drop.version_tag and m.status == "prelaunch")
        ]
        store.upsert(slot_obj)
        print("[prelaunch] dropped", drop.version_tag, "to free quota")

    try:
        # 用带 patch 的真实 challenger workflow
        from api.workflows_enhanced import _load_candidate_pool_list

        cand = next((x for x in _load_candidate_pool_list() if str(x.get("id")) == cand_id), None)
        wf_id = (cand or {}).get("challenger_workflow_id") or "workflow-load-forecast-backtest-v2"
        body = PrelaunchEnterBody(
            candidate_id=cand_id,
            workflow_id=str(wf_id),
            version_tag=version_tag,
            source_run_id=str((cand or {}).get("source_run_id") or "e2e-story"),
            note="e2e full storyline with real AR patch",
            experiment_patch=patch,
            observation_days=7,
        )
        entered = enter_prelaunch(slot, body)
        print("[enter_prelaunch]", entered.get("version_tag") or version_tag, "ok")
    except HTTPException as exc:
        if getattr(exc, "status_code", None) == 409:
            print("[enter_prelaunch] already exists, hydrate patch")
            slot_obj = store.get(slot)
            for m in slot_obj.prelaunch_models:
                if m.version_tag == version_tag or m.source_candidate_id == cand_id:
                    m.experiment_patch = patch
            store.upsert(slot_obj)
        else:
            raise

    slot_obj = store.get(slot)
    for m in slot_obj.prelaunch_models:
        if m.status == "prelaunch":
            print(
                "[prelaunch_active]",
                m.version_tag,
                "wf=",
                m.workflow_id,
                "patch=",
                bool(m.experiment_patch),
                "fp=",
                experiment_patch_fingerprint(m.experiment_patch) if m.experiment_patch else None,
            )

    # ---- 2) 喂 1 业务日 + pull ----
    adapter = DBAdapter(DBConfig())
    feeder = build_default_mock_feeder(adapter)
    feeder.ensure_tables()
    source = LocalDbMockDataSource(adapter)
    lf_repo = LoadForecastRepository(adapter)
    pull = make_data_pull_task(source, lf_repo, slot)
    preview = feeder.get_manual_feed_preview()
    exhausted = bool(getattr(preview, "exhausted", False))
    if hasattr(preview, "as_dict"):
        exhausted = bool(preview.as_dict().get("exhausted"))
    if exhausted:
        print("[feed] exhausted, skip feed; continue with existing watermark")
    else:
        result = feeder.feed_next_batch()
        print("[feed] inserted=", result)
        try:
            n = pull()
            print("[pull]", n)
        except Exception as exc:
            print("[pull] failed:", exc)

    # ---- 3) 日滚（生产+影子+预上线，各带自己的 patch）----
    rolling = make_daily_rolling_task(
        lf_repo=lf_repo,
        slot=slot,
        station_id="yARGkDuq",
        feature_name="load",
        slot_store=store,
    )
    cycle = rolling()
    print("[daily_rolling] cycle=", cycle)

    # ---- 4) 回填 ----
    backfill = make_accuracy_backfill_task(
        lf_repo=lf_repo,
        slot=slot,
        station_id="yARGkDuq",
        feature_name="load",
        slot_store=store,
    )
    updated = backfill()
    print("[backfill] updated=", updated)

    # ---- 5) 对比各版本最近预测是否分叉 ----
    from sqlalchemy import func
    from services.db.models.load_forecast import PredictionResult

    with lf_repo._adapter.get_sync_session() as session:
        versions = (
            session.query(
                PredictionResult.version_tag,
                PredictionResult.workflow_id,
                func.count(PredictionResult.id),
                func.max(PredictionResult.forecast_timestamp),
            )
            .filter(PredictionResult.slot == slot)
            .group_by(PredictionResult.version_tag, PredictionResult.workflow_id)
            .all()
        )
        print("[versions_in_db]")
        for v in versions:
            print(" ", v)

        # 取各 version 在同一最新业务日的预测均值，看是否分叉
        max_ts = (
            session.query(func.max(PredictionResult.forecast_timestamp))
            .filter(PredictionResult.slot == slot, PredictionResult.status != "failed")
            .scalar()
        )
        if max_ts is not None:
            day = max_ts.date() if hasattr(max_ts, "date") else max_ts
            from datetime import datetime, timedelta

            day_start = datetime.combine(day, datetime.min.time())
            day_end = day_start + timedelta(days=1)
            rows = (
                session.query(
                    PredictionResult.version_tag,
                    func.avg(PredictionResult.predicted_value),
                    func.count(PredictionResult.id),
                )
                .filter(
                    PredictionResult.slot == slot,
                    PredictionResult.forecast_timestamp >= day_start,
                    PredictionResult.forecast_timestamp < day_end,
                    PredictionResult.status != "failed",
                )
                .group_by(PredictionResult.version_tag)
                .all()
            )
            print("[pred_avg_on_latest_day]", day, rows)

    # ---- 6) prediction-series ----
    from api.accuracy_operations import get_prediction_series

    series = get_prediction_series(slot=slot, days=14)
    print(
        "[series]",
        "points=",
        series.get("point_count"),
        "tag=",
        series.get("version_tag"),
        "win=",
        series.get("window_start"),
        "->",
        series.get("window_end"),
    )

    slot_obj = store.get(slot)
    print(
        "[slot_summary]",
        "prod=",
        slot_obj.production_model.version_tag if slot_obj.production_model else None,
        "shadows=",
        [(m.version_tag, bool(m.experiment_patch)) for m in slot_obj.shadow_models if m.status == "shadow"],
        "prelaunch=",
        [
            (m.version_tag, bool(m.experiment_patch), experiment_patch_fingerprint(m.experiment_patch) if m.experiment_patch else None)
            for m in slot_obj.prelaunch_models
            if m.status == "prelaunch"
        ],
    )
    print("OVERALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# @AI_GENERATED: end
