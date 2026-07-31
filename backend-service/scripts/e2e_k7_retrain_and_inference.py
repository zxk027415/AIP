# @AI_GENERATED
"""K7 真实路径对比 + 全量 point_label 重训 + 预测侧 InferenceSample E2E。

用法（conda cp_web，在 backend-service 目录）:
  set PYTHONPATH=.
  python scripts/e2e_k7_retrain_and_inference.py

产物:
  - data/iterative_labeling/modeling_path_compare/pv_fault/latest.json
  - data/models/pv_fault_rfc_*.pkl（含 sample_strategy）
  - data/iterative_labeling/e2e_k7_retrain_report.json
"""
from __future__ import annotations

import asyncio
import json
import pickle
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REPORT_PATH = BACKEND / "data" / "iterative_labeling" / "e2e_k7_retrain_report.json"


def _log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}] {msg}"
    print(line, flush=True)


def _save_report(payload: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_path_compare(report: dict) -> None:
    from services.iterative_labeling.modeling_path_compare import (
        compare_modeling_paths,
        load_latest_compare,
    )

    _log("K7: 开始真实路径对比 n_repeats=1（3 路径，预计较久）")
    started = time.time()
    try:
        result = compare_modeling_paths(
            slot="pv_fault",
            paths=["legacy_day", "point_label_by_day", "point_label_by_day_night"],
            n_repeats=1,
            test_ratio=0.2,
            random_state=90,
        )
        report["path_compare"] = {
            "status": "completed",
            "elapsed_sec": round(time.time() - started, 1),
            "best_path_key": result.get("best_path_key"),
            "best_macro_f1_mean": result.get("best_macro_f1_mean"),
            "results": [
                {
                    "path_key": r.get("path_key"),
                    "macro_f1_mean": r.get("macro_f1_mean"),
                    "accuracy_mean": r.get("accuracy_mean"),
                    "n_samples": r.get("n_samples"),
                    "status": r.get("status"),
                    "error": r.get("error"),
                }
                for r in (result.get("results") or [])
            ],
            "deltas_vs_legacy": result.get("deltas_vs_legacy"),
        }
        _log(f"K7 完成 best={result.get('best_path_key')} f1={result.get('best_macro_f1_mean')}")
    except Exception as exc:
        report["path_compare"] = {
            "status": "failed",
            "error": str(exc),
            "elapsed_sec": round(time.time() - started, 1),
            "partial": load_latest_compare("pv_fault"),
        }
        _log(f"K7 失败: {exc}")
        raise


def run_full_retrain(report: dict, *, n_repeats: int = 10) -> str:
    from services.iterative_labeling.cumulative_training import CumulativeTrainingService
    from services.iterative_labeling.orchestrator import LoopOrchestrator
    from services.iterative_labeling.storage.file_backend import FileReviewResultRepository

    _log(f"重训: 创建 point_label 快照并训练 n_repeats={n_repeats}")
    service = CumulativeTrainingService(
        slot="pv_fault",
        review_repo=FileReviewResultRepository(),
    )
    summary = service.request_manual_retrain()
    request = summary.get("retrain_request") or {}
    request_id = str(request.get("request_id") or "")
    if not request_id:
        raise RuntimeError(f"无法创建重训请求: {summary.get('retrain_blocker')}")

    dataset_path = str(request.get("dataset_path") or "")
    _log(f"重训 request_id={request_id} dataset={dataset_path}")

    service.mark_retrain_request(request_id, "running")
    orchestrator = LoopOrchestrator(slot="pv_fault")
    loop = orchestrator.create_loop(base_dataset_version=dataset_path)
    started = time.time()
    train_result = orchestrator.trigger_train_eval(
        loop_id=loop["loop_id"],
        dataset_version=dataset_path,
        model_params={"n_repeats": n_repeats},
    )
    model_ref = str(train_result["model_ref"])
    model_path_rel = str(train_result["model_path"])
    project_root = BACKEND.parent
    model_abs = (project_root / model_path_rel.replace("\\", "/")).resolve()

    metrics = train_result.get("accuracy_record") or {}
    service.mark_retrain_request(
        request_id,
        "completed",
        model_ref=model_ref,
        train_summary={
            "model_ref": model_ref,
            "model_path": model_path_rel,
            "modeling_path": "point_label_by_day_night",
            "macro_f1_mean": metrics.get("macro_f1_mean"),
            "accuracy_mean": metrics.get("accuracy_mean"),
            "n_samples": metrics.get("n_samples"),
            "accuracy_record": metrics,
        },
    )
    service.register_path_model(
        "point_label_by_day_night",
        model_ref,
        request_id=request_id,
        metrics={
            "macro_f1_mean": metrics.get("macro_f1_mean"),
            "accuracy_mean": metrics.get("accuracy_mean"),
        },
    )

    with model_abs.open("rb") as handle:
        payload = pickle.load(handle)
    if not isinstance(payload, dict) or not payload.get("sample_strategy"):
        raise RuntimeError("训练产物 pickle 缺少 sample_strategy")

    report["retrain"] = {
        "status": "completed",
        "request_id": request_id,
        "model_ref": model_ref,
        "model_path": model_path_rel,
        "elapsed_sec": round(time.time() - started, 1),
        "macro_f1_mean": metrics.get("macro_f1_mean"),
        "accuracy_mean": metrics.get("accuracy_mean"),
        "sample_strategy_split_mode": (payload.get("sample_strategy") or {}).get("split_mode"),
        "label_snapshot_hash": payload.get("label_snapshot_hash"),
    }
    _log(f"重训完成 model={model_ref} split_mode={report['retrain']['sample_strategy_split_mode']}")
    return str(model_abs)


def run_inference_e2e(model_abs: str, report: dict) -> None:
    import pandas as pd
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from services.db.repositories.pv_fault import PVFaultRepository
    from services.iterative_labeling.inference_sample import InferenceSampleGenerator

    _log("预测 E2E: InferenceSampleGenerator")
    repo = PVFaultRepository(DBAdapter(DBConfig()))
    rows = repo.query_training_samples()
    if not rows:
        raise RuntimeError("training_samples 为空")

    # 武当湖 04# 单日
    target = None
    for r in rows:
        if "武当湖" in str(r.site_id) and "04#" in str(r.device_id) and str(r.branch_id) == "1":
            target = r
            break
    if target is None:
        target = rows[0]

    day = target.time.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day.replace(hour=23, minute=55, second=0)
    records = []
    for r in rows:
        if (
            str(r.site_id) == str(target.site_id)
            and str(r.device_id) == str(target.device_id)
            and str(r.branch_id) == str(target.branch_id)
            and day <= r.time <= day_end
        ):
            records.append(
                {
                    "time": r.time,
                    "site_id": r.site_id,
                    "device_id": r.device_id,
                    "branch_id": r.branch_id,
                    "value": r.value,
                    "i_cal": r.i_cal,
                }
            )
    measurements = pd.DataFrame(records).sort_values("time")
    if measurements.empty:
        raise RuntimeError("未找到预测测量数据")

    gen = InferenceSampleGenerator()
    out, audit = gen.generate_inference_samples(measurements, model_abs)
    tw = out["time_window"].astype(str)
    if not tw.str.startswith("inf-").all():
        raise RuntimeError("推理样本 time_window 须 inf- 前缀")
    if not tw.str.contains("#", na=False).all():
        raise RuntimeError("推理样本 time_window 须含 #")

    report["inference_e2e"] = {
        "status": "passed",
        "device": f"{target.site_id}|{target.device_id}|{target.branch_id}",
        "measurement_rows": int(len(measurements)),
        "inference_rows": int(len(out)),
        "sample_count": audit.get("sample_count"),
        "split_mode": audit.get("split_mode"),
        "sample_ids": tw.unique().tolist()[:5],
    }
    _log(f"预测 E2E PASSED samples={audit.get('sample_count')} rows={len(out)}")


def main() -> int:
    report: dict = {"started_at": datetime.utcnow().isoformat(), "slot": "pv_fault"}
    _save_report({**report, "status": "running"})

    # K7 与重训串行：避免同时跑 4 套 CV 打满 CPU
    compare_thread = threading.Thread(target=run_path_compare, args=(report,), name="k7-compare")
    compare_thread.start()
    compare_thread.join()

    model_abs = run_full_retrain(report, n_repeats=10)
    run_inference_e2e(model_abs, report)

    report["status"] = "completed"
    report["finished_at"] = datetime.utcnow().isoformat()
    _save_report(report)
    _log(f"全部完成，报告: {REPORT_PATH.relative_to(BACKEND.parent).as_posix()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        partial = {}
        if REPORT_PATH.exists():
            try:
                partial = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        partial["status"] = "failed"
        partial["error"] = str(exc)
        partial["finished_at"] = datetime.utcnow().isoformat()
        _save_report(partial)
        _log(f"FAILED: {exc}")
        raise

# @AI_GENERATED: end
