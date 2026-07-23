"""
增强版算法模板 API 路由
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any, Callable, Set, Tuple
from pydantic import BaseModel
from datetime import datetime
import json
import os
import math
import random
import logging
import hashlib
import subprocess
# @AI_GENERATED
import sys
import time
import uuid
import threading
import traceback
# @AI_GENERATED: end
from services.llm_service import LLMService
from services.function_library_service import get_function_library_service
from services.operator_execution.router import OperatorRouter
from services.feature_recipe_service import (
    resolve_recipe_structure_patch,
    known_recipe_ids,
    list_feature_recipe_metas,
)
from services.autoresearch_persister import AutoResearchPersister
from services.autoresearch_evaluator import AutoResearchEvaluator
from services.autoresearch_optuna_sampler import AutoResearchOptunaSampler
from services.autoresearch_proposal_manager import AutoResearchProposalManager
from services.autoresearch_batch_selector import AutoResearchBatchSelector
from services.autoresearch_candidate_planner import AutoResearchCandidatePlanner
from services.autoresearch_evidence import AutoResearchEvidenceBuilder
from services.autoresearch_hypothesis_tracker import AutoResearchHypothesisTracker
from services.autoresearch_convergence_monitor import AutoResearchConvergenceMonitor
from services.autoresearch_diagnostics import AutoResearchDiagnostics
from services.autoresearch_insight_builder import AutoResearchInsightBuilder
from services.autoresearch_question_lifecycle import AutoResearchQuestionLifecycle
from services.autoresearch_glm_question_generator import AutoResearchGLMQuestionGenerator
from services.autoresearch_memory_store import AutoResearchMemoryStore
from services.autoresearch_multifidelity_scheduler import AutoResearchMultiFidelityScheduler
from services.autoresearch_auto_apply_policy import AutoResearchAutoApplyPolicy
from services.autoresearch_self_heal import AutoResearchSelfHeal
from services.autoresearch_research_action import ProfileSignal, ResearchAction
from services.autoresearch_v6_services import AnalystService, ResearchActionPlanner, PatchCompiler
from services import autoresearch_paths as arp
from services import autoresearch_job_queue as _jq

router = APIRouter(prefix="/api/workflows/enhanced", tags=["enhanced-workflows"])
logger = logging.getLogger(__name__)

# 数据存储路径
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'workflows_enhanced')
os.makedirs(DATA_DIR, exist_ok=True)

# @AI_GENERATED
# Ensure backend dir is on sys.path for operator_execution imports
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_OPERATOR_BACKENDS_DIR = os.path.join(_BACKEND_DIR, "services", "operator_backends")
_BACKTEST_ARTIFACTS_ROOT = os.path.join(DATA_DIR, "_backtest_artifacts")
_DATASET_REGISTRY_PATH = arp.as_str(arp.dataset_registry_path())
_LEGACY_DATASET_REGISTRY_PATH = arp.as_str(arp.legacy_dataset_registry_path())
_AUTORESEARCH_RUNS_DIR = arp.as_str(arp.runs_dir())
os.makedirs(_BACKTEST_ARTIFACTS_ROOT, exist_ok=True)
os.makedirs(_AUTORESEARCH_RUNS_DIR, exist_ok=True)

# In-memory execution state store (execution_id -> state dict)
_execution_store: Dict[str, Dict[str, Any]] = {}
# Running backtest cancellation signals (workflow_id -> cancel_event)
_backtest_cancel_events: Dict[str, threading.Event] = {}
_backtest_cancel_lock = threading.Lock()
_backtest_async_cancel_events: Dict[str, threading.Event] = {}
# Baseline vs challenger multi-window compare (async jobs)
_comparison_store: Dict[str, Dict[str, Any]] = {}
_comparison_cancel_events: Dict[str, threading.Event] = {}
_auto_research_store: Dict[str, Dict[str, Any]] = {}
_auto_research_cancel_events: Dict[str, threading.Event] = {}
_auto_research_proposals_store: Dict[str, Dict[str, Any]] = {}
_auto_research_persister = AutoResearchPersister()
_auto_research_evaluator = AutoResearchEvaluator()
_auto_research_optuna_sampler = AutoResearchOptunaSampler()
_auto_research_proposal_manager = AutoResearchProposalManager()
_auto_research_batch_selector = AutoResearchBatchSelector()
_auto_research_candidate_planner = AutoResearchCandidatePlanner()
_auto_research_evidence_builder = AutoResearchEvidenceBuilder()
_auto_research_hypothesis_tracker = AutoResearchHypothesisTracker()
_auto_research_convergence_monitor = AutoResearchConvergenceMonitor()
_auto_research_diagnostics = AutoResearchDiagnostics()
_auto_research_insight_builder = AutoResearchInsightBuilder()
_auto_research_question_lifecycle = AutoResearchQuestionLifecycle()
_auto_research_glm_question_generator = AutoResearchGLMQuestionGenerator()
_auto_research_auto_apply_policy = AutoResearchAutoApplyPolicy()
_auto_research_self_heal = AutoResearchSelfHeal()
_auto_research_v6_analyst = AnalystService()
_auto_research_v6_planner = ResearchActionPlanner()
_auto_research_v6_patch_compiler = PatchCompiler()
_CANDIDATE_POOL_JSON = arp.as_str(arp.candidate_pool_path())
_LEGACY_CANDIDATE_POOL_JSON = arp.as_str(arp.legacy_candidate_pool_path())
_AUTO_RESEARCH_MEMORY_JSON = arp.as_str(arp.memory_cases_path())
# 任务 28：run insight 存储路径
_RUN_INSIGHTS_DIR = arp.as_str(arp.insights_dir())
_RUN_INSIGHTS_INDEX_JSON = arp.as_str(arp.insight_index_path())
_LEGACY_RUN_INSIGHTS_DIR = arp.as_str(arp.legacy_insights_dir())
_LEGACY_RUN_INSIGHTS_INDEX_JSON = arp.as_str(arp.legacy_insight_index_path())
_PROMOTIONS_LOG_JSON = arp.as_str(arp.promotions_log_path())
_LEGACY_PROMOTIONS_LOG_JSON = arp.as_str(arp.legacy_promotions_log_path())
_PRODUCTION_REGISTRY_JSON = arp.as_str(arp.production_registry_path())
_LEGACY_PRODUCTION_REGISTRY_JSON = arp.as_str(arp.legacy_production_registry_path())
_VERIFICATION_QUEUE_JSON = os.path.join(os.path.dirname(_CANDIDATE_POOL_JSON), "candidate_verification_queue.json")
_cached_operator_router: Optional[OperatorRouter] = None
_AUTO_RESEARCH_FILE_LOCK = threading.RLock()
_auto_research_memory_store = AutoResearchMemoryStore(
    _AUTO_RESEARCH_MEMORY_JSON,
    lock=_AUTO_RESEARCH_FILE_LOCK,
    legacy_path=arp.as_str(arp.legacy_memory_cases_path()),
)
_auto_research_multifidelity_scheduler = AutoResearchMultiFidelityScheduler()
_verification_active_job_id: Optional[str] = None
_AUTORESEARCH_BACKTEST_ACTIVE_LIMIT = max(
    1,
    int(os.getenv("AUTORESEARCH_BACKTEST_ACTIVE_LIMIT", "4") or 4),
)
_AUTORESEARCH_BACKTEST_POOL = ThreadPoolExecutor(
    max_workers=max(
        _AUTORESEARCH_BACKTEST_ACTIVE_LIMIT * 2,
        int(os.getenv("AUTORESEARCH_BACKTEST_MAX_WORKERS", str(max(8, _AUTORESEARCH_BACKTEST_ACTIVE_LIMIT * 3))) or max(8, _AUTORESEARCH_BACKTEST_ACTIVE_LIMIT * 3)),
    ),
    thread_name_prefix="autoresearch-backtest",
)
# 复验池独立线程池：与 AutoResearch 主循环资源分区，避免互相抢占
_VERIFICATION_BACKTEST_WORKERS = max(1, int(os.getenv("VERIFICATION_BACKTEST_WORKERS", "1") or 1))
_VERIFICATION_MIN_AVAILABLE_MEM_MB = max(
    0,
    int(os.getenv("VERIFICATION_MIN_AVAILABLE_MEM_MB", "1024") or 1024),
)
_VERIFICATION_BACKTEST_POOL = ThreadPoolExecutor(
    max_workers=_VERIFICATION_BACKTEST_WORKERS,
    thread_name_prefix="verification-backtest",
)
# 异步信号量：在 async 层面限流，防止多个 AutoResearch run 同时存在时内存耗尽。
# 单个 run 内的并发由 per-iteration _sem 控制（默认=batch_size，即全并发）。
# 每个 event loop 需要自己的 asyncio.Semaphore 实例（不能跨 loop 共享），
# 所以用 dict 按 loop id 缓存。
_AUTORESEARCH_ASYNC_SEMAPHORES: Dict[int, asyncio.Semaphore] = {}
_AUTORESEARCH_ASYNC_SEM_LOCK = threading.Lock()
# @AI_GENERATED: end


def _get_async_backtest_semaphore() -> asyncio.Semaphore:
    """获取当前 event loop 对应的 asyncio.Semaphore（每个 loop 一个实例）。"""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    if loop_id not in _AUTORESEARCH_ASYNC_SEMAPHORES:
        with _AUTORESEARCH_ASYNC_SEM_LOCK:
            if loop_id not in _AUTORESEARCH_ASYNC_SEMAPHORES:
                _AUTORESEARCH_ASYNC_SEMAPHORES[loop_id] = asyncio.Semaphore(_AUTORESEARCH_BACKTEST_ACTIVE_LIMIT)
    return _AUTORESEARCH_ASYNC_SEMAPHORES[loop_id]


async def _run_limited_backtest(fn: Callable[..., Any], *args: Any) -> Any:
    """在 async 层面限流后再提交到线程池执行，防止线程池饥饿死锁。"""
    sem = _get_async_backtest_semaphore()
    async with sem:
        loop = asyncio.get_running_loop()
        # 复验池使用独立线程池，通过 loop 上的标记区分
        pool = getattr(loop, "_verification_pool", None) or _AUTORESEARCH_BACKTEST_POOL
        return await loop.run_in_executor(pool, fn, *args)


def _read_available_memory_mb() -> Optional[int]:
    """Best-effort available-memory probe for verification start gating."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        parts = line.split()
                        return int(int(parts[1]) / 1024)
        if sys.platform == "darwin":
            output = subprocess.check_output(["vm_stat"], text=True, timeout=2)
            page_size = 16384
            available_pages = 0
            first = output.splitlines()[0] if output else ""
            if "page size of" in first:
                page_size = int(first.split("page size of", 1)[1].split("bytes", 1)[0].strip())
            for line in output.splitlines():
                name, _, raw_value = line.partition(":")
                if name.strip() in {"Pages free", "Pages speculative", "Pages purgeable"}:
                    available_pages += int(raw_value.strip().rstrip("."))
            return int((available_pages * page_size) / (1024 * 1024))
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        return int((page_size * available_pages) / (1024 * 1024))
    except Exception as exc:
        logger.debug("verification memory probe unavailable: %s", exc)
        return None


def _verification_resource_block(force: bool = False) -> Optional[Dict[str, Any]]:
    if force or _VERIFICATION_MIN_AVAILABLE_MEM_MB <= 0:
        return None
    available_mb = _read_available_memory_mb()
    if available_mb is None:
        return None
    if available_mb < _VERIFICATION_MIN_AVAILABLE_MEM_MB:
        logger.warning(
            "verification start blocked by resource pressure: available_memory_mb=%s required_memory_mb=%s",
            available_mb,
            _VERIFICATION_MIN_AVAILABLE_MEM_MB,
        )
        return {
            "started": False,
            "reason": "resource_pressure",
            "available_memory_mb": available_mb,
            "required_memory_mb": _VERIFICATION_MIN_AVAILABLE_MEM_MB,
            "force_supported": True,
        }
    return None


def _atomic_write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _smape(y_true, y_pred) -> float:
    import numpy as np

    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    denom = np.abs(yt) + np.abs(yp)
    mask = denom > 1e-8
    if not mask.any():
        return 0.0
    return float(np.round(2.0 * np.mean(np.abs(yp[mask] - yt[mask]) / denom[mask]) * 100, 4))


def _metrics_from_y_true_pred(y_true, y_pred) -> dict:
    """流水线未写回 metrics 时，用当日 y_true/y_pred 计算 SMAPE/RMSE/MAE/Bias/P95APE（与比对打分一致）。"""
    import numpy as np
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    try:
        yt = np.asarray(y_true, dtype=float)
        yp = np.asarray(y_pred, dtype=float)
    except Exception:
        return {}
    if yt.size == 0 or yp.size == 0:
        return {}
    n = min(int(yt.size), int(yp.size))
    yt, yp = yt.reshape(-1)[:n], yp.reshape(-1)[:n]
    finite = np.isfinite(yt) & np.isfinite(yp)
    if not finite.any():
        return {}
    yt, yp = yt[finite], yp[finite]
    sm = _smape(yt, yp)
    mse = float(mean_squared_error(yt, yp))
    rmse = float(np.sqrt(mse))
    mae = float(mean_absolute_error(yt, yp))

    # 任务 13.3：新增 bias（ME，预测偏差）和 p95_ape（第95百分位绝对百分误差）
    bias = round(float(np.mean(yp - yt)), 4)  # 正值=预测偏高，负值=预测偏低

    # p95_ape：|pred - actual| / |actual| * 100，actual 为 0 时跳过该点
    nonzero = np.abs(yt) > 1e-8
    p95_ape = None
    if nonzero.any():
        ape = np.abs(yp[nonzero] - yt[nonzero]) / np.abs(yt[nonzero]) * 100.0
        p95_ape = round(float(np.percentile(ape, 95)), 4)

    result = {
        "smape": round(sm, 4),
        "rmse": round(rmse, 4),
        "mae": round(mae, 4),
        "mse": round(mse, 4),
        "bias": bias,
    }
    if p95_ape is not None:
        result["p95_ape"] = p95_ape
    return result


def _save_backtest_artifacts(daily_results: List[Dict[str, Any]], output_dir: str) -> List[str]:
    """
    Persist backtest artifact files similar to load_forecast_refactored/output/weihai_backtest.
    """
    import numpy as np
    import pandas as pd
    from matplotlib import pyplot as plt

    plt.switch_backend("Agg")
    os.makedirs(output_dir, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for item in daily_results:
        if item.get("status") != "success":
            continue
        day = str(item.get("date", ""))
        y_true = item.get("y_true") or []
        y_pred = item.get("y_pred") or []
        n = min(len(y_true), len(y_pred))
        if n <= 0:
            continue
        day_start = pd.to_datetime(day)
        for i in range(n):
            rows.append(
                {
                    "record_time": day_start + pd.Timedelta(minutes=15 * i),
                    "true": float(y_true[i]),
                    "pred": float(y_pred[i]),
                    "pred_day": day,
                }
            )

    if not rows:
        return []

    pred_df = pd.DataFrame(rows).sort_values("record_time").reset_index(drop=True)
    pred_csv = os.path.join(output_dir, "weihai_predictions.csv")
    pred_df.to_csv(pred_csv, index=False)

    daily_metrics = []
    for day, grp in pred_df.groupby("pred_day"):
        yt = grp["true"].to_numpy()
        yp = grp["pred"].to_numpy()
        mae = float(np.mean(np.abs(yt - yp)))
        rmse = float(np.sqrt(np.mean(np.square(yt - yp))))
        daily_metrics.append(
            {
                "label": day,
                "SMAPE": _smape(yt, yp),
                "MAE": round(mae, 4),
                "RMSE": round(rmse, 4),
            }
        )
    metrics_csv = os.path.join(output_dir, "weihai_daily_metrics.csv")
    pd.DataFrame(daily_metrics).to_csv(metrics_csv, index=False)

    saved = [pred_csv, metrics_csv]

    # 1) forecast_vs_true
    fig, ax = plt.subplots(figsize=(18, 6))
    ax.plot(pred_df["record_time"], pred_df["true"], lw=1.2, label="True")
    ax.plot(pred_df["record_time"], pred_df["pred"], lw=1.0, label="Pred")
    ax.set_title("Backtest Forecast vs True")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right")
    p1 = os.path.join(output_dir, "forecast_vs_true.png")
    fig.tight_layout()
    fig.savefig(p1, dpi=140)
    plt.close(fig)
    saved.append(p1)

    # 2) daily_details
    days = sorted(pred_df["pred_day"].unique())
    n = len(days)
    cols = 3
    rows_n = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows_n, cols, figsize=(6 * cols, 3.6 * rows_n))
    axes_arr = axes.flatten() if hasattr(axes, "flatten") else [axes]
    for idx, d in enumerate(days):
        grp = pred_df[pred_df["pred_day"] == d]
        ax = axes_arr[idx]
        x = np.arange(len(grp))
        ax.plot(x, grp["true"].to_numpy(), lw=1.2, label="True")
        ax.plot(x, grp["pred"].to_numpy(), lw=1.0, label="Pred")
        ax.set_title(f"{d}  SMAPE={_smape(grp['true'].to_numpy(), grp['pred'].to_numpy()):.2f}%")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper right", fontsize=8)
    for idx in range(len(days), len(axes_arr)):
        axes_arr[idx].set_visible(False)
    p2 = os.path.join(output_dir, "daily_details.png")
    fig.tight_layout()
    fig.savefig(p2, dpi=140)
    plt.close(fig)
    saved.append(p2)

    # 3) daily_smape_bar
    mdf = pd.DataFrame(daily_metrics)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.bar(mdf["label"], mdf["SMAPE"], alpha=0.85)
    ax.set_ylabel("SMAPE (%)")
    ax.set_title("Daily SMAPE Distribution")
    ax.grid(True, alpha=0.25, axis="y")
    ax.tick_params(axis="x", rotation=30)
    p3 = os.path.join(output_dir, "daily_smape_bar.png")
    fig.tight_layout()
    fig.savefig(p3, dpi=140)
    plt.close(fig)
    saved.append(p3)

    # 4) scatter
    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    ax.scatter(pred_df["true"], pred_df["pred"], s=8, alpha=0.35)
    lo = float(min(pred_df["true"].min(), pred_df["pred"].min()) * 0.95)
    hi = float(max(pred_df["true"].max(), pred_df["pred"].max()) * 1.05)
    ax.plot([lo, hi], [lo, hi], "k--", lw=1)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("True")
    ax.set_ylabel("Pred")
    ax.set_title("True vs Predicted")
    ax.grid(True, alpha=0.25)
    p4 = os.path.join(output_dir, "scatter.png")
    fig.tight_layout()
    fig.savefig(p4, dpi=140)
    plt.close(fig)
    saved.append(p4)

    return saved


def _safe_subdir(raw: Optional[str]) -> str:
    if not raw:
        return "default"
    v = str(raw).replace("\\", "/").strip().strip("/")
    if not v:
        return "default"
    parts = [p for p in v.split("/") if p not in ("", ".", "..")]
    return "/".join(parts) or "default"


def _sanitize_json_floats(obj: Any) -> Any:
    """
    Convert NaN/Inf values to None recursively so JSONResponse can serialize safely.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_json_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json_floats(v) for v in obj]
    if isinstance(obj, tuple):
        return [_sanitize_json_floats(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    # numpy numeric scalars (e.g., np.float32/64) are converted here
    if hasattr(obj, "item"):
        try:
            v = obj.item()
            if isinstance(v, float):
                return v if math.isfinite(v) else None
            return v
        except Exception:
            return obj
    return obj


def _canonical_json_key(obj: Any) -> str:
    """
    Build a stable JSON key for de-duplication. NaN/Inf and numpy scalars are
    normalized first so semantically identical overrides do not split buckets.
    """
    normalized = _sanitize_json_floats(obj)
    try:
        return json.dumps(normalized, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return json.dumps(str(normalized), ensure_ascii=False)


def _error_response(message: str, code: str = "bad_request") -> Dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}}


def _load_json_file(path: Optional[str]) -> Optional[Any]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_json_with_fallback(primary_path: str, legacy_path: Optional[str], default: Any) -> Any:
    data = _load_json_file(primary_path)
    if data is not None:
        return data
    data = _load_json_file(legacy_path)
    return data if data is not None else default


def _load_dataset_registry() -> Dict[str, Any]:
    data = _load_json_with_fallback(_DATASET_REGISTRY_PATH, _LEGACY_DATASET_REGISTRY_PATH, {})
    return data if isinstance(data, dict) else {}


def _save_dataset_registry(registry: Dict[str, Any]) -> None:
    _atomic_write_json(_DATASET_REGISTRY_PATH, registry)


def _load_autoresearch_run_artifacts(run_id: str) -> Dict[str, Any]:
    state = _auto_research_store.get(run_id)
    if isinstance(state, dict):
        return state
    state = _auto_research_persister.load_snapshot(run_id)
    return state if isinstance(state, dict) else {}


def _persist_autoresearch_run_artifacts(run_id: str, state: Dict[str, Any]) -> None:
    if not isinstance(state, dict):
        return
    snapshot = dict(_auto_research_store.get(run_id) or _auto_research_persister.load_snapshot(run_id) or {})
    snapshot.update({
        "run_id": run_id,
        "updated_at": datetime.utcnow().isoformat(),
        "research_questions": state.get("research_questions") or [],
        "periodic_reflections": state.get("periodic_reflections") or [],
        "dataset_profile": state.get("dataset_profile") or None,
        "dataset_profiles": state.get("dataset_profiles") or [],
        "tri_dataset_diagnosis": state.get("tri_dataset_diagnosis") or None,
        "experiment_quality": state.get("experiment_quality") or None,
        "iteration_plot_data": state.get("iteration_plot_data") or [],
        "current_research_focus": state.get("current_research_focus") or None,
        "agent_trace": state.get("agent_traces") or state.get("agent_trace") or [],
        "agent_traces": state.get("agent_traces") or state.get("agent_trace") or [],
    })
    _auto_research_persister.save_snapshot(run_id, snapshot)


@router.get("/knowledge/search", summary="AutoResearch 知识检索")
async def search_autoresearch_knowledge(
    scenario_condition_hash: Optional[str] = None,
    layer: Optional[str] = None,
    min_confidence: float = 0.0,
    knowledge_type: Optional[str] = None,
    target_param: Optional[str] = None,
):
    try:
        from services.knowledge_layer import KnowledgeLayer

        rows = KnowledgeLayer().search(
            scenario_condition_hash=scenario_condition_hash,
            layer=layer,
            knowledge_type=knowledge_type,
            target_param=target_param,
            min_confidence=float(min_confidence),
        )
        return {"success": True, "data": rows}
    except Exception as exc:
        return _error_response(str(exc), "knowledge_search_failed")


@router.get("/datasets/available", summary="列出所有可用数据集文件")
async def list_available_datasets():
    """扫描 datasets/ 目录和 uploads/ 目录，返回所有可用的数据文件"""
    import pandas as pd

    datasets_dir = os.path.join(_BACKEND_DIR, "datasets")
    uploads_dir = os.path.join(_BACKEND_DIR, "data", "uploads")
    results = []

    # 扫描 datasets/ 目录
    if os.path.isdir(datasets_dir):
        for fname in sorted(os.listdir(datasets_dir)):
            fpath = os.path.join(datasets_dir, fname)
            if not os.path.isfile(fpath):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in (".csv", ".xlsx", ".xls", ".tsv"):
                continue
            info: Dict[str, Any] = {
                "file_name": fname,
                "file_path": f"datasets/{fname}",
                "source": "datasets",
                "size_bytes": os.path.getsize(fpath),
                "extension": ext,
            }
            # 快速读取行数和列名
            try:
                if ext == ".csv":
                    df = pd.read_csv(fpath, nrows=5)
                elif ext == ".tsv":
                    df = pd.read_csv(fpath, sep="\t", nrows=5)
                else:
                    df = pd.read_excel(fpath, nrows=5)
                info["columns"] = list(df.columns)
                info["row_count_estimate"] = sum(1 for _ in open(fpath)) - 1 if ext in (".csv", ".tsv") else None
            except Exception:
                info["columns"] = []
                info["row_count_estimate"] = None
            results.append(info)

    # 扫描 uploads/ 目录（只看有 .meta.json 的）
    if os.path.isdir(uploads_dir):
        for fname in sorted(os.listdir(uploads_dir)):
            if not fname.endswith(".meta.json"):
                continue
            try:
                with open(os.path.join(uploads_dir, fname), "r", encoding="utf-8") as f:
                    meta = json.load(f)
                fpath = meta.get("save_path", "")
                if not os.path.isfile(fpath):
                    continue
                results.append({
                    "file_name": meta.get("original_filename", fname),
                    "file_path": fpath,
                    "source": "uploads",
                    "size_bytes": meta.get("file_size", 0),
                    "extension": meta.get("extension", ""),
                    "upload_time": meta.get("upload_time"),
                    "file_id": meta.get("file_id"),
                })
            except Exception:
                continue

    # 标记 registry 中已注册的
    registry = _load_dataset_registry()
    registered_paths = {v.get("file_path") for v in registry.values()}
    for item in results:
        item["registered"] = item["file_path"] in registered_paths

    return {"success": True, "data": results}


@router.get("/datasets/current-for-workflow/{workflow_id}", summary="查看 workflow 当前使用的数据集")
async def get_current_dataset_for_workflow(workflow_id: str):
    """读取指定 workflow 的 load_csv 节点，返回当前 file_path"""
    wf_path = get_workflow_path(workflow_id)
    if not os.path.exists(wf_path):
        return _error_response(f"workflow not found: {workflow_id}", "not_found")
    with open(wf_path, "r", encoding="utf-8") as f:
        wf = json.load(f)
    nodes = wf.get("nodes", [])
    csv_nodes = []
    for n in nodes:
        data = n.get("data", {})
        config = data.get("config", {})
        if config.get("functionId") == "load_csv":
            csv_nodes.append({
                "node_id": n.get("id"),
                "label": data.get("label", ""),
                "file_path": config.get("file_path", ""),
                "timestamp_column": config.get("timestamp_column", ""),
                "parent_id": config.get("parent_id", ""),
                "child_id": config.get("child_id", ""),
            })
    return {"success": True, "data": csv_nodes}


@router.post("/datasets/switch", summary="切换 workflow 使用的数据集")
async def switch_workflow_dataset(payload: Dict[str, Any]):
    """修改指定 workflow 的 load_csv 节点的 file_path"""
    workflow_id = payload.get("workflow_id")
    new_file_path = payload.get("file_path")
    node_id = payload.get("node_id")  # 可选，指定哪个 load_csv 节点

    if not workflow_id or not new_file_path:
        return _error_response("workflow_id and file_path are required")

    # 验证文件存在
    abs_path = os.path.join(_BACKEND_DIR, new_file_path) if not os.path.isabs(new_file_path) else new_file_path
    if not os.path.isfile(abs_path):
        return _error_response(f"file not found: {new_file_path}", "file_not_found")

    wf_path = get_workflow_path(workflow_id)
    if not os.path.exists(wf_path):
        return _error_response(f"workflow not found: {workflow_id}", "not_found")

    with open(wf_path, "r", encoding="utf-8") as f:
        wf = json.load(f)

    updated_nodes = []
    nodes = wf.get("nodes", [])
    for n in nodes:
        data = n.get("data", {})
        config = data.get("config", {})
        if config.get("functionId") == "load_csv":
            if node_id and n.get("id") != node_id:
                continue
            config["file_path"] = new_file_path
            updated_nodes.append(n.get("id"))

    if not updated_nodes:
        return _error_response("no load_csv node found to update", "no_target_node")

    # 保存 workflow
    with open(wf_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    return {"success": True, "updated_nodes": updated_nodes, "new_file_path": new_file_path}


@router.get("/datasets/{dataset_id_or_path}/preview", summary="预览数据集前N行")
async def preview_dataset(dataset_id_or_path: str, rows: int = 20):
    """预览数据集内容"""
    import pandas as pd

    # 先从 registry 查
    registry = _load_dataset_registry()
    item = registry.get(dataset_id_or_path)
    if item:
        file_path = item.get("file_path", "")
    else:
        # 当作路径处理
        file_path = dataset_id_or_path.replace("__", "/")

    abs_path = os.path.join(_BACKEND_DIR, file_path) if not os.path.isabs(file_path) else file_path
    if not os.path.isfile(abs_path):
        return _error_response(f"file not found: {file_path}", "file_not_found")

    try:
        ext = os.path.splitext(abs_path)[1].lower()
        if ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            df = pd.read_csv(abs_path, sep=sep, nrows=rows)
        else:
            df = pd.read_excel(abs_path, nrows=rows)

        # 基本统计
        full_df = pd.read_csv(abs_path, sep="," if ext == ".csv" else "\t") if ext in (".csv", ".tsv") else pd.read_excel(abs_path)
        total_rows = len(full_df)
        date_range = None
        # 尝试找时间列
        for col in full_df.columns:
            if any(kw in col.lower() for kw in ("time", "date", "timestamp", "时间")):
                try:
                    ts = pd.to_datetime(full_df[col], errors="coerce").dropna()
                    if len(ts) > 0:
                        date_range = {"start": str(ts.min()), "end": str(ts.max())}
                except Exception:
                    pass
                break

        return {
            "success": True,
            "data": {
                "columns": list(df.columns),
                "rows": df.fillna("").to_dict(orient="records"),
                "total_rows": total_rows,
                "date_range": date_range,
                "file_path": file_path,
            },
        }
    except Exception as exc:
        return _error_response(f"preview failed: {exc}", "preview_failed")


@router.post("/datasets/register", summary="注册 AutoResearch 数据集")
async def register_autoresearch_dataset(payload: Dict[str, Any]):
    file_path = payload.get("file_path") or payload.get("upload_id")
    if not file_path:
        return _error_response("file_path or upload_id is required")
    dataset_id = payload.get("dataset_id") or f"dataset-{uuid.uuid4().hex[:12]}"
    registry = _load_dataset_registry()
    registry[dataset_id] = {
        "dataset_id": dataset_id,
        "file_path": file_path,
        "name": payload.get("name") or os.path.basename(str(file_path)),
        "registered_at": datetime.utcnow().isoformat(),
    }
    _save_dataset_registry(registry)
    return {"success": True, "data": registry[dataset_id]}


@router.get("/datasets", summary="AutoResearch 数据集列表")
async def list_autoresearch_datasets():
    return {"success": True, "data": list(_load_dataset_registry().values())}


@router.get("/datasets/{dataset_id}/profile", summary="AutoResearch 数据集画像")
async def get_autoresearch_dataset_profile(dataset_id: str):
    registry = _load_dataset_registry()
    item = registry.get(dataset_id)
    if not item:
        return _error_response(f"dataset not found: {dataset_id}", "dataset_not_found")
    try:
        import pandas as pd
        from services.dataset_profiler import DatasetProfiler

        df = pd.read_csv(item["file_path"])
        profile = DatasetProfiler().compute_train_profile(df)
        return {"success": True, "data": profile.to_dict()}
    except Exception as exc:
        return _error_response(f"failed to parse dataset: {exc}", "dataset_profile_failed")


@router.get("/auto-research/{run_id}/research-questions", summary="AutoResearch 研究问题查询")
async def get_autoresearch_research_questions(run_id: str):
    data = _load_autoresearch_run_artifacts(run_id)
    return {"success": True, "data": data.get("research_questions", [])}


@router.get("/auto-research/{run_id}/reflections", summary="AutoResearch 反思记录查询")
async def get_autoresearch_reflections(run_id: str):
    data = _load_autoresearch_run_artifacts(run_id)
    return {"success": True, "data": data.get("periodic_reflections", [])}


# 数据模型
class NodePort(BaseModel):
    id: str
    name: str
    type: str  # 'input' or 'output'
    dataType: str
    required: Optional[bool] = False
    description: Optional[str] = None


class NodeConfig(BaseModel):
    functionId: Optional[str] = None
    operation: Optional[str] = None
    chartType: Optional[str] = None
    # 允许其他任意字段
    class Config:
        extra = "allow"


class EnhancedNodeData(BaseModel):
    label: str
    type: str  # 'function', 'visualization', 'control', 'llm'
    icon: Optional[str] = None
    inputs: List[NodePort]
    outputs: List[NodePort]
    config: NodeConfig
    status: Optional[str] = 'idle'
    error: Optional[str] = None
    description: Optional[str] = None


class EnhancedWorkflowNode(BaseModel):
    id: str
    type: str = 'enhanced'
    position: Dict[str, float]
    data: EnhancedNodeData


class EnhancedEdgeData(BaseModel):
    sourcePort: Optional[str] = None
    targetPort: Optional[str] = None
    dataType: Optional[str] = None


class EnhancedWorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None
    type: Optional[str] = 'smoothstep'
    data: Optional[EnhancedEdgeData] = None


# @AI_GENERATED
class EnhancedWorkflow(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    nodes: List[EnhancedWorkflowNode]
    edges: List[EnhancedWorkflowEdge]
    metadata: Optional[Dict[str, Any]] = None
    scenario_id: Optional[str] = None
    source_template_id: Optional[str] = None  # 创建来源模板 ID（"新建"时记录溯源，空白创建时为 None）
    version: Optional[int] = None
    version_group_id: Optional[str] = None
    parent_version_id: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
# @AI_GENERATED: end


class WorkflowSummary(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    scenario_id: Optional[str] = None
    version: Optional[int] = None
    version_group_id: Optional[str] = None
    nodeCount: int = 0
    edgeCount: int = 0
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class WorkflowExecutionResult(BaseModel):
    success: bool
    nodeResults: Dict[str, Any]
    error: Optional[str] = None
    executionTime: float
    # @AI_GENERATED
    logs: Optional[List[Dict[str, Any]]] = None
    metrics: Optional[Dict[str, Any]] = None
    model_id: Optional[str] = None
    nodeDurations: Optional[Dict[str, float]] = None
    ranked_candidates: Optional[List[Dict[str, Any]]] = None
    best_recommendation: Optional[Dict[str, Any]] = None
    mode: Optional[str] = None
    fault_predictions: Optional[List[Dict[str, Any]]] = None
    # @AI_GENERATED: end


class WorkflowValidationResult(BaseModel):
    valid: bool
    errors: List[str]
    warnings: List[str]


# 辅助函数
def get_workflow_path(workflow_id: str) -> str:
    """获取算法模板文件路径"""
    return os.path.join(DATA_DIR, f"{workflow_id}.json")


def generate_workflow_id() -> str:
    """生成算法模板ID"""
    return f"workflow-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


# @AI_GENERATED
def _new_workflow_id() -> str:
    """生成全新的 workflow_id（'wf-' 前缀 + 12 位十六进制）。

    用于 spec algorithm-deployment-refactor 任务 7.1/7.2 中"统一新建"路径：
    - `POST /`（保存新工作流）
    - `POST /create-from-template`（从模板创建）
    保证与已有 `workflow-<timestamp>`/自定义 slug 命名的模板不冲突。
    """
    return f"wf-{uuid.uuid4().hex[:12]}"


def _new_version_group_id() -> str:
    """生成全新的 version_group_id（'grp-' 前缀 + 12 位十六进制）。

    每次"新建"（无论从模板还是空白）都要拿到独立的 version_group_id，
    与源模板/其他工作流的版本组完全隔离（Property 8）。
    """
    return f"grp-{uuid.uuid4().hex[:12]}"


def _ensure_unique_workflow_id(max_retries: int = 3) -> str:
    """生成一个尚未在持久化存储中出现的 workflow_id。

    - 依赖 `get_workflow_path(id)` 指向的 JSON 文件是否存在作为冲突判据；
    - UUID 碰撞概率极低，但保留最多 `max_retries` 次重试以满足 design.md
      "保存时 ID 冲突 → 重新生成 UUID 重试一次" 的错误处理约定；
    - 极端情况下仍冲突时返回 500，避免死循环。
    """
    for _ in range(max(1, max_retries + 1)):
        candidate = _new_workflow_id()
        if not os.path.exists(get_workflow_path(candidate)):
            return candidate
    raise HTTPException(status_code=500, detail="生成工作流 ID 失败：多次重试仍冲突")
# @AI_GENERATED: end


def load_workflow_from_file(workflow_id: str) -> Optional[EnhancedWorkflow]:
    """从文件加载算法模板"""
    path = get_workflow_path(workflow_id)
    if not os.path.exists(path):
        return None
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return EnhancedWorkflow(**data)
    except Exception as e:
        print(f"Error loading workflow {workflow_id}: {e}")
        return None


def save_workflow_to_file(workflow: EnhancedWorkflow) -> bool:
    """保存算法模板到文件"""
    try:
        path = get_workflow_path(workflow.id)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(workflow.dict(), f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving workflow {workflow.id}: {e}")
        return False


def list_all_workflows() -> List[EnhancedWorkflow]:
    """列出所有算法模板"""
    workflows = []
    
    if not os.path.exists(DATA_DIR):
        return workflows
    
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            workflow_id = filename[:-5]  # 移除 .json 后缀
            workflow = load_workflow_from_file(workflow_id)
            if workflow:
                workflows.append(workflow)
    
    # 按更新时间倒序排序
    workflows.sort(key=lambda w: w.updatedAt or w.createdAt or '', reverse=True)
    return workflows


def list_all_workflow_summaries() -> List[WorkflowSummary]:
    """列出所有算法模板摘要（不加载完整节点结构，性能更好）"""
    summaries: List[WorkflowSummary] = []
    if not os.path.exists(DATA_DIR):
        return summaries

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith('.json'):
            continue

        path = os.path.join(DATA_DIR, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue

        workflow_id = str(data.get('id') or filename[:-5])
        nodes = data.get('nodes') or []
        edges = data.get('edges') or []
        summaries.append(
            WorkflowSummary(
                id=workflow_id,
                name=data.get('name') or workflow_id,
                description=data.get('description'),
                scenario_id=data.get('scenario_id'),
                version=data.get('version'),
                version_group_id=data.get('version_group_id'),
                nodeCount=len(nodes) if isinstance(nodes, list) else 0,
                edgeCount=len(edges) if isinstance(edges, list) else 0,
                createdAt=data.get('createdAt'),
                updatedAt=data.get('updatedAt'),
            )
        )

    summaries.sort(key=lambda w: w.updatedAt or w.createdAt or '', reverse=True)
    return summaries


# API 端点
@router.post("", response_model=EnhancedWorkflow, summary="保存算法模板")
async def save_workflow(workflow_data: dict):
    """
    保存新的算法模板
    
    Args:
        workflow_data: 算法模板数据
        
    Returns:
        EnhancedWorkflow: 保存后的算法模板（包含ID和时间戳）
    """
    try:
        print(f"\n{'='*60}")
        print("收到保存算法模板请求")
        print(f"{'='*60}")
        print(f"算法模板名称: {workflow_data.get('name', 'N/A')}")
        print(f"节点数量: {len(workflow_data.get('nodes', []))}")
        print(f"连接线数量: {len(workflow_data.get('edges', []))}")
        print(f"完整数据: {json.dumps(workflow_data, indent=2, ensure_ascii=False)}")
        
        # @AI_GENERATED
        # spec algorithm-deployment-refactor 任务 7.1：统一新建行为
        # 不论从模板 / 空白画布进入，只要走 POST /，都生成独立的 workflow_id +
        # version_group_id，version=1，parent_version_id=None；source_template_id
        # 由前端可选传入（空白创建时应为空）。
        workflow_id = _ensure_unique_workflow_id()
        now = datetime.now().isoformat()

        workflow_data['id'] = workflow_id
        workflow_data['createdAt'] = now
        workflow_data['updatedAt'] = now
        workflow_data['version'] = 1
        workflow_data['version_group_id'] = _new_version_group_id()
        workflow_data['parent_version_id'] = None
        # source_template_id 允许来自请求（可空），不承袭模板的 version_group_id
        workflow_data['source_template_id'] = workflow_data.get('source_template_id') or None
        # @AI_GENERATED: end

        print(f"\n开始验证数据...")
        workflow = EnhancedWorkflow(**workflow_data)
        print(f"✅ 数据验证通过")
        
        print(f"\n开始保存到文件...")
        if save_workflow_to_file(workflow):
            print(f"✅ 文件保存成功: {workflow_id}")
            return workflow
        else:
            print(f"❌ 文件保存失败")
            raise HTTPException(status_code=500, detail="保存算法模板失败")
    
    except Exception as e:
        print(f"\n❌ 保存算法模板失败:")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        import traceback
        print(f"错误堆栈:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存算法模板失败: {str(e)}")


@router.get("", response_model=List[EnhancedWorkflow], summary="列出所有算法模板")
async def list_workflows():
    """
    获取所有算法模板列表
    
    Returns:
        List[EnhancedWorkflow]: 算法模板列表
    """
    try:
        return list_all_workflows()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取算法模板列表失败: {str(e)}")


@router.get("/summaries", response_model=List[WorkflowSummary], summary="列出算法模板摘要")
async def list_workflow_summaries():
    """
    获取算法模板摘要列表（用于列表页/下拉选择，避免传输完整 nodes/edges 提升性能）
    """
    try:
        return list_all_workflow_summaries()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取算法模板摘要失败: {str(e)}")


# @AI_GENERATED
class CreateFromTemplateRequest(BaseModel):
    """POST /create-from-template 请求体。

    - template_id — 源模板 workflow_id，必填
    - name — 新工作流名称，必填，且必须与模板名称不同
    """
    template_id: str
    name: str


@router.post(
    "/create-from-template",
    response_model=EnhancedWorkflow,
    summary="从模板创建独立工作流（生成新 workflow_id + 独立版本组）",
)
async def create_workflow_from_template(request: CreateFromTemplateRequest):
    """spec algorithm-deployment-refactor 任务 7.1：从模板新建统一走这里。

    行为：
    - 深拷贝源模板的 nodes/edges/metadata/scenario_id
    - 分配新的 workflow_id + 独立 version_group_id
    - version=1, parent_version_id=None, source_template_id=<template.id>
    - 名称必须与模板不同，否则返回 400 code="name_conflict"
    - 模板不存在 → 404
    """
    template_id = (request.template_id or "").strip()
    new_name = (request.name or "").strip()

    if not template_id:
        raise HTTPException(status_code=400, detail="template_id 不能为空")
    if not new_name:
        raise HTTPException(status_code=400, detail="name 不能为空")

    template = load_workflow_from_file(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"源模板不存在: {template_id}")

    if new_name == (template.name or "").strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "name_conflict",
                "message": "请输入新的工作流名称以区分模板",
            },
        )

    try:
        template_dict = template.dict()
        now = datetime.now().isoformat()
        new_id = _ensure_unique_workflow_id()

        # 只继承业务结构（节点/连线/元信息/场景），版本谱系全部重置
        new_data = {
            "id": new_id,
            "name": new_name,
            "description": template_dict.get("description"),
            "nodes": template_dict.get("nodes") or [],
            "edges": template_dict.get("edges") or [],
            "metadata": template_dict.get("metadata"),
            "scenario_id": template_dict.get("scenario_id"),
            "source_template_id": template.id,
            "version": 1,
            "version_group_id": _new_version_group_id(),
            "parent_version_id": None,
            "createdAt": now,
            "updatedAt": now,
        }

        cloned = EnhancedWorkflow(**new_data)
        if save_workflow_to_file(cloned):
            print(
                f"✅ create-from-template 成功: template={template_id} -> new={new_id}"
                f" name={new_name!r}"
            )
            return cloned
        raise HTTPException(status_code=500, detail="从模板创建工作流失败：写文件失败")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ create-from-template 失败: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"从模板创建工作流失败: {str(e)}")
# @AI_GENERATED: end


# 固定路径必须注册在 GET /{workflow_id} 之前，否则会被当成模板 ID（404），例如：
# tuning-candidate-pool、model-operators-available、structure-profiles 等。
@router.get("/auto-research-runs", summary="查询自动实验快照列表")
async def list_auto_research_runs(limit: int = 50):
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 50
    n = max(1, min(n, 200))
    rows_by_id: Dict[str, Dict[str, Any]] = {}
    for row in _auto_research_persister.list_runs(limit=n * 2, memory_store=_auto_research_store):
        run_id = str(row.get("run_id") or "")
        if run_id:
            rows_by_id[run_id] = dict(row)

    for job in _jq.list_jobs(limit=n * 2):
        run_id = str(job.get("run_id") or "")
        if not run_id:
            continue
        row = rows_by_id.get(run_id, {"run_id": run_id})
        snapshot = _auto_research_persister.load_snapshot(run_id)
        if isinstance(snapshot, dict):
            row.update({
                "status": snapshot.get("status", row.get("status")),
                "progress": snapshot.get("progress", row.get("progress")),
                "current_iteration": snapshot.get("current_iteration", row.get("current_iteration")),
                "current_iteration_live": snapshot.get("current_iteration_live", row.get("current_iteration_live")),
                "batch_eval_status": snapshot.get("batch_eval_status", row.get("batch_eval_status")),
                "error": snapshot.get("error", row.get("error")),
                "last_failed_trial": snapshot.get("last_failed_trial", row.get("last_failed_trial")),
                "baseline_workflow_id": snapshot.get("baseline_workflow_id", row.get("baseline_workflow_id")),
                "created_at": snapshot.get("created_at", row.get("created_at")),
                "updated_at": snapshot.get("updated_at", row.get("updated_at")),
                "snapshot_source": "disk+job",
            })
        job_view = dict(job)
        job_view.pop("payload", None)
        row["job"] = job_view
        row["job_status"] = job_view.get("status")
        row["job_updated_at"] = job_view.get("heartbeat_at") or job_view.get("started_at") or job_view.get("created_at")
        if str(row.get("status") or "").lower() in ("", "pending") and row.get("job_status"):
            row["status"] = row.get("job_status")
        rows_by_id[run_id] = row

    def _row_time(row: Dict[str, Any]) -> str:
        return str(row.get("job_updated_at") or row.get("updated_at") or row.get("created_at") or "")

    rows = sorted(rows_by_id.values(), key=_row_time, reverse=True)
    compact_rows = [_compact_autoresearch_run_row(row) for row in rows[:n]]
    return _sanitize_json_floats({"total": len(rows), "runs": compact_rows})


@router.get("/auto-research-runs/{run_id}/trials", summary="查询自动实验 Trial 账本")
async def list_auto_research_trials(run_id: str, limit: int = 200):
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 200
    n = max(1, min(n, 1000))
    rows = _auto_research_persister.list_trials(run_id, limit=n)
    return _sanitize_json_floats({"run_id": run_id, "total": len(rows), "trials": rows})


@router.get("/auto-research-runs/{run_id}/decisions", summary="查询自动实验 Decision 账本")
async def list_auto_research_decisions(run_id: str, limit: int = 200):
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 200
    n = max(1, min(n, 1000))
    rows = _auto_research_persister.list_decisions(run_id, limit=n)
    return _sanitize_json_floats({"run_id": run_id, "total": len(rows), "decisions": rows})


@router.get("/auto-research-stats", summary="查询自动实验全局统计")
async def get_auto_research_stats():
    return _sanitize_json_floats(_auto_research_persister.stats())


@router.get("/production-workflow-ref", summary="查询生产/基线模板登记（增强工作流 ID）")
async def get_production_workflow_ref():
    return _sanitize_json_floats(_load_production_registry())


@router.put("/production-workflow-ref", summary="登记生产模板 workflow_id（默认槽位 default）")
async def put_production_workflow_ref(payload: dict):
    workflow_id = str(payload.get("workflow_id") or "").strip()
    if not workflow_id:
        raise HTTPException(status_code=400, detail="需要 workflow_id")
    slot = str(payload.get("slot") or "default").strip() or "default"
    note = str(payload.get("note") or "").strip() or None
    entry = _set_production_workflow_slot(slot, workflow_id, note=note, source_candidate_id=None)
    return {"success": True, "slot": slot, "entry": _sanitize_json_floats(entry)}


@router.get("/tuning-candidate-pool", summary="调优比对候选池列表")
async def list_tuning_candidate_pool():
    pool = _load_candidate_pool_list()
    run_meta_cache: Dict[str, Dict[str, Any]] = {}

    def _run_meta(run_id: str) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            return {}
        if rid in run_meta_cache:
            return run_meta_cache[rid]
        snapshot = _auto_research_persister.load_snapshot(rid) or {}
        trials = _auto_research_persister.list_trials(rid, limit=10000)
        completed_iterations = set()
        for trial in trials or []:
            try:
                n = int(trial.get("iteration_no") or trial.get("iteration") or 0)
            except Exception:
                n = 0
            if n > 0 and str(trial.get("status") or "").lower() in {"success", "failed", "error", "cancelled", "interrupted"}:
                completed_iterations.add(n)
        if not completed_iterations:
            for item in snapshot.get("iterations") or []:
                if not isinstance(item, dict):
                    continue
                try:
                    n = int(item.get("iteration_no") or item.get("iteration") or 0)
                except Exception:
                    n = 0
                if n > 0 and str(item.get("status") or "").lower() in {"success", "failed", "error", "cancelled", "interrupted"}:
                    completed_iterations.add(n)
        progress = snapshot.get("progress") if isinstance(snapshot.get("progress"), dict) else {}
        meta = {
            "source_run_completed_iterations": len(completed_iterations),
            "source_run_max_completed_iteration": max(completed_iterations) if completed_iterations else int(progress.get("iteration") or snapshot.get("current_iteration") or 0),
            "source_run_total_iterations": int(snapshot.get("max_iterations") or progress.get("total_iterations") or 0),
            "source_run_status": snapshot.get("status"),
        }
        run_meta_cache[rid] = meta
        return meta

    def _adv(item: dict) -> float:
        s = (item.get("summary") or {}) if isinstance(item.get("summary"), dict) else {}
        a = s.get("mape_improvement", s.get("score_advantage"))
        try:
            return float(a) if a is not None else -1e18
        except Exception:
            return -1e18

    enriched_pool = []
    for item in pool:
        row = dict(item or {})
        row.update(_run_meta(str(row.get("source_run_id") or "")))
        enriched_pool.append(row)
    sorted_pool = sorted(enriched_pool, key=_adv, reverse=True)
    deduped_pool: List[Dict[str, Any]] = []
    seen_signatures: Set[str] = set()
    for row in sorted_pool:
        sig = _candidate_signature_from_entry(row)
        if sig and sig in seen_signatures:
            continue
        if sig:
            seen_signatures.add(sig)
        deduped_pool.append(row)
    return {
        "candidates": _sanitize_json_floats(deduped_pool),
        "total": len(deduped_pool),
        "raw_total": len(sorted_pool),
        "deduped_count": len(sorted_pool) - len(deduped_pool),
    }


@router.get("/tuning-candidate-pool/{candidate_id}", summary="候选池单条详情")
async def get_tuning_candidate(candidate_id: str):
    pool = _load_candidate_pool_list()
    for item in pool:
        if str(item.get("id")) == candidate_id:
            return {"candidate": _sanitize_json_floats(item)}
    raise HTTPException(status_code=404, detail=f"候选不存在: {candidate_id}")


@router.get("/candidate-verification-queue", summary="候选复验池列表")
async def list_candidate_verification_queue():
    items = _load_verification_queue()
    # 对缺少 source_metrics 的历史条目，从候选池回填
    need_backfill = [row for row in items if isinstance(row, dict) and not row.get("source_metrics")]
    if need_backfill:
        pool = _load_candidate_pool_list()
        pool_by_id = {str(c.get("id") or ""): c for c in pool if isinstance(c, dict)}
        dirty = False
        for row in need_backfill:
            cid = str(row.get("candidate_id") or "")
            candidate = pool_by_id.get(cid)
            if not candidate:
                continue
            summary = candidate.get("summary") if isinstance(candidate.get("summary"), dict) else {}
            evaluation = candidate.get("evaluation") if isinstance(candidate.get("evaluation"), dict) else {}
            row["source_metrics"] = _sanitize_json_floats({
                "baseline_mape": summary.get("aggregate_baseline_score") or evaluation.get("baseline_metric"),
                "challenger_mape": summary.get("aggregate_challenger_score") or evaluation.get("challenger_metric"),
                "mape_improvement": summary.get("score_advantage") or summary.get("mape_improvement") or evaluation.get("mape_improvement"),
                "windows_total": summary.get("windows_total") or summary.get("windows_comparable"),
                "windows_challenger_better": summary.get("windows_challenger_better"),
                "source_iteration": candidate.get("source_iteration"),
                "source_run_id": candidate.get("source_run_id"),
            })
            dirty = True
        if dirty:
            _save_verification_queue(items)
    return _sanitize_json_floats({
        "items": items,
        "total": len(items),
        "active_item_id": (_verification_active_item(items) or {}).get("id"),
    })


@router.post("/candidate-verification-queue/from-candidate/{candidate_id}", summary="候选加入复验池")
async def enqueue_candidate_verification(candidate_id: str, request: Request):
    payload: dict = {}
    try:
        body = await request.json()
        if isinstance(body, dict):
            payload = body
    except Exception:
        pass
    windows = payload.get("windows") if isinstance(payload.get("windows"), list) else None
    note = str(payload.get("note") or "").strip() or None
    auto_start = bool(payload.get("auto_start"))
    aggregate_method = str(payload.get("aggregate_method") or "mean").strip().lower()
    if aggregate_method not in {"mean", "median", "trimmed_mean"}:
        raise HTTPException(status_code=400, detail="aggregate_method 仅支持 mean / median / trimmed_mean")
    try:
        score_margin = float(payload.get("score_margin", 0.0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="score_margin 必须为数字")
    try:
        min_windows_challenger_better = int(payload.get("min_windows_challenger_better", 2))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="min_windows_challenger_better 必须为整数")
    if min_windows_challenger_better < 0:
        raise HTTPException(status_code=400, detail="min_windows_challenger_better 不能为负")
    with _AUTO_RESEARCH_FILE_LOCK:
        pool = _load_candidate_pool_list()
        candidate = next((row for row in pool if str(row.get("id") or "") == candidate_id), None)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"候选不存在: {candidate_id}")
        queue = _load_verification_queue()
        signature = _candidate_signature_from_entry(candidate)
        existing = next(
            (
                row for row in queue
                if str(row.get("candidate_id") or "") == candidate_id
                or (
                    str(row.get("candidate_signature") or "") == signature
                    and str(row.get("status") or "") in {"queued", "running", "passed"}
                )
            ),
            None,
        )
        if existing:
            return {"success": True, "item": _sanitize_json_floats(existing), "deduped": True}
        item = _verification_item_for_candidate(
            candidate,
            windows=windows,
            note=note,
            aggregate_method=aggregate_method,
            score_margin=score_margin,
            min_windows_challenger_better=min_windows_challenger_better,
            auto_start=auto_start,
        )
        queue.append(item)
        candidate["verification_status"] = "queued"
        candidate["verification_item_id"] = item["id"]
        _save_verification_queue(queue)
        _save_candidate_pool_list(pool)
    start_result = _start_verification_item(item["id"]) if auto_start else None
    return {
        "success": True,
        "item": _sanitize_json_floats(item),
        "deduped": False,
        "start_result": _sanitize_json_floats(start_result) if start_result else None,
    }


@router.post("/candidate-verification-queue/start-next", summary="启动下一条复验")
async def start_next_candidate_verification(request: Request):
    payload: dict = {}
    try:
        body = await request.json()
        if isinstance(body, dict):
            payload = body
    except Exception:
        pass
    return _sanitize_json_floats(_start_verification_item(force=bool(payload.get("force"))))


@router.post("/candidate-verification-queue/{item_id}/start", summary="启动指定复验")
async def start_candidate_verification(item_id: str, request: Request):
    payload: dict = {}
    try:
        body = await request.json()
        if isinstance(body, dict):
            payload = body
    except Exception:
        pass
    # 启动前允许更新复验配置（窗口、聚合方式、胜出窗数、分差）
    config_update = {}
    if isinstance(payload.get("windows"), list) and payload["windows"]:
        config_update["windows"] = payload["windows"]
    if payload.get("aggregate_method"):
        agg = str(payload["aggregate_method"]).strip().lower()
        if agg in {"mean", "median", "trimmed_mean"}:
            config_update["aggregate_method"] = agg
    if payload.get("min_windows_challenger_better") is not None:
        try:
            config_update["min_windows_challenger_better"] = int(payload["min_windows_challenger_better"])
        except (TypeError, ValueError):
            pass
    if payload.get("score_margin") is not None:
        try:
            config_update["score_margin"] = float(payload["score_margin"])
        except (TypeError, ValueError):
            pass
    if config_update:
        with _AUTO_RESEARCH_FILE_LOCK:
            items = _load_verification_queue()
            for row in items:
                if str(row.get("id") or "") == item_id:
                    row.update(config_update)
                    row["updated_at"] = datetime.now().isoformat()
                    break
            _save_verification_queue(items)
    return _sanitize_json_floats(_start_verification_item(item_id, force=bool(payload.get("force"))))


@router.post("/candidate-verification-queue/{item_id}/cancel", summary="取消指定复验")
async def cancel_candidate_verification(item_id: str):
    with _AUTO_RESEARCH_FILE_LOCK:
        items = _load_verification_queue()
        item = next((row for row in items if str(row.get("id") or "") == item_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail=f"复验项不存在: {item_id}")
        comparison_id = str(item.get("comparison_id") or "")
        if str(item.get("status") or "") == "running" and comparison_id:
            event = _comparison_cancel_events.get(comparison_id)
            if event:
                event.set()
            item["status"] = "cancel_requested"
            item["updated_at"] = datetime.now().isoformat()
        elif str(item.get("status") or "") == "queued":
            item["status"] = "cancelled"
            item["updated_at"] = datetime.now().isoformat()
            item["failure_reason"] = "cancelled_before_start"
        _save_verification_queue(items)
    return {"success": True, "item": _sanitize_json_floats(item)}


@router.post("/tuning-candidate-pool/{candidate_id}/promote", summary="标记候选为已 promote（登记）")
async def promote_tuning_candidate(candidate_id: str, request: Request):
    payload: dict = {}
    try:
        body = await request.json()
        if isinstance(body, dict):
            payload = body
    except Exception:
        pass
    note = str(payload.get("note") or "").strip()
    set_as_production = bool(payload.get("set_as_production"))
    production_slot = str(payload.get("production_slot") or "load_forecast").strip() or "load_forecast"
    force = bool(payload.get("force"))
    enter_prelaunch = bool(payload.get("enter_prelaunch"))
    prelaunch_slot = str(payload.get("prelaunch_slot") or production_slot or "load_forecast").strip() or "load_forecast"
    with _AUTO_RESEARCH_FILE_LOCK:
        pool = _load_candidate_pool_list()
        found: Optional[Dict[str, Any]] = None
        for item in pool:
            if str(item.get("id")) == candidate_id:
                found = item
                break
        if found is None:
            raise HTTPException(status_code=404, detail=f"候选不存在: {candidate_id}")
        if str(found.get("status") or "") == "ineligible":
            raise HTTPException(
                status_code=400,
                detail="该记录未满足比对准入条件（ineligible），无法 Promote",
            )
        summ = found.get("summary") if isinstance(found.get("summary"), dict) else {}
        if summ and summ.get("eligible_for_pool") is False:
            raise HTTPException(
                status_code=400,
                detail="该记录未满足比对准入条件（eligible_for_pool=false），无法 Promote",
            )
        if not force and not _candidate_has_passed_verification(candidate_id):
            raise HTTPException(
                status_code=400,
                detail="候选尚未通过复验池多窗口复验，不能直接 Promote；如需人工强制请传 force=true",
            )
        found["status"] = "promoted"
        found["promoted_at"] = datetime.now().isoformat()
        if note:
            found["promote_note"] = note
        production_entry: Optional[Dict[str, Any]] = None
        if set_as_production:
            cw = found.get("challenger_workflow_id")
            if not cw:
                raise HTTPException(status_code=400, detail="候选缺少 challenger_workflow_id，无法登记生产模板")
            production_entry = _set_production_workflow_slot(
                production_slot,
                str(cw),
                note=note or f"promote:{candidate_id}",
                source_candidate_id=candidate_id,
            )
            found["production_slot"] = production_slot
            found["production_workflow_id"] = str(cw)
        _save_candidate_pool_list(pool)
    log_row: Dict[str, Any] = {
        "candidate_id": candidate_id,
        "promoted_at": found["promoted_at"],
        "baseline_workflow_id": found.get("baseline_workflow_id"),
        "challenger_workflow_id": found.get("challenger_workflow_id"),
        "note": note or None,
        "set_as_production": set_as_production,
        "production_slot": production_slot if set_as_production else None,
    }
    _append_promotion_log(log_row)
    # @AI_GENERATED — 精度运营：Promote 成功后注册新版本到 Version Registry
    try:
        from services.precision_ops.version_registry import VersionRegistry
        _precision_vr = VersionRegistry()
        _reg_entry = {
            "workflow_id": str(found.get("challenger_workflow_id", "")),
            "version_tag": f"promoted-{candidate_id[:12]}",
            "status": "production" if set_as_production else "shadow",
            "slot": production_slot if set_as_production else "load_forecast",
            "source_candidate_id": candidate_id,
            "baseline_mape": float(found.get("summary", {}).get("challenger_mape") or 0) or None,
        }
        if _reg_entry["workflow_id"]:
            _precision_vr.register(_reg_entry)
    except Exception as _vr_exc:
        # 精度运营注册失败不阻塞 Promote 主流程
        import logging
        logging.getLogger(__name__).warning(
            "precision_ops version registry: Promote 后注册版本失败（非阻塞）: %s", _vr_exc
        )
    # @AI_GENERATED: end
    # 精度运营：Promote set_as_production 时同步更新 ProductionRegistry（预测任务读此真源）
    if set_as_production:
        try:
            from services.precision_ops.production_registry import ProductionRegistry
            _prod_reg = ProductionRegistry()
            _prod_reg.update(
                slot=production_slot,
                workflow_id=str(found.get("challenger_workflow_id", "")),
                version_tag=f"promoted-{candidate_id[:12]}",
                event_id=f"promote-{candidate_id}",
            )
        except Exception as _pr_exc:
            import logging
            logging.getLogger(__name__).warning(
                "precision_ops ProductionRegistry: Promote 后更新失败（非阻塞）: %s", _pr_exc
            )
    # @AI_GENERATED: Promote 可选写入部署预上线池；绝不改 slots.json production_model
    prelaunch_entry: Optional[Dict[str, Any]] = None
    if enter_prelaunch:
        cw = str(found.get("challenger_workflow_id") or "").strip()
        if not cw:
            raise HTTPException(status_code=400, detail="候选缺少 challenger_workflow_id，无法入预上线")
        try:
            from api.deployment import PrelaunchEnterBody, enter_prelaunch as deployment_enter_prelaunch
            prelaunch_entry = deployment_enter_prelaunch(
                prelaunch_slot,
                PrelaunchEnterBody(
                    candidate_id=candidate_id,
                    workflow_id=cw,
                    version_tag=f"prelaunch-{candidate_id[:12]}",
                    source_run_id=str(found.get("source_run_id") or "") or None,
                    note=note or f"promote_enter_prelaunch:{candidate_id}",
                ),
            )
        except HTTPException:
            raise
        except Exception as _pl_exc:
            raise HTTPException(
                status_code=500,
                detail=f"写入部署预上线失败: {_pl_exc}",
            ) from _pl_exc
    return {
        "success": True,
        "candidate": _sanitize_json_floats(found),
        "production_entry": _sanitize_json_floats(production_entry) if production_entry else None,
        "prelaunch_entry": _sanitize_json_floats(prelaunch_entry) if prelaunch_entry else None,
        "note": (
            "set_as_production 只更新 AutoResearch/精度登记侧，不改 DeploymentSlotStore.production_model；"
            "生产身份以算法部署 slots.json 为准。"
            if set_as_production
            else None
        ),
    }


@router.delete("/tuning-candidate-pool/{candidate_id}", summary="删除候选池中的单条记录")
async def delete_tuning_candidate(candidate_id: str):
    with _AUTO_RESEARCH_FILE_LOCK:
        pool = _load_candidate_pool_list()
        new_pool = [item for item in pool if str(item.get("id")) != candidate_id]
        if len(new_pool) == len(pool):
            raise HTTPException(status_code=404, detail=f"候选不存在: {candidate_id}")
        _save_candidate_pool_list(new_pool)
    return {"success": True, "deleted_id": candidate_id, "remaining": len(new_pool)}


@router.delete("/tuning-candidate-pool", summary="清空候选池")
async def clear_tuning_candidate_pool():
    with _AUTO_RESEARCH_FILE_LOCK:
        count = len(_load_candidate_pool_list())
        _save_candidate_pool_list([])
    return {"success": True, "deleted_count": count}


@router.get("/model-operators-available", summary="可调模型算子（函数库∩运行时注册）")
async def list_model_operators_available():
    try:
        return _sanitize_json_floats(_discover_forecast_operators_payload())
    except Exception as e:
        return _sanitize_json_floats({
            "operators": [],
            "model_operator_ids": [],
            "error": str(e),
        })


@router.get("/auto-research-insights", summary="列出所有 run insight 摘要")
async def list_auto_research_insights():
    """
    任务 28.4：返回所有 insight 的摘要列表。
    """
    index = _load_insight_index()
    return _sanitize_json_floats({
        "insights": index,
        "total": len(index),
    })


@router.get("/list-search-registries", summary="列出所有可用的搜索空间注册表")
async def list_search_registries():
    """
    任务 25.4：列出 data/autoresearch_search_registries/ 下所有可用注册表。
    返回：{"registries": [{"registry_id": "load_forecast_v1", "description": "...", "layers_count": 4}]}
    注意：此路由必须在 /{workflow_id} 之前注册，避免被动态路由匹配。
    """
    try:
        from services.autoresearch_registry_service import load_registry, list_registry_ids
    except Exception as e:
        return {"registries": [], "error": str(e)}

    result = []
    for rid in list_registry_ids():
        try:
            reg = load_registry(rid)
            if reg.get("registry_id") == "__empty__":
                continue
            layers = reg.get("layers") or {}
            result.append({
                "registry_id": rid,
                "description": str(reg.get("description") or ""),
                "layers_count": len(layers),
                "layers": list(layers.keys()),
            })
        except Exception:
            continue
    return {"registries": result}


@router.get("/{workflow_id}/suggest-search-registry", summary="根据模板自动生成搜索空间注册表草稿")
async def suggest_search_registry(workflow_id: str):
    """
    任务 14.2：扫描模板节点，自动生成搜索空间注册表草稿 JSON。
    用途：前端或人工审核后保存为正式注册表。
    """
    result = _auto_generate_registry_from_template(workflow_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return _sanitize_json_floats(result)


@router.get("/structure-profiles", summary="AutoResearch 结构档案列表")
async def list_structure_profiles():
    try:
        from services.workflow_slot_catalog_service import default_profile_id, list_profile_metas

        profiles = list_profile_metas()
        did = default_profile_id()
        if not did and profiles:
            did = profiles[0].get("profile_id")
        return _sanitize_json_floats({"profiles": profiles, "default_profile_id": did})
    except Exception as e:
        return _sanitize_json_floats({"profiles": [], "default_profile_id": None, "error": str(e)})


@router.get("/structure-profile-detail/{profile_id}", summary="结构档案详情（槽位 + 解析后的可选算子）")
async def get_structure_profile_detail(profile_id: str):
    from services.workflow_slot_catalog_service import resolve_structure_profile_detail

    router = _get_operator_router_cached()
    detail = resolve_structure_profile_detail(profile_id.strip(), router.has_operator)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"未知 structure_profile_id: {profile_id}")
    return _sanitize_json_floats(detail)


@router.get("/feature-recipes", summary="特征配方目录（Phase B：AutoResearch recipe）")
async def list_feature_recipes_http():
    try:
        return _sanitize_json_floats({"recipes": list_feature_recipe_metas()})
    except Exception as e:
        return _sanitize_json_floats({"recipes": [], "error": str(e)})

@router.post("/baseline-workflow-precheck", summary="基线模板流水线预检（不创建 AutoResearch）")
async def baseline_workflow_precheck(payload: dict):
    wf_id = str(payload.get("baseline_workflow_id") or payload.get("workflow_id") or "").strip()
    if not wf_id:
        raise HTTPException(status_code=400, detail="需要 baseline_workflow_id 或 workflow_id")
    try:
        max_rows = int(payload.get("max_rows", 800))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="max_rows 必须为整数")
    max_rows = max(10, min(max_rows, 5000))

    report = _workflow_preflight_report(wf_id, max_rows=max_rows)
    if report.get("workflow_missing"):
        raise HTTPException(status_code=404, detail=str(report.get("error") or "模板不存在"))
    return _sanitize_json_floats({k: v for k, v in report.items() if k != "workflow_missing"})


@router.get("/{workflow_id}/params-summary", summary="提取模板可调参数摘要")
async def get_workflow_params_summary(workflow_id: str):
    """
    解析模板，返回两类可调参数：
    1. global_config 层（回测行为控制）
    2. 节点级关键参数（按节点 functionId 分组，只返回有意义的可调字段）
    """
    wf = load_workflow_from_file(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"模板不存在: {workflow_id}")

    meta = wf.metadata or {}
    gc = dict(meta.get("global_config") or {})

    # global_config 里有意义的可调字段白名单（附说明）
    GC_FIELDS = [
        ("use_reference_rolling_engine", "执行引擎", "bool", "true=威海参考引擎 / false=平台通用引擎"),
        ("backtest_mode", "回测模式", "str", "rolling_retrain / inference_only"),
        ("backtest_train_days", "训练天数(gc)", "int", "每日回测训练窗口"),
        ("backtest_bo_n_iter", "贝叶斯迭代次数(gc)", "int", "参考引擎生效"),
        ("backtest_use_bayesian_tuning", "贝叶斯调参(gc)", "bool", "参考引擎生效"),
        ("backtest_apply_window_filter", "窗口过滤", "bool", ""),
        ("backtest_mask_target_values", "遮蔽目标值", "bool", ""),
        ("strict_alignment_mode", "严格对齐", "bool", ""),
        ("model_type", "模型类型(gc)", "str", "xgboost/lightgbm/catboost/ridge"),
    ]
    gc_params = []
    for key, label, vtype, hint in GC_FIELDS:
        gc_params.append({
            "key": key,
            "label": label,
            "type": vtype,
            "hint": hint,
            "value": gc.get(key),  # None 表示模板未设置，将用引擎默认值
            "source": "global_config",
        })

    # 节点级可调字段白名单（按 functionId）
    NODE_FIELD_MAP = {
        "auto_tune_xgboost": [
            ("n_trials", "贝叶斯搜索轮数", "int", "越大越准越慢，默认30"),
            ("cv_folds", "交叉验证折数", "int", "默认5"),
            ("metric", "优化指标", "str", "rmse/mae/smape"),
        ],
        "xgboost_forecast": [
            ("n_estimators", "树数量", "int", ""),
            ("local_parity_bo_n_iter", "集成贝叶斯轮数", "int", "local_parity模式生效"),
            ("local_parity_use_bayesian_tuning", "集成贝叶斯调参", "bool", ""),
            ("local_parity_n_splits", "集成CV折数", "int", ""),
            ("separate_modeling", "分段建模", "str", "true/false"),
            ("prefer_unit_len", "偏好单元长度", "int", ""),
            ("sample_weight_decay", "样本权重衰减", "float", "0~1"),
        ],
        "lightgbm_forecast": [
            ("n_estimators", "树数量", "int", ""),
            ("separate_modeling", "分段建模", "str", ""),
            ("sample_weight_decay", "样本权重衰减", "float", ""),
        ],
        "catboost_forecast": [
            ("n_estimators", "树数量", "int", ""),
            ("separate_modeling", "分段建模", "str", ""),
            ("sample_weight_decay", "样本权重衰减", "float", ""),
        ],
        "ridge_forecast": [
            ("separate_modeling", "分段建模", "str", ""),
        ],
        "create_lag_features": [
            ("lag_days", "滞后天数列表", "list", "如 [1,2,3,7,14]"),
            ("lags", "步长滞后", "list", ""),
        ],
        "rolling_statistics": [
            ("window_sizes", "滚动窗口大小列表", "list", "如 [4,8,24,96]"),
            ("statistics", "统计量", "list", "mean/std/max/min"),
            ("base_shift", "基础偏移", "int", ""),
        ],
        "detect_outliers": [
            ("threshold", "异常阈值(zscore)", "float", "越大越宽松"),
            ("window_size", "检测窗口", "int", ""),
        ],
        "train_test_split_ts": [
            ("train_ratio", "训练集比例", "float", ""),
            ("val_ratio", "验证集比例", "float", ""),
        ],
        "load_csv": [
            ("file_path", "数据文件路径", "str", ""),
            ("parent_id", "父节点ID", "str", ""),
            ("child_id", "子节点ID", "str", ""),
        ],
        "row_filter": [
            ("column_filters", "行过滤条件(JSON)", "str", ""),
        ],
    }

    node_params = []
    for node in (wf.nodes or []):
        raw_nd = node.data
        if raw_nd is None:
            continue
        # node.data 是 Pydantic 对象，用 .dict() 转成普通 dict 再操作
        nd = raw_nd.dict() if hasattr(raw_nd, "dict") else (raw_nd if isinstance(raw_nd, dict) else {})
        cfg = nd.get("config") or {}
        fid = cfg.get("functionId") or ""
        if fid not in NODE_FIELD_MAP:
            continue
        fields = NODE_FIELD_MAP[fid]
        node_fields = []
        for key, label, vtype, hint in fields:
            if key in cfg:
                node_fields.append({
                    "key": key,
                    "label": label,
                    "type": vtype,
                    "hint": hint,
                    "value": cfg[key],
                    "source": f"node:{node.id}:{fid}",
                    "node_id": node.id,
                    "function_id": fid,
                    "node_label": nd.get("label") or fid,
                })
        if node_fields:
            node_params.append({
                "node_id": node.id,
                "function_id": fid,
                "node_label": nd.get("label") or fid,
                "fields": node_fields,
            })

    return {
        "workflow_id": workflow_id,
        "workflow_name": wf.name,
        "global_config_params": gc_params,
        "node_params": node_params,
    }


@router.get("/{workflow_id}", response_model=EnhancedWorkflow, summary="加载算法模板")
async def load_workflow(workflow_id: str):
    """
    根据ID加载算法模板
    
    Args:
        workflow_id: 算法模板ID
        
    Returns:
        EnhancedWorkflow: 算法模板数据
    """
    workflow = load_workflow_from_file(workflow_id)
    
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"算法模板不存在: {workflow_id}")
    
    return workflow


# @AI_GENERATED
@router.post(
    "/{workflow_id}/save",
    response_model=EnhancedWorkflow,
    summary="保存已有工作流（编辑已有模式，版本号自增）",
)
async def save_existing_workflow(workflow_id: str, workflow_data: dict):
    """spec algorithm-deployment-refactor 任务 7.2：编辑已有 → 版本递增。

    - URL 带已有 workflow_id 时视为"编辑已有"模式，从存储加载后覆盖节点/连线/元信息；
    - `version = existing.version + 1`；
    - `parent_version_id = "{workflow_id}@v{old_version}"`（同一 workflow_id 内的
      逻辑父版本指针，避免与"跨记录克隆"的 parent_version_id 语义冲突）；
    - 保留 `version_group_id`、`source_template_id`、`createdAt` 与 id；
    - 不改动其他工作流或源模板的任何字段（Property 9：工作流版本隔离）。
    """
    existing_workflow = load_workflow_from_file(workflow_id)
    if existing_workflow is None:
        raise HTTPException(status_code=404, detail=f"工作流不存在: {workflow_id}")

    try:
        existing_dict = existing_workflow.dict()
        old_version = int(existing_dict.get("version") or 1)

        merged = dict(existing_dict)

        # 覆盖客户端可修改的业务字段（与 update_workflow 保持一致的字段白名单）
        for field in ("name", "description", "nodes", "edges", "metadata", "scenario_id"):
            if field in workflow_data:
                merged[field] = workflow_data[field]

        # 版本谱系
        merged["id"] = workflow_id
        merged["version"] = old_version + 1
        merged["parent_version_id"] = f"{workflow_id}@v{old_version}"
        # version_group_id / source_template_id / createdAt 全部沿用旧值
        merged["version_group_id"] = existing_dict.get("version_group_id")
        merged["source_template_id"] = existing_dict.get("source_template_id")
        merged["createdAt"] = existing_dict.get("createdAt")
        merged["updatedAt"] = datetime.now().isoformat()

        workflow = EnhancedWorkflow(**merged)
        if save_workflow_to_file(workflow):
            print(
                f"✅ save workflow {workflow_id}: v{old_version} -> v{workflow.version}"
            )
            return workflow
        raise HTTPException(status_code=500, detail="保存工作流失败：写文件失败")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ save workflow {workflow_id} 失败: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"保存工作流失败: {str(e)}")
# @AI_GENERATED: end


@router.post("/{workflow_id}/clone", response_model=EnhancedWorkflow, summary="克隆模板为新版本")
async def clone_workflow(workflow_id: str):
    """
    基于现有模板创建新版本（深拷贝）。

    行为：
    - 生成新 id
    - 继承源模板的 scenario_id、version_group_id
    - version 在源模板基础上 +1
    - parent_version_id 指向源模板 id
    - 若源模板没有 version_group_id，则生成一个并回写源模板
    """
    source = load_workflow_from_file(workflow_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"源模板不存在: {workflow_id}")

    source_dict = source.dict()
    now = datetime.now().isoformat()
    new_id = generate_workflow_id()

    # Ensure source has version_group_id; if not, create one and persist back
    version_group_id = source_dict.get('version_group_id')
    if not version_group_id:
        version_group_id = f"vg-{workflow_id}"
        source_dict['version_group_id'] = version_group_id
        source_dict['version'] = source_dict.get('version') or 1
        try:
            patched_source = EnhancedWorkflow(**source_dict)
            save_workflow_to_file(patched_source)
        except Exception:
            pass  # best-effort backfill

    source_version = source_dict.get('version') or 1

    # Build cloned workflow
    clone_data = {
        **source_dict,
        'id': new_id,
        'version_group_id': version_group_id,
        'version': source_version + 1,
        'parent_version_id': workflow_id,
        'createdAt': now,
        'updatedAt': now,
    }

    try:
        cloned = EnhancedWorkflow(**clone_data)
        if save_workflow_to_file(cloned):
            return cloned
        raise HTTPException(status_code=500, detail="克隆保存失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"克隆失败: {str(e)}")


@router.put("/{workflow_id}", response_model=EnhancedWorkflow, summary="更新算法模板")
async def update_workflow(workflow_id: str, workflow_data: dict):
    """
    更新现有算法模板
    
    Args:
        workflow_id: 算法模板ID
        workflow_data: 更新的算法模板数据
        
    Returns:
        EnhancedWorkflow: 更新后的算法模板
    """
    # 检查算法模板是否存在
    existing_workflow = load_workflow_from_file(workflow_id)
    if existing_workflow is None:
        raise HTTPException(status_code=404, detail=f"算法模板不存在: {workflow_id}")
    
    try:
        print(f"\n{'='*60}")
        print(f"更新算法模板: {workflow_id}")
        print(f"{'='*60}")
        print(f"更新字段: {list(workflow_data.keys())}")
        
        # 直接从文件重新加载JSON数据，避免Pydantic序列化问题
        path = get_workflow_path(workflow_id)
        with open(path, 'r', encoding='utf-8') as f:
            updated_data = json.load(f)
        
        print(f"从文件加载的数据keys: {list(updated_data.keys())}")
        print(f"nodes存在: {'nodes' in updated_data}, 值: {updated_data.get('nodes', 'N/A')}")
        print(f"edges存在: {'edges' in updated_data}, 值: {updated_data.get('edges', 'N/A')}")
        
        # 更新提供的字段
        if 'name' in workflow_data:
            updated_data['name'] = workflow_data['name']
            print(f"更新名称: {workflow_data['name']}")
        if 'description' in workflow_data:
            updated_data['description'] = workflow_data['description']
            print(f"更新描述: {workflow_data['description']}")
        if 'nodes' in workflow_data:
            updated_data['nodes'] = workflow_data['nodes']
            print(f"更新节点数: {len(workflow_data['nodes'])}")
        if 'edges' in workflow_data:
            updated_data['edges'] = workflow_data['edges']
            print(f"更新连接线数: {len(workflow_data['edges'])}")
        # @AI_GENERATED
        if 'metadata' in workflow_data:
            updated_data['metadata'] = workflow_data['metadata']
            print(f"更新 metadata: {list(workflow_data['metadata'].keys()) if workflow_data['metadata'] else None}")
        # @AI_GENERATED: end
        
        # 保持ID和创建时间不变，更新修改时间
        updated_data['id'] = workflow_id
        updated_data['updatedAt'] = datetime.now().isoformat()
        
        print(f"\n更新后的数据keys: {list(updated_data.keys())}")
        print(f"准备验证的数据: {json.dumps(updated_data, indent=2, ensure_ascii=False)[:500]}...")
        
        print(f"\n开始验证更新后的数据...")
        workflow = EnhancedWorkflow(**updated_data)
        print(f"✅ 数据验证通过")
        
        print(f"\n开始保存到文件...")
        if save_workflow_to_file(workflow):
            print(f"✅ 文件保存成功")
            return workflow
        else:
            print(f"❌ 文件保存失败")
            raise HTTPException(status_code=500, detail="更新算法模板失败")
    
    except Exception as e:
        print(f"\n❌ 更新算法模板失败:")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        import traceback
        print(f"错误堆栈:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新算法模板失败: {str(e)}")


@router.delete("/{workflow_id}", summary="删除算法模板")
async def delete_workflow(workflow_id: str):
    """
    删除算法模板
    
    Args:
        workflow_id: 算法模板ID
        
    Returns:
        dict: 操作结果
    """
    path = get_workflow_path(workflow_id)
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"算法模板不存在: {workflow_id}")
    
    try:
        os.remove(path)
        return {"message": "算法模板已删除", "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除算法模板失败: {str(e)}")


@router.post("/validate", response_model=WorkflowValidationResult, summary="验证算法模板")
async def validate_workflow(workflow_data: dict):
    """
    验证算法模板的正确性
    
    Args:
        workflow_data: 算法模板数据
        
    Returns:
        WorkflowValidationResult: 验证结果
    """
    errors = []
    warnings = []
    
    try:
        nodes = workflow_data.get('nodes', [])
        edges = workflow_data.get('edges', [])
        
        # 检查是否有节点
        if len(nodes) == 0:
            warnings.append("算法模板中没有节点")
        
        # 检查节点ID唯一性
        node_ids = [node['id'] for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            errors.append("存在重复的节点ID")
        
        # 检查连接的有效性
        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            
            if source not in node_ids:
                errors.append(f"连接的源节点不存在: {source}")
            
            if target not in node_ids:
                errors.append(f"连接的目标节点不存在: {target}")
        
        # 检查是否有循环依赖（简单检查）
        # TODO: 实现更完整的拓扑排序检查
        
        return WorkflowValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    except Exception as e:
        return WorkflowValidationResult(
            valid=False,
            errors=[f"验证失败: {str(e)}"],
            warnings=[]
        )


# @AI_GENERATED
def _topological_sort_nodes(nodes, edges):
    """Topological sort of workflow nodes using Kahn's algorithm."""
    adj: Dict[str, list] = {n.id: [] for n in nodes}
    in_degree: Dict[str, int] = {n.id: 0 for n in nodes}
    for edge in edges:
        if edge.source in adj and edge.target in in_degree:
            adj[edge.source].append(edge.target)
            in_degree[edge.target] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    order = []
    while queue:
        queue.sort()
        nid = queue.pop(0)
        order.append(nid)
        for child in adj.get(nid, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(order) != len(nodes):
        raise ValueError("工作流包含循环依赖")
    return order


def _collect_upstream_inputs(node_id, edges, node_outputs):
    """Collect upstream outputs as inputs for the given node.
    
    When an upstream operator returns {"data": DataFrame, ...}, the dict contents
    are merged into the inputs so downstream operators can access inputs["data"]
    directly as a DataFrame.

    When multiple upstream nodes output the same key (e.g. both output "data"),
    the targetHandle on the edge is used to disambiguate.  If the targetHandle
    contains a meaningful port name (e.g. "n3-in-1" → port "label_data" from the
    node's input port definition, or a raw name like "source_data"), that name is
    used as the input key so the downstream operator can distinguish them.
    """
    # Collect all edges pointing to this node, tagged with their targetHandle
    incoming = [e for e in edges if e.target == node_id]

    # First pass: count how many incoming edges share each output key
    # so we know when we need to disambiguate
    key_counts: Dict[str, int] = {}
    for edge in incoming:
        source_output = node_outputs.get(edge.source)
        if source_output is None:
            continue
        if isinstance(source_output, dict):
            for k in source_output:
                key_counts[k] = key_counts.get(k, 0) + 1
        else:
            key_counts["data"] = key_counts.get("data", 0) + 1

    inputs: Dict[str, Any] = {}
    for edge in incoming:
        source_output = node_outputs.get(edge.source)
        if source_output is None:
            continue

        # Determine an optional alias from targetHandle
        # Supported formats:
        #   "source_data"         → alias = "source_data"
        #   "label_data"          → alias = "label_data"
        #   "n3-in-1"             → no alias (positional handle, fall through)
        #   None / ""             → no alias
        target_handle = edge.targetHandle or ""
        alias = None
        if target_handle and "-" not in target_handle:
            # plain semantic name like "source_data" or "label_data"
            alias = target_handle

        if isinstance(source_output, dict):
            for k, v in source_output.items():
                # If this key is ambiguous (multiple upstreams output same key),
                # prefer the alias so we don't silently drop one
                if key_counts.get(k, 0) > 1 and alias:
                    dest_key = alias
                else:
                    dest_key = k
                if dest_key not in inputs:
                    inputs[dest_key] = v
        else:
            dest_key = alias or (target_handle.split("-")[-1] if "-" in target_handle else "data")
            if dest_key not in inputs:
                inputs[dest_key] = source_output

    return inputs


def _build_output_summary(output):
    """Build a JSON-serializable summary of operator output."""
    summary = {}
    if isinstance(output, dict):
        for k, v in output.items():
            if isinstance(v, (int, float, str, bool)):
                summary[k] = v
            elif isinstance(v, list):
                summary[k] = f"list[{len(v)}]"
            elif isinstance(v, dict):
                summary[k] = f"dict[{len(v)}]"
            elif hasattr(v, "shape"):
                summary[k] = f"DataFrame{list(v.shape)}"
            else:
                summary[k] = type(v).__name__
    return summary


def _execute_pipeline_sync(
    workflow,
    execution_data=None,
    max_rows=None,
    execution_id=None,
    cancel_event: Optional[threading.Event] = None,
):
    """
    Core synchronous pipeline execution logic.

    Args:
        workflow: EnhancedWorkflow instance
        execution_data: Optional dict with extra execution params
        max_rows: If set, truncate input data to this many rows (preflight mode)
        execution_id: If set, updates _execution_store in real-time for polling
        cancel_event: If set, checked between nodes (e.g. baseline 比对取消)

    Returns:
        dict with keys: success, nodeResults, logs, executionTime, error
    """
    from services.operator_execution import (
        OperatorRouter,
        SchemaValidator,
        DataAdapter,
        GlobalConfigInjector,
    )

    start_time = time.time()
    node_results: Dict[str, Any] = {}
    logs: list = []

    # @AI_GENERATED
    def _log(msg, log_type="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = {"timestamp": ts, "message": msg, "type": log_type}
        logs.append(entry)
        # Real-time update to execution store for polling
        if execution_id and execution_id in _execution_store:
            _execution_store[execution_id]["logs"] = list(logs)

    def _update_store_node(node_id, status_dict):
        """Update node result in execution store for real-time polling."""
        node_results[node_id] = status_dict
        if execution_id and execution_id in _execution_store:
            _execution_store[execution_id]["nodeResults"] = dict(node_results)
    # @AI_GENERATED: end

    nodes = workflow.nodes
    edges = workflow.edges

    # Read global config from metadata
    metadata = workflow.metadata or {}
    global_config = metadata.get("global_config", {})

    # Initialize framework components
    config_injector = GlobalConfigInjector(global_config)
    op_router = OperatorRouter()
    op_router.auto_discover(_OPERATOR_BACKENDS_DIR)
    schema_validator = SchemaValidator()
    data_adapter = DataAdapter()

    _log(f"流水线开始执行: {workflow.name} (算子数: {len(nodes)})", "start")

    try:
        execution_order = _topological_sort_nodes(nodes, edges)
    except ValueError as e:
        _log(str(e), "error")
        return {
            "success": False,
            "nodeResults": node_results,
            "logs": logs,
            "executionTime": time.time() - start_time,
            "error": str(e),
        }

    node_outputs: Dict[str, Any] = {}

    for node_id in execution_order:
        # @AI_GENERATED
        # Check if execution was cancelled
        if execution_id and execution_id in _execution_store:
            if _execution_store[execution_id].get("cancelled"):
                _log("⊘ 执行已被用户取消", "error")
                return {
                    "success": False, "nodeResults": node_results, "logs": logs,
                    "executionTime": time.time() - start_time, "error": "用户手动取消",
                }
        if cancel_event is not None and cancel_event.is_set():
            _log("⊘ 流水线已中止（比对/回测取消）", "error")
            return {
                "success": False,
                "nodeResults": node_results,
                "logs": logs,
                "executionTime": time.time() - start_time,
                "error": "比对已取消",
            }
        # @AI_GENERATED: end

        node = next((n for n in nodes if n.id == node_id), None)
        if not node:
            continue

        node_start = time.time()
        node_label = node.data.label
        config = node.data.config.dict() if hasattr(node.data.config, "dict") else dict(node.data.config)
        function_id = config.get("functionId")
        enabled = config.get("enabled", True)
        if enabled is not None and not bool(enabled):
            inputs_for_skip = _collect_upstream_inputs(node_id, edges, node_outputs)
            passthrough = None
            if isinstance(inputs_for_skip, dict):
                if len(inputs_for_skip) == 1:
                    passthrough = next(iter(inputs_for_skip.values()))
                else:
                    passthrough = inputs_for_skip
            node_outputs[node_id] = passthrough
            _update_store_node(node_id, {
                "status": "skipped",
                "outputSummary": _build_output_summary(passthrough),
                "executionTime": round(time.time() - node_start, 3),
            })
            _log(f"◇ {node_label} 已禁用（enabled=false），跳过执行", "warning")
            continue

        if not function_id:
            _log(f"✗ {node_label} 缺少 functionId，跳过", "warning")
            node_results[node_id] = {"status": "skipped", "executionTime": 0}
            continue

        _log(f"▶ {node_label} 开始执行...", "start")

        try:
            # 1. Collect upstream inputs
            inputs = _collect_upstream_inputs(node_id, edges, node_outputs)

            # Preflight: truncate data inputs
            if max_rows is not None:
                import pandas as pd
                for k, v in inputs.items():
                    if isinstance(v, pd.DataFrame) and len(v) > max_rows:
                        inputs[k] = v.head(max_rows).copy()
                    elif isinstance(v, dict):
                        for dk, dv in v.items():
                            if isinstance(dv, pd.DataFrame) and len(dv) > max_rows:
                                v[dk] = dv.head(max_rows).copy()

            # 2. Build params from config (strip internal keys)
            params = {k: v for k, v in config.items() if k not in ("functionId", "operation", "chartType")}

            # Merge execution_data overrides if provided
            if execution_data:
                params.update({k: v for k, v in execution_data.items() if k not in ("functionId",)})

            # 3. Inject global config
            params = config_injector.inject(params)

            # @AI_GENERATED
            # 4. Inject log function so operators can write real-time training logs
            params["_log_fn"] = lambda msg, t="info": _log(f"  [{node_label}] {msg}", t)
            params["_cancel_event"] = cancel_event
            # @AI_GENERATED: end

            # 5. Route to operator backend
            if op_router.has_operator(function_id):
                output = op_router.execute(function_id, params, inputs)
            else:
                _log(f"  算子 {function_id} 未注册，使用旧路由", "warning")
                output = {"status": "skipped", "message": f"算子 {function_id} 未注册"}

            node_outputs[node_id] = output
            elapsed = time.time() - node_start

            _update_store_node(node_id, {
                "status": "success",
                "outputSummary": _build_output_summary(output),
                "executionTime": round(elapsed, 3),
            })
            _log(f"✓ {node_label} 完成 (耗时 {elapsed:.2f}s)", "success")

        except Exception as e:
            elapsed = time.time() - node_start
            error_msg = str(e)
            _update_store_node(node_id, {
                "status": "failed",
                "error": error_msg,
                "executionTime": round(elapsed, 3),
            })
            _log(f"✗ {node_label} 失败: {error_msg}", "error")
            return {
                "success": False,
                "nodeResults": node_results,
                "logs": logs,
                "executionTime": time.time() - start_time,
                "error": f"节点 {node_label} 执行失败: {error_msg}",
            }

    total_time = time.time() - start_time
    _log(f"✓ 流水线执行完成，总耗时 {total_time:.2f}s", "success")

    # @AI_GENERATED
    # Extract training metrics from node outputs for frontend visualization
    training_metrics = {}
    model_id = None
    for nid, output in node_outputs.items():
        if isinstance(output, dict):
            # Extract model_id from classifier / xgboost
            if "model_id" in output:
                model_id = output["model_id"]
                training_metrics["model_id"] = model_id
            if "model_path" in output:
                training_metrics["model_path"] = output["model_path"]
            # Extract feature_list (PV fault diagnosis)
            if "feature_list" in output and isinstance(output["feature_list"], list):
                training_metrics["feature_list"] = output["feature_list"]
            # Extract SMAPE score（smape_score 算子或兼容字段）
            if "score" in output and isinstance(output["score"], (int, float)):
                training_metrics["smape"] = round(float(output["score"]), 4)
            for _k in ("smape", "SMAPE"):
                if _k in output and output[_k] is not None and "smape" not in training_metrics:
                    try:
                        training_metrics["smape"] = round(float(output[_k]), 4)
                    except (TypeError, ValueError):
                        pass
            # MSE/RMSE/MAE
            if "mse" in output and output["mse"] is not None:
                try:
                    training_metrics["mse"] = round(float(output["mse"]), 4)
                except (TypeError, ValueError):
                    pass
            if "rmse" in output and output["rmse"] is not None:
                try:
                    training_metrics["rmse"] = round(float(output["rmse"]), 4)
                except (TypeError, ValueError):
                    pass
            if "mae" in output and output["mae"] is not None:
                try:
                    training_metrics["mae"] = round(float(output["mae"]), 4)
                except (TypeError, ValueError):
                    pass
            # 分类指标（precision_recall_f1 算子）
            for _k in ("accuracy", "precision", "recall", "f1"):
                if _k in output and output[_k] is not None:
                    try:
                        training_metrics[_k] = round(float(output[_k]), 4)
                    except (TypeError, ValueError):
                        pass
            # 混淆矩阵（confusion_matrix 算子）
            if "matrix" in output and output["matrix"] is not None:
                try:
                    import pandas as _pd
                    cm = output["matrix"]
                    if isinstance(cm, _pd.DataFrame):
                        training_metrics["confusion_matrix"] = {
                            "labels": [str(x) for x in cm.columns.tolist()],
                            "data": cm.values.tolist(),
                        }
                except Exception:
                    pass
            if "report" in output and isinstance(output["report"], str):
                training_metrics["classification_report"] = output["report"]
            # 分层重复评估算子（stratified_cv_eval）→ 映射为标准分类指标，供训练结果面板展示
            if "macro_f1_mean" in output and "per_repeat_macro_f1" in output:
                if output.get("accuracy_mean") is not None:
                    training_metrics["accuracy"] = output["accuracy_mean"]
                if output.get("macro_precision_mean") is not None:
                    training_metrics["precision"] = output["macro_precision_mean"]
                if output.get("macro_recall_mean") is not None:
                    training_metrics["recall"] = output["macro_recall_mean"]
                if output.get("macro_f1_mean") is not None:
                    training_metrics["f1"] = output["macro_f1_mean"]
                for _rich_key in (
                    "accuracy_mean",
                    "accuracy_std",
                    "macro_precision_mean",
                    "macro_recall_mean",
                    "macro_f1_mean",
                    "macro_f1_std",
                    "per_repeat_macro_f1",
                    "per_class_recall_mean",
                    "per_class_metrics",
                    "class_distribution",
                    "n_repeats",
                    "n_samples",
                    "n_classes",
                    "warnings",
                ):
                    if _rich_key in output:
                        training_metrics[_rich_key] = output[_rich_key]
                _cm = output.get("confusion_matrix")
                if isinstance(_cm, dict) and "labels" in _cm and "data" in _cm:
                    training_metrics["confusion_matrix"] = {
                        "labels": _cm["labels"], "data": _cm["data"],
                    }
                # 富化分类报告：把重复分层的均值±标准差/每次F1/各类recall/告警放进报告头
                _hdr = [
                    "【无泄漏 · 重复分层留出评估】",
                    f"重复次数 n_repeats={output.get('n_repeats')}  每次测试占比 test_ratio={output.get('test_ratio')}  "
                    f"样本数={output.get('n_samples')}  类别数={output.get('n_classes')}",
                    f"Accuracy = {output.get('accuracy_mean')} ± {output.get('accuracy_std')}    "
                    f"Macro-F1 = {output.get('macro_f1_mean')} ± {output.get('macro_f1_std')}",
                    f"每次 Macro-F1 = {output.get('per_repeat_macro_f1')}",
                ]
                _pcr = output.get("per_class_recall_mean")
                if isinstance(_pcr, dict):
                    _hdr.append("各类 Recall 均值 = " + ", ".join(f"{k}:{v}" for k, v in _pcr.items()))
                _warns = output.get("warnings")
                if _warns:
                    _hdr.append("告警 = " + ", ".join(str(w) for w in _warns))
                _base_report = output.get("classification_report") or ""
                training_metrics["classification_report"] = (
                    "\n".join(_hdr) + "\n" + ("-" * 60) + "\n" + _base_report
                )

    # Build per-node duration map
    node_durations = {}
    for nid, nr in node_results.items():
        node_obj = next((n for n in nodes if n.id == nid), None)
        label = node_obj.data.label if node_obj else nid
        node_durations[label] = nr.get("executionTime", 0)
    # @AI_GENERATED: end

    # @AI_GENERATED
    # Extract prediction payload from xgboost outputs for backtest/prediction dashboards
    y_true_list = None
    y_pred_list = None
    forecast_timestamps = None
    forecast_values = None
    cv_fold_metrics = []
    for _, output in node_outputs.items():
        if not isinstance(output, dict):
            continue
        if "y_true" in output and "y_pred" in output:
            yt = output["y_true"]
            yp = output["y_pred"]
            if hasattr(yt, 'tolist'):
                y_true_list = yt.tolist()
            elif isinstance(yt, list):
                y_true_list = yt
            if hasattr(yp, 'tolist'):
                y_pred_list = yp.tolist()
            elif isinstance(yp, list):
                y_pred_list = yp
        if "forecast_timestamps" in output and "forecast_values" in output:
            ts = output.get("forecast_timestamps")
            fv = output.get("forecast_values")
            if isinstance(ts, list) and isinstance(fv, list):
                forecast_timestamps = ts
                forecast_values = fv
        if "cv_fold_metrics" in output and isinstance(output.get("cv_fold_metrics"), list):
            cv_fold_metrics = output.get("cv_fold_metrics") or []
    if forecast_timestamps is None and y_pred_list is not None:
        forecast_timestamps = [str(i) for i in range(len(y_pred_list))]
    if forecast_values is None and y_pred_list is not None:
        forecast_values = y_pred_list

    # 提取故障诊断预测结果（label_encode decode 输出的 DataFrame）
    fault_predictions = None
    model_metrics = None
    fault_timeseries = None
    for nid, output in node_outputs.items():
        if isinstance(output, dict):
            # 提取模型预测时保存的历史评估指标
            if "model_metrics" in output and output["model_metrics"]:
                model_metrics = output["model_metrics"]
            # 提取故障诊断预测结果（label_encode decode 输出的 DataFrame）
            if "data" in output:
                import pandas as _pd
                df_out = output["data"]
                if isinstance(df_out, _pd.DataFrame) and fault_predictions is None:
                    # 兼容不同列名：predictions 或 predict_label
                    if "predictions" in df_out.columns or "predict_label" in df_out.columns:
                        # 完整写出供预测批次持久化；勿 head(500) 截断，否则大批次审核缺样本
                        fault_predictions = df_out.fillna("").to_dict(orient="records")
    # @AI_GENERATED: end

    # 提取故障设备时序曲线
    if fault_predictions and len(fault_predictions) > 0:
        import pandas as _pd
        try:
            preds_df = _pd.DataFrame(fault_predictions)
            pred_col = "predictions" if "predictions" in preds_df.columns else "predict_label"

            # 附加置信度（来自 RF predict 的 confidences，按行序对齐）
            if "confidence" not in preds_df.columns:
                for _nid, _output in node_outputs.items():
                    if isinstance(_output, dict) and _output.get("confidences") is not None:
                        _conf = _output["confidences"]
                        try:
                            if len(_conf) == len(preds_df):
                                preds_df["confidence"] = [round(float(c), 4) for c in _conf]
                                break
                        except Exception:
                            pass

            # 附加 explain_features（供 SHAP / 相似案例），按行序对齐为 _features 字典列
            if "_features" not in preds_df.columns:
                for _nid, _output in node_outputs.items():
                    if not isinstance(_output, dict):
                        continue
                    _ef = _output.get("explain_features")
                    if not isinstance(_ef, _pd.DataFrame) or len(_ef) != len(preds_df):
                        continue
                    id_like = {"site_id", "device_id", "branch_id", "time_window", "label", "predictions", "predict_label", "confidence"}
                    feat_cols = [c for c in _ef.columns if c not in id_like]
                    if not feat_cols:
                        continue
                    feature_rows = []
                    for i in range(len(_ef)):
                        row = {}
                        for c in feat_cols:
                            try:
                                val = _ef.iloc[i][c]
                                row[str(c)] = None if _pd.isna(val) else float(val)
                            except Exception:
                                row[str(c)] = None
                        feature_rows.append(row)
                    preds_df["_features"] = feature_rows
                    break

            # 如果 preds_df 没有 device_id，尝试从 node_outputs 中找到有 id 字段的 DataFrame 合并
            if "device_id" not in preds_df.columns:
                # 从 feature_select 或其他节点获取 id 映射（按行序对齐）
                for nid, output in node_outputs.items():
                    if isinstance(output, dict) and "data" in output:
                        df_candidate = output["data"]
                        if isinstance(df_candidate, _pd.DataFrame) and "device_id" in df_candidate.columns and "time_window" in df_candidate.columns:
                            # 聚合后的 DataFrame（每行一个组），行数应和 predictions 一致
                            if len(df_candidate) == len(preds_df):
                                id_cols = [c for c in ["site_id", "device_id", "branch_id", "time_window"] if c in df_candidate.columns]
                                for c in id_cols:
                                    preds_df[c] = df_candidate[c].values
                                break

            # 优先选一个有故障的设备×窗口
            fault_rows = preds_df[~preds_df[pred_col].astype(str).isin(["7", "0", ""])]
            if len(fault_rows) == 0:
                fault_rows = preds_df.head(1)
            sample_row = fault_rows.iloc[0]
            device_id = str(sample_row.get("device_id", ""))
            branch_id = sample_row.get("branch_id", "")
            time_window_val = str(sample_row.get("time_window", ""))
            tw_date = time_window_val[:10]

            # 从源文件直接读取
            source_file = None
            if device_id and tw_date:
                for node in (workflow.nodes if hasattr(workflow, 'nodes') else []):
                    try:
                        if hasattr(node, 'data') and hasattr(node.data, 'config'):
                            cfg = node.data.config
                            if getattr(cfg, 'functionId', None) == "load_csv":
                                source_file = getattr(cfg, 'file_path', None)
                                if source_file:
                                    break
                    except Exception:
                        pass

            if source_file and os.path.exists(source_file) and device_id and tw_date:
                if source_file.endswith(".parquet"):
                    raw_df = _pd.read_parquet(source_file)
                else:
                    raw_df = _pd.read_csv(source_file)
                if "time" in raw_df.columns:
                    raw_df["time"] = _pd.to_datetime(raw_df["time"])
                if "time_window" not in raw_df.columns and "time" in raw_df.columns:
                    raw_df["time_window"] = raw_df["time"].dt.normalize()

                mask = raw_df["device_id"].astype(str) == device_id
                if "branch_id" in raw_df.columns and branch_id:
                    mask = mask & (raw_df["branch_id"].astype(str) == str(branch_id))
                if tw_date and "time_window" in raw_df.columns:
                    mask = mask & (raw_df["time_window"].astype(str).str[:10] == tw_date)
                ts_slice = raw_df.loc[mask].sort_values("time").head(300)

                if len(ts_slice) > 0:
                    value_cols = [c for c in ts_slice.columns if c in ("value", "i_cal", "voltage", "current")]
                    if not value_cols:
                        value_cols = [c for c in ts_slice.select_dtypes(include="number").columns if c not in ("branch_id",)][:2]
                    fault_timeseries = {
                        "device_id": device_id,
                        "branch_id": str(branch_id),
                        "time_window": time_window_val,
                        "fault_type": str(sample_row.get(pred_col, "")),
                        "timestamps": ts_slice["time"].astype(str).tolist(),
                        "series": {col: ts_slice[col].fillna(0).round(4).tolist() for col in value_cols},
                    }

            # 同时更新 fault_predictions 使其包含完整 id 信息
            if "device_id" in preds_df.columns:
                fault_predictions = preds_df.fillna("").to_dict(orient="records")
        except Exception as e:
            import traceback
            print(f"[TS-DEBUG] EXCEPTION: {e}\n{traceback.format_exc()}", flush=True)

    return {
        "success": True,
        "nodeResults": node_results,
        "logs": logs,
        "executionTime": round(total_time, 3),
        "error": None,
        "metrics": training_metrics if any(k not in ("model_id", "feature_list") for k in training_metrics) else model_metrics,
        "model_id": model_id,
        "nodeDurations": node_durations,
        "y_true": y_true_list,
        "y_pred": y_pred_list,
        "forecast_timestamps": forecast_timestamps,
        "forecast_values": forecast_values,
        "cv_fold_metrics": cv_fold_metrics,
        "fault_predictions": fault_predictions,
        "fault_timeseries": fault_timeseries,
    }
# @AI_GENERATED: end


# @AI_GENERATED: Kiro v1.0
@router.post("/{workflow_id}/execute", response_model=WorkflowExecutionResult, summary="执行算法模板")
async def execute_workflow(workflow_id: str, execution_data: dict):
    """
    执行算法模板 - 通过算子执行框架逐节点执行工作流

    Args:
        workflow_id: 算法模板ID
        execution_data: 执行参数

    Returns:
        WorkflowExecutionResult: 执行结果
    """
    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"算法模板不存在: {workflow_id}")

    metadata = workflow.metadata or {}
    global_config = dict(metadata.get("global_config", {}))
    run_tuning_orchestration = _is_tuning_run(workflow, execution_data)
    if run_tuning_orchestration:
        start_date = execution_data.get("start_date") or execution_data.get("backtest_start_date") or global_config.get("backtest_start_date")
        end_date = execution_data.get("end_date") or execution_data.get("backtest_end_date") or global_config.get("backtest_end_date")
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="调优执行需要配置 backtest_start_date 与 backtest_end_date")
        tuning_candidates = _resolve_tuning_candidates(execution_data, global_config)
        if not tuning_candidates:
            raise HTTPException(status_code=400, detail="调优模板未配置 tuning_candidates，无法执行候选循环")
        tuning_result = await _run_tuning_batch(
            workflow,
            start_date,
            end_date,
            dict(execution_data),
            global_config,
            tuning_candidates,
            cancel_event=None,
        )
        result = {
            "success": True,
            "nodeResults": {
                "tuning_orchestrator": {
                    "status": "success",
                    "executionTime": 0.0,
                    "outputSummary": {
                        "successful_candidates": tuning_result.get("successful_candidates"),
                        "failed_candidates": tuning_result.get("failed_candidates"),
                    },
                }
            },
            "executionTime": 0.0,
            "error": None,
            "logs": [],
            "metrics": {
                "mode": "tuning_batch",
                "successful_candidates": tuning_result.get("successful_candidates"),
                "failed_candidates": tuning_result.get("failed_candidates"),
                "best_candidate_score": ((tuning_result.get("best_recommendation") or {}).get("candidate_score") or {}).get("score"),
            },
            "ranked_candidates": tuning_result.get("ranked_candidates"),
            "best_recommendation": tuning_result.get("best_recommendation"),
            "mode": tuning_result.get("mode"),
            "nodeDurations": {"tuning_orchestrator": 0.0},
            "model_id": None,
        }
    else:
        result = _execute_pipeline_sync(workflow, execution_data)

    return WorkflowExecutionResult(
        success=result["success"],
        nodeResults=result["nodeResults"],
        error=result.get("error"),
        executionTime=result["executionTime"],
        logs=result.get("logs"),
        metrics=result.get("metrics"),
        model_id=result.get("model_id"),
        nodeDurations=result.get("nodeDurations"),
        ranked_candidates=result.get("ranked_candidates"),
        best_recommendation=result.get("best_recommendation"),
        mode=result.get("mode"),
        fault_predictions=result.get("fault_predictions"),
    )
# @AI_GENERATED: end


# @AI_GENERATED
# ---------------------------------------------------------------------------
# Task 9.2: Async execution and status polling endpoints
# ---------------------------------------------------------------------------

def _persist_latest_execution(workflow_id: str, state: dict) -> None:
    """
    把最近一次执行结果写到磁盘，切换页面后前端仍可通过
    GET /{workflow_id}/latest-execution 读回来。

    只保存可 JSON 序列化的字段（nodeResults outputSummary、logs、metrics 等），
    跳过 numpy array、DataFrame 等不可序列化对象。
    """
    import json as _json
    _exec_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "execution_history")
    os.makedirs(_exec_dir, exist_ok=True)

    def _safe(obj, depth=0):
        if depth > 6:
            return str(obj)
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, dict):
            return {k: _safe(v, depth+1) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_safe(i, depth+1) for i in obj]
        # numpy / pandas → skip or stringify
        try:
            import numpy as _np
            if isinstance(obj, _np.ndarray):
                return f"ndarray{list(obj.shape)}"
            if isinstance(obj, _np.integer):
                return int(obj)
            if isinstance(obj, _np.floating):
                return float(obj)
        except ImportError:
            pass
        try:
            import pandas as _pd
            if isinstance(obj, _pd.DataFrame):
                return f"DataFrame{list(obj.shape)}"
        except ImportError:
            pass
        return str(obj)

    payload = _safe(state)
    path = os.path.join(_exec_dir, f"{workflow_id}_latest.json")
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"[persist] Execution result saved: {path}")


def _run_async_execution(execution_id: str, workflow, execution_data: Optional[dict]):
    """Background thread target for async pipeline execution."""
    state = _execution_store[execution_id]
    state["status"] = "running"
    state["started_at"] = datetime.now().isoformat()

    try:
        exec_params = execution_data if isinstance(execution_data, dict) else {}
        if _is_tuning_run(workflow, exec_params):
            metadata = workflow.metadata or {}
            global_config = dict(metadata.get("global_config", {}))
            start_date = exec_params.get("start_date") or exec_params.get("backtest_start_date") or global_config.get("backtest_start_date")
            end_date = exec_params.get("end_date") or exec_params.get("backtest_end_date") or global_config.get("backtest_end_date")
            if not start_date or not end_date:
                raise ValueError("调优执行需要配置 backtest_start_date 与 backtest_end_date")
            tuning_candidates = _resolve_tuning_candidates(exec_params, global_config)
            if not tuning_candidates:
                raise ValueError("调优模板未配置 tuning_candidates，无法执行候选循环")
            # 异步执行线程内无请求上下文，复用候选编排并返回统一结果结构。
            result = asyncio.run(
                _run_tuning_batch(
                    workflow,
                    start_date,
                    end_date,
                    dict(exec_params),
                    global_config,
                    tuning_candidates,
                    cancel_event=None,
                )
            )
            state["status"] = "success"
            state["nodeResults"] = {
                "tuning_orchestrator": {
                    "status": "success",
                    "executionTime": 0.0,
                    "outputSummary": {
                        "successful_candidates": result.get("successful_candidates"),
                        "failed_candidates": result.get("failed_candidates"),
                    },
                }
            }
            state["logs"] = [{
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "type": "success",
                "message": f"调优候选循环完成: success={result.get('successful_candidates')} failed={result.get('failed_candidates')}",
            }]
            state["executionTime"] = 0.0
            state["error"] = None
            state["metrics"] = {
                "mode": "tuning_batch",
                "successful_candidates": result.get("successful_candidates"),
                "failed_candidates": result.get("failed_candidates"),
                "best_candidate_score": ((result.get("best_recommendation") or {}).get("candidate_score") or {}).get("score"),
            }
            state["model_id"] = None
            state["nodeDurations"] = {"tuning_orchestrator": 0.0}
            state["ranked_candidates"] = result.get("ranked_candidates")
            state["best_recommendation"] = result.get("best_recommendation")
            state["mode"] = result.get("mode")
        else:
            result = _execute_pipeline_sync(workflow, execution_data, execution_id=execution_id)
            state["status"] = "success" if result["success"] else "failed"
            state["nodeResults"] = result["nodeResults"]
            state["logs"] = result["logs"]
            state["executionTime"] = result["executionTime"]
            state["error"] = result.get("error")
            state["metrics"] = result.get("metrics")
            state["model_id"] = result.get("model_id")
            state["nodeDurations"] = result.get("nodeDurations")
            state["forecast_timestamps"] = result.get("forecast_timestamps")
            state["forecast_values"] = result.get("forecast_values")
            state["y_true"] = result.get("y_true")
            state["y_pred"] = result.get("y_pred")
            state["fault_predictions"] = result.get("fault_predictions")
            state["fault_timeseries"] = result.get("fault_timeseries")
    except Exception as e:
        state["status"] = "failed"
        state["error"] = str(e)
        state["executionTime"] = 0.0
    finally:
        state["finished_at"] = datetime.now().isoformat()
        # 持久化最近一次执行结果到磁盘，切换页面后仍可读取
        try:
            _persist_latest_execution(state["workflow_id"], state)
        except Exception:
            pass  # 持久化失败不影响主流程


@router.post("/{workflow_id}/execute-async", summary="异步执行算法模板")
async def execute_workflow_async(workflow_id: str, execution_data: Optional[dict] = None):
    """
    异步执行算法模板 — 在后台线程中执行，立即返回 execution_id。

    如果 execution_data 中包含 live_nodes，则用前端实时传来的节点配置覆盖磁盘版本，
    这样前端改了参数不需要先保存再执行。

    Args:
        workflow_id: 算法模板ID
        execution_data: 可选执行参数（含 global_config / live_nodes）

    Returns:
        dict: 包含 execution_id 的响应
    """
    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"算法模板不存在: {workflow_id}")

    # 如果前端传了 live_nodes，用它覆盖磁盘上的节点配置
    if execution_data and isinstance(execution_data, dict) and execution_data.get("live_nodes"):
        live_nodes = execution_data["live_nodes"]
        if isinstance(live_nodes, list) and len(live_nodes) > 0:
            try:
                workflow.nodes = [EnhancedWorkflowNode(**n) if isinstance(n, dict) else n for n in live_nodes]
            except Exception as e:
                logger.warning(f"live_nodes 解析失败，使用磁盘版本: {e}")

    execution_id = f"exec-{uuid.uuid4().hex[:12]}"
    _execution_store[execution_id] = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "status": "pending",
        "nodeResults": {},
        "logs": [],
        "executionTime": 0.0,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "finished_at": None,
        "forecast_timestamps": None,
        "forecast_values": None,
        "y_true": None,
        "y_pred": None,
        "ranked_candidates": None,
        "best_recommendation": None,
        "mode": None,
    }

    thread = threading.Thread(
        target=_run_async_execution,
        args=(execution_id, workflow, execution_data),
        daemon=True,
    )
    thread.start()

    return {"execution_id": execution_id, "status": "pending"}


@router.get("/{workflow_id}/execution-status/{execution_id}", summary="查询执行状态")
async def get_execution_status(workflow_id: str, execution_id: str):
    """
    查询异步执行的当前状态、节点结果和日志。

    Args:
        workflow_id: 算法模板ID
        execution_id: 执行ID

    Returns:
        dict: 执行状态详情
    """
    state = _execution_store.get(execution_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"执行记录不存在: {execution_id}")
    if state["workflow_id"] != workflow_id:
        raise HTTPException(status_code=404, detail=f"执行记录不属于该工作流")

    return {
        "execution_id": state["execution_id"],
        "workflow_id": state["workflow_id"],
        "status": state["status"],
        "nodeResults": state["nodeResults"],
        "logs": state["logs"],
        "executionTime": state["executionTime"],
        "error": state["error"],
        "metrics": state.get("metrics"),
        "model_id": state.get("model_id"),
        "nodeDurations": state.get("nodeDurations"),
        "forecast_timestamps": state.get("forecast_timestamps"),
        "forecast_values": state.get("forecast_values"),
        "y_true": state.get("y_true"),
        "y_pred": state.get("y_pred"),
        "fault_predictions": state.get("fault_predictions"),
        "fault_timeseries": state.get("fault_timeseries"),
        "ranked_candidates": state.get("ranked_candidates"),
        "best_recommendation": state.get("best_recommendation"),
        "mode": state.get("mode"),
        "created_at": state["created_at"],
        "started_at": state["started_at"],
        "finished_at": state["finished_at"],
    }


# @AI_GENERATED
@router.get("/{workflow_id}/latest-execution", summary="读取最近一次执行结果（持久化版）")
async def get_latest_execution(workflow_id: str):
    """
    读取该工作流最近一次执行的结果（从磁盘读取，切换页面后仍有效）。

    Returns:
        dict: 最近一次执行的状态、节点结果、日志、metrics
    """
    import json as _json
    _exec_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "execution_history")
    path = os.path.join(_exec_dir, f"{workflow_id}_latest.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"暂无 {workflow_id} 的历史执行记录，请先执行一次训练。")
    with open(path, "r", encoding="utf-8") as f:
        state = _json.load(f)
    return state
# @AI_GENERATED: end


# @AI_GENERATED
@router.post("/{workflow_id}/cancel/{execution_id}", summary="取消执行")
async def cancel_execution(workflow_id: str, execution_id: str):
    """取消正在执行的流水线。设置 cancelled 标志，执行循环会在下一个节点前检查并中止。"""
    state = _execution_store.get(execution_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"执行记录不存在: {execution_id}")
    if state["status"] not in ("pending", "running"):
        return {"success": False, "message": f"执行已结束 (status={state['status']})"}
    state["cancelled"] = True
    state["status"] = "failed"
    state["error"] = "用户手动取消"
    state["finished_at"] = datetime.now().isoformat()
    return {"success": True, "message": "已发送取消信号"}
# @AI_GENERATED: end


# ---------------------------------------------------------------------------
# Task 9.3: Preflight endpoint
# ---------------------------------------------------------------------------

def _workflow_preflight_report(workflow_id: str, *, max_rows: int = 800) -> Dict[str, Any]:
    """样本限流行执行 + 逐边传输报告；供预检接口与 AutoResearch 启动闸门复用。"""
    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        return {
            "success": False,
            "workflow_missing": True,
            "error": f"算法模板不存在: {workflow_id}",
            "edge_reports": [],
            "logs": [],
            "executionTime": 0,
        }

    result = _execute_pipeline_sync(workflow, max_rows=max_rows)
    edge_reports: List[Dict[str, Any]] = []
    for edge in workflow.edges:
        src_result = result["nodeResults"].get(edge.source, {})
        tgt_result = result["nodeResults"].get(edge.target, {})
        src_status = src_result.get("status", "unknown")
        tgt_status = tgt_result.get("status", "unknown")

        passed = src_status == "success" and tgt_status in ("success", "skipped")
        edge_reports.append({
            "source": edge.source,
            "target": edge.target,
            "passed": passed,
            "source_summary": src_result.get("outputSummary", {}),
            "source_time": src_result.get("executionTime", 0),
            "target_time": tgt_result.get("executionTime", 0),
            "error": tgt_result.get("error") if not passed else None,
        })

    return {
        "success": bool(result["success"]),
        "workflow_missing": False,
        "edge_reports": edge_reports,
        "logs": result["logs"],
        "executionTime": result["executionTime"],
        "error": result.get("error"),
    }


@router.post("/{workflow_id}/preflight", summary="流水线预检")
async def preflight_workflow(workflow_id: str):
    """
    使用前 100 行样本数据执行流水线预检，验证每对相邻算子之间的数据契约。

    Args:
        workflow_id: 算法模板ID

    Returns:
        dict: 预检报告
    """
    report = _workflow_preflight_report(workflow_id, max_rows=800)
    if report.get("workflow_missing"):
        raise HTTPException(status_code=404, detail=str(report.get("error") or "模板不存在"))
    return {k: v for k, v in report.items() if k != "workflow_missing"}


# ---------------------------------------------------------------------------
# Task 9.5: Backtest execution logic
# ---------------------------------------------------------------------------


def _load_csv_config_from_workflow(workflow) -> dict:
    """从算法模板中读取首個 load_csv 節點的 file_path / parent / child（與圖中一致）。"""
    if hasattr(workflow, "model_dump"):
        data = workflow.model_dump()
    else:
        data = workflow.dict()
    for n in data.get("nodes") or []:
        cfg = (n.get("data") or {}).get("config") or {}
        if cfg.get("functionId") == "load_csv":
            return {
                "file_path": cfg.get("file_path"),
                "parent_id": cfg.get("parent_id"),
                "child_id": cfg.get("child_id"),
            }
    return {}


def _should_use_reference_rolling_engine(workflow, backtest_params: dict, global_config: dict) -> bool:
    if backtest_params.get("use_reference_engine") is not None:
        return bool(backtest_params.get("use_reference_engine"))
    if global_config.get("use_reference_rolling_engine") is not None:
        result = bool(global_config.get("use_reference_rolling_engine"))
        if result:
            print(f"[DEBUG] _should_use_reference_rolling_engine=True! gc.use_reference_rolling_engine={global_config.get('use_reference_rolling_engine')}")
        return result
    return False


def _normalize_metrics_dict(m: Optional[dict]) -> dict:
    """统一指标键名（兼容 SMAPE / smape 等），便于聚合与打分。"""
    if not m or not isinstance(m, dict):
        return {}
    aliases = [
        ("smape", ("smape", "SMAPE")),
        ("rmse", ("rmse", "RMSE")),
        ("mae", ("mae", "MAE")),
        ("mse", ("mse", "MSE")),
        # 任务 13：新增 bias（预测偏差 ME）和 p95_ape（第95百分位绝对百分误差）
        ("bias", ("bias", "me", "ME", "avg_me", "avg_bias")),
        ("p95_ape", ("p95_ape", "P95APE", "p95ape")),
    ]
    out: Dict[str, float] = {}
    for canon, keys in aliases:
        for k in keys:
            if k in m and m[k] is not None:
                try:
                    out[canon] = float(m[k])
                except (TypeError, ValueError):
                    pass
                break
    return out


def _build_candidate_score(avg_metrics: Optional[dict]) -> Optional[dict]:
    """
    Build a simple normalized score for tuning/ranking use.

    Current scoring focuses on SMAPE (if available) because it is the primary
    business-facing metric in this platform. Score range: [0, 100], higher better.
    若无 SMAPE 则尝试用 avg_rmse 单调映射，避免候选分全空导致无法比对。
    """
    if not avg_metrics:
        return None
    smape = avg_metrics.get("avg_smape")
    if smape is not None:
        try:
            smape_value = float(smape)
        except Exception:
            smape_value = None
        if smape_value is not None:
            score = max(0.0, min(100.0, 100.0 - smape_value))
            return {
                "name": "smape_inverse_100",
                "score": round(score, 4),
                "higher_is_better": True,
                "based_on": {"avg_smape": round(smape_value, 4)},
            }
    rmse = avg_metrics.get("avg_rmse")
    if rmse is not None:
        try:
            rv = float(rmse)
        except Exception:
            rv = None
        if rv is not None and rv >= 0:
            score = max(0.0, min(100.0, 100.0 * math.exp(-rv / 10000.0)))
            return {
                "name": "rmse_exp_decay_100",
                "score": round(score, 4),
                "higher_is_better": True,
                "based_on": {"avg_rmse": round(rv, 4)},
            }
    return None


def _candidate_sort_key(item: dict) -> tuple:
    """
    Sort candidates by score desc, then avg_smape asc.
    """
    cs = item.get("candidate_score") or {}
    score = cs.get("score")
    avg = item.get("avg_metrics") or {}
    smape = avg.get("avg_smape")
    try:
        score_val = float(score) if score is not None else -1e9
    except Exception:
        score_val = -1e9
    try:
        smape_val = float(smape) if smape is not None else 1e9
    except Exception:
        smape_val = 1e9
    return (-score_val, smape_val)


def _aggregate_cv_fold_metrics(daily_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregate per-day CV fold diagnostics into one backtest-level fold list.
    """
    folds: Dict[int, Dict[str, Any]] = {}
    for item in daily_results or []:
        if item.get("status") != "success":
            continue
        for metric in item.get("cv_fold_metrics") or []:
            if not isinstance(metric, dict):
                continue
            try:
                fold_id = int(metric.get("fold_id"))
                train_loss = float(metric.get("train_loss"))
                val_loss = float(metric.get("val_loss"))
                val_mape = float(metric.get("val_mape"))
            except Exception:
                continue
            bucket = folds.setdefault(
                fold_id,
                {
                    "fold_id": fold_id,
                    "train_loss_sum": 0.0,
                    "val_loss_sum": 0.0,
                    "val_mape_sum": 0.0,
                    "count": 0,
                },
            )
            bucket["train_loss_sum"] += train_loss
            bucket["val_loss_sum"] += val_loss
            bucket["val_mape_sum"] += val_mape
            bucket["count"] += 1

    aggregated = []
    for fold_id in sorted(folds):
        bucket = folds[fold_id]
        count = max(1, int(bucket["count"]))
        aggregated.append(
            {
                "fold_id": fold_id,
                "train_loss": round(bucket["train_loss_sum"] / count, 6),
                "val_loss": round(bucket["val_loss_sum"] / count, 6),
                "val_mape": round(bucket["val_mape_sum"] / count, 6),
            }
        )
    return aggregated


def _resolve_tuning_candidates(
    execution_params: dict,
    global_config: dict,
) -> List[dict]:
    """
    Resolve tuning candidates from request params or template global_config.
    Supports list directly or JSON string.
    """
    candidates_raw = execution_params.get("tuning_candidates")
    if candidates_raw is None:
        candidates_raw = global_config.get("tuning_candidates")
    if candidates_raw is None:
        return []
    if isinstance(candidates_raw, str):
        try:
            candidates_raw = json.loads(candidates_raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"tuning_candidates JSON 解析失败: {exc}") from exc
    if not isinstance(candidates_raw, list):
        raise HTTPException(status_code=400, detail="tuning_candidates 必须是数组")
    result: List[dict] = []
    for idx, item in enumerate(candidates_raw):
        if isinstance(item, dict):
            result.append(item)
        else:
            result.append({"name": f"candidate_{idx + 1}", "params": {}})
    return result


def _is_tuning_run(workflow, execution_params: Optional[dict]) -> bool:
    metadata = workflow.metadata or {}
    global_config = dict(metadata.get("global_config", {}))
    request_mode = ""
    if execution_params and isinstance(execution_params, dict):
        request_mode = str(
            execution_params.get("run_mode") or execution_params.get("operate_status") or ""
        ).strip().lower()
    template_mode = str(
        global_config.get("run_mode") or global_config.get("operate_status") or ""
    ).strip().lower()
    return (request_mode or template_mode) == "tuning"


async def _run_one_backtest_no_tuning(
    workflow,
    start_date: str,
    end_date: str,
    backtest_params: dict,
    global_config: dict,
    cancel_event: Optional[threading.Event] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
    progress_fn: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """单次回测（不跑 tuning_candidates），供 baseline/challenger 公平比对。"""
    if cancel_event is None:
        cancel_event = threading.Event()
    bp = dict(backtest_params)
    bp.pop("tuning_candidates", None)
    bp["start_date"] = start_date
    bp["end_date"] = end_date

    backtest_mode = str(
        bp.get("backtest_mode")
        or global_config.get("backtest_mode")
        or "rolling_retrain"
    ).strip().lower()
    model_ref = (
        bp.get("model_ref")
        or bp.get("backtest_model_ref")
        or global_config.get("backtest_model_ref")
    )
    if backtest_mode not in ("rolling_retrain", "inference_only"):
        return {
            "total_days": 0,
            "success_days": 0,
            "skipped_days": 0,
            "failed_days": 1,
            "total_duration": 0.0,
            "daily_results": [],
            "cancelled": False,
            "error": f"invalid backtest_mode: {backtest_mode}",
            "avg_metrics": None,
            "candidate_score": None,
        }
    if backtest_mode == "inference_only" and not model_ref:
        return {
            "total_days": 0,
            "success_days": 0,
            "skipped_days": 0,
            "failed_days": 1,
            "total_duration": 0.0,
            "daily_results": [],
            "cancelled": False,
            "error": "inference_only requires model_ref",
            "avg_metrics": None,
            "candidate_score": None,
        }

    try:
        if _should_use_reference_rolling_engine(workflow, bp, global_config):
            return await _run_limited_backtest(
                _execute_backtest_reference,
                workflow,
                start_date,
                end_date,
                bp,
                global_config,
                cancel_event,
                log_fn,
            )
        _train_days_used = int(bp.get("train_days") or global_config.get("backtest_train_days") or 30)
        if log_fn:
            log_fn(f"[compare] train_days={_train_days_used}, bp.train_days={bp.get('train_days')}, gc.backtest_train_days={global_config.get('backtest_train_days')}", "info")
        return await _run_limited_backtest(
            _execute_backtest,
            workflow,
            start_date,
            end_date,
            bp.get("training_node_ids"),
            bp.get("prediction_node_ids"),
            _train_days_used,
            bool(
                bp.get("apply_window_filter")
                if bp.get("apply_window_filter") is not None
                else global_config.get("backtest_apply_window_filter", True)
            ),
            bool(
                bp.get("mask_target_values")
                if bp.get("mask_target_values") is not None
                else global_config.get("backtest_mask_target_values", True)
            ),
            backtest_mode,
            model_ref,
            cancel_event,
            log_fn,
            progress_fn,
            int(bp.get("gap_days") if bp.get("gap_days") is not None else global_config.get("backtest_gap_days", 1)),
        )
    except Exception as e:
        traceback.print_exc()
        return {
            "total_days": 0,
            "success_days": 0,
            "skipped_days": 0,
            "failed_days": 1,
            "total_duration": 0.0,
            "daily_results": [],
            "cancelled": bool(cancel_event.is_set()),
            "error": str(e),
            "avg_metrics": None,
            "candidate_score": None,
        }


def _merge_evaluation_contract_into_global(workflow, contract: dict) -> dict:
    base = dict((workflow.metadata or {}).get("global_config") or {})
    return {**base, **contract}


def _summarize_backtest_for_compare(res: Optional[dict]) -> dict:
    if not res or not isinstance(res, dict):
        return {}
    return {
        "error": res.get("error"),
        "avg_metrics": res.get("avg_metrics"),
        "candidate_score": res.get("candidate_score"),
        "cv_fold_metrics": res.get("cv_fold_metrics") or [],
        "daily_results": res.get("daily_results") or [],
        "success_days": res.get("success_days"),
        "failed_days": res.get("failed_days"),
        "skipped_days": res.get("skipped_days"),
        "total_duration": res.get("total_duration"),
    }


def _score_from_backtest_result(res: Optional[dict]) -> Optional[float]:
    if not res or res.get("error"):
        return None
    cs = res.get("candidate_score") or {}
    s = cs.get("score")
    try:
        return float(s) if s is not None else None
    except Exception:
        return None


def _mean_scores(values: List[Optional[float]]) -> Optional[float]:
    xs = [float(x) for x in values if x is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def _aggregate_scores(values: List[Optional[float]], method: str) -> Optional[float]:
    xs = [float(x) for x in values if x is not None]
    if not xs:
        return None
    m = str(method or "mean").strip().lower()
    if m == "median":
        xs_sorted = sorted(xs)
        n = len(xs_sorted)
        mid = n // 2
        if n % 2:
            return xs_sorted[mid]
        return (xs_sorted[mid - 1] + xs_sorted[mid]) / 2.0
    if m == "trimmed_mean":
        xs_sorted = sorted(xs)
        n = len(xs_sorted)
        if n <= 2:
            return sum(xs_sorted) / n
        trimmed = xs_sorted[1:-1]
        return sum(trimmed) / len(trimmed)
    return sum(xs) / len(xs)


def _mean_metric_from_windows(window_results: List[Dict[str, Any]], side: str, metric_keys: List[str]) -> Optional[float]:
    vals: List[float] = []
    for item in window_results or []:
        target = item.get(side) if isinstance(item, dict) else None
        avg = (target or {}).get("avg_metrics") if isinstance(target, dict) else None
        if not isinstance(avg, dict):
            continue
        value: Optional[float] = None
        for k in metric_keys:
            raw = avg.get(k)
            if raw is None:
                continue
            try:
                value = float(raw)
                break
            except (TypeError, ValueError):
                continue
        if value is not None:
            vals.append(value)
    if not vals:
        return None
    return float(sum(vals) / len(vals))


def _evaluate_autoresearch_candidate(
    compare_state: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    return _auto_research_evaluator.evaluate_candidate(compare_state, policy)


def _autoresearch_rank_key(item: Dict[str, Any]) -> tuple:
    return _auto_research_evaluator.rank_key(item)


def _select_autoresearch_batch_best(
    rows: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    return _auto_research_batch_selector.select_best_successful(rows)


def _check_convergence(
    iterations: List[dict],
    window: int = 5,
    var_threshold: float = 0.01,
) -> Dict[str, Any]:
    return _auto_research_convergence_monitor.check_convergence(
        iterations,
        window=window,
        var_threshold=var_threshold,
    )


def _compute_pareto_frontier(candidates: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
    return _auto_research_evaluator.compute_pareto_frontier(candidates, top_k=top_k)


def _build_autoresearch_override_candidates(search_space: Dict[str, Any], iteration: int, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed + iteration * 7919)
    out: Dict[str, Any] = {}
    for k, v in (search_space or {}).items():
        key = str(k).strip()
        if not key:
            continue
        if isinstance(v, list) and len(v) > 0:
            out[key] = v[rng.randrange(0, len(v))]
        else:
            out[key] = v
    return out


def _sample_override_with_memory_prior(
    search_space: Dict[str, Any],
    iteration: int,
    seed: int,
    memory_cases: List[Dict[str, Any]],
    avoid_set: Optional[List[Dict[str, Any]]] = None,
    prior_weight: float = 0.4,
) -> Dict[str, Any]:
    """
    任务 7.1：带历史先验的采样器。

    策略：
    - 以 prior_weight 概率从历史成功 patch 中随机选一个作为起点（先验引导）
    - 以 (1 - prior_weight) 概率走原有纯随机逻辑
    - 若采样结果命中 avoid_set（失败模式回避集），则退化为纯随机

    Args:
        search_space: 当前搜索空间
        iteration: 当前迭代轮次（用于随机种子）
        seed: 基础随机种子
        memory_cases: 经验库案例列表（已按 retrieval_score 排序）
        avoid_set: 失败模式回避集（任务 7.2 填充）
        prior_weight: 先验引导概率，默认 0.4

    Returns:
        采样得到的 override dict
    """
    rng = random.Random(seed + iteration * 7919)

    # 收集历史成功 patch 中与 search_space 有交集的 override
    success_overrides: List[Dict[str, Any]] = []
    for c in (memory_cases or []):
        if not isinstance(c, dict):
            continue
        out_info = c.get("outcome") or {}
        if not bool(out_info.get("improved")):
            continue
        patch = c.get("applied_patch") or {}
        override_patch = patch.get("override") or {}
        if not isinstance(override_patch, dict):
            continue
        # 只保留与 search_space 有交集的键
        filtered = {k: v for k, v in override_patch.items() if k in search_space}
        if filtered:
            success_overrides.append(filtered)

    # 决定是否使用先验
    use_prior = bool(success_overrides) and rng.random() < prior_weight
    if use_prior:
        base = dict(rng.choice(success_overrides))
        # 对 search_space 中未被先验覆盖的键，随机补全
        for k, v in (search_space or {}).items():
            key = str(k).strip()
            if not key or key in base:
                continue
            if isinstance(v, list) and len(v) > 0:
                base[key] = v[rng.randrange(0, len(v))]
            else:
                base[key] = v
        candidate = base
    else:
        candidate = _build_autoresearch_override_candidates(search_space, iteration, seed)

    # 检查是否命中回避集
    avoid = avoid_set or []
    for bad in avoid:
        if not isinstance(bad, dict):
            continue
        # 若候选与失败模式完全匹配（所有 bad 的键值相同），则退化为纯随机
        if all(candidate.get(k) == v for k, v in bad.items() if k in candidate):
            candidate = _build_autoresearch_override_candidates(search_space, iteration, seed + 1)
            break

    return candidate


def _translate_intent_to_patches(
    intent: Dict[str, Any],
    workflow_id: str,
    registry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    任务 33.2：意图→patch 翻译器。

    将 GLM 输出的意图（intent）翻译为具体的 patch，保证 node_id 一定是模板中真实存在的。

    Args:
        intent（意图对象）: GLM 输出的 intent dict
        workflow_id（模板 ID）: 用于查找真实节点
        registry（注册表对象）: 用于查找参数选项

    Returns:
        {
            "structure_patch": {...},
            "node_param_patches": [...],
            "global_config_patch": {...},
        }
        翻译失败时返回空 patch（不报错）
    """
    if not isinstance(intent, dict):
        return {}

    action = str(intent.get("action") or "").strip()
    target_fid = str(intent.get("target_function_id") or "").strip()
    param_key = str(intent.get("param_key") or "").strip()
    direction = str(intent.get("direction") or "increase").strip()
    value_hint = intent.get("value_hint")

    result: Dict[str, Any] = {
        "structure_patch": {},
        "node_param_patches": [],
        "global_config_patch": {},
        "search_space_patch": {},
    }

    try:
        # 从模板中查找真实 node_id
        wf = load_workflow_from_file(str(workflow_id).strip())
        if wf is None:
            return result
        node_id_by_fid: Dict[str, str] = {}
        node_config_by_fid: Dict[str, Dict[str, Any]] = {}
        for n in (wf.dict().get("nodes") or []):
            nid = str(n.get("id") or "").strip()
            cfg = ((n.get("data") or {}).get("config") or {})
            fid = str(cfg.get("functionId") or "").strip()
            if nid and fid:
                node_id_by_fid[fid] = nid
                node_config_by_fid[fid] = cfg

        if action == "adjust_param" and target_fid and param_key:
            real_nid = node_id_by_fid.get(target_fid)
            if not real_nid:
                return result
            # 从注册表找选项，按 direction 选值
            current_val = node_config_by_fid.get(target_fid, {}).get(param_key)
            new_val = None
            if registry:
                all_reg_params: Dict[str, Any] = {}
                for _layer in (registry.get("layers") or {}).values():
                    all_reg_params.update((_layer.get("params") or {}))
                # 查找匹配的注册表参数
                for reg_key, reg_spec in all_reg_params.items():
                    if (str(reg_spec.get("node_function_id") or "") == target_fid
                            and str(reg_spec.get("param_key") or "") == param_key):
                        options = reg_spec.get("options") or []
                        if isinstance(options, list) and options:
                            if direction == "increase":
                                # 选比当前值大的选项
                                bigger = [o for o in options if _compare_option(o, current_val, ">")]
                                new_val = bigger[0] if bigger else options[-1]
                            elif direction == "decrease":
                                smaller = [o for o in options if _compare_option(o, current_val, "<")]
                                new_val = smaller[-1] if smaller else options[0]
                            else:  # set
                                new_val = options[len(options) // 2]
                        break
            if new_val is None and value_hint is not None:
                new_val = value_hint
            if new_val is not None:
                result["node_param_patches"] = [{
                    "node_id": real_nid,
                    "functionId": target_fid,
                    "param_patch": {param_key: new_val},
                }]

        elif action in ("enable_node", "disable_node") and target_fid:
            real_nid = node_id_by_fid.get(target_fid)
            if real_nid:
                result["structure_patch"] = {
                    "node_switches": [{
                        "node_id": real_nid,
                        "functionId": target_fid,
                        "enabled": action == "enable_node",
                    }]
                }

        elif action == "change_ensemble":
            mode = str(value_hint or "all_adaptive").strip()
            em_patches = _build_ensemble_mode_patches(
                workflow_id, mode, weight_strategy="oof_rmse_inverse"
            )
            result["structure_patch"] = em_patches.get("structure_patch") or {}
            result["node_param_patches"] = em_patches.get("node_param_patches") or []
            result["global_config_patch"] = {"ensemble_mode": mode}

        elif action == "add_feature_recipe":
            # C5 FIX: allow GLM to propose feature recipes via intent
            from services.feature_recipe_service import resolve_recipe_structure_patch
            _known = known_recipe_ids()
            _rid_candidates = [
                intent.get("recipe_id"),
                intent.get("feature_recipe_id"),
                value_hint,
                param_key,
                target_fid,
            ]
            _rid = ""
            for _candidate in _rid_candidates:
                _candidate_s = str(_candidate or "").strip()
                if not _candidate_s:
                    continue
                if not _known or _candidate_s in _known:
                    _rid = _candidate_s
                    break
            if _rid:
                try:
                    _recipe_patch = resolve_recipe_structure_patch(
                        workflow_id, _rid, load_workflow_from_file
                    )
                    if _recipe_patch.get("node_switches"):
                        result["structure_patch"] = _recipe_patch
                        result["search_space_patch"] = {"feature_recipe_id": [_rid]}
                        result["feature_recipe_id"] = _rid
                except Exception as exc:
                    logger.warning("feature recipe intent translation failed for %s: %s", _rid, exc)

    except Exception as exc:
        logger.warning("intent translation failed: %s", exc)

    return result


def _compare_option(option: Any, current: Any, op: str) -> bool:
    """比较两个选项值（支持列表和标量）。"""
    try:
        if isinstance(option, list) and isinstance(current, list):
            return (max(option) > max(current)) if op == ">" else (max(option) < max(current))
        return (float(option) > float(current)) if op == ">" else (float(option) < float(current))
    except (TypeError, ValueError):
        return False


def _validate_sample_constraints(sample: Dict[str, Any], registry: Dict[str, Any]) -> bool:
    """
    任务 32.1：参数约束规则引擎，检查采样结果是否满足内置约束。

    Args:
        sample（采样结果）: _sample_from_registry 的输出
        registry（注册表对象）: 当前使用的注册表

    Returns:
        True 表示满足所有约束，False 表示有约束违反
    """
    # lags 最大值不能超过 train_days
    lags = sample.get("create_lag_features.lags")
    train_days = sample.get("train_days", 30)
    if isinstance(lags, list) and lags:
        try:
            if max(lags) > int(train_days):
                return False
        except (TypeError, ValueError):
            pass

    # single_best 模式下不需要 active_models（条件参数，32.2 处理）
    ensemble_mode = sample.get("ensemble_mode")
    if ensemble_mode == "single_best" and "active_models" in sample:
        return False

    # sliding_window.step 不能大于 sliding_window.window_size
    sw_step = sample.get("sliding_window.step")
    sw_size = sample.get("sliding_window.window_size")
    if sw_step is not None and sw_size is not None:
        try:
            if int(sw_step) > int(sw_size):
                return False
        except (TypeError, ValueError):
            pass

    # cv_folds 不能大于 train_days / daily_horizon（避免折数 > 样本数）
    cv_folds = sample.get("cv_folds")
    daily_horizon = sample.get("daily_horizon", 96)
    if cv_folds is not None and train_days is not None:
        try:
            max_folds = max(1, int(train_days) // max(1, int(daily_horizon) // 96))
            if int(cv_folds) > max_folds:
                return False
        except (TypeError, ValueError):
            pass

    return True


def _build_locked_params_from_runtime_patch(runtime_patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    任务 30：从 runtime_patch 提取已锁定的参数集合，供采样器跳过。

    锁定范围：
    - node_param_patches 中的 functionId.param_key（任务 30.1）
    - structure_patch.node_switches 中显式设置的 functionId（任务 30.2）

    Returns:
        {"functionId.param_key": value, "structure_switch.functionId": enabled} 格式的 dict
    """
    locked: Dict[str, Any] = {}
    # node_param_patches：锁定 functionId.param_key
    npp = runtime_patch.get("node_param_patches") or []
    for item in (npp if isinstance(npp, list) else []):
        if not isinstance(item, dict):
            continue
        fid = str(item.get("functionId") or "").strip()
        pp = item.get("param_patch") or {}
        if fid and isinstance(pp, dict):
            for pk in pp.keys():
                locked[f"{fid}.{pk}"] = pp[pk]
    # structure_patch.node_switches：锁定 functionId 的开关状态
    stp = runtime_patch.get("structure_patch") or {}
    switches = (stp.get("node_switches") or []) if isinstance(stp, dict) else []
    for sw in (switches if isinstance(switches, list) else []):
        if not isinstance(sw, dict):
            continue
        fid = str(sw.get("functionId") or "").strip()
        if fid:
            locked[f"structure_switch.{fid}"] = sw.get("enabled")
    return locked


def _sample_from_registry(
    registry: Dict[str, Any],
    active_layers: List[str],
    diagnosis: Optional[Dict[str, Any]] = None,
    memory_cases: Optional[List[Dict[str, Any]]] = None,
    avoid_set: Optional[List[Dict[str, Any]]] = None,
    rng: Optional[Any] = None,
    locked_params: Optional[Dict[str, Any]] = None,
    research_focus: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    任务 9.3：统一采样器，从注册表的激活层中采样一组参数配置。

    采样策略：
    - 30% 概率：纯随机采样（保持探索多样性）
    - 70% 概率：诊断引导 + 经验先验加权采样
    - 回避集中的参数组合权重归零

    Args:
        registry（注册表对象）: load_registry() 的返回值
        active_layers（激活层列表）: get_active_layers() 的返回值，如 ["training", "feature"]
        diagnosis（误差诊断）: error_diagnosis dict，含 primary_error_source（主要误差来源）
        memory_cases（经验库案例）: _retrieve_memory_cases() 的返回值
        avoid_set（回避集）: 历史失败的参数组合列表
        rng（随机数生成器）: random.Random 实例，None 时自动创建
        locked_params（已锁定参数）: 任务 30.1，格式 {"functionId.param_key": value}，跳过这些参数

    Returns:
        {param_key: sampled_value} 的 dict，key 为注册表中的参数名
    """
    import random as _random
    if rng is None:
        rng = _random.Random()

    # 收集所有激活层的参数定义
    all_params: Dict[str, Any] = {}
    param_layers: Dict[str, str] = {}
    layers = registry.get("layers") or {}
    for layer_name in active_layers:
        layer = layers.get(layer_name) or {}
        params = layer.get("params") or {}
        all_params.update(params)
        for param_key in params:
            param_layers[str(param_key)] = str(layer_name)

    if not all_params:
        return {}

    # 诊断引导权重：根据 primary_error_source 对特定参数加权
    diagnosis_weights: Dict[str, float] = {}
    if isinstance(diagnosis, dict):
        source = str(diagnosis.get("primary_error_source") or "")
        if source == "weekend_pattern_shift":
            # 周末误差大 → 优先探索日历特征开关和更大的 lags
            diagnosis_weights["holiday_features.enabled"] = 2.0
            diagnosis_weights["workday_features.enabled"] = 2.0
            diagnosis_weights["create_lag_features.lags"] = 1.5
        elif source == "data_coverage_insufficient":
            # 数据覆盖不足 → 优先缩短 train_days
            diagnosis_weights["train_days"] = 2.0
            diagnosis_weights["daily_horizon"] = 1.5
        elif source == "outlier_days":
            # 异常天误差大 → 优先探索差分特征和统计特征
            diagnosis_weights["diff_features.enabled"] = 2.0
            diagnosis_weights["extract_statistical_features.enabled"] = 1.5
        elif source == "model_divergence":
            # 模型间差异大 → 优先探索集成模式
            diagnosis_weights["ensemble_mode"] = 2.0
            diagnosis_weights["active_models"] = 1.5

    # 经验先验：历史成功 patch 中的参数值作为候选偏好
    prior_values: Dict[str, List[Any]] = {}
    for case in (memory_cases or []):
        if not isinstance(case, dict):
            continue
        if not bool((case.get("outcome") or {}).get("improved")):
            continue
        patch = case.get("applied_patch") or {}
        override = patch.get("override") or {}
        for k, v in override.items():
            if k in all_params:
                prior_values.setdefault(k, []).append(v)

    # 任务 29.3：首轮采样权重偏好——从历史 insight 的推荐配置加权（×2）
    # insight_prior 由调用方注入（_run_autoresearch_task 第一轮时传入）
    insight_prior: Dict[str, Any] = {}
    if hasattr(rng, '_insight_prior'):
        insight_prior = getattr(rng, '_insight_prior') or {}
    for k, v in insight_prior.items():
        if k in all_params:
            # 加入两次，相当于权重 ×2
            prior_values.setdefault(k, []).extend([v, v])

    # 决定采样策略
    use_random = rng.random() < 0.3  # 30% 纯随机

    sample: Dict[str, Any] = {}
    _locked = locked_params or {}
    focus = research_focus or {}
    priority_layers = set(str(x) for x in (focus.get("priority_layers") or []))
    avoid_layers = set(str(x) for x in (focus.get("avoid_layers") or []))
    import logging as _logging_30
    for param_key, param_spec in all_params.items():
        if not isinstance(param_spec, dict):
            continue
        if focus:
            layer_name = param_layers.get(str(param_key), "")
            layer_weight = 1.0
            if layer_name in priority_layers:
                layer_weight = 2.0
            elif layer_name in avoid_layers:
                layer_weight = 0.5
            include_probability = min(1.0, 0.5 * layer_weight)
            if rng.random() > include_probability:
                continue
        # 任务 30.1：跳过已锁定的参数（来自上一轮建议的 runtime_patch）
        fid = str(param_spec.get("node_function_id") or "")
        p_key = str(param_spec.get("param_key") or "")
        target_type = str(param_spec.get("patch_target") or "")
        # node_param 锁定键：functionId.param_key
        # structure_switch 锁定键：structure_switch.functionId
        if target_type == "structure_switch" and fid:
            lock_key = f"structure_switch.{fid}"
        elif fid and p_key:
            lock_key = f"{fid}.{p_key}"
        else:
            lock_key = param_key
        if lock_key in _locked or param_key in _locked:
            _logging_30.getLogger(__name__).debug(
                f"跳过已锁定参数: {lock_key}（来自上一轮建议）"
            )
            continue

        # 任务 32.2：条件参数处理——检查 condition 字段
        condition = str(param_spec.get("condition") or "").strip()
        if condition:
            # 简单条件解析：只处理 "key != value" 和 "key > 0" 两种格式
            try:
                if "!=" in condition:
                    cond_key, cond_val = [x.strip() for x in condition.split("!=", 1)]
                    if str(sample.get(cond_key, "")) == cond_val.strip():
                        continue  # 条件不满足，跳过
                elif "> 0" in condition:
                    cond_key = condition.replace("> 0", "").strip()
                    if not sample.get(cond_key):
                        continue  # 条件不满足，跳过
            except Exception:
                pass
        ptype = str(param_spec.get("type") or "categorical")
        options = param_spec.get("options") or []
        universe = param_spec.get("universe") or []
        min_size = int(param_spec.get("min_size") or 1)

        if use_random:
            # 纯随机
            if ptype == "boolean":
                sample[param_key] = rng.choice([True, False])
            elif ptype == "subset" and universe:
                k_size = rng.randint(min_size, len(universe))
                sample[param_key] = rng.sample(universe, k_size)
            elif options:
                sample[param_key] = rng.choice(options)
        else:
            # 诊断引导 + 经验先验
            weight = diagnosis_weights.get(param_key, 1.0)
            prior = prior_values.get(param_key, [])

            if ptype == "boolean":
                # 有先验时按先验频率，否则随机
                if prior:
                    true_count = sum(1 for v in prior if v is True)
                    p_true = (true_count + weight) / (len(prior) + 2 * weight)
                    sample[param_key] = rng.random() < p_true
                else:
                    sample[param_key] = rng.choice([True, False])
            elif ptype == "subset" and universe:
                k_size = rng.randint(min_size, len(universe))
                if prior and rng.random() < 0.6:
                    # 从先验中选
                    flat_prior = [v for sublist in prior if isinstance(sublist, list) for v in sublist]
                    if flat_prior:
                        preferred = list(set(flat_prior) & set(universe))
                        if preferred:
                            k_size = min(k_size, len(preferred))
                            sample[param_key] = rng.sample(preferred, k_size)
                        else:
                            sample[param_key] = rng.sample(universe, k_size)
                    else:
                        sample[param_key] = rng.sample(universe, k_size)
                else:
                    sample[param_key] = rng.sample(universe, k_size)
            elif options:
                if prior and rng.random() < min(0.7, weight * 0.5):
                    # 从先验中选（过滤出在 options 范围内的）
                    valid_prior = [v for v in prior if v in options]
                    if valid_prior:
                        sample[param_key] = rng.choice(valid_prior)
                    else:
                        sample[param_key] = rng.choice(options)
                else:
                    sample[param_key] = rng.choice(options)

    # 检查回避集：若命中则对该参数重新随机采样一次
    for bad in (avoid_set or []):
        if not isinstance(bad, dict):
            continue
        for param_key, bad_val in bad.items():
            if param_key in sample and sample[param_key] == bad_val:
                param_spec = all_params.get(param_key) or {}
                options = param_spec.get("options") or []
                if options:
                    alts = [v for v in options if v != bad_val]
                    if alts:
                        sample[param_key] = rng.choice(alts)

    # 任务 32.1：参数约束检查，不满足则重新采样（最多重试 5 次）
    for _retry in range(5):
        if _validate_sample_constraints(sample, registry):
            break
        # 约束违反，重新采样（纯随机，避免死循环）
        sample = {}
        for param_key, param_spec in all_params.items():
            if not isinstance(param_spec, dict):
                continue
            ptype = str(param_spec.get("type") or "categorical")
            options = param_spec.get("options") or []
            universe = param_spec.get("universe") or []
            min_size = int(param_spec.get("min_size") or 1)
            if ptype == "boolean":
                sample[param_key] = rng.choice([True, False])
            elif ptype == "subset" and universe:
                k_size = rng.randint(min_size, len(universe))
                sample[param_key] = rng.sample(universe, k_size)
            elif options:
                sample[param_key] = rng.choice(options)
    # 任务 32.2：条件参数处理——single_best 时移除 active_models
    if sample.get("ensemble_mode") == "single_best":
        sample.pop("active_models", None)

    return sample


def _sample_to_patches(
    sample: Dict[str, Any],
    registry: Dict[str, Any],
    workflow_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    任务 9.4：将采样结果转换为各类 patch，按 patch_target 分类路由。

    路由规则：
    - "global_config"  → global_config_patch dict
    - "node_param"     → node_param_patches 数组（需要 node_function_id + param_key）
    - "structure_switch" → structure_patch.node_switches 数组（需要 node_function_id）
    - "model_focus"    → model_focus 列表（active_models 子集）

    Args:
        sample（采样结果）: _sample_from_registry() 的返回值
        registry（注册表对象）: load_registry() 的返回值
        workflow_id（模板 ID）: 可选，用于从模板中查找 node_id（structure_switch 需要）

    Returns:
        {
            "structure_patch": {"node_switches": [...]},  # 结构开关补丁
            "node_param_patches": [...],                  # 节点参数补丁列表
            "global_config_patch": {...},                 # 全局配置补丁
            "model_focus": [...],                         # 关注模型列表
        }
    """
    # 收集所有层的参数定义（用于查找 patch_target）
    all_params: Dict[str, Any] = {}
    for _layer_name, layer_spec in (registry.get("layers") or {}).items():
        params = (layer_spec or {}).get("params") or {}
        all_params.update(params)

    global_config_patch: Dict[str, Any] = {}
    node_param_patches: List[Dict[str, Any]] = []
    node_switches: List[Dict[str, Any]] = []
    model_focus: List[str] = []

    # 若需要 structure_switch，尝试从模板中查找 node_id
    node_id_by_function: Dict[str, str] = {}
    if workflow_id:
        try:
            wf = load_workflow_from_file(str(workflow_id).strip())
            if wf is not None:
                for n in (wf.dict().get("nodes") or []):
                    nid = str(n.get("id") or "").strip()
                    cfg = ((n.get("data") or {}).get("config") or {})
                    fid = str(cfg.get("functionId") or "").strip()
                    if nid and fid:
                        node_id_by_function[fid] = nid
        except Exception:
            pass

    for param_key, value in sample.items():
        param_spec = all_params.get(param_key)
        if not isinstance(param_spec, dict):
            continue
        target = str(param_spec.get("patch_target") or "global_config")
        func_id = str(param_spec.get("node_function_id") or "").strip()
        p_key = str(param_spec.get("param_key") or "").strip()

        if target == "global_config":
            # 直接写入 global_config_patch
            gc_key = p_key or param_key
            global_config_patch[gc_key] = value

        elif target == "node_param":
            # 写入 node_param_patches 数组
            if func_id and p_key:
                node_id = node_id_by_function.get(func_id, "")
                node_param_patches.append({
                    "node_id": node_id,
                    "functionId": func_id,
                    "param_patch": {p_key: value},
                })

        elif target == "structure_switch":
            # 写入 node_switches 数组（boolean 类型）
            if func_id and isinstance(value, bool):
                node_id = node_id_by_function.get(func_id, "")
                node_switches.append({
                    "node_id": node_id,
                    "functionId": func_id,
                    "enabled": value,
                })

        elif target == "model_focus":
            # active_models 子集 → model_focus 列表
            if isinstance(value, list):
                model_focus = [str(v) for v in value if v]
            elif isinstance(value, str) and value:
                model_focus = [value]

    return {
        "structure_patch": {"node_switches": node_switches} if node_switches else {},
        "node_param_patches": node_param_patches,
        "global_config_patch": global_config_patch,
        "model_focus": model_focus,
    }


def _force_override_diff_from_contract(
    override: Dict[str, Any],
    search_space: Dict[str, Any],
    contract: Dict[str, Any],
    iteration: int,
    seed: int,
    registry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    保证 challenger 覆盖参数至少有一个与 baseline contract 不同，避免"同参白跑"导致分差恒 0。
    任务 31.1：有注册表时从注册表选项重新选值，避免产出极端值（如 train_days=2）。
    """
    if not isinstance(override, dict):
        return {}
    contract = contract or {}
    differs = False
    for k, v in override.items():
        if k not in contract and v not in (None, "", [], {}):
            differs = True
            break
        if k in contract and contract[k] != v:
            differs = True
            break
    if differs:
        return override

    rng = random.Random(seed + iteration * 104729)

    # 任务 31.1：有注册表时，从注册表选项中选一个不同的值（避免极端值）
    if registry and isinstance(registry, dict) and registry.get("registry_id") != "__empty__":
        all_reg_params: Dict[str, Any] = {}
        for _layer in (registry.get("layers") or {}).values():
            all_reg_params.update((_layer.get("params") or {}))
        for k, v in (search_space or {}).items():
            key = str(k).strip()
            if not key:
                continue
            base_val = contract.get(key)
            reg_param = all_reg_params.get(key) or {}
            reg_options = reg_param.get("options") or []
            if isinstance(reg_options, list) and len(reg_options) > 1:
                candidates = [x for x in reg_options if x != base_val]
                if candidates:
                    override[key] = candidates[rng.randrange(0, len(candidates))]
                    return override
            if isinstance(v, list) and len(v) > 1:
                candidates = [x for x in v if x != base_val]
                if candidates:
                    override[key] = candidates[rng.randrange(0, len(candidates))]
                    return override
        return override

    # 旧逻辑（无注册表时）
    for k, v in (search_space or {}).items():
        key = str(k).strip()
        if not key:
            continue
        if not isinstance(v, list) or len(v) <= 1:
            continue
        base_val = contract.get(key)
        candidates = [x for x in v if x != base_val]
        if not candidates:
            continue
        override[key] = candidates[rng.randrange(0, len(candidates))]
        return override
    return override


_ALLOWED_EVAL_PATCH_KEYS = {
    "train_days",
    "backtest_train_days",
    "auto_tune_n_trials",
    "daily_horizon",
    "backtest_apply_window_filter",
    "backtest_mask_target_values",
    "backtest_mode",
}
_ALLOWED_SEARCH_SPACE_PATCH_KEYS = {
    "train_days",
    "backtest_train_days",
    "auto_tune_n_trials",
    "daily_horizon",
    "backtest_apply_window_filter",
    "backtest_mask_target_values",
    # deep search v1: xgboost bayes bounds
    "xgb_eta_low",
    "xgb_eta_high",
    "xgb_max_depth_low",
    "xgb_max_depth_high",
    "xgb_subsample_low",
    "xgb_subsample_high",
    "xgb_lambda_low",
    "xgb_lambda_high",
    "xgb_min_child_weight_low",
    "xgb_min_child_weight_high",
    # Phase B：特征配方 id 枚举（值为字符串数组，元素须存在于 feature_recipes.json）
    "feature_recipe_id",
    # 任务 3.1：扩展搜索空间白名单
    "backtest_mode",
    "sliding_window.window_size",
    "sliding_window.step",
    "xgb_n_estimators",
    # H3 FIX: feature node enable/disable keys (11 total, previously missing)
    "enable_auto_tune_xgboost",
    "enable_xgboost_forecast",
    "enable_lightgbm_forecast",
    "enable_catboost_forecast",
    "enable_ridge_forecast",
    "enable_ensemble_forecast",
    "enable_create_lag_features",
    "enable_rolling_statistics",
    "enable_detect_outliers",
    "enable_train_test_split_ts",
}

# AutoResearch 采样覆盖里不写进 evaluation/global 合同的键（结构层单独消费）
_AUTORESEARCH_META_OVERRIDE_KEYS = frozenset({"feature_recipe_id"})

# Phase D：runtime_patch.global_config_patch（写入模板 metadata.global_config，先于 contract 合并）
_ALLOWED_GLOBAL_CONFIG_PATCH_KEYS: Set[str] = frozenset({
    "use_reference_rolling_engine",
    "backtest_mode",
    "backtest_train_days",
    "backtest_bo_n_iter",
    "backtest_use_bayesian_tuning",
    "backtest_apply_window_filter",
    "backtest_mask_target_values",
    "strict_alignment_mode",
    "model_type",
    "auto_tune_n_trials",
    # @AI_GENERATED
    "backtest_gap_days",  # 训练截止到 pred_day - 1 - gap_days，默认 1（D-2），0 为无 gap
    "xgb_eta_low",
    "xgb_eta_high",
    "xgb_max_depth_low",
    "xgb_max_depth_high",
    "xgb_min_child_weight_low",
    "xgb_min_child_weight_high",
    "xgb_subsample_low",
    "xgb_subsample_high",
    "xgb_lambda_low",
    "xgb_lambda_high",
    "xgb_seed",
    "xgb_nthread",
    # @AI_GENERATED: end
})

# functionId -> 节点 param_patch 允许键 -> 类型（与 params-summary 对齐，限可自动建议/应用范围）
_AUTORESEARCH_NODE_PARAM_FIELDS: Dict[str, Dict[str, str]] = {
    "auto_tune_xgboost": {"n_trials": "int", "cv_folds": "int", "metric": "str"},
    "xgboost_forecast": {
        "n_estimators": "int",
        "local_parity_bo_n_iter": "int",
        "local_parity_use_bayesian_tuning": "bool",
        "local_parity_n_splits": "int",
        "separate_modeling": "str",
        "prefer_unit_len": "int",
        "sample_weight_decay": "float",
    },
    "lightgbm_forecast": {"n_estimators": "int", "separate_modeling": "str", "sample_weight_decay": "float"},
    "catboost_forecast": {"n_estimators": "int", "separate_modeling": "str", "sample_weight_decay": "float"},
    "ridge_forecast": {"separate_modeling": "str"},
    "ensemble_forecast": {"weight_mode": "str", "prediction_keys": "str"},
    "create_lag_features": {"lag_days": "list", "lags": "list"},
    "rolling_statistics": {"window_sizes": "list", "statistics": "list", "base_shift": "int"},
    "detect_outliers": {"threshold": "float", "window_size": "int"},
    "train_test_split_ts": {"train_ratio": "float", "val_ratio": "float"},
}

_AUTORESEARCH_MAX_NODE_PARAM_PATCH_ITEMS = 24

# Phase C：节点 config 浅合并白名单（functionId -> 允许的 config 键）
_ALLOWED_NODE_CONFIG_PATCH_KEYS_BY_FUNCTION: Dict[str, Set[str]] = {
    "sliding_window": {"window_size", "step"},
}

_FEATURE_STRUCTURE_SWITCH_FUNCTIONS = frozenset({
    "holiday_features",
    "workday_features",
    "rolling_statistics",
    "create_lag_features",
    "diff_features",
    "extract_statistical_features",
})

_FORECAST_STRUCTURE_AUX_FUNCTIONS = frozenset({"auto_tune_xgboost", "ensemble_forecast"})
# 关注模型补丁里不参与「至少保留一个叶子预报」统计（编排/集成/调参入口）
_MODEL_FOCUS_NON_LEAF_REGISTERED = frozenset(
    {"ensemble_forecast", "auto_tune_xgboost", "multi_step_forecast"}
)


def _registered_ts_forecast_operator_ids() -> Set[str]:
    snap = _discover_forecast_operators_payload()
    return {
        str(x.get("function_id")).strip()
        for x in (snap.get("operators") or [])
        if isinstance(x, dict) and x.get("function_id")
    }


def _structure_switch_allowed(fid: str) -> bool:
    if fid in _FEATURE_STRUCTURE_SWITCH_FUNCTIONS:
        return True
    if fid in _FORECAST_STRUCTURE_AUX_FUNCTIONS:
        return True
    return fid in _registered_ts_forecast_operator_ids()


def _glm_structure_patch_whitelist_keys() -> List[str]:
    return sorted(set(_FEATURE_STRUCTURE_SWITCH_FUNCTIONS) | _FORECAST_STRUCTURE_AUX_FUNCTIONS | _registered_ts_forecast_operator_ids())


def _proposal_structure_switch_cap(switches: List[Any]) -> int:
    """提案里 node_switches 数量上限：特征开关保守；模型族可多节点并行开关。"""
    if not switches:
        return 2
    fids: List[str] = []
    for it in switches:
        if not isinstance(it, dict):
            return 2
        fids.append(str(it.get("functionId") or "").strip())
    model_aux = set(_FORECAST_STRUCTURE_AUX_FUNCTIONS) | _registered_ts_forecast_operator_ids()
    if fids and all(x in model_aux for x in fids):
        return 24
    if fids and all(x in _FEATURE_STRUCTURE_SWITCH_FUNCTIONS for x in fids):
        return 6  # 特征开关：允许一次改多个（GLM 可能建议同时开/关多个特征节点）
    return 8


def _merge_structure_patches(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """合并 structure_patch：overlay 覆盖同 node_id 的开关。"""
    out = dict(base or {})
    ovr = dict(overlay or {})
    out.update({k: v for k, v in ovr.items() if k != "node_switches"})
    bs = base.get("node_switches") if isinstance(base.get("node_switches"), list) else []
    oswitches = ovr.get("node_switches") if isinstance(ovr.get("node_switches"), list) else []
    by_id: Dict[str, Dict[str, Any]] = {}
    for item in bs:
        if isinstance(item, dict) and item.get("node_id"):
            nid = str(item["node_id"]).strip()
            if nid:
                by_id[nid] = dict(item)
    for item in oswitches:
        if isinstance(item, dict) and item.get("node_id"):
            nid = str(item["node_id"]).strip()
            if nid:
                prev = by_id.get(nid, {})
                merged = {**prev, **item}
                by_id[nid] = merged
    out["node_switches"] = list(by_id.values())
    return out


def _merge_structure_patch_bundle(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """合并 Phase A/B/C：node_switches（按 node_id）+ node_config_patches（按 node_id 浅合并 config_patch）。"""
    base = dict(base or {})
    overlay = dict(overlay or {})
    bs_sw = base.get("node_switches") if isinstance(base.get("node_switches"), list) else []
    ov_sw = overlay.get("node_switches") if isinstance(overlay.get("node_switches"), list) else []
    sw_merged = _merge_structure_patches({"node_switches": bs_sw}, {"node_switches": ov_sw})
    out: Dict[str, Any] = {"node_switches": sw_merged.get("node_switches") or []}
    bm: Dict[str, Dict[str, Any]] = {}
    for item in base.get("node_config_patches") if isinstance(base.get("node_config_patches"), list) else []:
        if isinstance(item, dict) and item.get("node_id"):
            nid = str(item["node_id"]).strip()
            if nid:
                bm[nid] = dict(item)
    for item in overlay.get("node_config_patches") if isinstance(overlay.get("node_config_patches"), list) else []:
        if isinstance(item, dict) and item.get("node_id"):
            nid = str(item["node_id"]).strip()
            if nid:
                prev = bm.get(nid, {})
                p_cp = prev.get("config_patch") if isinstance(prev.get("config_patch"), dict) else {}
                o_cp = item.get("config_patch") if isinstance(item.get("config_patch"), dict) else {}
                merged_cp = {**p_cp, **o_cp}
                bm[nid] = {**prev, **item, "node_id": nid, "config_patch": merged_cp}
    out["node_config_patches"] = list(bm.values())
    return out


def _merge_global_config_patch_bundle(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for k, v in dict(overlay or {}).items():
        sk = str(k).strip()
        if sk in _ALLOWED_GLOBAL_CONFIG_PATCH_KEYS:
            out[sk] = v
    return out


def _build_model_focus_structure_patch(workflow_id: str, model_focus: List[str]) -> Dict[str, Any]:
    """把模型关注列表转换成 workflow node_switches。"""
    focus_set = {str(x).strip() for x in (model_focus or []) if str(x).strip()}
    if not focus_set:
        return {}
    wf = load_workflow_from_file(str(workflow_id).strip())
    if wf is None:
        return {}
    try:
        nodes = wf.dict().get("nodes") or []
    except Exception:
        nodes = []
    model_function_ids = {
        "xgboost_forecast",
        "lightgbm_forecast",
        "catboost_forecast",
        "ridge_forecast",
    }
    switches: List[Dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        cfg = ((node.get("data") or {}).get("config") or {})
        func_id = str(cfg.get("functionId") or "").strip()
        if not node_id or func_id not in model_function_ids:
            continue
        switches.append({
            "node_id": node_id,
            "functionId": func_id,
            "enabled": func_id in focus_set,
        })
    return {"node_switches": switches} if switches else {}


def _merge_node_param_patches_bundle(base: Any, overlay: Any) -> List[Dict[str, Any]]:
    bm: Dict[str, Dict[str, Any]] = {}
    for item in base if isinstance(base, list) else []:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("node_id") or "").strip()
        if not nid:
            continue
        prev = bm.get(nid, {})
        p_pp = prev.get("param_patch") if isinstance(prev.get("param_patch"), dict) else {}
        o_pp = item.get("param_patch") if isinstance(item.get("param_patch"), dict) else {}
        merged_pp = {**p_pp, **o_pp}
        bm[nid] = {**prev, **item, "node_id": nid, "param_patch": merged_pp}
    for item in overlay if isinstance(overlay, list) else []:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("node_id") or "").strip()
        if not nid:
            continue
        prev = bm.get(nid, {})
        p_pp = prev.get("param_patch") if isinstance(prev.get("param_patch"), dict) else {}
        o_pp = item.get("param_patch") if isinstance(item.get("param_patch"), dict) else {}
        merged_pp = {**p_pp, **o_pp}
        bm[nid] = {**prev, **item, "node_id": nid, "param_patch": merged_pp}
    return list(bm.values())


def _coerce_node_param_value(vtype: str, val: Any) -> Tuple[Any, Optional[str]]:
    t = str(vtype or "").strip().lower()
    if t == "int":
        try:
            return int(val), None
        except (TypeError, ValueError):
            return None, "须为整数"
    if t == "float":
        try:
            return float(val), None
        except (TypeError, ValueError):
            return None, "须为数值"
    if t == "bool":
        if isinstance(val, bool):
            return val, None
        s = str(val).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True, None
        if s in ("0", "false", "no", "off"):
            return False, None
        return None, "须为布尔"
    if t == "str":
        return str(val), None
    if t == "list":
        if not isinstance(val, list):
            return None, "须为数组"
        if len(val) > 64:
            return None, "数组过长(>64)"
        return val, None
    return None, f"未知类型 {vtype}"


def _validate_global_config_patch_entries(patch: Any) -> List[str]:
    errs: List[str] = []
    if patch is None:
        return errs
    if not isinstance(patch, dict):
        return ["global_config_patch 必须为对象"]
    for k, v in patch.items():
        sk = str(k).strip()
        if sk not in _ALLOWED_GLOBAL_CONFIG_PATCH_KEYS:
            errs.append(f"global_config_patch 不允许字段: {sk}")
            continue
        if sk in (
            "use_reference_rolling_engine",
            "backtest_use_bayesian_tuning",
            "backtest_apply_window_filter",
            "backtest_mask_target_values",
            "strict_alignment_mode",
        ):
            if not isinstance(v, bool):
                errs.append(f"global_config_patch.{sk} 必须为布尔")
        elif sk == "backtest_mode":
            if str(v).strip().lower() not in ("rolling_retrain", "inference_only"):
                errs.append("global_config_patch.backtest_mode 仅允许 rolling_retrain / inference_only")
        elif sk == "model_type":
            if str(v).strip().lower() not in ("xgboost", "lightgbm", "catboost", "ridge"):
                errs.append("global_config_patch.model_type 取值不在白名单")
        elif sk == "backtest_train_days":
            try:
                iv = int(v)
                if iv < 1 or iv > 730:
                    errs.append("global_config_patch.backtest_train_days 范围 1..730")
            except (TypeError, ValueError):
                errs.append("global_config_patch.backtest_train_days 须为整数")
        elif sk == "backtest_bo_n_iter":
            try:
                iv = int(v)
                if iv < 1 or iv > 200:
                    errs.append("global_config_patch.backtest_bo_n_iter 范围 1..200")
            except (TypeError, ValueError):
                errs.append("global_config_patch.backtest_bo_n_iter 须为整数")
        elif sk == "auto_tune_n_trials":
            try:
                iv = int(v)
                if iv < 1 or iv > 100:
                    errs.append("global_config_patch.auto_tune_n_trials 范围 1..100")
            except (TypeError, ValueError):
                errs.append("global_config_patch.auto_tune_n_trials 须为整数")
    return errs


def _validate_node_param_patches_autoresearch(wf_id: str, patches: Any) -> List[str]:
    errs: List[str] = []
    if patches is None:
        return errs
    if not isinstance(patches, list):
        return ["node_param_patches 必须为数组"]
    if len(patches) > _AUTORESEARCH_MAX_NODE_PARAM_PATCH_ITEMS:
        errs.append(f"node_param_patches 最多 {_AUTORESEARCH_MAX_NODE_PARAM_PATCH_ITEMS} 条")
        return errs
    wf = load_workflow_from_file(str(wf_id).strip())
    if wf is None:
        return [f"模板不存在，无法校验 node_param_patches: {wf_id}"]
    node_map = {str(n.get("id")): n for n in (wf.dict().get("nodes") or [])}
    for idx, item in enumerate(patches):
        if not isinstance(item, dict):
            errs.append(f"node_param_patches[{idx}] 必须为对象")
            continue
        node_id = str(item.get("node_id") or "").strip()
        pp = item.get("param_patch")
        if not node_id:
            errs.append(f"node_param_patches[{idx}].node_id 不能为空")
            continue
        if not isinstance(pp, dict):
            errs.append(f"node_param_patches[{idx}].param_patch 必须为对象")
            continue
        node = node_map.get(node_id)
        if not isinstance(node, dict):
            errs.append(f"node_param_patches[{idx}] 未知 node_id: {node_id}")
            continue
        cfg = ((node.get("data") or {}).get("config") or {})
        fid = str(cfg.get("functionId") or "").strip()
        declared = str(item.get("functionId") or "").strip()
        if declared and declared != fid:
            errs.append(f"node_param_patches[{idx}] functionId 与模板不符（模板={fid}）")
            continue
        allowed_map = _AUTORESEARCH_NODE_PARAM_FIELDS.get(fid)
        if not allowed_map:
            errs.append(f"node_param_patches[{idx}] 不支持 patches 的 functionId={fid}")
            continue
        for pk, pv in pp.items():
            key = str(pk).strip()
            if key not in allowed_map:
                errs.append(f"node_param_patches[{idx}] 不允许字段 {key}")
                continue
            vtype = allowed_map[key]
            _, verr = _coerce_node_param_value(vtype, pv)
            if verr:
                errs.append(f"node_param_patches[{idx}].param_patch.{key}: {verr}")
    return errs


def _apply_runtime_parameter_layers_to_workflow(
    workflow: Any,
    global_config_patch: Optional[Dict[str, Any]],
    node_param_patches: Optional[List[Dict[str, Any]]],
) -> Any:
    """在结构补丁之后应用：合并 global_config + 节点 config（仅白名单键）。"""
    wf_dict = workflow.dict()
    meta = dict(wf_dict.get("metadata") or {})
    gc = dict(meta.get("global_config") or {})
    if isinstance(global_config_patch, dict):
        for k, v in global_config_patch.items():
            sk = str(k).strip()
            if sk not in _ALLOWED_GLOBAL_CONFIG_PATCH_KEYS:
                continue
            gc[sk] = v
    meta["global_config"] = gc
    wf_dict["metadata"] = meta

    node_map = {str(n.get("id")): n for n in (wf_dict.get("nodes") or [])}
    if isinstance(node_param_patches, list):
        for item in node_param_patches:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "").strip()
            pp = item.get("param_patch") if isinstance(item.get("param_patch"), dict) else {}
            if not node_id or not pp:
                continue
            node = node_map.get(node_id)
            if not isinstance(node, dict):
                continue
            data = dict(node.get("data") or {})
            cfg = dict(data.get("config") or {})
            fid = str(cfg.get("functionId") or "").strip()
            allowed_map = _AUTORESEARCH_NODE_PARAM_FIELDS.get(fid)
            if not allowed_map:
                continue
            for pk, pv in pp.items():
                key = str(pk).strip()
                if key not in allowed_map:
                    continue
                vtype = allowed_map[key]
                coerced, _ = _coerce_node_param_value(vtype, pv)
                if coerced is None:
                    continue
                cfg[key] = coerced
            data["config"] = cfg
            node["data"] = data
            node_map[node_id] = node
    wf_dict["nodes"] = list(node_map.values())
    return EnhancedWorkflow(**wf_dict)


def _build_light_parameter_hints_from_workflow(wf_id: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """规则建议：从模板推导一小步参数层 hint（不改变结构）。"""
    wf = load_workflow_from_file(str(wf_id).strip())
    if wf is None:
        return {}, []
    gcp: Dict[str, Any] = {}
    npp: List[Dict[str, Any]] = []
    meta_gc = dict((wf.metadata or {}).get("global_config") or {})
    bo = meta_gc.get("backtest_bo_n_iter")
    try:
        bi = int(bo) if bo is not None else None
    except (TypeError, ValueError):
        bi = None
    use_bt = meta_gc.get("backtest_use_bayesian_tuning")
    if bi is not None:
        gcp["backtest_bo_n_iter"] = min(bi + 2, 48)
    elif use_bt is False:
        gcp["backtest_use_bayesian_tuning"] = True
    for n in (wf.dict().get("nodes") or []):
        nid = str(n.get("id") or "").strip()
        cfg = ((n.get("data") or {}).get("config") or {})
        fid = str(cfg.get("functionId") or "").strip()
        if fid == "xgboost_forecast":
            try:
                n_est = int(cfg.get("n_estimators")) if cfg.get("n_estimators") is not None else 120
            except (TypeError, ValueError):
                n_est = 120
            npp.append({"node_id": nid, "functionId": fid, "param_patch": {"n_estimators": min(n_est + 80, 800)}})
            break
        if fid == "auto_tune_xgboost":
            try:
                nt_i = int(cfg.get("n_trials")) if cfg.get("n_trials") is not None else 30
            except (TypeError, ValueError):
                nt_i = 30
            npp.append({"node_id": nid, "functionId": fid, "param_patch": {"n_trials": min(nt_i + 5, 40)}})
            break
        if fid == "create_lag_features":
            npp.append({
                "node_id": nid,
                "functionId": fid,
                "param_patch": {"lags": [1, 2, 3, 7, 14]},
            })
            break
        if fid == "rolling_statistics":
            npp.append({
                "node_id": nid,
                "functionId": fid,
                "param_patch": {"window_sizes": [4, 8, 24, 96]},
            })
            break
    return gcp, npp
    """
    根据「关注模型」构造 challenger 结构补丁：仅开启 preferred 中的 ts_forecast 算子节点，
    其余已在模板中的同类节点关闭；multi_step_forecast / ensemble_forecast 始终开启；
    auto_tune_xgboost 仅在偏好包含 xgboost_forecast 时开启；
    ensemble_forecast 若在 discovery 列表中须先于 registered 分支处理（见下属分支顺序）。
    """
    pref = {str(x).strip() for x in (preferred_operator_ids or []) if str(x).strip()}
    if not pref:
        return {}
    wf = load_workflow_from_file(workflow_id)
    if wf is None:
        return {}
    registered = _registered_ts_forecast_operator_ids()
    switches: List[Dict[str, Any]] = []
    for n in (wf.dict().get("nodes") or []):
        node_id = str(n.get("id") or "").strip()
        if not node_id:
            continue
        cfg = ((n.get("data") or {}).get("config") or {})
        fid = str(cfg.get("functionId") or "").strip()
        # ensemble_forecast 也在 discovery 的 ts_forecast 列表里，必须先于 registered 分支处理，否则会按偏好被关掉。
        if fid == "ensemble_forecast":
            switches.append({"node_id": node_id, "enabled": True, "functionId": fid})
        elif fid == "multi_step_forecast":
            # 多步预测配置属编排节点，不应随「叶子预报偏好」被关掉
            switches.append({"node_id": node_id, "enabled": True, "functionId": fid})
        elif fid == "auto_tune_xgboost":
            switches.append({"node_id": node_id, "enabled": "xgboost_forecast" in pref, "functionId": fid})
        elif fid in registered:
            switches.append({"node_id": node_id, "enabled": fid in pref, "functionId": fid})
    enabled_models = [
        s
        for s in switches
        if s.get("enabled")
        and s.get("functionId") in registered
        and s.get("functionId") not in _MODEL_FOCUS_NON_LEAF_REGISTERED
    ]
    if not enabled_models:
        return {}
    return {"node_switches": switches}


def _build_ensemble_mode_patches(
    workflow_id: str,
    ensemble_mode: str,
    active_models: Optional[List[str]] = None,
    weight_strategy: str = "equal",
) -> Dict[str, Any]:
    """
    任务 11.1：根据 ensemble_mode 生成 structure_patch + node_param_patches。

    三种模式：
    - "single_best"（单模型）：只开一个模型节点，关闭 ensemble_forecast 节点
    - "all_adaptive"（全模型自适应）：全部模型开 + ensemble 开 + weight_strategy=oof_rmse_inverse
    - "subset_adaptive"（子集自适应）：active_models 子集开 + ensemble 开 + weight_strategy=oof_rmse_inverse

    Args:
        workflow_id（模板 ID）: 用于查找节点 ID
        ensemble_mode（集成模式）: "single_best" / "all_adaptive" / "subset_adaptive"
        active_models（激活模型列表）: subset_adaptive 时指定子集；single_best 时取第一个
        weight_strategy（权重策略）: "equal"（等权）/ "oof_rmse_inverse"（OOF RMSE 逆权重）

    Returns:
        {
            "structure_patch": {"node_switches": [...]},
            "node_param_patches": [...],
        }
    """
    wf = load_workflow_from_file(str(workflow_id).strip())
    if wf is None:
        return {"structure_patch": {}, "node_param_patches": []}

    registered = _registered_ts_forecast_operator_ids()
    mode = str(ensemble_mode or "single_best").strip()
    models = [str(m).strip() for m in (active_models or []) if str(m).strip()]

    switches: List[Dict[str, Any]] = []
    ensemble_node_id: Optional[str] = None

    for n in (wf.dict().get("nodes") or []):
        node_id = str(n.get("id") or "").strip()
        if not node_id:
            continue
        cfg = ((n.get("data") or {}).get("config") or {})
        fid = str(cfg.get("functionId") or "").strip()

        if fid == "ensemble_forecast":
            ensemble_node_id = node_id
            # single_best 关闭 ensemble，其他模式开启
            switches.append({
                "node_id": node_id,
                "functionId": fid,
                "enabled": mode != "single_best",
            })
        elif fid in registered:
            if mode == "single_best":
                # 只开第一个（或 active_models 中的第一个）
                target = models[0] if models else None
                already_has_enabled = any(
                    s.get("enabled") and s.get("functionId") in registered
                    for s in switches
                )
                enabled = (target is None and not already_has_enabled) or (fid == target)
                switches.append({"node_id": node_id, "functionId": fid, "enabled": enabled})
            elif mode == "all_adaptive":
                switches.append({"node_id": node_id, "functionId": fid, "enabled": True})
            elif mode == "subset_adaptive":
                switches.append({"node_id": node_id, "functionId": fid, "enabled": fid in models})

    # ensemble 节点的 weight_strategy 参数
    node_param_patches: List[Dict[str, Any]] = []
    if mode in ("all_adaptive", "subset_adaptive") and ensemble_node_id:
        ws = weight_strategy if weight_strategy in ("equal", "oof_rmse_inverse") else "equal"
        node_param_patches.append({
            "node_id": ensemble_node_id,
            "functionId": "ensemble_forecast",
            "param_patch": {"weight_strategy": ws},
        })

    return {
        "structure_patch": {"node_switches": switches} if switches else {},
        "node_param_patches": node_param_patches,
    }


def _match_similar_run_insights(
    current_fingerprint: Dict[str, Any],
    current_registry_id: str,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    任务 29.1：从历史 insights 中找最相似的 K 个。

    评分：registry_id 匹配（0.4 权重）+ 场景指纹相似度（0.6 权重）

    Args:
        current_fingerprint（当前场景指纹）: _compute_scenario_fingerprint 的输出
        current_registry_id（当前注册表 ID）: 用于优先匹配同类型实验
        top_k（返回数量）: 默认 3

    Returns:
        按相似度排序的 insight 列表（完整内容）
    """
    index = _load_insight_index()
    if not index:
        return []

    scored: List[tuple] = []
    for entry in index:
        if not isinstance(entry, dict):
            continue
        # registry_id 匹配分
        registry_match = 1.0 if str(entry.get("registry_id") or "") == str(current_registry_id or "") else 0.0
        # 场景指纹相似度（复用已有的 _fingerprint_similarity 函数）
        entry_fp = entry.get("fingerprint") or {}
        fp_sim = 0.5  # 默认中性分
        try:
            # 使用 _retrieve_memory_cases 里的内部函数逻辑
            score_val = 0.0
            weight_total = 0.0
            for key, w in [("granularity", 0.2), ("load_type", 0.15), ("seasonality", 0.1),
                           ("weekend_sensitivity", 0.1), ("backtest_mode", 0.1)]:
                va = current_fingerprint.get(key)
                vb = entry_fp.get(key)
                weight_total += w
                if va is None or vb is None:
                    score_val += w * 0.5
                elif va == vb:
                    score_val += w
            for key, w, scale in [("train_days", 0.15, 30.0), ("span_days", 0.1, 90.0),
                                   ("anomaly_ratio", 0.1, 0.3)]:
                va = current_fingerprint.get(key)
                vb = entry_fp.get(key)
                weight_total += w
                if va is None or vb is None:
                    score_val += w * 0.5
                else:
                    diff = abs(float(va) - float(vb)) / max(scale, 1e-6)
                    score_val += w * max(0.0, 1.0 - diff)
            fp_sim = score_val / weight_total if weight_total > 0 else 0.5
        except Exception:
            fp_sim = 0.5

        total_score = registry_match * 0.4 + fp_sim * 0.6
        scored.append((entry, total_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    results = []
    for entry, sim in scored[:top_k]:
        run_id = str(entry.get("run_id") or "")
        insight = _load_run_insight(run_id)
        if insight:
            insight["_similarity_score"] = round(sim, 3)
            results.append(insight)
    return results


def _load_insight_index() -> List[Dict[str, Any]]:
    """加载 insight 索引文件。"""
    data = _load_json_with_fallback(_RUN_INSIGHTS_INDEX_JSON, _LEGACY_RUN_INSIGHTS_INDEX_JSON, [])
    return list(data) if isinstance(data, list) else []


def _save_insight_index(index: List[Dict[str, Any]]) -> None:
    """保存 insight 索引文件。"""
    with _AUTO_RESEARCH_FILE_LOCK:
        _atomic_write_json(_RUN_INSIGHTS_INDEX_JSON, index)


def _load_run_insight(run_id: str) -> Optional[Dict[str, Any]]:
    """加载单个 run 的 insight。"""
    data = _load_json_with_fallback(
        arp.as_str(arp.insight_path(run_id)),
        arp.as_str(arp.legacy_insight_path(run_id)),
        None,
    )
    return data if isinstance(data, dict) else None


def _save_run_insight(run_id: str, insight: Dict[str, Any]) -> None:
    """保存单个 run 的 insight，并更新索引。"""
    with _AUTO_RESEARCH_FILE_LOCK:
        path = arp.as_str(arp.insight_path(run_id))
        _atomic_write_json(path, insight)
        # 更新索引
        index = _load_insight_index()
        # 移除旧条目（如有）
        index = [e for e in index if str(e.get("run_id") or "") != run_id]
        index.append({
            "run_id": run_id,
            "created_at": insight.get("created_at") or datetime.now().isoformat(),
            "baseline_workflow_id": insight.get("baseline_workflow_id"),
            "registry_id": insight.get("registry_id"),
            "best_mape_improvement": insight.get("best_mape_improvement"),
            "fingerprint": insight.get("scenario_fingerprint") or {},
            "learned_rules_preview": (insight.get("learned_rules") or [])[:3],
        })
        _save_insight_index(index)


def _generate_run_insight(run_id: str) -> Dict[str, Any]:
    """
    任务 28.1：从 run_state 生成结构化复盘（run_insight）。

    两步：
    1. 规则提取（必做）：从 iterations / insights / disproved_hypotheses / best_candidate 自动提取
    2. GLM 增强（可选）：让 GLM 写 open_questions 和更好的 learned_rules

    Args:
        run_id（运行 ID）: _auto_research_store 中的 key

    Returns:
        完整的 insight dict
    """
    state = _auto_research_store.get(run_id)
    if state is None:
        return {"error": f"run 不存在: {run_id}"}
    return _auto_research_insight_builder.build(
        run_id,
        state,
        scenario_fingerprint=_compute_scenario_fingerprint(state),
    )


async def _generate_run_insight_with_glm(run_id: str) -> Dict[str, Any]:
    """
    任务 28.2：GLM 增强 insight——让 GLM 写 open_questions 和更好的 learned_rules。
    GLM 不可用时降级为规则版本。
    """
    insight = _generate_run_insight(run_id)
    if "error" in insight:
        return insight

    if not _env_bool("GLM_ENABLE", False):
        return insight

    try:
        system_prompt = (
            "你是一位机器学习实验分析师。根据提供的实验复盘数据，"
            "生成 open_questions（未解决问题）和改进后的 learned_rules（学到的规律）。"
            "只输出 JSON，格式：{\"open_questions\": [...], \"learned_rules\": [...]}"
        )
        user_prompt = (
            f"实验复盘数据：\n{json.dumps(insight, ensure_ascii=False)}\n\n"
            "请生成：\n"
            "1. open_questions：2-3 个未解决的问题（如某类误差始终降不下来）\n"
            "2. learned_rules：改进后的规律描述（更有洞察，不只是复述数据）\n"
            "输出 JSON：{\"open_questions\": [...], \"learned_rules\": [...]}"
        )
        resp = await _glm_chat_json(system_prompt, user_prompt, temperature=0.3)
        raw = resp.get("content") or ""
        extracted = _extract_json_block(raw) or raw
        obj = _strict_json_loads(extracted)
        if isinstance(obj, dict):
            if isinstance(obj.get("open_questions"), list):
                insight["open_questions"] = obj["open_questions"]
            if isinstance(obj.get("learned_rules"), list) and obj["learned_rules"]:
                insight["learned_rules"] = obj["learned_rules"]
    except Exception:
        pass  # 降级为规则版本

    return insight


def _auto_match_registry_for_workflow(workflow_id: str) -> str:
    """
    任务 25.1：自动匹配最适合当前模板的搜索空间注册表。

    第六代默认优先匹配 v3（带 actions 字段的 registry），
    如果没有 v3 或 v3 不适用才 fallback 到 v1/v2。

    Args:
        workflow_id（模板 ID）: baseline 模板 ID

    Returns:
        最匹配的 registry_id，或空字符串（无匹配时）
    """
    try:
        from services.autoresearch_registry_service import load_registry, list_registry_ids
    except Exception:
        return ""

    # 提取模板节点的 functionId 集合
    wf = load_workflow_from_file(str(workflow_id).strip())
    if wf is None:
        return ""
    wf_function_ids: set = set()
    for n in (wf.dict().get("nodes") or []):
        fid = str(((n.get("data") or {}).get("config") or {}).get("functionId") or "").strip()
        if fid:
            wf_function_ids.add(fid)

    if not wf_function_ids:
        return ""

    # 优先：找带 actions 字段的 v3 registry
    best_v3_id = ""
    best_v3_count = 0
    best_legacy_id = ""
    best_legacy_count = 0

    for rid in list_registry_ids():
        try:
            reg = load_registry(rid)
            if reg.get("registry_id") == "__empty__":
                continue

            reg_function_ids: set = set()

            # v3 格式：从 actions 的 patch_template.node_params 提取 function_id
            if isinstance(reg.get("actions"), list):
                for action in reg["actions"]:
                    if not isinstance(action, dict):
                        continue
                    template = action.get("patch_template") or {}
                    for func_id in (template.get("node_params") or {}).keys():
                        if func_id:
                            reg_function_ids.add(str(func_id).strip())
                    for func_id in (template.get("structure_switches") or {}).keys():
                        if func_id:
                            reg_function_ids.add(str(func_id).strip())
                intersection = len(wf_function_ids & reg_function_ids)
                if intersection > best_v3_count:
                    best_v3_count = intersection
                    best_v3_id = rid
            else:
                # 旧格式：从 layers.params 提取 node_function_id
                for _layer in (reg.get("layers") or {}).values():
                    for _param in (_layer.get("params") or {}).values():
                        nfid = str(_param.get("node_function_id") or "").strip()
                        if nfid:
                            reg_function_ids.add(nfid)
                intersection = len(wf_function_ids & reg_function_ids)
                if intersection > best_legacy_count:
                    best_legacy_count = intersection
                    best_legacy_id = rid
        except Exception:
            continue

    # 优先 v3，只要有任何 function_id 匹配就用 v3
    if best_v3_id and best_v3_count > 0:
        import logging as _logging
        _logging.getLogger(__name__).info(
            f"自动匹配搜索空间注册表: {best_v3_id}（v3 actions，匹配 {best_v3_count} 个节点）"
        )
        return best_v3_id

    # fallback 到 v1/v2
    if best_legacy_id and best_legacy_count > 0:
        import logging as _logging
        _logging.getLogger(__name__).info(
            f"自动匹配搜索空间注册表: {best_legacy_id}（legacy layers，匹配 {best_legacy_count} 个节点）"
        )
        return best_legacy_id

    return ""


def _auto_generate_registry_from_template(workflow_id: str) -> Dict[str, Any]:
    """
    任务 14.1：从模板自动生成搜索空间注册表草稿。

    扫描模板所有节点的 functionId 和 config，对已知 functionId（在内置映射表里的）
    自动生成参数条目。输出草稿 JSON（不直接保存，返回给调用方审核）。

    Args:
        workflow_id（模板 ID）: 要分析的模板

    Returns:
        注册表草稿 dict（格式与 load_forecast_v1.json 一致）
    """
    wf = load_workflow_from_file(str(workflow_id).strip())
    if wf is None:
        return {"error": f"模板不存在: {workflow_id}"}

    # 内置映射表：functionId → 可生成的参数条目
    _PARAM_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
        "auto_tune_xgboost": [
            {"key": "auto_tune_n_trials", "type": "categorical", "options": [3, 5, 8, 12, 20],
             "patch_target": "node_param", "param_key": "n_trials", "layer": "training",
             "description": "贝叶斯调参轮数"},
            {"key": "cv_folds", "type": "categorical", "options": [3, 5],
             "patch_target": "node_param", "param_key": "cv_folds", "layer": "training",
             "description": "交叉验证折数"},
        ],
        "xgboost_forecast": [
            {"key": "xgb_n_estimators", "type": "categorical", "options": [100, 200, 300, 500, 800],
             "patch_target": "node_param", "param_key": "n_estimators", "layer": "model",
             "description": "XGBoost 树数量"},
        ],
        "lightgbm_forecast": [
            {"key": "lgb_n_estimators", "type": "categorical", "options": [100, 200, 300, 500],
             "patch_target": "node_param", "param_key": "n_estimators", "layer": "model",
             "description": "LightGBM 树数量"},
        ],
        "catboost_forecast": [
            {"key": "catb_n_estimators", "type": "categorical", "options": [100, 200, 300, 500],
             "patch_target": "node_param", "param_key": "n_estimators", "layer": "model",
             "description": "CatBoost 迭代次数"},
        ],
        "create_lag_features": [
            {"key": "create_lag_features.lags", "type": "categorical",
             "options": [[1,2,3], [1,2,3,7,14], [1,2,3,7,14,21,28]],
             "patch_target": "node_param", "param_key": "lags", "layer": "feature",
             "description": "滞后特征步数组合"},
        ],
        "rolling_statistics": [
            {"key": "rolling_statistics.window_sizes", "type": "categorical",
             "options": [[4, 8, 24], [4, 8, 24, 96], [8, 24, 48, 96]],
             "patch_target": "node_param", "param_key": "window_sizes", "layer": "feature",
             "description": "滚动统计窗口大小列表"},
        ],
        "sliding_window": [
            {"key": "sliding_window.window_size", "type": "categorical", "options": [48, 96, 144, 192],
             "patch_target": "node_param", "param_key": "window_size", "layer": "feature",
             "description": "滑动窗口大小"},
            {"key": "sliding_window.step", "type": "categorical", "options": [1, 12, 24, 48],
             "patch_target": "node_param", "param_key": "step", "layer": "data",
             "description": "滑动步长"},
        ],
        "holiday_features": [
            {"key": "holiday_features.enabled", "type": "boolean",
             "patch_target": "structure_switch", "layer": "feature",
             "description": "是否启用节假日特征"},
        ],
        "workday_features": [
            {"key": "workday_features.enabled", "type": "boolean",
             "patch_target": "structure_switch", "layer": "feature",
             "description": "是否启用工作日特征"},
        ],
        "diff_features": [
            {"key": "diff_features.enabled", "type": "boolean",
             "patch_target": "structure_switch", "layer": "feature",
             "description": "是否启用差分特征"},
        ],
        "extract_statistical_features": [
            {"key": "extract_statistical_features.enabled", "type": "boolean",
             "patch_target": "structure_switch", "layer": "feature",
             "description": "是否启用统计特征"},
        ],
    }

    # 扫描模板节点
    layers: Dict[str, Dict[str, Any]] = {
        "training": {"activation_order": 1, "description": "训练策略层", "params": {}},
        "feature": {"activation_order": 2, "description": "特征工程层", "params": {}},
        "model": {"activation_order": 3, "description": "模型组合层", "params": {}},
        "data": {"activation_order": 4, "description": "数据策略层", "params": {}},
    }

    # 全局配置参数（不依赖节点）
    layers["training"]["params"]["train_days"] = {
        "type": "categorical",
        "options": [14, 21, 30, 45, 60, 75, 90],
        "patch_target": "global_config",
        "description": "训练窗口天数",
    }
    layers["data"]["params"]["daily_horizon"] = {
        "type": "categorical",
        "options": [48, 96],
        "patch_target": "global_config",
        "description": "每日预测步数",
    }

    # 检测到的模型列表（用于 active_models）
    detected_models: List[str] = []

    for n in (wf.dict().get("nodes") or []):
        cfg = ((n.get("data") or {}).get("config") or {})
        fid = str(cfg.get("functionId") or "").strip()
        if not fid:
            continue

        # 记录预报模型
        if fid in ("xgboost_forecast", "lightgbm_forecast", "catboost_forecast", "ridge_forecast"):
            detected_models.append(fid)

        # 从映射表生成参数条目
        templates = _PARAM_TEMPLATES.get(fid) or []
        for tmpl in templates:
            layer_name = tmpl.get("layer") or "training"
            param_key = tmpl["key"]
            entry: Dict[str, Any] = {
                "type": tmpl["type"],
                "patch_target": tmpl["patch_target"],
                "node_function_id": fid,
                "description": tmpl.get("description") or param_key,
            }
            if tmpl.get("options"):
                entry["options"] = tmpl["options"]
            if tmpl.get("param_key"):
                entry["param_key"] = tmpl["param_key"]
            layers[layer_name]["params"][param_key] = entry

    # 模型组合参数
    if len(detected_models) >= 2:
        layers["model"]["params"]["ensemble_mode"] = {
            "type": "categorical",
            "options": ["single_best", "all_adaptive", "subset_adaptive"],
            "patch_target": "global_config",
            "description": "模型集成模式",
        }
        layers["model"]["params"]["active_models"] = {
            "type": "subset",
            "universe": sorted(set(detected_models)),
            "min_size": 1,
            "patch_target": "model_focus",
            "description": "参与预测的模型子集",
        }

    # 清理空层
    layers = {k: v for k, v in layers.items() if v.get("params")}

    return {
        "registry_id": f"{workflow_id}_auto_draft",
        "description": f"从模板 {workflow_id} 自动生成的搜索空间草稿（需人工审核）",
        "layers": layers,
        "detected_models": detected_models,
        "_auto_generated": True,
    }


def _known_structure_profile_ids() -> set:
    from services.workflow_slot_catalog_service import known_profile_ids

    return set(known_profile_ids())


def _get_operator_router_cached() -> OperatorRouter:
    global _cached_operator_router
    if _cached_operator_router is None:
        _cached_operator_router = OperatorRouter()
        _cached_operator_router.auto_discover(_OPERATOR_BACKENDS_DIR)
    return _cached_operator_router


def _discover_forecast_operators_payload() -> Dict[str, Any]:
    """函数库候选 ∩ 运行时注册；用于前端展示可用模型算子。"""
    router = _get_operator_router_cached()
    candidates_lib: List[Dict[str, Any]] = []
    try:
        svc = get_function_library_service()
        for fn in svc.get_all_functions():
            cat = str(getattr(fn, "category", "") or "")
            fid = str(getattr(fn, "id", "") or "")
            if cat != "ts_forecast":
                continue
            if not fid.endswith("_forecast"):
                continue
            candidates_lib.append(
                {
                    "function_id": fid,
                    "name": getattr(fn, "name", fid),
                    "category": cat,
                    "description": getattr(fn, "description", "") or "",
                    "registered": router.has_operator(fid),
                }
            )
    except Exception as e:
        return {
            "operators": [],
            "catalog_unavailable": [],
            "discovery": {"categories": ["ts_forecast"], "id_suffix": "_forecast", "error": str(e)},
        }

    candidates_lib.sort(key=lambda x: x["function_id"])
    operators = [x for x in candidates_lib if x["registered"]]
    catalog_unavailable = [x for x in candidates_lib if not x["registered"]]
    return {
        "operators": operators,
        "catalog_unavailable": catalog_unavailable,
        "discovery": {"categories": ["ts_forecast"], "id_suffix": "_forecast"},
    }


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _glm_questioner_runtime_status() -> Dict[str, Any]:
    has_key = bool(str(os.getenv("GLM_API_KEY") or "").strip())
    base_url_configured = bool(str(os.getenv("GLM_BASE_URL") or "").strip())
    glm_enable = _env_bool("GLM_ENABLE", has_key and base_url_configured)
    rq_raw = os.getenv("GLM_RESEARCH_QUESTIONS_ENABLE")
    rq_enabled = _env_bool("GLM_RESEARCH_QUESTIONS_ENABLE", glm_enable)
    disabled_reason = None
    if not rq_enabled:
        disabled_reason = "GLM_RESEARCH_QUESTIONS_ENABLE_disabled"
    elif not has_key:
        disabled_reason = "GLM_API_KEY_missing"
    elif not base_url_configured:
        disabled_reason = "GLM_BASE_URL_missing"
    return {
        "glm_enable": glm_enable,
        "glm_research_questions_enable": rq_enabled,
        "glm_research_questions_env_present": rq_raw is not None,
        "has_api_key": has_key,
        "model": os.getenv("GLM_MODEL", "glm-5.1"),
        "base_url_configured": base_url_configured,
        "ready": bool(rq_enabled and has_key and base_url_configured),
        "disabled_reason": disabled_reason,
    }


def _get_autoresearch_batch_group_timeout_s(
    compare_config: Optional[Dict[str, Any]] = None,
    windows_count: int = 3,
) -> float:
    """动态超时：窗口数 × 15min/窗口，下限 30min，上限 2h。用户可通过 compare_config 或环境变量覆盖。"""
    cfg = compare_config if isinstance(compare_config, dict) else {}
    raw = cfg.get("batch_group_timeout_s")
    if raw in (None, ""):
        raw = os.getenv("AUTORESEARCH_BATCH_GROUP_TIMEOUT_S", "")
    if raw not in (None, ""):
        try:
            timeout_s = float(raw)
        except (TypeError, ValueError):
            timeout_s = None
        if timeout_s is not None:
            return max(300.0, min(timeout_s, 7200.0))
    # 动态计算：每窗口 15 分钟基准
    timeout_s = max(windows_count, 1) * 900.0
    return max(1800.0, min(timeout_s, 7200.0))


def _extract_json_block(text: str) -> Optional[str]:
    if not text:
        return None
    s = str(text)
    # 1) fenced ```json ... ```
    fence = "```json"
    i = s.lower().find(fence)
    if i >= 0:
        j = s.find("```", i + len(fence))
        if j >= 0:
            block = s[i + len(fence):j]
            return block.strip()
    # 2) bracket matching for first {..} or [..]
    start = None
    for idx, ch in enumerate(s):
        if ch in "{[":
            start = idx
            break
    if start is None:
        return None
    stack = []
    in_str = False
    esc = False
    for idx in range(start, len(s)):
        ch = s[idx]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                continue
            op = stack.pop()
            if not stack:
                return s[start: idx + 1].strip()
    return None


def _strict_json_loads(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {"_": obj}
    except Exception:
        return None


async def _glm_chat_json(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
    timeout_s: float = 60.0,
) -> Dict[str, Any]:
    api_key = os.getenv("GLM_API_KEY", "").strip()
    api_base = os.getenv("GLM_BASE_URL", "").strip()
    model = os.getenv("GLM_MODEL", "glm-5.1").strip()
    try:
        timeout_env = float(os.getenv("GLM_TIMEOUT_S", "").strip() or 60.0)
    except Exception:
        timeout_env = 60.0
    if not api_key or not api_base:
        raise ValueError("GLM_API_KEY / GLM_BASE_URL 未配置")
    svc = LLMService({
        "provider": "zhipu",
        "api_key": api_key,
        "api_base": api_base,
        "model": model,
        "temperature": float(temperature),
        "max_tokens": 4096,
        "timeout_s": timeout_env,
    })
    # LLMService 内部 timeout 固定为 60s，此处保持一致
    return await svc.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])


async def _glm_generate_proposal_candidates(report: Dict[str, Any]) -> Dict[str, Any]:
    # H2 FIX: inject knowledge layer candidates before GLM proposal generation
    _kl_injections = []
    try:
        from services.knowledge_layer import KnowledgeLayer
        _scenario = report.get("scenario_fingerprint") or {}
        _kl = KnowledgeLayer()
        _kl_injections = _kl.get_injection_candidates(
            scenario_fingerprint=_scenario if isinstance(_scenario, dict) else None,
            min_confidence=0.3,
        )
        if _kl_injections:
            logger.info(f"KnowledgeLayer injected {len(_kl_injections)} candidates (confidence >= 0.3)")
    except Exception as _kl_err:
        logger.warning(f"KnowledgeLayer injection failed (non-fatal): {_kl_err}")
        _kl_injections = []
    """
    Return: { candidates: [proposal_like...], llm_used: bool, llm_error?: str,
              observation: str, hypothesis: str, expected_outcome: dict, ... }
    任务 20：思维链模式 prompt，注入迭代间上下文（假设验证历史、累积洞察、已否证假设集）
    """
    if not _env_bool("GLM_ENABLE", False):
        return {"candidates": [], "llm_used": False}

    # ── 任务 20.1：思维链 system prompt ──────────────────────────────────────
    system_prompt = (
        "你是一位严谨的机器学习实验研究员，专注于时序预测模型的自动优化。\n"
        "你只能输出 JSON，禁止任何解释文字。你必须遵守 allowed_keys 白名单。\n\n"
        "【思维链要求】在生成建议前，你必须按以下五步思考：\n"
        "1. 观察（Observation）：从 error_profile、data_coverage、iterations 中提炼 2-3 句关键事实，必须引用具体数值。\n"
        "2. 假设（Hypothesis）：基于观察，提出一个可验证的因果假设（1 句话，格式：'因为 X，所以调整 Y 应该能改善 Z'）。\n"
        "3. 设计（Design）：设计最小化实验——每次只验证一个核心假设，不要同时改太多变量。\n"
        "4. 预期（Expected Outcome）：明确预期改善的指标、方向和阈值（如 'MAPE 改善 > 0.5%'）。\n"
        "5. 回退（Fallback）：若假设未成立，下一步应该怎么做。\n\n"
        "【约束】\n"
        "- 已否证假设集中的方向不得再次出现在建议中\n"
        "- rationale 必须引用 observation 中的具体数值\n"
        "- 每个候选验证不同的假设，不要生成相似的候选\n"
        "- 遵守 allowed_keys 白名单，不允许输出其他字段\n"
    )

    allowed = {
        "search_space_patch": sorted(list(_ALLOWED_SEARCH_SPACE_PATCH_KEYS)),
        "evaluation_contract_patch": sorted(list(_ALLOWED_EVAL_PATCH_KEYS)),
        "structure_patch_function_whitelist": _glm_structure_patch_whitelist_keys(),
        "global_config_patch_allowed_keys": sorted(_ALLOWED_GLOBAL_CONFIG_PATCH_KEYS),
        "node_param_patches_allowed_keys_by_function": {
            fid: sorted(keys.keys()) for fid, keys in _AUTORESEARCH_NODE_PARAM_FIELDS.items()
        },
    }

    # ── slim_iters：最近 5 轮迭代摘要 ────────────────────────────────────────
    iters = report.get("iterations") or []
    iters_tail = iters[-5:] if isinstance(iters, list) else []
    slim_iters = []
    for it in iters_tail:
        if not isinstance(it, dict):
            continue
        ev = it.get("evaluation") or {}
        hv = it.get("hypothesis_verification") or {}
        slim_iters.append({
            "iteration": it.get("iteration"),
            "status": it.get("status"),
            "evaluation": {
                "mape_improvement": ev.get("mape_improvement"),       # MAPE 改善量
                "challenger_mape": ev.get("challenger_mape"),          # Challenger 的 MAPE
                "challenger_rmse": ev.get("challenger_rmse"),          # Challenger 的 RMSE
                "score_advantage": ev.get("score_advantage"),          # 分差优势
                "meets_constraints": ev.get("meets_constraints"),      # 是否满足约束
            },
            "override": it.get("override"),                            # 本轮覆盖参数
            "error": it.get("error"),
            "error_profile": it.get("error_profile"),                  # 误差画像
            "data_coverage": it.get("data_coverage"),                  # 数据覆盖情况
            # 任务 20.2：注入假设验证结果
            "hypothesis_verification": {
                "hypothesis": hv.get("hypothesis"),                    # 上轮假设文本
                "verified": hv.get("verified"),                        # 是否成立
                "actual_improvement": hv.get("actual_improvement"),    # 实际改善量
                "conclusion": hv.get("conclusion"),                    # 验证结论
            } if hv else None,
        })

    # ── 任务 20.2：迭代间上下文（假设验证历史、累积洞察、已否证假设集）────────
    last_verification = report.get("last_hypothesis_verification") or {}
    insights = report.get("insights") or {}
    disproved = report.get("disproved_hypotheses") or []
    is_first_round = len([it for it in slim_iters if it.get("status") in ("success", "failed")]) == 0

    # 最近一轮成功迭代的误差画像
    last_error_profile: Optional[Dict[str, Any]] = None
    last_data_coverage: Optional[Dict[str, Any]] = None
    for it in reversed(slim_iters):
        if isinstance(it, dict) and str(it.get("status")) == "success":
            last_error_profile = it.get("error_profile")
            last_data_coverage = it.get("data_coverage")
            break

    slim_report = {
        "run_id": report.get("run_id"),
        "baseline_workflow_id": report.get("baseline_workflow_id"),
        "scenario_tags": report.get("scenario_tags") or [],
        "scenario_fingerprint": report.get("scenario_fingerprint") or {},
        "evaluation_contract": report.get("evaluation_contract") or {},
        "search_space": report.get("search_space") or {},
        "summary": report.get("summary") or {},
        "iterations": slim_iters,
        "phase": report.get("phase") or "parameter_exploration",      # 当前搜索阶段
        "active_layers": report.get("active_layers") or [],           # 当前激活的搜索层
        "error_diagnosis": _compute_error_diagnosis(report),          # 误差诊断结论
        "latest_error_profile": last_error_profile,                   # 最近一轮误差画像
        "latest_data_coverage": last_data_coverage,                   # 最近一轮数据覆盖
        # 上一轮批量评估的所有组结果（供 GLM 学习"什么有效、什么无效"）
        "last_batch_results": report.get("last_batch_results") or None,
        "parallel_research_results": report.get("parallel_research_results") or None,
        "research_questions": report.get("research_questions") or [],
        "latest_reflection_decision": report.get("latest_reflection_decision") or None,
        "current_research_focus": report.get("current_research_focus") or None,
        "dataset_profile": report.get("dataset_profile") or None,
        "tri_dataset_diagnosis": report.get("tri_dataset_diagnosis") or None,
        "experiment_quality": report.get("experiment_quality") or None,
        "agent_mode": report.get("agent_mode") or "single_agent",
    }

    memory_refs = report.get("memory_references") if isinstance(report.get("memory_references"), list) else []
    slim_memory_refs: List[Dict[str, Any]] = []
    for m in memory_refs[:3]:
        if not isinstance(m, dict):
            continue
        out_m = m.get("outcome") or {}
        patch = m.get("applied_patch") or {}
        slim_memory_refs.append({
            "case_id": m.get("case_id"),
            "retrieval_score": m.get("retrieval_score"),
            "patch_summary": {
                "override": patch.get("override") or {},
                "structure_patch": patch.get("structure_patch") or {},
            },
            "outcome": {
                "improved": out_m.get("improved"),
                "mape_delta": out_m.get("mape_delta"),
            },
        })

    # ── 任务 20.2：user prompt 注入三个上下文区块 ────────────────────────────
    # 任务 29.2：首轮注入历史相似实验经验
    historical_insight_block = ""
    if is_first_round:
        try:
            run_id_for_insight = str(slim_report.get("run_id") or "")
            state_for_insight = _auto_research_store.get(run_id_for_insight) or {}
            current_fp = _compute_scenario_fingerprint(state_for_insight)
            current_reg = str(state_for_insight.get("registry_id") or "")
            similar_insights = _match_similar_run_insights(current_fp, current_reg, top_k=3)
            if similar_insights:
                historical_insight_block = "## 历史相似实验的经验\n\n"
                for si in similar_insights:
                    sim_score = si.get("_similarity_score", 0)
                    rid = str(si.get("run_id") or "")
                    rules = (si.get("learned_rules") or [])[:3]
                    ineffective = (si.get("ineffective_attempts") or [])[:2]
                    rec = si.get("recommended_starting_config_for_similar") or {}
                    historical_insight_block += (
                        f"### 实验 {rid}（相似度 {sim_score}）\n"
                        f"- 学到的规律：{'; '.join(rules) if rules else '无'}\n"
                        f"- 无效尝试：{'; '.join(ineffective) if ineffective else '无'}\n"
                        f"- 推荐起始配置：{json.dumps(rec, ensure_ascii=False)}\n\n"
                    )
                historical_insight_block += "请参考这些经验设计你的第一个假设，但不要盲目复制——当前数据可能有不同特征。\n\n"
        except Exception:
            historical_insight_block = ""

    # H2 FIX: knowledge layer injection candidates for GLM context
    knowledge_injection_block = ""
    if _kl_injections:
        knowledge_injection_block = "【知识库注入（跨实验学习）】\n"
        for ci in (_kl_injections or [])[:8]:
            ck = ci.get("claim_key", {})
            knowledge_injection_block += (
                f"- 参数 {ck.get('target_param', '?')} → {ci.get('knowledge_type', '?')} "
                f"(layer={ci.get('layer', '?')}, confidence={ci.get('confidence', 0):.2f}, "
                f"evidence={len(ci.get('evidence', []))}, "
                f"injection_weight={ci.get('injection_weight', 0):.3f})\n"
            )
        knowledge_injection_block += "请在假设设计时优先考虑上述高置信度方向，但需验证对当前场景的适用性。\n\n"

    history_block = (
        "【这是第一轮实验，无历史假设数据】\n"
        if is_first_round else
        f"【上一轮假设与结果】\n"
        f"假设：{last_verification.get('hypothesis', '无')}\n"
        f"预期：{last_verification.get('expected_threshold', '无')}\n"
        f"实际：{last_verification.get('actual_improvement', '无')}\n"
        f"结论：{'✓ 成立' if last_verification.get('verified') else '✗ 未成立'} — {last_verification.get('conclusion', '')}\n"
    )

    insights_block = (
        f"【累积洞察】\n"
        f"有效方向：{json.dumps(insights.get('effective_directions') or [], ensure_ascii=False)}\n"
        f"无效方向：{json.dumps(insights.get('ineffective_directions') or [], ensure_ascii=False)}\n"
        f"已测试 {insights.get('total_hypotheses_tested', 0)} 个假设，"
        f"{insights.get('hypotheses_verified', 0)} 个成立，"
        f"{insights.get('hypotheses_disproved', 0)} 个否证\n"
    )

    disproved_block = (
        f"【已否证假设集（不得重复）】\n"
        + "\n".join([
            f"- {d.get('hypothesis', '')}（第{d.get('iteration', '?')}轮，实际={d.get('actual_result', '?')}）"
            for d in disproved[-5:]
        ]) + "\n"
        if disproved else "【已否证假设集】（暂无）\n"
    )

    phase_hint = (
        "【重要】当前处于结构探索阶段（phase=structure_exploration），参数层已饱和，"
        "候选 C 必须包含非空 structure_patch。\n"
        if str(slim_report.get("phase") or "") == "structure_exploration" else ""
    )

    research_question_block = ""
    if slim_report.get("research_questions"):
        recent_questions = slim_report.get("research_questions")[-5:]
        research_question_block = (
            "【本轮研究问题（必须优先围绕这些问题设计假设）】\n"
            + json.dumps(recent_questions, ensure_ascii=False)
            + "\n"
        )

    reflection_block = ""
    if slim_report.get("latest_reflection_decision"):
        reflection_block = (
            "【最近一次阶段性反思决策】\n"
            + json.dumps(slim_report.get("latest_reflection_decision"), ensure_ascii=False)
            + "\n"
        )

    quality_block = ""
    if isinstance(slim_report.get("experiment_quality"), dict):
        quality_block = (
            "【最近一次实验质量评分】\n"
            + json.dumps(slim_report.get("experiment_quality"), ensure_ascii=False)
            + "\n请避免重复低质量实验设计，优先生成单变量、可验证、风险可控的候选。\n"
        )

    # ── 任务 20.3：升级输出 schema，要求 observation/hypothesis/expected_outcome ──
    # ── 任务 33.1：升级为意图模式 schema（GLM 不再写 node_id，只写意图）──
    output_schema = (
        "输出 JSON schema（严格遵守）：\n"
        "{\n"
        "  \"observation\": \"2-3句话，描述当前误差模式的关键事实，必须引用具体数值\",\n"
        "  \"hypothesis\": \"1句话，格式：因为X，所以调整Y应该能改善Z\",\n"
        "  \"hypothesis_type\": \"parameter | feature | model | data\",\n"
        "  \"expected_outcome\": {\n"
        "    \"metric\": \"mape_improvement | challenger_mape | score_advantage\",\n"
        "    \"direction\": \"increase | decrease\",\n"
        "    \"threshold\": 0.005,\n"
        "    \"description\": \"预期 MAPE 改善 > 0.5%\"\n"
        "  },\n"
        "  \"fallback_if_failed\": \"若假设未成立，下一步建议\",\n"
        "  \"deepen_if_verified\": \"若假设成立，如何深入（可选）\",\n"
        "  \"candidates\": [\n"
        "    {\n"
        "      \"name\": \"candidate_A\",\n"
        "      \"observation\": \"该候选自己的观察，可引用并行组结果\",\n"
        "      \"hypothesis\": \"该候选自己的可验证假设\",\n"
        "      \"hypothesis_type\": \"parameter | feature | model | data\",\n"
        "      \"expected_outcome\": {\"metric\": \"mape_improvement\", \"direction\": \"increase\", \"threshold\": 0.005},\n"
        "      \"fallback_if_failed\": \"该候选若失败的下一步\",\n"
        "      \"risk_level\": \"low|medium|high\",\n"
        "      \"rationale\": \"<=150字，必须引用 observation 中的具体数值\",\n"
        "      \"search_space_patch\": {},\n"
        "      \"evaluation_contract_patch\": {},\n"
        "      \"global_config_patch\": {},\n"
        "      \"intent\": {\n"
        "        \"action\": \"adjust_param | enable_node | disable_node | change_ensemble | add_feature_recipe\",\n"
        "        \"target_function_id\": \"rolling_statistics\",\n"
        "        \"param_key\": \"window_sizes\",\n"
        "        \"recipe_id\": \"features_trim_calendar_v1，仅 action=add_feature_recipe 时填写\",\n"
        "        \"direction\": \"increase | decrease | set\",\n"
        "        \"value_hint\": \"更大的窗口（如 48 或 96）\"\n"
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "注意：每个 candidate 必须代表不同假设；如存在 parallel_research_results，优先给每个并行组设计一个对应候选。"
        "candidates 中不要写 node_id 或 node_param_patches，只写 intent。"
        "翻译器会根据 intent 自动生成正确的 patch。\n"
    )

    # 构建批量对比区块（如果上一轮有多组结果）
    batch_comparison_block = ""
    _last_batch = slim_report.get("last_batch_results")
    if isinstance(_last_batch, list) and len(_last_batch) > 1:
        batch_comparison_block = "【上一轮批量评估对比（多组参数同时测试）】\n"
        for _bg in _last_batch:
            if not isinstance(_bg, dict):
                continue
            _g_idx = _bg.get("group_idx", "?")
            _g_ov = _bg.get("override") or {}
            _g_adv = _bg.get("score_advantage")
            _g_mi = _bg.get("mape_improvement")
            _g_best = "★最优" if _bg.get("is_best") else ""
            batch_comparison_block += (
                f"  组{_g_idx}{_g_best}: override={json.dumps(_g_ov, ensure_ascii=False)}"
                f" → score_advantage={_g_adv}, mape_improvement={_g_mi}\n"
            )
        batch_comparison_block += "请分析哪些参数方向有效、哪些无效，据此设计下一轮假设。\n\n"

    parallel_research_block = ""
    _parallel_research = slim_report.get("parallel_research_results")
    if isinstance(_parallel_research, list) and len(_parallel_research) > 1:
        parallel_research_block = (
            "【上一轮并行研究结果（每组独立的问题分析/研究问题种子）】\n"
            + json.dumps(_parallel_research, ensure_ascii=False)
            + "\n请基于每组的 diagnosis/research_question_seed 生成差异化候选假设，不要只围绕最优组。\n\n"
        )

    user_prompt = (
        # 任务 29.2：首轮注入历史相似实验经验
        historical_insight_block
        + knowledge_injection_block
        + history_block
        + insights_block
        + disproved_block
        + batch_comparison_block
        + parallel_research_block
        + phase_hint
        + research_question_block
        + reflection_block
        + quality_block
        + f"allowed_keys={json.dumps(allowed, ensure_ascii=False)}\n"
        + f"experiment_report={json.dumps(slim_report, ensure_ascii=False)}\n"
        + f"memory_references={json.dumps(slim_memory_refs, ensure_ascii=False)}\n"
        + output_schema
    )

    # 日志打印最终 prompt
    import logging as _logging
    _logging.getLogger(__name__).info(
        "[GLM prompt] system=%s | user_head=%s",
        system_prompt[:300],
        user_prompt[:800],
    )

    try:
        try:
            resp = await _glm_chat_json(system_prompt, user_prompt, temperature=0.2)
        except Exception as e:
            if "timeout" in str(e).lower():
                resp = await _glm_chat_json(system_prompt, user_prompt, temperature=0.0)
            else:
                raise
        raw = resp.get("content") or ""
        extracted = _extract_json_block(raw) or raw
        obj = _strict_json_loads(extracted)
        if obj is None:
            repair_sys = "你是 JSON 修复器。你只输出 JSON，禁止任何解释文字。"
            repair_user = f"请把下面文本修复为合法 JSON，保持语义不变，只输出 JSON：\n{raw}\n"
            rep = await _glm_chat_json(repair_sys, repair_user, temperature=0.0)
            raw2 = rep.get("content") or ""
            extracted2 = _extract_json_block(raw2) or raw2
            obj = _strict_json_loads(extracted2)
        if obj is None:
            return {"candidates": [], "llm_used": True, "llm_error": "json_parse_failed"}
        cands = obj.get("candidates") if isinstance(obj, dict) else None
        if not isinstance(cands, list):
            return {"candidates": [], "llm_used": True, "llm_error": "schema_missing_candidates"}

        # ── 任务 20.4：解析新字段，写入每个 proposal ──────────────────────────
        # 顶层字段（observation/hypothesis 等）
        top_observation = str(obj.get("observation") or "")
        top_hypothesis = str(obj.get("hypothesis") or "")
        top_hypothesis_type = str(obj.get("hypothesis_type") or "parameter")
        top_expected_outcome = obj.get("expected_outcome") if isinstance(obj.get("expected_outcome"), dict) else {}
        top_fallback = str(obj.get("fallback_if_failed") or "")
        top_deepen = str(obj.get("deepen_if_verified") or "")

        out: List[Dict[str, Any]] = []
        for c in cands[:3]:
            if not isinstance(c, dict):
                continue
            # 任务 33.3：适配意图格式——如果有 intent 字段，翻译为 patch
            intent = c.get("intent")
            translated_patches: Dict[str, Any] = {}
            if isinstance(intent, dict) and intent.get("action"):
                # 新格式：GLM 输出了 intent，翻译为 patch
                _baseline_wf_id_for_intent = str(slim_report.get("baseline_workflow_id") or "")
                _registry_for_intent = None
                try:
                    from services.autoresearch_registry_service import load_registry as _lr
                    _rid = str(slim_report.get("registry_id") or "")
                    if _rid:
                        _registry_for_intent = _lr(_rid)
                except Exception:
                    pass
                translated_patches = _translate_intent_to_patches(
                    intent, _baseline_wf_id_for_intent, _registry_for_intent
                )
            # 合并：intent 翻译的 patch 优先，旧格式 patch 作为兜底
            search_space_patch = dict(c.get("search_space_patch") or {})
            search_space_patch.update(dict(translated_patches.get("search_space_patch") or {}))
            out.append({
                "name": c.get("name") or "glm_candidate",
                "risk_level": c.get("risk_level") or "low",
                "search_space_patch": search_space_patch,
                "evaluation_contract_patch": c.get("evaluation_contract_patch") or {},
                "structure_patch": translated_patches.get("structure_patch") or c.get("structure_patch") or {},
                "global_config_patch": translated_patches.get("global_config_patch") or (c.get("global_config_patch") if isinstance(c.get("global_config_patch"), dict) else {}),
                "node_param_patches": translated_patches.get("node_param_patches") or (c.get("node_param_patches") if isinstance(c.get("node_param_patches"), list) else []),
                "feature_recipe_id": translated_patches.get("feature_recipe_id") or c.get("feature_recipe_id"),
                "notes": [c.get("rationale") or "glm rationale"],
                "llm_used": True,
                "llm_model": os.getenv("GLM_MODEL", "glm-5.1"),
                "intent": intent,  # 保留原始意图，供调试
                # 任务 20.4：新增假设相关字段（容错：缺失填 null）
                "observation": str(c.get("observation") or top_observation or "") or None,
                "hypothesis": str(c.get("hypothesis") or top_hypothesis or "") or None,
                "hypothesis_type": str(c.get("hypothesis_type") or top_hypothesis_type or "parameter"),
                "expected_outcome": c.get("expected_outcome") if isinstance(c.get("expected_outcome"), dict) else (top_expected_outcome or None),
                "fallback_if_failed": str(c.get("fallback_if_failed") or top_fallback or "") or None,
                "deepen_if_verified": str(c.get("deepen_if_verified") or top_deepen or "") or None,
                # 任务 27.1：推断主变量（GLM 候选也标记）
                "primary_variable": _infer_primary_variable(c),
            })
        return {
            "candidates": out,
            "llm_used": True,
            "glm_input_debug": {
                "system_prompt": _truncate_debug_text(system_prompt, 6000),
                "user_prompt": _truncate_debug_text(user_prompt, 16000),
                "allowed_keys": allowed,
                "slim_report": slim_report,
                "memory_references": slim_memory_refs,
                "prompt_chars": len(user_prompt),
                "system_prompt_chars": len(system_prompt),
                "truncated": len(user_prompt) > 16000 or len(system_prompt) > 6000,
            },
            # 顶层也返回，供调用方写入 run_state
            "observation": top_observation or None,
            "hypothesis": top_hypothesis or None,
            "hypothesis_type": top_hypothesis_type or None,
            "expected_outcome": top_expected_outcome or None,
            "fallback_if_failed": top_fallback or None,
        }
    except Exception as e:
        return {
            "candidates": [],
            "llm_used": True,
            "llm_error": f"{type(e).__name__}: {str(e)}",
            "glm_input_debug": {
                "system_prompt": _truncate_debug_text(system_prompt, 6000),
                "user_prompt": _truncate_debug_text(user_prompt, 16000),
                "allowed_keys": allowed,
                "slim_report": slim_report,
                "memory_references": slim_memory_refs,
                "prompt_chars": len(user_prompt),
                "system_prompt_chars": len(system_prompt),
                "truncated": len(user_prompt) > 16000 or len(system_prompt) > 6000,
            },
        }


def _compute_iteration_error_profile(window_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _auto_research_diagnostics.compute_iteration_error_profile(window_results)


def _build_autoresearch_report(run_state: Dict[str, Any]) -> Dict[str, Any]:
    iterations = run_state.get("iterations") or []
    no_test_data = 0
    insufficient_train_data = 0
    failed_count = 0
    for it in iterations:
        if not isinstance(it, dict):
            continue
        if str(it.get("status")) != "success":
            failed_count += 1
        err = str(it.get("error") or "").lower()
        if "无测试数据" in err or "no test data" in err:
            no_test_data += 1
        if "训练数据不足" in err or "insufficient_train_data" in err:
            insufficient_train_data += 1

    # 为每个 iteration 补充 error_profile 和 data_coverage
    enriched_iterations = []
    for it in iterations:
        if not isinstance(it, dict):
            enriched_iterations.append(it)
            continue
        it_copy = dict(it)
        # 优先从内存中的 comparison_store 取 window_results
        cmp_id = str(it_copy.get("comparison_id") or "")
        window_results: List[Dict[str, Any]] = []
        if cmp_id and cmp_id in _comparison_store:
            cmp_state = _comparison_store[cmp_id]
            wr = cmp_state.get("window_results")
            if isinstance(wr, list):
                window_results = wr
        # 若内存里没有，尝试从 iteration 自身的 summary 降级
        if not window_results:
            summ = it_copy.get("summary")
            if isinstance(summ, dict):
                wr2 = summ.get("window_results")
                if isinstance(wr2, list):
                    window_results = wr2
        profile = _compute_iteration_error_profile(window_results)
        it_copy["error_profile"] = profile["error_profile"]
        it_copy["data_coverage"] = profile["data_coverage"]
        enriched_iterations.append(it_copy)

    best = run_state.get("best_candidate") or {}
    best_eval = (best.get("evaluation") or {}) if isinstance(best, dict) else {}
    return _sanitize_json_floats({
        "run_id": run_state.get("run_id"),
        "status": run_state.get("status"),
        "progress": run_state.get("progress"),
        "search_space": run_state.get("search_space") or {},
        "evaluation_contract": run_state.get("evaluation_contract") or {},
        "compare_config": run_state.get("compare_config") or {},
        "scenario_tags": run_state.get("scenario_tags") or [],
        "scenario_fingerprint": _compute_scenario_fingerprint(run_state),
        "baseline_workflow_id": run_state.get("baseline_workflow_id"),
        "runtime_patch": run_state.get("runtime_patch") or {},
        "summary": {
            "iterations_total": len(iterations),
            "failed_count": failed_count,
            "best_iteration": best.get("iteration") if isinstance(best, dict) else None,
            "best_mape_improvement": best_eval.get("mape_improvement"),
            "failure_stats": {
                "no_test_data": no_test_data,
                "insufficient_train_data": insufficient_train_data,
            },
        },
        "iterations": enriched_iterations,
        "phase": run_state.get("phase") or "parameter_exploration",
        "pareto_frontier": run_state.get("pareto_frontier") or [],
        "convergence_status": run_state.get("convergence_status") or {"converged": False, "reason": "尚未检测"},
        # 任务 10：透传激活层状态，供前端展示
        "active_layers": run_state.get("active_layers") or [],
        "registry_id": run_state.get("registry_id") or None,
        # 任务 21：透传假设验证相关状态
        "last_hypothesis_verification": run_state.get("last_hypothesis_verification") or None,
        "insights": run_state.get("insights") or {},
        "disproved_hypotheses": run_state.get("disproved_hypotheses") or [],
        # 任务 27.3：透传连续类型计数
        "consecutive_type_count": run_state.get("consecutive_type_count") or {},
        # 任务 27.4：透传对照组结果
        "control_group_results": run_state.get("control_group_results") or [],
        # 任务 34：透传并发评估状态
        "batch_eval_status": run_state.get("batch_eval_status") or None,
        # 上一轮批量评估所有组的结果（供 GLM 学习对比）
        "last_batch_results": run_state.get("last_batch_results") or None,
        "parallel_research_results": run_state.get("parallel_research_results") or None,
        "dataset_profile": run_state.get("dataset_profile") or None,
        "dataset_profiles": run_state.get("dataset_profiles") or [],
        "tri_dataset_diagnosis": run_state.get("tri_dataset_diagnosis") or None,
        "research_questions": run_state.get("research_questions") or [],
        "experiment_quality": run_state.get("experiment_quality") or None,
        "periodic_reflections": run_state.get("periodic_reflections") or [],
        "latest_reflection_decision": (
            (run_state.get("periodic_reflections") or [{}])[-1].get("reflection_decision")
            if run_state.get("periodic_reflections") else None
        ),
        "current_research_focus": run_state.get("current_research_focus") or None,
        "iteration_plot_data": run_state.get("iteration_plot_data") or [],
        "agent_trace": run_state.get("agent_traces") or run_state.get("agent_trace") or [],
        "agent_traces": run_state.get("agent_traces") or run_state.get("agent_trace") or [],
        "agent_mode": run_state.get("agent_mode") or (run_state.get("compare_config") or {}).get("agent_mode") or "single_agent",
    })


def _collect_challenger_cv_metrics(window_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for window in window_results or []:
        if not isinstance(window, dict):
            continue
        challenger = window.get("challenger") or {}
        if isinstance(challenger, dict):
            rows.extend([x for x in challenger.get("cv_fold_metrics") or [] if isinstance(x, dict)])
    return _aggregate_cv_fold_metrics([{"status": "success", "cv_fold_metrics": rows}]) if rows else []


def _extract_challenger_daily_results(window_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for window in window_results or []:
        if not isinstance(window, dict):
            continue
        challenger = window.get("challenger") or {}
        if isinstance(challenger, dict):
            for item in challenger.get("daily_results") or []:
                if isinstance(item, dict) and item.get("status") == "success":
                    rows.append(item)
    return rows


def _extract_baseline_daily_results(window_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for window in window_results or []:
        if not isinstance(window, dict):
            continue
        baseline = window.get("baseline") or {}
        if isinstance(baseline, dict):
            for item in baseline.get("daily_results") or []:
                if isinstance(item, dict) and item.get("status") == "success":
                    rows.append(item)
    return rows


def _build_iteration_plot_data(iteration: int, window_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    import numpy as np
    import pandas as pd
    from scipy.signal import find_peaks

    points: List[Dict[str, Any]] = []
    daily_results = _extract_challenger_daily_results(window_results)
    baseline_predictions = {
        str(day.get("date") or ""): list(day.get("y_pred") or [])
        for day in _extract_baseline_daily_results(window_results)
    }
    for day in daily_results:
        date_str = str(day.get("date") or "")
        y_true = day.get("y_true") or []
        y_pred = day.get("y_pred") or []
        baseline_y_pred = baseline_predictions.get(date_str) or []
        n = min(len(y_true), len(y_pred))
        if n <= 0:
            continue
        try:
            base_ts = pd.to_datetime(date_str)
        except Exception:
            base_ts = None
        actual = np.asarray(y_true[:n], dtype=float)
        prominence = max(float(np.nanstd(actual)) * 0.5, 1e-8) if n >= 3 else 1e-8
        peaks, _ = find_peaks(actual, prominence=prominence, distance=4) if n >= 3 else ([], {})
        valleys, _ = find_peaks(-actual, prominence=prominence, distance=4) if n >= 3 else ([], {})
        peak_set = set(int(x) for x in peaks)
        valley_set = set(int(x) for x in valleys)
        for i in range(n):
            ts = str(base_ts + pd.Timedelta(minutes=15 * i)) if base_ts is not None else str(i)
            point = {
                "timestamp": ts,
                "actual": float(y_true[i]),
                "predicted": float(y_pred[i]),
                "is_peak": i in peak_set,
                "is_valley": i in valley_set,
                "date": date_str,
            }
            if i < len(baseline_y_pred):
                try:
                    point["baseline_predicted"] = float(baseline_y_pred[i])
                except (TypeError, ValueError):
                    pass
            points.append(point)
    return {
        "iteration": iteration,
        "created_at": datetime.utcnow().isoformat(),
        "points": points,
    }


def _build_test_profiles_from_windows(window_results: List[Dict[str, Any]]) -> List[Any]:
    import numpy as np
    import pandas as pd
    from services.dataset_profiler import DatasetProfiler

    profiler = DatasetProfiler()
    profiles = []
    for day in _extract_challenger_daily_results(window_results):
        y_true = day.get("y_true") or []
        y_pred = day.get("y_pred") or []
        n = min(len(y_true), len(y_pred))
        if n <= 0:
            continue
        date_str = str(day.get("date") or "")
        try:
            base_ts = pd.to_datetime(date_str)
            timestamps = [(base_ts + pd.Timedelta(minutes=15 * i)).isoformat() for i in range(n)]
        except Exception:
            timestamps = [str(i) for i in range(n)]
        try:
            profiles.append(
                profiler.compute_test_profile(
                    np.asarray(y_true[:n], dtype=float),
                    np.asarray(y_pred[:n], dtype=float),
                    timestamps,
                )
            )
        except Exception:
            continue
    return profiles


def _build_train_profile_from_windows(window_results: List[Dict[str, Any]], train_fit_mape: Optional[float] = None) -> Any:
    import pandas as pd
    from services.dataset_profiler import DatasetProfiler
    from services.dataset_profiler_models import TrainProfile

    rows: List[Dict[str, Any]] = []
    for day in _extract_challenger_daily_results(window_results):
        y_true = day.get("y_true") or []
        if not y_true:
            continue
        date_str = str(day.get("date") or "")
        try:
            base_ts = pd.to_datetime(date_str)
        except Exception:
            base_ts = None
        for i, value in enumerate(y_true):
            try:
                load_value = float(value)
            except (TypeError, ValueError):
                continue
            timestamp = (
                base_ts + pd.Timedelta(minutes=15 * i)
                if base_ts is not None else
                pd.Timestamp("1970-01-01") + pd.Timedelta(minutes=15 * len(rows))
            )
            rows.append({"timestamp": timestamp, "load": load_value})
    if rows:
        try:
            df = pd.DataFrame(rows).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
            return DatasetProfiler().compute_train_profile(df, train_fit_mape=train_fit_mape)
        except Exception as exc:
            logger.warning("train profile build from window actuals failed: %s", exc)
    return TrainProfile(
        load_curve_stats={},
        peak_valley_distribution={},
        data_quality={},
        periodicity_strength={},
        period_distribution={},
        dominant_pattern="unknown",
        weekday_weekend_gap=None,
        train_fit_mape=train_fit_mape,
        profile_quality={
            "source": "fallback_empty",
            "point_count": 0,
            "valid_point_count": 0,
            "source_days": 0,
            "is_empty": True,
            "has_real_load_curve": False,
            "has_periodicity_signal": False,
            "has_weekday_weekend_signal": False,
        },
    )


def _flatten_autoresearch_history_for_reflection(iterations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in iterations or []:
        if not isinstance(item, dict):
            continue
        ev = item.get("evaluation") or {}
        mape = ev.get("challenger_mape")
        if mape is None:
            continue
        override = item.get("override") or {}
        direction = ",".join(sorted(str(k) for k in override.keys())) if isinstance(override, dict) else ""
        delta = ev.get("mape_improvement")
        rows.append(
            {
                "mape": mape,
                "direction": direction or item.get("hypothesis_type") or "parameter",
                "delta_mape": -float(delta) if delta is not None else None,
            }
        )
    return rows


async def _update_autoresearch_nextgen_artifacts(
    run_id: str,
    state: Dict[str, Any],
    candidate: Dict[str, Any],
    compare_config: Dict[str, Any],
) -> None:
    """
    Attach next-gen research artifacts to the existing AutoResearch loop.
    This is intentionally side-effect-light: failures are logged by caller and
    must not block the experiment loop.
    """
    from services.analyst_agent import AnalystAgent, ErrorAttribution
    from services.dataset_profiler import DatasetProfiler
    from services.experiment_quality import ExperimentQualityScorer
    from services.knowledge_layer import ClaimKey, KnowledgeClaim, KnowledgeLayer
    from services.periodic_reflection import PeriodicReflection
    from services.research_question_generator import ResearchQuestionGenerator

    iteration = int(candidate.get("iteration") or state.get("current_iteration") or 0)
    cmp_id = str(candidate.get("comparison_id") or "")
    cmp_state = _comparison_store.get(cmp_id) or {}
    window_results = cmp_state.get("window_results") or (candidate.get("summary") or {}).get("window_results") or []
    ev = candidate.get("evaluation") or {}
    cv_fold_metrics = _collect_challenger_cv_metrics(window_results)

    profiler = DatasetProfiler()
    validation_profile = profiler.compute_validation_profile(cv_fold_metrics)
    test_profiles = _build_test_profiles_from_windows(window_results)
    cross_window_pattern = (
        profiler.compute_cross_window_pattern(test_profiles)
        if len(test_profiles) >= 3 else None
    )

    # C6 FIX: build best-effort TrainProfile from available backtest metrics
    _bl_mape = None
    _bl_metrics = (candidate.get("summary") or {}).get("baseline_metrics") or (
        cmp_state.get("summary") or {}
    ).get("baseline_metrics")
    if isinstance(_bl_metrics, dict):
        _bl_mape = _bl_metrics.get("mape")
    if _bl_mape is None:
        # fallback: derive from challenger mape + improvement
        _ch_mape = ev.get("challenger_mape")
        _mi = ev.get("mape_improvement")
        if _ch_mape is not None and _mi is not None:
            try:
                _bl_mape = float(_ch_mape) - float(_mi)
            except (TypeError, ValueError):
                pass
    train_profile = _build_train_profile_from_windows(window_results, train_fit_mape=_bl_mape)

    # C4 FIX: use full AnalystAgent 7-step priority chain (with fallback)
    tri_diagnosis = (
        profiler.compute_tri_dataset_diagnosis(train_profile, validation_profile, test_profiles[-1])
        if test_profiles else None
    )
    analyst_output = None
    if test_profiles:
        analyst_output = AnalystAgent().analyze(
            train_profile=train_profile,
            test_profile=test_profiles[-1],
            tri_dataset_diagnosis=tri_diagnosis,
            cross_window_pattern=cross_window_pattern,
        )
        primary = analyst_output.error_attribution.primary_cause
        evidence = list(analyst_output.error_attribution.evidence)
    else:
        # fallback: simplified diagnosis when no test windows available
        primary = "parameter_saturation"
        evidence = []
        if validation_profile.overfit_indicator in ("high", "moderate"):
            primary = "confirmed_overfit"
            evidence.append(f"cv overfit_indicator={validation_profile.overfit_indicator}")
        if cross_window_pattern and float(cross_window_pattern.drift_signal or 0.0) > 0:
            if primary == "parameter_saturation":
                primary = "drift_signal"
            evidence.append(f"drift_signal={cross_window_pattern.drift_signal}")
    if tri_diagnosis is not None:
        evidence.append(f"tri_dataset_diagnosis={tri_diagnosis.diagnosis_conclusion}")
    if ev.get("mape_improvement") is not None:
        evidence.append(f"mape_improvement={ev.get('mape_improvement')}")
    if ev.get("challenger_mape") is not None:
        evidence.append(f"challenger_mape={ev.get('challenger_mape')}")

    diagnosis = tri_diagnosis.to_dict() if tri_diagnosis is not None else {
        "pattern_consistency": {"status": "unknown"},
        "overfit_detection": primary if primary == "confirmed_overfit" else "not_confirmed",
        "generalization_assessment": "unknown",
        "diagnosis_conclusion": f"轻量诊断 → primary={primary}",
    }
    diagnosis["analyst_primary_cause"] = primary
    diagnosis["analyst_evidence"] = evidence
    diagnosis["validation_profile"] = validation_profile.to_dict()
    if analyst_output is not None:
        diagnosis["analyst_output"] = analyst_output.to_dict()
    state["tri_dataset_diagnosis"] = diagnosis
    state["dataset_profile"] = {
        "train_profile": train_profile.to_dict(),
        "validation_profile": validation_profile.to_dict(),
        "test_profiles": [p.to_dict() for p in test_profiles],
        "cross_window_pattern": cross_window_pattern.to_dict() if cross_window_pattern else None,
        "source": "autoresearch_backtest_actual_load_and_cv_metrics",
    }
    state.setdefault("dataset_profiles", [])
    state["dataset_profiles"].append(
        {
            "iteration": iteration,
            "created_at": datetime.utcnow().isoformat(),
            "train_profile": train_profile.to_dict(),
            "validation_profile": validation_profile.to_dict(),
            "test_profile": test_profiles[-1].to_dict() if test_profiles else None,
            "test_profiles": [p.to_dict() for p in test_profiles],
            "tri_dataset_diagnosis": diagnosis,
            "cross_window_pattern": cross_window_pattern.to_dict() if cross_window_pattern else None,
        }
    )
    state["dataset_profiles"] = state["dataset_profiles"][-100:]

    plot_data = _build_iteration_plot_data(iteration, window_results)
    if plot_data.get("points"):
        state.setdefault("iteration_plot_data", [])
        state["iteration_plot_data"].append(plot_data)
        state["iteration_plot_data"] = state["iteration_plot_data"][-100:]

    questions = ResearchQuestionGenerator().generate(
        ErrorAttribution(primary_cause=primary, contributing_factors=[], evidence=evidence),
        cross_window_pattern=cross_window_pattern,
        recent_questions=state.get("research_questions") or [],
    )
    fallback_question_rows = [q.to_dict() for q in questions]
    candidate_fp = str(candidate.get("applied_patch_fingerprint") or _auto_research_evidence_builder.patch_fingerprint(candidate))
    evidence_rows = []
    try:
        evidence_rows = [_auto_research_evidence_builder.build_for_candidate(run_id=run_id, candidate=candidate, comparison_state=cmp_state).to_dict()]
    except Exception:
        evidence_rows = []
    question_rows = fallback_question_rows
    glm_question_result = None
    try:
        glm_runtime = _glm_questioner_runtime_status()
        state["glm_questioner_runtime"] = glm_runtime
        glm_questioner_enabled = bool(glm_runtime.get("ready"))
        glm_questioner = AutoResearchGLMQuestionGenerator(
            _glm_chat_json,
            enabled=glm_questioner_enabled,
        )
        health = state.get("exploration_health") if isinstance(state.get("exploration_health"), dict) else {}
        glm_question_result = await glm_questioner.generate(
            context={
                "run_id": run_id,
                "iteration": iteration,
                "primary_cause": primary,
                "evidence": evidence,
                "evaluation": ev,
                "tri_dataset_diagnosis": diagnosis,
                "dataset_profile": state.get("dataset_profile") or {},
                "cross_window_pattern": cross_window_pattern.to_dict() if cross_window_pattern else None,
                "exploration_health": health,
                "active_layers": state.get("active_layers") or [],
                "direction_coverage": health.get("direction_coverage") if isinstance(health, dict) else {},
                "evidence_records": evidence_rows,
            },
            fallback_questions=fallback_question_rows,
            recent_questions=state.get("research_questions") or [],
        )
        question_rows = glm_question_result.questions
        state["research_question_generation"] = {
            "iteration": iteration,
            "source": glm_question_result.source,
            "question_source": glm_question_result.source,
            "llm_used": glm_question_result.llm_used,
            "llm_error": glm_question_result.llm_error,
            "glm_questioner_enabled": bool(glm_questioner_enabled),
            "glm_runtime": glm_runtime,
            "disabled_reason": glm_question_result.disabled_reason,
            "fallback_reason": (
                glm_question_result.disabled_reason
                or glm_question_result.llm_error
                or ("no_glm_needed" if not glm_question_result.llm_used else None)
            ),
            "accepted_count": len(glm_question_result.questions),
            "rejected_count": len(glm_question_result.rejected),
            "rejected": glm_question_result.rejected[-10:],
            "created_at": datetime.utcnow().isoformat(),
        }
        state.setdefault("research_question_generation_history", [])
        state["research_question_generation_history"].append(state["research_question_generation"])
        state["research_question_generation_history"] = state["research_question_generation_history"][-50:]
    except Exception as _question_err:
        question_rows = [
            {
                **row,
                "proposal_source": "rule",
                "audit_status": "fallback",
            }
            for row in fallback_question_rows
        ]
        state["research_question_generation"] = {
            "iteration": iteration,
            "source": "rule",
            "question_source": "rule",
            "llm_used": False,
            "llm_error": str(_question_err)[:300],
            "glm_questioner_enabled": False,
            "disabled_reason": "question_generation_exception",
            "fallback_reason": str(_question_err)[:300],
            "accepted_count": len(question_rows),
            "rejected_count": 0,
            "created_at": datetime.utcnow().isoformat(),
        }
    state["research_questions"] = _auto_research_question_lifecycle.merge_questions(
        state.get("research_questions") or [],
        question_rows,
        iteration=iteration,
        patch_fingerprint=candidate_fp,
        evidence_records=evidence_rows,
    )
    state.setdefault("agent_traces", [])
    state["agent_traces"].extend(
        [
            {
                "from_agent": "dataset_profiler",
                "to_agent": "analyst",
                "message_type": "facts",
                "payload": state["dataset_profiles"][-1] if state.get("dataset_profiles") else {},
                "timestamp": datetime.utcnow().isoformat(),
                "iteration": iteration,
            },
            {
                "from_agent": "analyst",
                "to_agent": "research_question_generator",
                "message_type": "attribution",
                "payload": {
                    "primary_cause": primary,
                    "evidence": evidence,
                    "analyst_output": analyst_output.to_dict() if analyst_output is not None else None,
                },
                "timestamp": datetime.utcnow().isoformat(),
                "iteration": iteration,
            },
            {
                "from_agent": "research_question_generator",
                "to_agent": "glm_prompt",
                "message_type": "research_questions",
                "payload": {
                    "research_questions": question_rows,
                    "generation": state.get("research_question_generation") or {},
                },
                "timestamp": datetime.utcnow().isoformat(),
                "iteration": iteration,
            },
        ]
    )
    state["agent_traces"] = state["agent_traces"][-300:]

    override = candidate.get("override") or {}
    patches = [
        {"target_function_id": "global_config", "param_key": str(k), "direction": "set", "value": v}
        for k, v in (override.items() if isinstance(override, dict) else [])
    ]
    quality = ExperimentQualityScorer().score(
        {
            "patches": patches,
            "hypothesis": (question_rows[0].get("question") if question_rows else ""),
            "expected_outcome": {"metric": "mape_improvement"},
            "risk_level": "low",
            "expected_metric_gain": ev.get("mape_improvement") or 0.0,
        }
    )
    state["experiment_quality"] = {
        "iteration": iteration,
        "quality": quality.to_dict(),
    }
    candidate["experiment_quality"] = quality.to_dict()

    try:
        if patches:
            first = patches[0]
            claim = KnowledgeClaim(
                claim_key=ClaimKey(target_param=str(first.get("param_key")), recommended_value=first.get("value")),
                claim=f"{first.get('param_key')}={first.get('value')} 在当前场景的 AutoResearch 候选中产生可验证结果",
                condition={"baseline_workflow_id": state.get("baseline_workflow_id"), "registry_id": state.get("registry_id")},
                evidence=[f"{run_id}:iter{iteration}"] if (ev.get("mape_improvement") or 0) > 0 else [],
                counter_evidence=[f"{run_id}:iter{iteration}"] if (ev.get("mape_improvement") or 0) <= 0 else [],
                confidence=0.5,
                knowledge_type="causal_candidate",
                layer="L2",
            )
            KnowledgeLayer().update_evidence(claim, f"{run_id}:iter{iteration}", supports=(ev.get("mape_improvement") or 0) > 0)
    except Exception:
        pass

    state["history"] = _flatten_autoresearch_history_for_reflection(state.get("iterations") or [])
    reflection_interval = int(compare_config.get("reflection_interval") or 5)
    target_mape = compare_config.get("target_mape")
    reflector = PeriodicReflection(reflection_interval=reflection_interval, target_mape=target_mape)
    if reflector.should_trigger(iteration):
        reflector.reflect(state, iteration=iteration, target_mape=target_mape)

    _persist_autoresearch_run_artifacts(run_id, state)


def _apply_structure_patch_to_workflow(workflow, structure_patch: Dict[str, Any]):
    if not isinstance(structure_patch, dict):
        return workflow
    workflow_dict = workflow.dict()
    node_map = {str(n.get("id")): n for n in (workflow_dict.get("nodes") or [])}

    ncp = structure_patch.get("node_config_patches")
    if isinstance(ncp, list) and len(ncp) > 0:
        for item in ncp:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "").strip()
            cp = item.get("config_patch") if isinstance(item.get("config_patch"), dict) else {}
            if not node_id or not cp:
                continue
            node = node_map.get(node_id)
            if not isinstance(node, dict):
                continue
            data = node.get("data") or {}
            cfg = dict(data.get("config") or {})
            fid = str(cfg.get("functionId") or "")
            allowed = _ALLOWED_NODE_CONFIG_PATCH_KEYS_BY_FUNCTION.get(fid)
            if not allowed:
                continue
            for ck, cv in cp.items():
                key = str(ck).strip()
                if key not in allowed:
                    continue
                if key in ("window_size", "step"):
                    try:
                        cfg[key] = int(cv)
                    except (TypeError, ValueError):
                        continue
                else:
                    cfg[key] = cv
            data["config"] = cfg
            node["data"] = data
            node_map[node_id] = node

    switches = structure_patch.get("node_switches")
    if isinstance(switches, list) and len(switches) > 0:
        for item in switches:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id") or "").strip()
            enabled = item.get("enabled")
            if not node_id or not isinstance(enabled, bool):
                continue
            node = node_map.get(node_id)
            if not isinstance(node, dict):
                continue
            data = node.get("data") or {}
            cfg = data.get("config") or {}
            fid = str(cfg.get("functionId") or "")
            if not _structure_switch_allowed(fid):
                continue
            cfg["enabled"] = enabled
            data["config"] = cfg
            node["data"] = data
            node_map[node_id] = node

    workflow_dict["nodes"] = list(node_map.values())
    return EnhancedWorkflow(**workflow_dict)


def _build_structure_patch_candidate_from_workflow(workflow_id: str) -> Dict[str, Any]:
    wf = load_workflow_from_file(workflow_id)
    if wf is None:
        return {}
    switches: List[Dict[str, Any]] = []
    for n in (wf.dict().get("nodes") or []):
        node_id = str(n.get("id") or "")
        cfg = ((n.get("data") or {}).get("config") or {})
        fid = str(cfg.get("functionId") or "")
        if fid in _FEATURE_STRUCTURE_SWITCH_FUNCTIONS:
            current_enabled = bool(cfg.get("enabled", True))
            switches.append({"node_id": node_id, "enabled": (not current_enabled), "functionId": fid})
            break
    if not switches:
        return {}
    return {"node_switches": switches}


def _load_memory_cases() -> List[Dict[str, Any]]:
    return _auto_research_memory_store.load()


def _save_memory_cases(cases: List[Dict[str, Any]]) -> None:
    _auto_research_memory_store.save(cases)


def _append_memory_case(case: Dict[str, Any]) -> None:
    _auto_research_memory_store.append(case)


def _memory_context_fingerprint(state: Dict[str, Any]) -> Dict[str, Any]:
    ec = state.get("evaluation_contract") or {}
    return {
        "baseline_workflow_id": state.get("baseline_workflow_id"),
        "backtest_mode": ec.get("backtest_mode"),
        "daily_horizon": ec.get("daily_horizon"),
        "mask_target_values": ec.get("backtest_mask_target_values"),
        "apply_window_filter": ec.get("backtest_apply_window_filter"),
    }


def _compute_scenario_fingerprint(
    state: Dict[str, Any],
    windows: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    fp = _auto_research_memory_store.compute_scenario_fingerprint(state, windows=windows)
    fp["baseline_workflow_id"] = state.get("baseline_workflow_id")
    fp["registry_id"] = state.get("registry_id")
    try:
        from services.knowledge_layer import normalize_scenario_fingerprint
        return normalize_scenario_fingerprint(fp)
    except Exception:
        return {k: v for k, v in fp.items() if v not in (None, "", [], {})}


def _retrieve_memory_cases(
    baseline_workflow_id: str,
    scenario_tags: List[str],
    limit: int = 5,
    query_fingerprint: Optional[Dict[str, Any]] = None,
    query_diagnosis: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return _auto_research_memory_store.retrieve(
        baseline_workflow_id,
        scenario_tags,
        limit=limit,
        query_fingerprint=query_fingerprint,
        query_diagnosis=query_diagnosis,
    )


def _validate_node_config_patches_for_workflow(wf_id: str, patches: Any) -> List[str]:
    errs: List[str] = []
    if not isinstance(patches, list):
        return ["structure_patch.node_config_patches 必须为数组"]
    wf = load_workflow_from_file(wf_id)
    if wf is None:
        return [f"模板不存在，无法校验 node_config_patches: {wf_id}"]
    node_map = {str(n.get("id")): n for n in (wf.dict().get("nodes") or [])}
    for idx, item in enumerate(patches):
        if not isinstance(item, dict):
            errs.append(f"structure_patch.node_config_patches[{idx}] 必须为对象")
            continue
        node_id = str(item.get("node_id") or "").strip()
        cp = item.get("config_patch")
        if not node_id:
            errs.append(f"structure_patch.node_config_patches[{idx}].node_id 不能为空")
            continue
        if not isinstance(cp, dict):
            errs.append(f"structure_patch.node_config_patches[{idx}].config_patch 必须为对象")
            continue
        node = node_map.get(node_id)
        if not isinstance(node, dict):
            errs.append(f"structure_patch.node_config_patches[{idx}] 未知 node_id: {node_id}")
            continue
        cfg = ((node.get("data") or {}).get("config") or {})
        fid = str(cfg.get("functionId") or "").strip()
        declared = str(item.get("functionId") or "").strip()
        if declared and declared != fid:
            errs.append(f"structure_patch.node_config_patches[{idx}] functionId 与模板不符（模板={fid}）")
            continue
        allowed = _ALLOWED_NODE_CONFIG_PATCH_KEYS_BY_FUNCTION.get(fid)
        if not allowed:
            errs.append(f"structure_patch.node_config_patches[{idx}] 不支持补丁 functionId={fid}")
            continue
        for ck, cv in cp.items():
            key = str(ck).strip()
            if key not in allowed:
                errs.append(f"structure_patch.node_config_patches[{idx}] 不允许字段 {key}")
                continue
            if key in ("window_size", "step"):
                try:
                    int(cv)
                except (TypeError, ValueError):
                    errs.append(f"structure_patch.node_config_patches[{idx}].config_patch.{key} 必须为整数")
    return errs


def _fix_node_ids_by_function_id(
    patches: List[Dict[str, Any]],
    baseline_workflow_id: str,
    patch_type: str = "node_param_patches",
) -> tuple:
    """
    任务 26.1：按 functionId 自动修复 node_id。

    GLM 输出的 node_id 可能是语义名（如 "feat_rolling"），而模板里是真实 ID（如 "tpl-rolling_statistics-8"）。
    此函数扫描模板节点，按 functionId 找到真实 node_id 并替换。

    Args:
        patches（补丁列表）: node_param_patches 或 node_switches 列表
        baseline_workflow_id（模板 ID）: 用于查找真实节点
        patch_type（补丁类型）: 用于日志

    Returns:
        (fixed_patches, fix_logs) — 修复后的补丁列表 + 修复日志列表
    """
    import logging as _logging
    wf = load_workflow_from_file(str(baseline_workflow_id).strip())
    if wf is None:
        return patches, []

    # 构建 functionId → node_id 映射（取第一个匹配）
    fid_to_node_id: Dict[str, str] = {}
    node_ids_in_template: set = set()
    for n in (wf.dict().get("nodes") or []):
        nid = str(n.get("id") or "").strip()
        fid = str(((n.get("data") or {}).get("config") or {}).get("functionId") or "").strip()
        if nid:
            node_ids_in_template.add(nid)
        if nid and fid and fid not in fid_to_node_id:
            fid_to_node_id[fid] = nid

    fixed = []
    logs = []
    for item in (patches or []):
        if not isinstance(item, dict):
            fixed.append(item)
            continue
        item = dict(item)
        node_id = str(item.get("node_id") or "").strip()
        fid = str(item.get("functionId") or item.get("functionId") or "").strip()

        if node_id and node_id not in node_ids_in_template:
            # node_id 不在模板中，尝试按 functionId 修复
            real_nid = fid_to_node_id.get(fid) if fid else None
            if not real_nid:
                # 尝试从 node_id 本身推断 functionId（如 "feat_rolling" → "rolling_statistics"）
                for known_fid, known_nid in fid_to_node_id.items():
                    if known_fid.lower() in node_id.lower() or node_id.lower() in known_fid.lower():
                        real_nid = known_nid
                        fid = known_fid
                        break
            if real_nid:
                log_msg = f"自动修复 node_id: {node_id} → {real_nid}（按 functionId={fid} 匹配，{patch_type}）"
                _logging.getLogger(__name__).info(log_msg)
                logs.append(log_msg)
                item["node_id"] = real_nid
                if fid and not item.get("functionId"):
                    item["functionId"] = fid
        elif not node_id and fid:
            # node_id 为空但有 functionId，直接填入
            real_nid = fid_to_node_id.get(fid)
            if real_nid:
                item["node_id"] = real_nid
                logs.append(f"自动填充 node_id: {real_nid}（按 functionId={fid}，{patch_type}）")

        fixed.append(item)
    return fixed, logs


def _validate_proposal_patch(proposal: Dict[str, Any], baseline_workflow_id: Optional[str] = None) -> Dict[str, Any]:
    errors: List[str] = []
    search_patch = proposal.get("search_space_patch") or {}
    eval_patch = proposal.get("evaluation_contract_patch") or {}
    structure_patch = proposal.get("structure_patch") or {}
    if not isinstance(search_patch, dict):
        errors.append("search_space_patch 必须为对象")
        search_patch = {}
    if not isinstance(eval_patch, dict):
        errors.append("evaluation_contract_patch 必须为对象")
        eval_patch = {}
    if not isinstance(structure_patch, dict):
        errors.append("structure_patch 必须为对象")
        structure_patch = {}

    # 任务 26.1：在校验前，按 functionId 自动修复 node_id
    fix_logs: List[str] = []
    if baseline_workflow_id:
        # 修复 structure_patch.node_switches
        switches_raw = structure_patch.get("node_switches")
        if isinstance(switches_raw, list) and switches_raw:
            fixed_switches, sw_logs = _fix_node_ids_by_function_id(
                switches_raw, baseline_workflow_id, "node_switches"
            )
            structure_patch = dict(structure_patch)
            structure_patch["node_switches"] = fixed_switches
            proposal = dict(proposal)
            proposal["structure_patch"] = structure_patch
            fix_logs.extend(sw_logs)
        # 修复 node_param_patches
        npp_raw = proposal.get("node_param_patches")
        if isinstance(npp_raw, list) and npp_raw:
            fixed_npp, npp_logs = _fix_node_ids_by_function_id(
                npp_raw, baseline_workflow_id, "node_param_patches"
            )
            proposal = dict(proposal)
            proposal["node_param_patches"] = fixed_npp
            fix_logs.extend(npp_logs)

    for k, v in search_patch.items():
        if k not in _ALLOWED_SEARCH_SPACE_PATCH_KEYS:
            errors.append(f"search_space_patch 不允许字段: {k}")
            continue
        if not isinstance(v, list):
            errors.append(f"search_space_patch.{k} 必须为数组")
            continue
        if len(v) == 0 or len(v) > 50:
            errors.append(f"search_space_patch.{k} 长度必须在 1..50")
            continue
        if k == "feature_recipe_id":
            rk = known_recipe_ids()
            for i, item in enumerate(v):
                s = str(item).strip()
                if not s:
                    errors.append(f"search_space_patch.feature_recipe_id[{i}] 不能为空")
                elif rk and s not in rk:
                    errors.append(f"search_space_patch.feature_recipe_id[{i}] 未知 recipe: {s}")

    fr_top = proposal.get("feature_recipe_id")
    if fr_top is not None and fr_top != "":
        if not isinstance(fr_top, str):
            errors.append("proposal.feature_recipe_id 必须为字符串")
        else:
            rs = fr_top.strip()
            rk = known_recipe_ids()
            if rs and rk and rs not in rk:
                errors.append(f"proposal.feature_recipe_id 未知 recipe: {rs}")

    for k, v in eval_patch.items():
        if k not in _ALLOWED_EVAL_PATCH_KEYS:
            errors.append(f"evaluation_contract_patch 不允许字段: {k}")
            continue
        if isinstance(v, (dict, list)):
            errors.append(f"evaluation_contract_patch.{k} 不能为对象/数组")

    switches = structure_patch.get("node_switches")
    if switches is not None:
        if not isinstance(switches, list):
            errors.append("structure_patch.node_switches 必须为数组")
        else:
            cap = _proposal_structure_switch_cap(switches)
            if len(switches) > cap:
                errors.append(f"structure_patch.node_switches 最多允许 {cap} 个")
            # 降级：过滤掉 node_id 无效或 functionId 不在白名单的 switch
            valid_switches = []
            for idx, it in enumerate(switches):
                if not isinstance(it, dict):
                    continue
                node_id = str(it.get("node_id") or "").strip()
                enabled = it.get("enabled")
                fid = str(it.get("functionId") or "").strip()
                if not node_id:
                    fix_logs.append(f"node_switches[{idx}] 丢弃：node_id 为空（functionId={fid}）")
                    continue
                if not isinstance(enabled, bool):
                    fix_logs.append(f"node_switches[{idx}] 丢弃：enabled 不是布尔（node_id={node_id}）")
                    continue
                if fid and not _structure_switch_allowed(fid):
                    fix_logs.append(f"node_switches[{idx}] 丢弃：functionId={fid} 不在白名单")
                    continue
                valid_switches.append(it)
            if len(valid_switches) != len(switches):
                fix_logs.append(
                    f"node_switches 降级：{len(switches)} 条中保留 {len(valid_switches)} 条合法 switch"
                )
                structure_patch = dict(structure_patch)
                structure_patch["node_switches"] = valid_switches
                proposal = dict(proposal)
                proposal["structure_patch"] = structure_patch

    ncp = structure_patch.get("node_config_patches")
    if ncp is not None:
        if not isinstance(ncp, list):
            errors.append("structure_patch.node_config_patches 必须为数组")
        elif len(ncp) > 12:
            errors.append("structure_patch.node_config_patches 最多允许 12 条")
        elif baseline_workflow_id:
            errors.extend(_validate_node_config_patches_for_workflow(str(baseline_workflow_id).strip(), ncp))

    gcp = proposal.get("global_config_patch")
    if gcp is not None:
        if not isinstance(gcp, dict):
            errors.append("global_config_patch 必须为对象")
        else:
            errors.extend(_validate_global_config_patch_entries(gcp))

    npp = proposal.get("node_param_patches")
    if npp is not None:
        if not isinstance(npp, list):
            errors.append("node_param_patches 必须为数组")
        elif baseline_workflow_id:
            npp_errors = _validate_node_param_patches_autoresearch(str(baseline_workflow_id).strip(), npp)
            if npp_errors:
                # 降级处理：过滤掉有问题的 patch，保留合法的，不让整个候选失败
                # 这对 GLM 候选尤其重要（GLM 可能输出空 node_id）
                valid_npp = []
                wf_tmp = load_workflow_from_file(str(baseline_workflow_id).strip())
                node_ids_valid: set = set()
                if wf_tmp is not None:
                    for _n in (wf_tmp.dict().get("nodes") or []):
                        _nid = str(_n.get("id") or "").strip()
                        if _nid:
                            node_ids_valid.add(_nid)
                for item in npp:
                    if not isinstance(item, dict):
                        continue
                    nid = str(item.get("node_id") or "").strip()
                    if nid and nid in node_ids_valid:
                        valid_npp.append(item)
                    # 空 node_id 或不在模板中的 patch 直接丢弃（已在修复阶段尝试过）
                fix_logs.append(
                    f"node_param_patches 降级：{len(npp)} 条中保留 {len(valid_npp)} 条合法 patch，"
                    f"丢弃 {len(npp) - len(valid_npp)} 条（node_id 无效）"
                )
                proposal["node_param_patches"] = valid_npp
        elif len(npp) > 0:
            errors.append("node_param_patches 校验需要 baseline_workflow_id")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "fix_logs": fix_logs,  # 任务 26.1：记录自动修复的 node_id
    }


def _compute_error_diagnosis(report: Dict[str, Any]) -> Dict[str, Any]:
    return _auto_research_diagnostics.compute_error_diagnosis(
        report,
        comparison_store=_comparison_store,
    )


def _generate_proposal_from_report(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    failure_stats = summary.get("failure_stats") or {}
    eval_contract = dict(report.get("evaluation_contract") or {})
    search_space = dict(report.get("search_space") or {})
    scenario_tags = report.get("scenario_tags") or []
    baseline_wf_id = str(report.get("baseline_workflow_id") or "")
    memory_refs = report.get("memory_references") if isinstance(report.get("memory_references"), list) else []
    if not memory_refs:
        memory_refs = _retrieve_memory_cases(baseline_wf_id, scenario_tags, limit=3) if baseline_wf_id else []
    search_patch: Dict[str, Any] = {}
    eval_patch: Dict[str, Any] = {}
    notes: List[str] = []
    risk_level = "low"

    # 任务 3.4：读取当前 phase，结构探索阶段调整策略
    current_phase = str(report.get("phase") or "parameter_exploration")
    in_structure_exploration = (current_phase == "structure_exploration")

    if memory_refs:
        # 任务 7.3：区分"参考"（成功）和"回避"（失败）case_id
        ref_ids = [str(x.get("case_id")) for x in memory_refs if x.get("case_id") and bool((x.get("outcome") or {}).get("improved"))]
        avoid_ids = [str(x.get("case_id")) for x in memory_refs if x.get("case_id") and not bool((x.get("outcome") or {}).get("improved"))]
        if ref_ids:
            notes.append("参考历史案例（成功）：" + ", ".join(ref_ids))
        if avoid_ids:
            notes.append("回避历史案例（失败）：" + ", ".join(avoid_ids))

    if int(failure_stats.get("insufficient_train_data") or 0) > 0:
        td = eval_contract.get("train_days") or eval_contract.get("backtest_train_days") or 30
        try:
            td_val = int(td)
            new_td = max(7, td_val - 7)
            if new_td != td_val:
                eval_patch["train_days"] = new_td
                eval_patch["backtest_train_days"] = new_td
                notes.append("检测到训练数据不足，建议下调 train_days 提升可执行率")
        except (TypeError, ValueError):
            pass

    if int(failure_stats.get("no_test_data") or 0) > 0:
        notes.append("检测到部分窗口无测试数据，建议调整时间窗到数据覆盖区间")
        risk_level = "medium"

    best_impr = summary.get("best_mape_improvement")
    try:
        best_impr_val = float(best_impr) if best_impr is not None else None
    except (TypeError, ValueError):
        best_impr_val = None
    if best_impr_val is None or best_impr_val <= 0:
        base_trials = eval_contract.get("auto_tune_n_trials", 5)
        try:
            bt = int(base_trials)
        except (TypeError, ValueError):
            bt = 5
        search_patch["auto_tune_n_trials"] = sorted(list(set([max(2, bt - 2), bt, min(12, bt + 2)])))
        notes.append("当前最优改善有限，建议扩展 auto_tune_n_trials 的探索范围")

    if "train_days" not in search_patch:
        base_td = eval_contract.get("train_days") or 30
        try:
            td = int(base_td)
            search_patch["train_days"] = sorted(list(set([max(7, td - 14), td, td + 14])))
            search_patch["backtest_train_days"] = list(search_patch["train_days"])
        except (TypeError, ValueError):
            pass

    # Phase D：优先参数层——改善偏弱时给出 global_config / 节点 param 小步 hint
    global_config_patch: Dict[str, Any] = {}
    node_param_patches: List[Dict[str, Any]] = []
    if baseline_wf_id and best_impr_val is not None and best_impr_val <= 0.08:
        hg, hn = _build_light_parameter_hints_from_workflow(baseline_wf_id)
        global_config_patch = dict(hg or {})
        node_param_patches = list(hn or [])
        if global_config_patch or node_param_patches:
            notes.append("参数优先：建议在应用后继续探索全局/节点参数（未改 DAG 开关）")

    # Phase A/B：特征配方枚举（结构层）
    # 任务 24.1：recipe_threshold 从 0.02 放宽到 0.08（改善 < 8% 就加特征配方）
    # 诊断明确指向结构问题时，不管 phase 是什么都强制加结构改动
    structure_patch: Dict[str, Any] = {}
    recipe_threshold = 1.0 if in_structure_exploration else 0.08
    try:
        rk = known_recipe_ids()
        if rk and (in_structure_exploration or (best_impr_val is not None and best_impr_val <= recipe_threshold)):
            cand_ids = ["features_trim_calendar_v1", "features_trim_diff_v1", "features_full_default_v1"]
            ids_ordered = [x for x in cand_ids if x in rk]
            if ids_ordered:
                search_patch["feature_recipe_id"] = ids_ordered
                if in_structure_exploration:
                    notes.append("结构探索阶段：主动加入特征配方抽样空间（候选 C 含结构变更）")
                    structure_patch = {"feature_recipe_id": ids_ordered[0]}
                    risk_level = "medium"
                else:
                    notes.append("改善 < 8%：加入特征配方抽样空间（弱化日历/差分或保持默认）")
    except Exception:
        pass

    if not notes:
        notes.append("建议保持当前策略，继续小步探索")

    # 生成 error_diagnosis：从最近一轮成功 iteration 的 error_profile 做规则判断
    error_diagnosis = _compute_error_diagnosis(report)

    # 任务 12.1：按诊断结论分支调整候选策略
    # 任务 24.1：诊断明确指向结构问题时，force_structure_from_diagnosis=True，不管 phase 都加结构改动
    diag_source = str((error_diagnosis or {}).get("primary_error_source") or "")
    force_structure_from_diagnosis = diag_source in ("weekend_pattern_shift", "outlier_days", "model_divergence")

    if diag_source == "weekend_pattern_shift":
        # 周末误差大 → 开启日历特征节点 + 扩大 lags（任务 24.2）
        notes.append("诊断：周末误差显著（weekend_pattern_shift），建议启用节假日/工作日特征并扩大滞后步数")
        if not structure_patch:
            structure_patch = {}
        if baseline_wf_id:
            wf_tmp = load_workflow_from_file(baseline_wf_id)
            if wf_tmp is not None:
                for n in (wf_tmp.dict().get("nodes") or []):
                    nid = str(n.get("id") or "")
                    fid = str(((n.get("data") or {}).get("config") or {}).get("functionId") or "")
                    if fid in ("holiday_features", "workday_features"):
                        sw = structure_patch.get("node_switches") or []
                        sw.append({"node_id": nid, "functionId": fid, "enabled": True})
                        structure_patch["node_switches"] = sw
                    # 任务 24.2：同时生成 node_param_patches（扩大 lags 覆盖周末）
                    if fid == "create_lag_features":
                        node_param_patches.append({
                            "node_id": nid,
                            "functionId": fid,
                            "param_patch": {"lags": [1, 2, 3, 7, 14, 21]},
                        })
        risk_level = "medium"
    elif diag_source == "data_coverage_insufficient":
        # 数据覆盖不足 → 缩短 train_days
        notes.append("诊断：数据覆盖不足（data_coverage_insufficient），建议缩短 train_days 提升可执行率")
        base_td = eval_contract.get("train_days") or 30
        try:
            td = int(base_td)
            eval_patch["train_days"] = max(7, td - 7)
            eval_patch["backtest_train_days"] = eval_patch["train_days"]
        except (TypeError, ValueError):
            pass
    elif diag_source == "outlier_days":
        # 异常天误差大 → 开启差分特征 + 扩大滚动窗口（任务 24.2）
        notes.append("诊断：存在高误差异常天（outlier_days），建议启用差分特征增强鲁棒性")
        if baseline_wf_id:
            wf_tmp = load_workflow_from_file(baseline_wf_id)
            if wf_tmp is not None:
                for n in (wf_tmp.dict().get("nodes") or []):
                    nid = str(n.get("id") or "")
                    fid = str(((n.get("data") or {}).get("config") or {}).get("functionId") or "")
                    if fid == "diff_features":
                        sw = (structure_patch or {}).get("node_switches") or []
                        sw.append({"node_id": nid, "functionId": fid, "enabled": True})
                        if not structure_patch:
                            structure_patch = {}
                        structure_patch["node_switches"] = sw
                    # 任务 24.2：同时生成 node_param_patches（扩大滚动窗口捕捉异常模式）
                    if fid == "rolling_statistics":
                        node_param_patches.append({
                            "node_id": nid,
                            "functionId": fid,
                            "param_patch": {"window_sizes": [4, 8, 24, 48]},
                        })
        risk_level = "medium"
    elif diag_source == "model_divergence":
        # 模型间差异大 → 建议集成模式
        notes.append("诊断：各模型表现差异大（model_divergence），建议尝试 all_adaptive 集成模式")
        global_config_patch["ensemble_mode"] = "all_adaptive"
        risk_level = "medium"

    # 任务 22.1：为规则候选生成假设（诊断驱动 / 洞察深入 / 探索性）
    # 候选 A：基于 error_diagnosis 的诊断驱动假设
    hypothesis_a: Optional[str] = None
    hypothesis_type_a = "parameter"
    expected_outcome_a: Optional[Dict[str, Any]] = None
    fallback_a: Optional[str] = None

    if diag_source == "weekend_pattern_shift":
        hypothesis_a = "因为节假日/工作日特征不足，所以启用日历特征并扩大滞后步数应该能降低周末误差"
        hypothesis_type_a = "feature"
        expected_outcome_a = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.003, "description": "MAPE 改善 > 0.3%"}
        fallback_a = "若无改善，考虑调整 train_days 覆盖更多周末样本"
    elif diag_source == "data_coverage_insufficient":
        hypothesis_a = "因为训练数据不足，所以缩短 train_days 应该能提升回测成功率"
        hypothesis_type_a = "parameter"
        expected_outcome_a = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.001, "description": "回测成功率提升"}
        fallback_a = "若仍不足，考虑调整时间窗到数据覆盖区间"
    elif diag_source == "outlier_days":
        hypothesis_a = "因为存在高误差异常天，所以启用差分特征并扩大滚动窗口应该能增强鲁棒性"
        hypothesis_type_a = "feature"
        expected_outcome_a = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.003, "description": "MAPE 改善 > 0.3%"}
        fallback_a = "若无改善，考虑调整异常值检测阈值"
    elif diag_source == "model_divergence":
        hypothesis_a = "因为各模型表现差异大，所以启用自适应集成权重应该能利用模型互补性"
        hypothesis_type_a = "model"
        expected_outcome_a = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.005, "description": "MAPE 改善 > 0.5%"}
        fallback_a = "若无改善，考虑去掉表现最差的模型"
    elif best_impr_val is not None and best_impr_val <= 0:
        hypothesis_a = "因为当前参数组合无改善，所以扩大调参轮数应该能找到更优参数"
        hypothesis_type_a = "parameter"
        expected_outcome_a = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.002, "description": "MAPE 改善 > 0.2%"}
        fallback_a = "若仍无改善，考虑引入特征配方变更"
    else:
        hypothesis_a = "因为改善空间有限，所以调整训练天数应该能找到更优的数据窗口"
        hypothesis_type_a = "parameter"
        expected_outcome_a = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.002, "description": "MAPE 改善 > 0.2%"}
        fallback_a = "若无改善，考虑引入特征层变更"

    # 候选 B：基于已验证有效方向的深入假设
    insights = report.get("insights") or {}
    effective_dirs = insights.get("effective_directions") or []
    hypothesis_b: Optional[str] = None
    if effective_dirs:
        last_effective = effective_dirs[-1]
        hypothesis_b = f"基于已验证有效方向（{last_effective[:50]}），进一步优化相同方向应该能再降误差"
    else:
        hypothesis_b = "在当前参数基础上，引入特征配方变更应该能带来额外改善"

    # 候选 C：探索性假设（注册表随机采样方向）
    hypothesis_c = "探索未试过的参数组合，可能发现意外的改善空间"

    # 任务 22.2：已否证假设集中的方向不再生成（按 patch 内容去重，不靠文本匹配）
    disproved = report.get("disproved_hypotheses") or []
    disproved_fingerprints = [d.get("patch_fingerprint") for d in disproved if d.get("patch_fingerprint")]
    # 检查候选 A 的 patch 是否和已否证的 patch 重复
    _candidate_a_fp = _build_patch_fingerprint({
        "structure_patch": structure_patch,
        "node_param_patches": node_param_patches,
        "global_config_patch": global_config_patch,
    })
    if _candidate_a_fp and _candidate_a_fp in disproved_fingerprints:
        notes.append(f"⚠️ 候选 A 的改动方向已被否证（patch 指纹匹配），已调整为探索性方向")
        hypothesis_a = "探索新方向（原方向已否证）：" + (hypothesis_a or "")
        # 清空已否证的 patch，避免重复执行
        structure_patch = {}
        node_param_patches = []

    return {
        "search_space_patch": search_patch,
        "evaluation_contract_patch": eval_patch,
        "structure_patch": structure_patch,
        "global_config_patch": global_config_patch,
        "node_param_patches": node_param_patches,
        "notes": notes,
        "risk_level": risk_level,
        "base_search_space": search_space,
        "base_evaluation_contract": eval_contract,
        "memory_references": memory_refs,
        "error_diagnosis": error_diagnosis,
        # 任务 22.1：假设相关字段
        "hypothesis": hypothesis_a,
        "hypothesis_type": hypothesis_type_a,
        "expected_outcome": expected_outcome_a,
        "fallback_if_failed": fallback_a,
        "hypothesis_b": hypothesis_b,
        "hypothesis_c": hypothesis_c,
    }


def _proposal_risk_rank(risk_level: str) -> int:
    return _auto_research_proposal_manager.risk_rank(risk_level)


def _truncate_debug_text(value: Any, limit: int = 12000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _score_proposal_candidate(candidate: Dict[str, Any]) -> float:
    return _auto_research_proposal_manager.score_candidate(candidate)


def _score_proposal_experiment_quality(proposal: Dict[str, Any]) -> Dict[str, Any]:
    return _auto_research_proposal_manager.score_experiment_quality(proposal)


def _infer_primary_variable(candidate: Dict[str, Any]) -> Optional[str]:
    """
    任务 27.1：推断候选的主变量（primary_variable）。

    如果候选只改了一个维度的参数，返回该维度的代表参数名。
    多维度改动返回 None（不标记主变量）。

    Args:
        candidate（候选对象）: proposal 候选

    Returns:
        主变量名（如 "train_days" / "lags" / "ensemble_mode"），或 None
    """
    sp = candidate.get("search_space_patch") or {}
    ep = candidate.get("evaluation_contract_patch") or {}
    stp = candidate.get("structure_patch") or {}
    gcp = candidate.get("global_config_patch") or {}
    npp = candidate.get("node_param_patches") or []

    # 统计各维度的改动
    dimensions: List[str] = []

    # 参数层：train_days / n_trials 等
    param_keys = set(sp.keys()) | set(ep.keys()) | set(gcp.keys())
    if param_keys:
        # 找最具代表性的 key
        for key in ("train_days", "auto_tune_n_trials", "daily_horizon", "backtest_mode", "ensemble_mode"):
            if key in param_keys:
                dimensions.append(key)
                break
        else:
            dimensions.append(next(iter(param_keys)))

    # 特征层：node_param_patches（lags / window_sizes 等）
    if isinstance(npp, list) and npp:
        for item in npp:
            if not isinstance(item, dict):
                continue
            pp = item.get("param_patch") or {}
            for key in ("lags", "window_sizes", "window_size", "step"):
                if key in pp:
                    dimensions.append(key)
                    break
            else:
                fid = str(item.get("functionId") or "")
                if fid:
                    dimensions.append(fid)
            break  # 只取第一个 patch 的代表

    # 结构层：node_switches
    switches = (stp.get("node_switches") or []) if isinstance(stp, dict) else []
    if isinstance(switches, list) and switches:
        fids = [str(s.get("functionId") or "") for s in switches if isinstance(s, dict)]
        if fids:
            dimensions.append(fids[0])

    # 只有一个维度时才标记主变量
    if len(dimensions) == 1:
        return dimensions[0]
    return None


def _infer_hypothesis_type_from_patch(
    *,
    override: Optional[Dict[str, Any]] = None,
    structure_patch: Optional[Dict[str, Any]] = None,
    node_param_patches: Optional[List[Dict[str, Any]]] = None,
    global_config_patch: Optional[Dict[str, Any]] = None,
) -> str:
    """从实际生效补丁推断实验类型，供连续类型统计和 trial ledger 使用。"""
    switches = (structure_patch or {}).get("node_switches") if isinstance(structure_patch, dict) else []
    if isinstance(switches, list):
        for item in switches:
            if not isinstance(item, dict):
                continue
            fid = str(item.get("functionId") or "")
            if fid in {"xgboost_forecast", "lightgbm_forecast", "catboost_forecast", "ridge_forecast", "ensemble_forecast"}:
                return "model"
        if switches:
            return "feature"
    if isinstance(node_param_patches, list) and node_param_patches:
        for item in node_param_patches:
            if not isinstance(item, dict):
                continue
            fid = str(item.get("functionId") or "")
            if fid in {"xgboost_forecast", "lightgbm_forecast", "catboost_forecast", "ridge_forecast", "ensemble_forecast"}:
                return "model"
        return "feature"
    keys = set((override or {}).keys()) | set((global_config_patch or {}).keys())
    if keys & {"ensemble_mode", "ensemble_weight_mode", "active_models"}:
        return "model"
    if keys & {"daily_horizon", "sliding_window.step"}:
        return "data"
    return "parameter"


def _layer_from_hypothesis_type(hypothesis_type: str) -> str:
    value = str(hypothesis_type or "").strip().lower()
    if value in {"feature", "model", "data"}:
        return value
    return "training"


def _build_applied_patch_fingerprint(
    *,
    override: Optional[Dict[str, Any]] = None,
    structure_patch: Optional[Dict[str, Any]] = None,
    global_config_patch: Optional[Dict[str, Any]] = None,
    node_param_patches: Optional[List[Dict[str, Any]]] = None,
) -> str:
    return _canonical_json_key({
        "override": override or {},
        "structure_patch": structure_patch or {},
        "global_config_patch": global_config_patch or {},
        "node_param_patches": node_param_patches or [],
    })


def _build_autoresearch_batch_group_record(
    *,
    iteration: int,
    group_idx: int,
    comparison_id: str,
    override: Dict[str, Any],
    compare_state: Dict[str, Any],
    policy: Dict[str, Any],
    group_spec: Dict[str, Any],
    is_best: bool,
    is_primary: bool,
    runtime_patch_snapshot: Dict[str, Any],
    effective_search_space: Dict[str, Any],
    effective_evaluation_contract: Dict[str, Any],
) -> Dict[str, Any]:
    status = str((compare_state or {}).get("status") or "unknown")
    summary = (compare_state or {}).get("summary") if isinstance((compare_state or {}).get("summary"), dict) else {}
    evaluation = _evaluate_autoresearch_candidate(compare_state, policy) if status == "success" else {}
    if status == "success" and "windows_comparable" in summary and int(summary.get("windows_comparable") or 0) <= 0:
        status = "failed"
        evaluation = {}
    structure_patch = group_spec.get("structure_patch") if isinstance(group_spec.get("structure_patch"), dict) else {}
    global_config_patch = group_spec.get("global_config_patch") if isinstance(group_spec.get("global_config_patch"), dict) else {}
    node_param_patches = group_spec.get("node_param_patches") if isinstance(group_spec.get("node_param_patches"), list) else []
    hypothesis_type = str(group_spec.get("hypothesis_type") or _infer_hypothesis_type_from_patch(
        override=override,
        structure_patch=structure_patch,
        node_param_patches=node_param_patches,
        global_config_patch=global_config_patch,
    ))
    record = {
        "iteration_no": iteration,
        "group_idx": group_idx,
        "comparison_id": comparison_id,
        "candidate_source": group_spec.get("candidate_source") or "unknown",
        "selected_layer": group_spec.get("selected_layer") or _layer_from_hypothesis_type(hypothesis_type),
        "target_direction": group_spec.get("target_direction"),
        "target_layer": group_spec.get("target_layer"),
        "exploration_role": group_spec.get("exploration_role"),
        "planner_reason": group_spec.get("planner_reason"),
        "hypothesis": group_spec.get("hypothesis"),
        "hypothesis_type": hypothesis_type,
        "primary_variable": group_spec.get("primary_variable"),
        "status": status,
        "override": override or {},
        "structure_patch": structure_patch or {},
        "global_config_patch": global_config_patch or {},
        "node_param_patches": node_param_patches or [],
        "runtime_patch_snapshot": runtime_patch_snapshot or {},
        "effective_search_space": effective_search_space or {},
        "effective_evaluation_contract": effective_evaluation_contract or {},
        "summary": summary or {},
        "windows_total": summary.get("windows_total"),
        "windows_comparable": summary.get("windows_comparable"),
        "windows_challenger_better": summary.get("windows_challenger_better"),
        "score_advantage": evaluation.get("score_advantage") or summary.get("score_advantage"),
        "mape_improvement": evaluation.get("mape_improvement"),
        "challenger_mape": evaluation.get("challenger_mape"),
        "baseline_mape": evaluation.get("baseline_mape"),
        "duration_s": evaluation.get("training_duration_s") or (compare_state or {}).get("total_duration"),
        "error": (compare_state or {}).get("error") or summary.get("failure_reason"),
        "failure_reason": (compare_state or {}).get("error") or summary.get("failure_reason"),
        "is_best": bool(is_best),
        "is_primary": bool(is_primary),
        "v3_plan_item": group_spec.get("v3_plan_item") if isinstance(group_spec.get("v3_plan_item"), dict) else None,
        "patch_fingerprint": group_spec.get("patch_fingerprint"),
        "action_id": group_spec.get("action_id"),
        "variant_index": group_spec.get("variant_index"),
    }
    record["applied_patch_fingerprint"] = _build_applied_patch_fingerprint(
        override=record["override"],
        structure_patch=record["structure_patch"],
        global_config_patch=record["global_config_patch"],
        node_param_patches=record["node_param_patches"],
    )
    return _sanitize_json_floats(record)


def _generate_proposal_variants(report: Dict[str, Any], count: int = 3) -> List[Dict[str, Any]]:
    base = _generate_proposal_from_report(report)
    run_id = str(report.get("run_id") or "")
    run_state = _auto_research_store.get(run_id) or {}
    baseline_wf_id = str(run_state.get("baseline_workflow_id") or "")
    structure_candidate = _build_structure_patch_candidate_from_workflow(baseline_wf_id) if baseline_wf_id else {}
    summary = report.get("summary") or {}
    error_diagnosis = report.get("error_diagnosis") or {}
    diag_source = str(error_diagnosis.get("primary_error_source") or "parameter_saturation")
    try:
        bm_trace = float(summary.get("best_mape_improvement")) if summary.get("best_mape_improvement") is not None else None
    except (TypeError, ValueError):
        bm_trace = None
    has_param_layer = bool((base.get("global_config_patch") or {}) or (base.get("node_param_patches") or []))

    # 根据诊断结论生成假设文本
    _hypothesis_map = {
        "weekend_pattern_shift": "周末/节假日误差偏高，加强日历特征可能改善整体 MAPE",
        "data_coverage_insufficient": "数据覆盖不足，缩短训练窗口可提升可执行率",
        "outlier_days": "存在高误差异常天，引入差分/统计特征可降低尖峰误差",
        "model_divergence": "各模型表现差异大，集成模式可能优于单模型",
        "parameter_saturation": "参数层已接近饱和，扩展搜索范围或引入结构变更",
    }
    _base_hypothesis = _hypothesis_map.get(diag_source, "继续探索参数空间寻找更优配置")

    variants: List[Dict[str, Any]] = []
    count = max(1, min(int(count or 1), 5))
    for i in range(count):
        c = {
            "search_space_patch": dict(base.get("search_space_patch") or {}),
            "evaluation_contract_patch": dict(base.get("evaluation_contract_patch") or {}),
            "structure_patch": dict(base.get("structure_patch") or {}),
            "global_config_patch": dict(base.get("global_config_patch") or {}),
            "node_param_patches": list(base.get("node_param_patches") or []),
            "notes": list(base.get("notes") or []),
            "risk_level": base.get("risk_level") or "low",
            "base_search_space": dict(base.get("base_search_space") or {}),
            "base_evaluation_contract": dict(base.get("base_evaluation_contract") or {}),
            "source": "rules",
        }
        if i == 1:
            c["risk_level"] = "medium" if c["risk_level"] == "low" else c["risk_level"]
            ssp = c["search_space_patch"]
            if isinstance(ssp.get("train_days"), list) and len(ssp["train_days"]) > 0:
                ssp["train_days"] = sorted(list(set([max(7, int(x) - 7) for x in ssp["train_days"] if isinstance(x, (int, float))])))
                if ssp["train_days"]:
                    ssp["backtest_train_days"] = list(ssp["train_days"])
            c["notes"].append("候选B：偏保守收缩训练窗口")
            c["hypothesis"] = f"训练窗口偏长导致过拟合，缩短后 MAPE 应有改善（诊断：{diag_source}）"
            c["hypothesis_type"] = "parameter"
            c["expected_outcome"] = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.1, "description": "MAPE 改善 > 0.1%"}
            c["fallback_if_failed"] = "训练窗口不是瓶颈，转向特征工程或模型结构"
        elif i == 2:
            ssp = c["search_space_patch"]
            ntr = ssp.get("auto_tune_n_trials")
            if isinstance(ntr, list) and len(ntr) > 0:
                ssp["auto_tune_n_trials"] = sorted(list(set([min(20, int(x) + 2) for x in ntr if isinstance(x, (int, float))])))
            c["notes"].append("候选C：提高调参探索强度")
            c["risk_level"] = "medium" if c["risk_level"] == "low" else c["risk_level"]
            defer_structure = bool(
                structure_candidate
                and has_param_layer
                and bm_trace is not None
                and bm_trace > 0.02
            )
            if defer_structure:
                c["notes"].append("候选C：已有参数层建议且改善>0.02，暂缓结构翻转")
                c["hypothesis"] = "增加贝叶斯调参轮数可在当前参数空间找到更优解"
                c["hypothesis_type"] = "parameter"
            elif structure_candidate:
                c["structure_patch"] = dict(structure_candidate)
                c["notes"].append("候选C附带小幅结构开关（白名单节点 enabled 切换）")
                # 白名单节点开关是安全操作，风险降为 low
                _sc_switches = structure_candidate.get("node_switches") or []
                if _sc_switches and all(isinstance(s, dict) and s.get("functionId") for s in _sc_switches):
                    c["risk_level"] = "low"
                else:
                    c["risk_level"] = "medium"
                c["hypothesis"] = f"结构调整（开关特征节点）可突破当前参数层瓶颈（诊断：{diag_source}）"
                c["hypothesis_type"] = "feature"
            else:
                c["hypothesis"] = "提高调参强度可在当前搜索空间找到更优参数组合"
                c["hypothesis_type"] = "parameter"
            c["expected_outcome"] = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.2, "description": "MAPE 改善 > 0.2%"}
            c["fallback_if_failed"] = "调参空间已饱和，需要引入特征工程或模型结构变更"
        else:
            c["notes"].append("候选A：基线建议")
            c["hypothesis"] = _base_hypothesis
            c["hypothesis_type"] = "parameter"
            c["expected_outcome"] = {"metric": "mape_improvement", "direction": "increase", "threshold": 0.05, "description": "MAPE 有正向改善"}
            c["fallback_if_failed"] = "当前方向无效，尝试其他搜索维度"
        # 任务 27.1：推断并标记主变量
        c["primary_variable"] = _infer_primary_variable(c)
        variants.append(c)
    return variants


def _load_production_registry() -> Dict[str, Any]:
    data = _load_json_with_fallback(
        _PRODUCTION_REGISTRY_JSON,
        _LEGACY_PRODUCTION_REGISTRY_JSON,
        {"slots": {}},
    )
    if isinstance(data, dict) and isinstance(data.get("slots"), dict):
        return data
    return {"slots": {}}


def _save_production_registry(data: Dict[str, Any]) -> None:
    _atomic_write_json(_PRODUCTION_REGISTRY_JSON, data)


def _set_production_workflow_slot(
    slot: str,
    workflow_id: str,
    note: Optional[str] = None,
    source_candidate_id: Optional[str] = None,
) -> Dict[str, Any]:
    reg = _load_production_registry()
    slots = reg.setdefault("slots", {})
    entry = {
        "workflow_id": str(workflow_id),
        "updated_at": datetime.now().isoformat(),
        "note": note,
        "source_candidate_id": source_candidate_id,
    }
    slots[str(slot or "default")] = entry
    _save_production_registry(reg)
    return entry


def _load_candidate_pool_list() -> List[Dict[str, Any]]:
    # @AI_GENERATED: Phase 2 读切换 — DB 优先读候选池
    db_result = _load_candidate_pool_from_db()
    if db_result is not None:
        return db_result
    # @AI_GENERATED: end
    data = _load_json_with_fallback(_CANDIDATE_POOL_JSON, _LEGACY_CANDIDATE_POOL_JSON, {})
    cand = data.get("candidates") if isinstance(data, dict) else None
    return list(cand) if isinstance(cand, list) else []


def _prepare_v3_autoresearch_plans(
    *,
    registry: Dict[str, Any],
    state: Dict[str, Any],
    baseline_workflow_id: str,
    batch_size: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """从 v3 action registry 生成主循环可直接消费的 plan + runtime patch。"""
    raw_actions = registry.get("actions") if isinstance(registry, dict) else None
    if not isinstance(raw_actions, list) or not raw_actions:
        return [], []

    actions: List[ResearchAction] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        try:
            actions.append(ResearchAction.from_dict(item))
        except Exception as exc:
            logger.warning("skip invalid v3 action: %s", exc)
    if not actions:
        return [], []

    dataset_profile = state.get("dataset_profile") if isinstance(state.get("dataset_profile"), dict) else {}
    train_profile = dataset_profile.get("train_profile") if isinstance(dataset_profile.get("train_profile"), dict) else {}
    if not train_profile and isinstance(state.get("train_profile"), dict):
        train_profile = state.get("train_profile") or {}
    profile_signal = ProfileSignal.from_train_profile(train_profile)

    evidence_records = state.get("evidence_records") if isinstance(state.get("evidence_records"), list) else []
    existing_questions = state.get("research_questions") if isinstance(state.get("research_questions"), list) else []
    generated_questions = _auto_research_v6_analyst.generate_questions(
        profile_signal=profile_signal,
        evidence_records=evidence_records,
        existing_questions=existing_questions,
        max_questions=max(5, int(batch_size or 1)),
    )
    questions = list(existing_questions or []) + list(generated_questions or [])

    plans = _auto_research_v6_planner.plan(
        questions=questions,
        available_actions=actions,
        profile_signal=profile_signal,
        evidence_records=evidence_records,
        candidate_pool=_load_candidate_pool_list(),
        run_iterations=state.get("iterations") if isinstance(state.get("iterations"), list) else [],
        run_state=state,
        max_actions=max(1, int(batch_size or 1)),
    )
    if not plans:
        return [], []

    workflow = load_workflow_from_file(str(baseline_workflow_id).strip())
    runtime_patches: List[Dict[str, Any]] = []
    for plan in plans:
        action_payload = plan.get("action") if isinstance(plan.get("action"), dict) else {}
        action = ResearchAction.from_dict(action_payload)
        runtime_patch = _auto_research_v6_patch_compiler.compile_runtime_patch(
            action,
            variant_index=int(plan.get("variant_index") or 0),
            workflow=workflow,
        )
        runtime_patches.append(runtime_patch)
    state["v3_planner_profile_signal"] = _sanitize_json_floats(profile_signal.to_dict())
    state["v3_planner_questions"] = _sanitize_json_floats(questions[-10:])
    state["v3_planner_plans"] = _sanitize_json_floats(plans)
    return plans, runtime_patches


def _build_v3_group_spec(
    *,
    plan: Dict[str, Any],
    runtime_patch: Dict[str, Any],
    baseline_workflow_id: str,
    challenger_contract_delta: Dict[str, Any],
    slot: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """把 v3 plan 编译结果转换为 batch group spec 和 challenger override。"""
    action_payload = plan.get("action") if isinstance(plan.get("action"), dict) else {}
    global_patch = dict(runtime_patch.get("global_config_patch") or {})
    structure_patch = dict(runtime_patch.get("structure_patch") or {})
    model_focus = runtime_patch.get("model_focus") if isinstance(runtime_patch.get("model_focus"), list) else []
    if model_focus:
        structure_patch = _merge_structure_patch_bundle(
            structure_patch,
            _build_model_focus_structure_patch(baseline_workflow_id, model_focus),
        )
    node_patches = list(runtime_patch.get("node_param_patches") or [])
    override = dict(challenger_contract_delta or {})
    override.update(global_patch)
    group_spec = {
        "candidate_source": "v3_action",
        "proposal_id": None,
        "action_id": plan.get("action_id"),
        "v3_plan_item": plan,
        "patch_fingerprint": plan.get("patch_fingerprint"),
        "hypothesis": action_payload.get("description"),
        "hypothesis_type": action_payload.get("target_direction"),
        "primary_variable": _infer_primary_variable({
            "search_space_patch": global_patch,
            "evaluation_contract_patch": {},
            "structure_patch": structure_patch,
            "global_config_patch": global_patch,
            "node_param_patches": node_patches,
        }),
        "selected_layer": action_payload.get("target_layer"),
        "target_direction": action_payload.get("target_direction"),
        "target_layer": action_payload.get("target_layer"),
        "exploration_role": (slot or {}).get("exploration_role") or "v3_action",
        "planner_reason": plan.get("reason"),
        "structure_patch": structure_patch,
        "global_config_patch": global_patch,
        "node_param_patches": node_patches,
        "variant_index": plan.get("variant_index"),
    }
    return group_spec, override


def _commit_v3_successful_batch_plans(state: Dict[str, Any], batch_group_records: List[Dict[str, Any]]) -> None:
    executed_plans: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for record in batch_group_records or []:
        if str(record.get("status") or "") != "success":
            continue
        plan = record.get("v3_plan_item") if isinstance(record.get("v3_plan_item"), dict) else None
        if not plan:
            continue
        key = str(plan.get("patch_fingerprint") or plan.get("action_id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        executed_plans.append(plan)
    if executed_plans:
        _auto_research_v6_planner.commit_plan_result(state, executed_plans)


def _save_candidate_pool_list(candidates: List[Dict[str, Any]]) -> None:
    with _AUTO_RESEARCH_FILE_LOCK:
        _atomic_write_json(_CANDIDATE_POOL_JSON, {"candidates": candidates})
    # @AI_GENERATED: Phase 1 双写 — 候选池全量同步到 MySQL candidate_pool
    _dual_write_candidate_pool_to_db(candidates)
    # @AI_GENERATED: end


def _load_verification_queue() -> List[Dict[str, Any]]:
    # @AI_GENERATED: Phase 2 读切换 — DB 优先读复验队列
    db_result = _load_verification_queue_from_db()
    if db_result is not None:
        return db_result
    # @AI_GENERATED: end
    data = _load_json_with_fallback(_VERIFICATION_QUEUE_JSON, None, {})
    rows = data.get("items") if isinstance(data, dict) else None
    return list(rows) if isinstance(rows, list) else []


def _save_verification_queue(items: List[Dict[str, Any]]) -> None:
    with _AUTO_RESEARCH_FILE_LOCK:
        _atomic_write_json(_VERIFICATION_QUEUE_JSON, {"items": items})
    # @AI_GENERATED: Phase 1 双写 — 复验队列全量同步到 MySQL candidate_verification
    _dual_write_verification_queue_to_db(items)
    # @AI_GENERATED: end


# @AI_GENERATED: Phase 1 双写辅助 — 候选池 / 复验队列 → MySQL
def _dual_write_candidate_pool_to_db(candidates: List[Dict[str, Any]]) -> None:
    """把候选池逐条 upsert 到 MySQL candidate_pool 表。失败降级 warning。

    字段映射与 scripts/migrate_autoresearch_storage_to_db.py::migrate_candidates 保持一致：
      - id / slot / run_id(comparison_id) / workflow_id / patch_signature / best_mape / evidence / status
    """
    try:
        from services.db.repositories import get_autoresearch_repo, is_dual_write_enabled
        if not is_dual_write_enabled():
            return
        repo = get_autoresearch_repo()
        if repo is None:
            return
        for c in candidates or []:
            if not isinstance(c, dict):
                continue
            cid = c.get("id") or c.get("candidate_id")
            if not cid:
                continue
            summary = c.get("summary") or {}
            best_mape = None
            for key in ("aggregate_baseline_score", "challenger_score", "mape_improvement"):
                v = summary.get(key) if isinstance(summary, dict) else None
                v = v if v is not None else c.get(key)
                if isinstance(v, (int, float)):
                    best_mape = float(v)
                    break
            try:
                repo.upsert_candidate({
                    "id": str(cid)[:64],
                    "slot": str(c.get("slot") or "default")[:64],
                    "run_id": str(c.get("run_id") or c.get("comparison_id") or "")[:64],
                    "workflow_id": str(c.get("baseline_workflow_id") or c.get("challenger_workflow_id") or "")[:128],
                    "patch_signature": str(c.get("applied_patch_fingerprint") or c.get("patch_signature") or "")[:256],
                    "best_mape": best_mape,
                    "evidence": c.get("evidence_records") or c.get("evidence") or {},
                    "status": str(c.get("status") or "candidate")[:32],
                })
            except Exception as _e:
                logger.warning("candidate_pool dual-write (id=%s) failed: %s", cid, _e)
    except Exception as exc:
        logger.warning("candidate_pool dual-write batch failed (non-fatal): %s", exc)


def _dual_write_verification_queue_to_db(items: List[Dict[str, Any]]) -> None:
    """把复验队列逐条 upsert 到 MySQL candidate_verification 表。失败降级 warning。"""
    try:
        from services.db.repositories import get_autoresearch_repo, is_dual_write_enabled
        if not is_dual_write_enabled():
            return
        repo = get_autoresearch_repo()
        if repo is None:
            return
        for item in items or []:
            if not isinstance(item, dict):
                continue
            iid = item.get("id")
            if not iid:
                continue

            def _dt(v):
                if not v:
                    return None
                try:
                    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                except Exception:
                    return None

            try:
                repo.upsert_verification({
                    "id": str(iid)[:64],
                    "candidate_id": str(item.get("candidate_id") or "")[:64],
                    "slot": str(item.get("slot") or "default")[:64],
                    "source_run_id": (str(item.get("source_run_id"))[:64] if item.get("source_run_id") else None),
                    "source_iteration": item.get("source_iteration"),
                    "status": str(item.get("status") or "queued")[:32],
                    "config_json": item.get("config") or item.get("verification_config") or {},
                    "evidence_json": item.get("evidence") or {},
                    "started_at": _dt(item.get("started_at")),
                    "finished_at": _dt(item.get("finished_at")),
                })
            except Exception as _e:
                logger.warning("candidate_verification dual-write (id=%s) failed: %s", iid, _e)
    except Exception as exc:
        logger.warning("candidate_verification dual-write batch failed (non-fatal): %s", exc)
# @AI_GENERATED: end


# @AI_GENERATED: Phase 2 读切换辅助 — 候选池 / 复验队列从 MySQL 读
def _load_candidate_pool_from_db() -> Optional[List[Dict[str, Any]]]:
    """DB 优先读候选池。返回 None 表示未启用/异常/DB 空，调用方走 JSON 兜底。"""
    try:
        from services.db.repositories import get_autoresearch_repo, is_db_read_enabled
        if not is_db_read_enabled():
            return None
        repo = get_autoresearch_repo()
        if repo is None:
            return None
        rows = repo.list_candidates("default", limit=2000)
        if not rows:
            return None  # DB 空时退回 JSON（可能是老数据还没迁移）
        result: List[Dict[str, Any]] = []
        for r in rows:
            item = {
                "id": r.id,
                "slot": r.slot,
                "run_id": r.run_id,
                "baseline_workflow_id": r.workflow_id,
                "applied_patch_fingerprint": r.patch_signature,
                "best_mape": r.best_mape,
                "status": r.status,
                "evidence": r.evidence if isinstance(r.evidence, dict) else {},
                "created_at": (r.created_at.isoformat() if r.created_at else None),
            }
            result.append(item)
        return result
    except Exception as exc:
        logger.warning("_load_candidate_pool_from_db failed (fallback to JSON): %s", exc)
        return None


def _load_verification_queue_from_db() -> Optional[List[Dict[str, Any]]]:
    """DB 优先读复验队列。返回 None 表示未启用/异常/DB 空，走 JSON 兜底。"""
    try:
        from services.db.repositories import get_autoresearch_repo, is_db_read_enabled
        if not is_db_read_enabled():
            return None
        repo = get_autoresearch_repo()
        if repo is None:
            return None
        rows = repo.list_verifications("default", limit=500)
        if not rows:
            return None
        result: List[Dict[str, Any]] = []
        for r in rows:
            item = {
                "id": r.id,
                "candidate_id": r.candidate_id,
                "slot": r.slot,
                "source_run_id": r.source_run_id,
                "source_iteration": r.source_iteration,
                "status": r.status,
                "config": r.config_json if isinstance(r.config_json, dict) else {},
                "evidence": r.evidence_json if isinstance(r.evidence_json, dict) else {},
                "created_at": (r.created_at.isoformat() if r.created_at else None),
                "started_at": (r.started_at.isoformat() if r.started_at else None),
                "finished_at": (r.finished_at.isoformat() if r.finished_at else None),
            }
            result.append(item)
        return result
    except Exception as exc:
        logger.warning("_load_verification_queue_from_db failed (fallback to JSON): %s", exc)
        return None
# @AI_GENERATED: end


def _verification_default_windows(candidate: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {"start_date": "2026-03-01", "end_date": "2026-03-08"},
        {"start_date": "2026-03-08", "end_date": "2026-03-15"},
        {"start_date": "2026-03-15", "end_date": "2026-03-22"},
    ]


def _verification_item_for_candidate(
    candidate: Dict[str, Any],
    *,
    windows: Optional[List[Dict[str, Any]]] = None,
    note: Optional[str] = None,
    aggregate_method: Optional[str] = None,
    score_margin: Optional[float] = None,
    min_windows_challenger_better: Optional[int] = None,
    auto_start: bool = False,
) -> Dict[str, Any]:
    candidate_id = str(candidate.get("id") or "").strip()
    if not candidate_id:
        raise ValueError("candidate 缺少 id")
    summary = candidate.get("summary") if isinstance(candidate.get("summary"), dict) else {}
    # 入池时记录候选的原始精度快照（来自候选池 summary / evaluation）
    evaluation = candidate.get("evaluation") if isinstance(candidate.get("evaluation"), dict) else {}
    source_metrics = {
        "baseline_mape": summary.get("aggregate_baseline_score") or evaluation.get("baseline_metric"),
        "challenger_mape": summary.get("aggregate_challenger_score") or evaluation.get("challenger_metric"),
        "mape_improvement": summary.get("score_advantage") or summary.get("mape_improvement") or evaluation.get("mape_improvement"),
        "windows_total": summary.get("windows_total") or summary.get("windows_comparable"),
        "windows_challenger_better": summary.get("windows_challenger_better"),
        "source_iteration": candidate.get("source_iteration"),
        "source_run_id": candidate.get("source_run_id"),
    }
    return {
        "id": f"ver-{uuid.uuid4().hex[:12]}",
        "candidate_id": candidate_id,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "status": "queued",
        "note": note or None,
        "baseline_workflow_id": candidate.get("baseline_workflow_id"),
        "challenger_workflow_id": candidate.get("challenger_workflow_id"),
        "evaluation_contract": candidate.get("evaluation_contract") or {},
        "challenger_config_override": candidate.get("challenger_override") or {},
        "challenger_structure_override": candidate.get("effective_structure_patch") or {},
        "challenger_global_config_patch": candidate.get("effective_parameter_patch") or {},
        "challenger_node_param_patches": candidate.get("node_param_patches") or [],
        "windows": windows if isinstance(windows, list) and windows else _verification_default_windows(candidate),
        "aggregate_method": str(aggregate_method or summary.get("aggregate_method") or "mean"),
        "score_margin": float(score_margin if score_margin is not None else 0.0),
        "min_windows_challenger_better": int(min_windows_challenger_better if min_windows_challenger_better is not None else 2),
        "auto_start_requested": bool(auto_start),
        "source_run_id": candidate.get("source_run_id"),
        "source_iteration": candidate.get("source_iteration"),
        "candidate_signature": _candidate_signature_from_entry(candidate),
        "source_metrics": _sanitize_json_floats(source_metrics),
        "comparison_id": None,
        "result": None,
        "failure_reason": None,
    }


def _verification_active_item(items: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    rows = items if isinstance(items, list) else _load_verification_queue()
    for row in rows:
        if isinstance(row, dict) and str(row.get("status") or "") == "running":
            return row
    return None


def _candidate_has_passed_verification(candidate_id: str) -> bool:
    cid = str(candidate_id or "").strip()
    if not cid:
        return False
    for row in _load_verification_queue():
        if str(row.get("candidate_id") or "") == cid and str(row.get("status") or "") == "passed":
            return True
    return False


def _pool_evidence_from_entry(entry: Dict[str, Any], *, run_id: str = "") -> Dict[str, Any]:
    """Derive pool-entry evidence from stored fields or summary/window_results."""
    existing = entry.get("evidence")
    if isinstance(existing, dict) and str(existing.get("evidence_strength") or ""):
        return existing
    summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
    evaluation = entry.get("evaluation") if isinstance(entry.get("evaluation"), dict) else {}
    if evaluation.get("mape_improvement") is None and summary.get("score_advantage") is not None:
        evaluation = dict(evaluation)
        evaluation["mape_improvement"] = summary.get("score_advantage")
    comparable = int(summary.get("windows_comparable") or summary.get("windows_total") or 0)
    pseudo = {
        "iteration": entry.get("source_iteration"),
        "status": "success" if comparable > 0 else "failed",
        "evaluation": evaluation,
        "summary": summary,
        "override": entry.get("challenger_override") or entry.get("effective_parameter_patch") or {},
        "structure_patch": entry.get("effective_structure_patch") or {},
        "global_config_patch": entry.get("effective_parameter_patch") or {},
        "node_param_patches": entry.get("node_param_patches") or [],
    }
    cmp_state = {
        "status": pseudo["status"],
        "summary": summary,
        "window_results": entry.get("window_results") or [],
    }
    rid = str(run_id or entry.get("source_run_id") or "")
    return _auto_research_evidence_builder.build_for_candidate(
        run_id=rid,
        candidate=pseudo,
        comparison_state=cmp_state,
    ).to_dict()


def _sync_candidate_pool_evidence(candidate_id: str, evidence: Dict[str, Any]) -> None:
    cid = str(candidate_id or "").strip()
    if not cid or not isinstance(evidence, dict):
        return
    with _AUTO_RESEARCH_FILE_LOCK:
        pool = _load_candidate_pool_list()
        updated = False
        for idx, row in enumerate(pool):
            if not isinstance(row, dict) or str(row.get("id") or "") != cid:
                continue
            row["evidence"] = evidence
            pool[idx] = row
            updated = True
            break
        if updated:
            _save_candidate_pool_list(pool)


def _resolve_autoresearch_run_state(run_id: str) -> Optional[Dict[str, Any]]:
    rid = str(run_id or "").strip()
    if not rid:
        return None
    state = _auto_research_store.get(rid)
    if isinstance(state, dict):
        return state
    loaded = _auto_research_persister.load_snapshot(rid)
    if isinstance(loaded, dict):
        _auto_research_store[rid] = loaded
        return loaded
    return None


def _append_verification_evidence_to_run(
    source_run_id: str,
    evidence: Dict[str, Any],
    *,
    candidate_id: Optional[str] = None,
) -> None:
    state = _resolve_autoresearch_run_state(source_run_id)
    if not isinstance(state, dict):
        logger.warning("verification backfill: run %s not found for persistence", source_run_id)
        return
    fp = str(evidence.get("patch_fingerprint") or "")
    existing = [
        str(r.get("patch_fingerprint") or "")
        for r in (state.get("evidence_records") or [])
        if isinstance(r, dict)
    ]
    if fp and fp in existing:
        return
    state.setdefault("evidence_records", []).append(evidence)
    state["evidence_summary"] = _auto_research_evidence_builder.summarize(state.get("evidence_records") or [])
    try:
        from services.knowledge_layer import KnowledgeLayer
        KnowledgeLayer().ingest_run_insight(state)
    except Exception:
        pass
    _snapshot_autoresearch_state(source_run_id)
    if candidate_id:
        _sync_candidate_pool_evidence(str(candidate_id), evidence)


def _bootstrap_train_profile_at_run_start(
    baseline_workflow_id: str,
    windows: List[dict],
    evaluation_contract: Dict[str, Any],
) -> Optional[Any]:
    """Load full training-series CSV and compute TrainProfile before iteration 1."""
    try:
        import pandas as pd
        from services.dataset_profiler import DatasetProfiler
        from services.reference_rolling_backtest.data_io import load_wide_or_long_load_series, resolve_dataset_path

        workflow = load_workflow_from_file(baseline_workflow_id)
        if workflow is None:
            return None
        csv_cfg = _load_csv_config_from_workflow(workflow)
        file_path = csv_cfg.get("file_path")
        if not file_path:
            return None
        abs_path = resolve_dataset_path(str(file_path), _BACKEND_DIR)
        if not os.path.exists(abs_path):
            return None
        load_df = load_wide_or_long_load_series(
            abs_path,
            parent_id=csv_cfg.get("parent_id"),
            child_id=csv_cfg.get("child_id"),
        )
        if load_df is None or load_df.empty:
            return None
        time_col = "record_time" if "record_time" in load_df.columns else load_df.columns[0]
        load_col = "load" if "load" in load_df.columns else load_df.columns[1]
        train_days = int((evaluation_contract or {}).get("train_days") or 30)
        starts = [pd.to_datetime(w.get("start_date")) for w in (windows or []) if w.get("start_date")]
        ends = [pd.to_datetime(w.get("end_date")) for w in (windows or []) if w.get("end_date")]
        if starts and ends:
            range_start = min(starts) - pd.Timedelta(days=train_days)
            range_end = max(ends)
            mask = (load_df[time_col] >= range_start) & (load_df[time_col] <= range_end + pd.Timedelta(days=1))
            sliced = load_df.loc[mask].copy()
            if not sliced.empty:
                load_df = sliced
        profile_df = load_df.rename(columns={time_col: "timestamp", load_col: "load"})
        profile = DatasetProfiler().compute_train_profile(profile_df)
        pq = dict(getattr(profile, "profile_quality", None) or {})
        pq["source"] = "full_training_dataset"
        profile.profile_quality = pq
        return profile
    except Exception as exc:
        logger.warning("bootstrap train profile failed: %s", exc)
        return None


def _auto_enqueue_candidates_for_verification(
    run_id: str,
    max_batch: int = 2,
    logger_fn: Optional[Callable[[str, str], None]] = None,
) -> int:
    """扫描候选池，将 novel + single_window_positive 的候选自动加入复验池。
    限流: 每次最多 max_batch 条。
    返回本批入池数。"""
    enqueued = 0
    queue = _load_verification_queue()
    queued_signatures = {
        str(row.get("candidate_signature") or "")
        for row in queue
        if isinstance(row, dict)
    }
    pool_dirty = False
    with _AUTO_RESEARCH_FILE_LOCK:
        pool = _load_candidate_pool_list()
        for candidate in pool:
            if enqueued >= max_batch:
                break
            candidate_id = str(candidate.get("id") or "").strip()
            if not candidate_id:
                continue
            # 已在复验池中（同 signature）
            signature = _candidate_signature_from_entry(candidate)
            if signature in queued_signatures:
                continue
            # 必须是 novel
            novelty_audit = candidate.get("novelty_audit") if isinstance(candidate.get("novelty_audit"), dict) else {}
            if not bool(novelty_audit.get("is_novel")):
                continue
            evidence = _pool_evidence_from_entry(candidate, run_id=run_id)
            if not isinstance(candidate.get("evidence"), dict) or not candidate["evidence"].get("evidence_strength"):
                candidate["evidence"] = evidence
                pool_dirty = True
            if str(evidence.get("evidence_strength") or "") != "single_window_positive":
                continue
            # 入池
            item = _verification_item_for_candidate(candidate)
            queue.append(item)
            candidate["verification_status"] = "queued"
            candidate["verification_item_id"] = item["id"]
            queued_signatures.add(signature)
            enqueued += 1
            if logger_fn:
                logger_fn(
                    f"auto-enqueue: candidate={candidate_id} signature={signature[:12]}... "
                    f"已加入复验池 (item={item['id']})",
                    "info",
                )
        if enqueued > 0:
            _save_verification_queue(queue)
        if enqueued > 0 or pool_dirty:
            _save_candidate_pool_list(pool)
    return enqueued


def _has_active_autoresearch_run() -> bool:
    active_statuses = {"pending", "running", "waiting_review", "cancelling"}
    for state in _auto_research_store.values():
        if isinstance(state, dict) and str(state.get("status") or "").lower() in active_statuses:
            return True
    for job in _jq.list_jobs(limit=100):
        if isinstance(job, dict) and str(job.get("status") or "").lower() in active_statuses:
            return True
    for row in _auto_research_persister.list_runs(limit=50, memory_store=_auto_research_store):
        if isinstance(row, dict) and str(row.get("status") or "").lower() in active_statuses:
            return True
    return False


def _baseline_cache_key(
    baseline_workflow_id: str,
    windows: List[dict],
    baseline_contract: Dict[str, Any],
    baseline_config_override: Optional[Dict[str, Any]] = None,
) -> str:
    wf = load_workflow_from_file(str(baseline_workflow_id or "").strip())
    wf_payload = wf.dict() if hasattr(wf, "dict") else {}
    payload = {
        "baseline_workflow_id": baseline_workflow_id,
        "baseline_workflow": wf_payload,
        "windows": windows or [],
        "baseline_contract": baseline_contract or {},
        "baseline_config_override": baseline_config_override or {},
    }
    raw = json.dumps(_sanitize_json_floats(payload), sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _baseline_cache_is_valid(
    state: Dict[str, Any],
    expected_key: str,
    *,
    ttl_seconds: int = 86400,
) -> Tuple[bool, str, float]:
    if not state.get("_baseline_cache"):
        return False, "missing_cache", 0.0
    age = time.time() - float(state.get("_baseline_cache_ts") or 0)
    if age >= ttl_seconds:
        return False, "ttl_expired", age
    existing_key = str(state.get("_baseline_cache_key") or "")
    if existing_key != expected_key:
        return False, "content_hash_mismatch", age
    return True, "valid", age


def _verify_hypothesis(iteration_result: Dict[str, Any], last_proposal: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return _auto_research_hypothesis_tracker.verify(iteration_result, last_proposal)


def _update_hypothesis_state(
    run_state: Dict[str, Any],
    iteration: int,
    verification: Optional[Dict[str, Any]],
) -> None:
    _auto_research_hypothesis_tracker.update_state(run_state, iteration, verification)


def _build_patch_fingerprint(proposal: Dict[str, Any]) -> str:
    return _auto_research_hypothesis_tracker.patch_fingerprint(proposal)


def _is_parameter_saturated(iterations: List[dict], k: int = 4, threshold: float = 0.05) -> bool:
    return _auto_research_convergence_monitor.is_parameter_saturated(
        iterations,
        k=k,
        threshold=threshold,
    )


def _compute_diff_from_baseline(
    baseline_wf: dict,
    challenger_override: Optional[dict],
    structure_patch: Optional[dict],
    parameter_patch: Optional[dict],
) -> dict:
    """
    计算 Challenger 相对 Baseline 的配置差异
    
    Args:
        baseline_wf: Baseline 工作流模板对象
        challenger_override: challenger_config_override（评测量约层覆盖）
        structure_patch: challenger_structure_override（结构层补丁）
        parameter_patch: challenger_global_config_patch（全局配置补丁）
    
    Returns:
        {
            "added_keys": [...],  # 新增的键
            "changed_keys": [{"key": str, "baseline": Any, "challenger": Any}],  # 变更的键
            "removed_keys": [...]  # 移除的键（通常为空，因为是补丁模式）
        }
    """
    added_keys = []
    changed_keys = []
    removed_keys = []

    # Pydantic 模型对象转 dict，避免 .get() AttributeError
    if hasattr(baseline_wf, 'dict'):
        baseline_wf = baseline_wf.dict()
    if not isinstance(baseline_wf, dict):
        baseline_wf = {}

    # 1. 处理 config_override（评测量约层）
    if isinstance(challenger_override, dict):
        for key, challenger_val in challenger_override.items():
            baseline_val = baseline_wf.get(key)
            if baseline_val is None:
                added_keys.append(f"config.{key}")
            elif baseline_val != challenger_val:
                changed_keys.append({
                    "key": f"config.{key}",
                    "baseline": baseline_val,
                    "challenger": challenger_val,
                })
    
    # 2. 处理 structure_patch（结构层）
    if isinstance(structure_patch, dict):
        for key, challenger_val in structure_patch.items():
            baseline_val = baseline_wf.get(key)
            if baseline_val is None:
                added_keys.append(f"structure.{key}")
            elif baseline_val != challenger_val:
                changed_keys.append({
                    "key": f"structure.{key}",
                    "baseline": baseline_val,
                    "challenger": challenger_val,
                })
    
    # 3. 处理 parameter_patch（全局配置层）
    if isinstance(parameter_patch, dict):
        baseline_global = baseline_wf.get("global_config") or {}
        for key, challenger_val in parameter_patch.items():
            baseline_val = baseline_global.get(key)
            if baseline_val is None:
                added_keys.append(f"global_config.{key}")
            elif baseline_val != challenger_val:
                changed_keys.append({
                    "key": f"global_config.{key}",
                    "baseline": baseline_val,
                    "challenger": challenger_val,
                })
    
    return {
        "added_keys": added_keys,
        "changed_keys": changed_keys,
        "removed_keys": removed_keys,
    }


def _candidate_signature_from_parts(
    override: Optional[Dict[str, Any]],
    structure_patch: Optional[Dict[str, Any]],
    parameter_patch: Optional[Dict[str, Any]],
    node_param_patches: Optional[List[Dict[str, Any]]] = None,
) -> str:
    payload = {
        "override": override or {},
        "structure_patch": structure_patch or {},
        "parameter_patch": parameter_patch or {},
        "node_param_patches": node_param_patches or [],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _candidate_signature_from_entry(entry: Dict[str, Any]) -> str:
    return _candidate_signature_from_parts(
        entry.get("challenger_override") if isinstance(entry.get("challenger_override"), dict) else entry.get("override"),
        entry.get("effective_structure_patch") if isinstance(entry.get("effective_structure_patch"), dict) else entry.get("structure_patch"),
        entry.get("effective_parameter_patch") if isinstance(entry.get("effective_parameter_patch"), dict) else entry.get("global_config_patch"),
        entry.get("node_param_patches") if isinstance(entry.get("node_param_patches"), list) else None,
    )


def _sample_override_from_search_space_patch(
    search_space_patch: Optional[Dict[str, Any]],
    *,
    iteration: int,
    seed: int,
) -> Dict[str, Any]:
    """Convert proposal search-space arrays into one executable challenger override."""
    if not isinstance(search_space_patch, dict):
        return {}
    rng = random.Random(int(seed) + int(iteration or 0) * 104729)
    override: Dict[str, Any] = {}
    for key, value in search_space_patch.items():
        k = str(key or "").strip()
        if not k or k == "feature_recipe_id":
            continue
        if isinstance(value, list):
            vals = [v for v in value if not isinstance(v, (dict, list))]
            if vals:
                override[k] = vals[rng.randrange(0, len(vals))]
        elif not isinstance(value, dict):
            override[k] = value
    if "train_days" in override and "backtest_train_days" in override:
        override.pop("backtest_train_days", None)
    return override


def _score_from_candidate_entry(entry: Dict[str, Any]) -> Optional[float]:
    summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
    raw = summary.get("score_advantage")
    if raw is None:
        raw = entry.get("score_advantage")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _mape_from_candidate_entry(entry: Dict[str, Any]) -> Optional[float]:
    for window in entry.get("window_results") or []:
        if not isinstance(window, dict):
            continue
        challenger = window.get("challenger") if isinstance(window.get("challenger"), dict) else {}
        metrics = challenger.get("avg_metrics") if isinstance(challenger.get("avg_metrics"), dict) else {}
        raw = metrics.get("avg_mape") if metrics.get("avg_mape") is not None else metrics.get("avg_smape")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    evaluation = entry.get("evaluation") if isinstance(entry.get("evaluation"), dict) else {}
    raw = evaluation.get("challenger_mape") or entry.get("challenger_mape")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _candidate_changed_variables_from_entry(entry: Dict[str, Any]) -> List[str]:
    payload = {
        "override": entry.get("challenger_override") or entry.get("override") or {},
        "global_config_patch": entry.get("effective_parameter_patch") or entry.get("global_config_patch") or {},
        "node_param_patches": entry.get("node_param_patches") or [],
        "structure_patch": entry.get("effective_structure_patch") or entry.get("structure_patch") or {},
    }
    return _auto_research_evidence_builder.changed_variables(payload)


def _build_candidate_novelty_audit(entry: Dict[str, Any], pool: List[Dict[str, Any]]) -> Dict[str, Any]:
    signature = _candidate_signature_from_entry(entry)
    current_mape = _mape_from_candidate_entry(entry)
    changed_variables = _candidate_changed_variables_from_entry(entry)
    same_signature = []
    same_mape = []
    same_variables = []
    for prev in pool or []:
        if not isinstance(prev, dict):
            continue
        source_run = prev.get("source_run_id")
        source_iteration = prev.get("source_iteration")
        prev_id = prev.get("id")
        if _candidate_signature_from_entry(prev) == signature:
            same_signature.append({"id": prev_id, "source_run_id": source_run, "source_iteration": source_iteration})
        prev_mape = _mape_from_candidate_entry(prev)
        if current_mape is not None and prev_mape is not None and abs(prev_mape - current_mape) <= 0.001:
            same_mape.append({
                "id": prev_id,
                "source_run_id": source_run,
                "source_iteration": source_iteration,
                "challenger_mape": round(prev_mape, 6),
            })
        prev_vars = _candidate_changed_variables_from_entry(prev)
        if changed_variables and prev_vars and set(prev_vars) == set(changed_variables):
            same_variables.append({"id": prev_id, "source_run_id": source_run, "source_iteration": source_iteration})
    duplicate = bool(same_signature or same_mape)
    return {
        "signature": signature,
        "is_novel": not duplicate,
        "duplicate_reason": (
            "same_patch_signature" if same_signature else
            "same_challenger_mape" if same_mape else
            None
        ),
        "same_signature_count": len(same_signature),
        "same_mape_count": len(same_mape),
        "same_changed_variables_count": len(same_variables),
        "changed_variables": changed_variables,
        "historical_matches": {
            "same_signature": same_signature[:5],
            "same_mape": same_mape[:5],
            "same_changed_variables": same_variables[:5],
        },
    }


def _summarize_candidate_novelty(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    audits = [
        c.get("novelty_audit")
        for c in candidates or []
        if isinstance(c, dict) and isinstance(c.get("novelty_audit"), dict)
    ]
    duplicate_count = len([a for a in audits if not bool(a.get("is_novel"))])
    return {
        "total": len(audits),
        "new_count": len(audits) - duplicate_count,
        "duplicate_count": duplicate_count,
        "same_mape_duplicates": sum(1 for a in audits if int(a.get("same_mape_count") or 0) > 0),
        "same_signature_duplicates": sum(1 for a in audits if int(a.get("same_signature_count") or 0) > 0),
    }


def _append_candidate_pool_entry(entry: Dict[str, Any]) -> str:
    with _AUTO_RESEARCH_FILE_LOCK:
        pool = _load_candidate_pool_list()
        if not isinstance(entry.get("evidence"), dict) or not entry["evidence"].get("evidence_strength"):
            entry["evidence"] = _pool_evidence_from_entry(entry)
        entry["novelty_audit"] = _build_candidate_novelty_audit(entry, pool)
        signature = _candidate_signature_from_entry(entry)
        for idx, prev in enumerate(pool):
            if not isinstance(prev, dict):
                continue
            if _candidate_signature_from_entry(prev) != signature:
                continue
            new_id = str(entry.get("id") or "")
            existing_id = str(prev.get("id") or new_id)
            new_score = _score_from_candidate_entry(entry)
            old_score = _score_from_candidate_entry(prev)
            duplicate_observations = list(prev.get("duplicate_observations") or [])
            duplicate_observations.append({
                "candidate_id": entry.get("id"),
                "source_run_id": entry.get("source_run_id"),
                "source_iteration": entry.get("source_iteration"),
                "score_advantage": new_score,
                "created_at": entry.get("created_at"),
            })
            should_replace = (
                new_score is not None
                and (old_score is None or float(new_score) > float(old_score))
            )
            if should_replace:
                entry["id"] = existing_id
                entry["duplicate_observations"] = duplicate_observations[-20:]
                entry["deduped_candidate_ids"] = list(dict.fromkeys(
                    list(prev.get("deduped_candidate_ids") or []) + [new_id, existing_id]
                ))
                entry["novelty_audit"] = _build_candidate_novelty_audit(entry, pool[:idx] + pool[idx + 1:])
                pool[idx] = entry
            else:
                prev["duplicate_observations"] = duplicate_observations[-20:]
                prev["novelty_audit"] = prev.get("novelty_audit") or {}
                if isinstance(prev["novelty_audit"], dict):
                    prev["novelty_audit"]["duplicate_observation_count"] = len(prev["duplicate_observations"])
                    prev["novelty_audit"]["last_duplicate_candidate_id"] = entry.get("id")
            _save_candidate_pool_list(pool)
            return existing_id or str(entry.get("id") or "")
        pool.append(entry)
        _save_candidate_pool_list(pool)
        return str(entry.get("id") or "")


def _append_promotion_log(record: Dict[str, Any]) -> None:
    rows: List[Dict[str, Any]] = []
    prev = _load_json_with_fallback(_PROMOTIONS_LOG_JSON, _LEGACY_PROMOTIONS_LOG_JSON, [])
    if isinstance(prev, list):
        rows = prev
    elif isinstance(prev, dict) and isinstance(prev.get("log"), list):
        rows = prev["log"]
    rows.append(record)
    _atomic_write_json(_PROMOTIONS_LOG_JSON, rows)
    # @AI_GENERATED: Phase 1 双写 — promotion 审计同步到 MySQL candidate_promotion_log
    try:
        from services.db.repositories import get_autoresearch_repo, is_dual_write_enabled
        if is_dual_write_enabled():
            _promo_repo = get_autoresearch_repo()
            if _promo_repo is not None:
                cid = record.get("candidate_id")
                if cid:
                    _promo_repo.append_promotion(
                        slot=str(record.get("production_slot") or "default")[:64],
                        candidate_id=str(cid)[:64],
                        action="force_promoted" if record.get("force") else "promoted",
                        actor="user",
                        reason=str(record.get("note") or "")[:2048],
                        payload=record,
                    )
    except Exception as _promo_exc:
        logger.warning("candidate_promotion_log dual-write failed (non-fatal): %s", _promo_exc)
    # @AI_GENERATED: end


async def _run_compare_backtest_batch_task(
    comparison_id: str,
    baseline_workflow_id: str,
    challenger_workflow_ids: List[str],
    windows: List[dict],
    evaluation_contract: dict,
    score_margin: float,
    add_to_candidate_pool: bool,
    cancel_event: threading.Event,
    aggregate_method: str = "mean",
    min_windows_challenger_better: Optional[int] = None,
    challenger_config_override: Optional[dict] = None,
    baseline_config_override: Optional[dict] = None,
    challenger_structure_override: Optional[dict] = None,
    challenger_global_config_patch: Optional[dict] = None,
    challenger_node_param_patches: Optional[List[Dict[str, Any]]] = None,
    live_update_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    state = _comparison_store[comparison_id]
    state["status"] = "running"
    state["started_at"] = datetime.now().isoformat()

    def _log(message: str, log_type: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        logs = state.get("logs") or []
        logs.append({"timestamp": ts, "message": message, "type": log_type})
        state["logs"] = logs[-2000:]

    seen: set = set()
    deduped_challengers: List[str] = []
    for raw in challenger_workflow_ids:
        cid = str(raw or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        deduped_challengers.append(cid)

    pool_ids_collected: List[str] = []
    all_challenger_results: List[Dict[str, Any]] = []
    try:
        if not deduped_challengers:
            raise ValueError("challenger_workflow_id(s) 不能为空")

        baseline_wf = load_workflow_from_file(baseline_workflow_id)
        if baseline_wf is None:
            raise ValueError(f"baseline 算法模板不存在: {baseline_workflow_id}")

        contract = dict(evaluation_contract or {})
        for k in ("tuning_candidates", "start_date", "end_date"):
            contract.pop(k, None)

        agg_method = str(aggregate_method or "mean").strip().lower()
        if agg_method not in ("mean", "median", "trimmed_mean"):
            agg_method = "mean"
        min_win = min_windows_challenger_better

        total_w = len(windows)
        n_ch = len(deduped_challengers)

        for ci, challenger_workflow_id in enumerate(deduped_challengers):
            if cancel_event.is_set():
                _log("比对已取消", "error")
                break

            challenger_wf = load_workflow_from_file(challenger_workflow_id)
            if challenger_wf is None:
                all_challenger_results.append({
                    "challenger_workflow_id": challenger_workflow_id,
                    "error": f"challenger 算法模板不存在: {challenger_workflow_id}",
                    "summary": None,
                    "window_results": [],
                    "pool_candidate_id": None,
                })
                _log(f"✗ 跳过无效 challenger: {challenger_workflow_id}", "error")
                continue

            _log(f"▶ Challenger {ci + 1}/{n_ch}: {challenger_workflow_id}", "start")
            window_results: List[Dict[str, Any]] = []
            baseline_scores: List[Optional[float]] = []
            challenger_scores: List[Optional[float]] = []
            wins_challenger = 0
            comparable_windows = 0

            # Baseline 缓存：若调用方注入了 _cached_baseline_results，按窗口索引直接复用，跳过 Baseline 回测
            _cached_b_results = state.get("_cached_baseline_results") or {}
            if not isinstance(_cached_b_results, dict):
                _cached_b_results = {}

            # 窗口级 progress_fn 工厂：将滚动回测的每日进度透传到 live_update_hook
            def _make_window_progress_callback(live_hook, st, total_w_val, win_results_list, sd_val, ed_val, b_scores_list, agg_method_val):
                def progress_cb(day_idx, total_days, day_str):
                    if not live_hook:
                        return
                    try:
                        live_hook({
                            "progress": dict(st.get("progress") or {}),
                            "live_summary": _sanitize_json_floats({
                                "windows_done": len(win_results_list),
                                "windows_total": total_w_val,
                                "current_window": f"{sd_val} ~ {ed_val}",
                                "current_phase": "rolling_backtest",
                                "aggregate_baseline_score": _aggregate_scores(b_scores_list, agg_method_val),
                                "days_done": day_idx,
                                "days_total": total_days,
                                "current_day": day_str,
                            }),
                        })
                    except Exception:
                        pass
                return progress_cb

            for idx, w in enumerate(windows):
                if cancel_event.is_set():
                    break
                state["progress"] = {
                    "challenger_index": ci + 1,
                    "challenger_total": n_ch,
                    "window_index": idx + 1,
                    "window_total": total_w,
                }
                if live_update_hook:
                    try:
                        live_update_hook({
                            "progress": dict(state.get("progress") or {}),
                            "live_summary": state.get("live_summary"),
                            "live_window_results": state.get("live_window_results"),
                        })
                    except Exception:
                        pass
                sd = str(w.get("start_date") or w.get("start") or "").strip()
                ed = str(w.get("end_date") or w.get("end") or "").strip()
                if not sd or not ed:
                    window_results.append({
                        "start_date": sd,
                        "end_date": ed,
                        "error": "window 缺少 start_date/end_date",
                        "baseline": {},
                        "challenger": {},
                    })
                    continue

                _log(f"  窗口 {idx + 1}/{total_w}: {sd} ~ {ed} — 开始跑 Baseline", "start")
                if live_update_hook:
                    try:
                        live_update_hook({
                            "progress": dict(state.get("progress") or {}),
                            "live_summary": _sanitize_json_floats({
                                "windows_done": len(window_results),
                                "windows_total": total_w,
                                "current_window": f"{sd} ~ {ed}",
                                "current_phase": "baseline_running",
                                "aggregate_baseline_score": _aggregate_scores(baseline_scores, agg_method),
                                "aggregate_challenger_score": _aggregate_scores(challenger_scores, agg_method),
                                "score_advantage": None,
                                "windows_challenger_better": wins_challenger,
                                "windows_comparable": comparable_windows,
                            }),
                            "live_window_results": state.get("live_window_results"),
                        })
                    except Exception:
                        pass
                # baseline 额外叠加用户编辑的覆盖参数
                b_contract = dict(contract)
                if isinstance(baseline_config_override, dict) and baseline_config_override:
                    b_contract.update(baseline_config_override)
                b_global = _merge_evaluation_contract_into_global(baseline_wf, b_contract)
                # challenger 额外叠加用户在页面上编辑的覆盖参数
                c_contract = dict(contract)
                if isinstance(challenger_config_override, dict) and challenger_config_override:
                    c_contract.update(challenger_config_override)
                challenger_wf_effective = _apply_structure_patch_to_workflow(
                    challenger_wf,
                    challenger_structure_override if isinstance(challenger_structure_override, dict) else {},
                )
                challenger_wf_effective = _apply_runtime_parameter_layers_to_workflow(
                    challenger_wf_effective,
                    challenger_global_config_patch if isinstance(challenger_global_config_patch, dict) else None,
                    challenger_node_param_patches if isinstance(challenger_node_param_patches, list) else None,
                )
                c_global = _merge_evaluation_contract_into_global(challenger_wf_effective, c_contract)
                _log(f"  [debug] baseline train_days={b_contract.get('train_days')} challenger train_days={c_contract.get('train_days')} challenger_config_override={challenger_config_override}", "info")

                # 优先使用缓存的 Baseline 结果，避免重复回测
                _cache_key = f"{sd}~{ed}"
                if _cache_key in _cached_b_results:
                    b_res = _cached_b_results[_cache_key]
                    _log(f"  窗口 {idx + 1}/{total_w}: {sd} ~ {ed} — Baseline 命中缓存（跳过回测）", "info")
                else:
                    _baseline_progress_fn = _make_window_progress_callback(
                        live_update_hook, state, total_w, window_results, sd, ed, baseline_scores, agg_method
                    )
                    b_res = await _run_one_backtest_no_tuning(
                        baseline_wf, sd, ed, b_contract, b_global, cancel_event, log_fn=None, progress_fn=_baseline_progress_fn
                    )
                if cancel_event.is_set():
                    break

                # Baseline 跑完后立即写一次中间状态，让前端能看到 Baseline 分
                bs_early = _score_from_backtest_result(b_res)
                state["live_summary"] = _sanitize_json_floats({
                    "windows_done": len(window_results),
                    "windows_total": total_w,
                    "current_window": f"{sd} ~ {ed}",
                    "current_phase": "challenger_running",
                    "aggregate_baseline_score": _aggregate_scores(baseline_scores + [bs_early], agg_method),
                    "aggregate_challenger_score": _aggregate_scores(challenger_scores, agg_method),
                    "score_advantage": None,
                    "windows_challenger_better": wins_challenger,
                    "windows_comparable": comparable_windows,
                })
                if live_update_hook:
                    try:
                        live_update_hook({
                            "progress": dict(state.get("progress") or {}),
                            "live_summary": state.get("live_summary"),
                            "live_window_results": state.get("live_window_results"),
                        })
                    except Exception:
                        pass

                _log(f"  窗口 {idx + 1}/{total_w}: {sd} ~ {ed} — Baseline 完成，开始跑 Challenger", "info")
                _challenger_progress_fn = _make_window_progress_callback(
                    live_update_hook, state, total_w, window_results, sd, ed, baseline_scores, agg_method
                )
                c_res = await _run_one_backtest_no_tuning(
                    challenger_wf_effective, sd, ed, c_contract, c_global, cancel_event, log_fn=None, progress_fn=_challenger_progress_fn
                )

                bs = _score_from_backtest_result(b_res)
                cs = _score_from_backtest_result(c_res)
                baseline_scores.append(bs)
                challenger_scores.append(cs)
                if bs is not None and cs is not None:
                    comparable_windows += 1
                    if cs > bs:
                        wins_challenger += 1

                window_results.append({
                    "start_date": sd,
                    "end_date": ed,
                    "baseline": _summarize_backtest_for_compare(b_res),
                    "challenger": _summarize_backtest_for_compare(c_res),
                    "challenger_score": cs,
                    "baseline_score": bs,
                    "challenger_better": (cs is not None and bs is not None and cs > bs),
                })

                # 实时更新 state，让前端轮询时能看到中间结果
                agg_b_live = _aggregate_scores(baseline_scores, agg_method)
                agg_c_live = _aggregate_scores(challenger_scores, agg_method)
                adv_live = (agg_c_live - agg_b_live) if agg_b_live is not None and agg_c_live is not None else None
                state["live_summary"] = _sanitize_json_floats({
                    "windows_done": len(window_results),
                    "windows_total": total_w,
                    "aggregate_baseline_score": agg_b_live,
                    "aggregate_challenger_score": agg_c_live,
                    "score_advantage": adv_live,
                    "windows_challenger_better": wins_challenger,
                    "windows_comparable": comparable_windows,
                })
                state["live_window_results"] = _sanitize_json_floats(window_results)
                if live_update_hook:
                    try:
                        live_update_hook({
                            "progress": dict(state.get("progress") or {}),
                            "live_summary": state.get("live_summary"),
                            "live_window_results": state.get("live_window_results"),
                        })
                    except Exception:
                        pass

            pool_candidate_id: Optional[str] = None
            agg_baseline = _aggregate_scores(baseline_scores, agg_method)
            agg_challenger = _aggregate_scores(challenger_scores, agg_method)
            advantage = (
                (agg_challenger - agg_baseline)
                if agg_baseline is not None and agg_challenger is not None
                else None
            )
            meets_score_margin = advantage is not None and advantage >= float(score_margin)
            meets_win_count = True
            if min_win is not None and int(min_win) > 0:
                meets_win_count = wins_challenger >= int(min_win)
            eligible_for_pool = meets_score_margin and meets_win_count

            summary = {
                "aggregate_method": agg_method,
                "aggregate_baseline_score": agg_baseline,
                "aggregate_challenger_score": agg_challenger,
                "score_advantage": advantage,
                "score_margin": float(score_margin),
                "min_windows_challenger_better": min_win,
                "meets_score_margin": meets_score_margin,
                "meets_win_count": meets_win_count,
                "meets_margin": eligible_for_pool,
                "eligible_for_pool": eligible_for_pool,
                "windows_total": total_w,
                "windows_comparable": comparable_windows,
                "windows_challenger_better": wins_challenger,
            }
            result_error: Optional[str] = None
            if comparable_windows <= 0:
                result_error = "no_comparable_windows"
                summary["failure_reason"] = result_error
                summary["meets_score_margin"] = False
                summary["meets_margin"] = False
                summary["eligible_for_pool"] = False

            if add_to_candidate_pool and not cancel_event.is_set() and comparable_windows > 0:
                pool_candidate_id = f"cand-{uuid.uuid4().hex[:12]}"
                entry_status = "pending_promote" if eligible_for_pool else "ineligible"
                
                # 计算 diff_from_baseline
                diff_from_baseline = _compute_diff_from_baseline(
                    baseline_wf,
                    challenger_config_override,
                    challenger_structure_override,
                    challenger_global_config_patch,
                )
                
                # 从 state 中提取 source_run_id 和 source_iteration（若来自 AutoResearch）
                source_run_id = state.get("source_autoresearch_run_id") or ""
                source_iteration = state.get("source_iteration") or ""
                
                # 提取 feature_recipe_id（若有）
                feature_recipe_id = ""
                if isinstance(challenger_structure_override, dict):
                    feature_recipe_id = challenger_structure_override.get("feature_recipe_id") or ""
                
                entry = {
                    "id": pool_candidate_id,
                    "created_at": datetime.now().isoformat(),
                    "comparison_id": comparison_id,
                    "baseline_workflow_id": baseline_workflow_id,
                    "challenger_workflow_id": challenger_workflow_id,
                    "evaluation_contract": contract,
                    "summary": summary,
                    "window_results": window_results,
                    "status": entry_status,
                    # 新增字段（任务 1.1）
                    "challenger_override": challenger_config_override or {},
                    "effective_structure_patch": challenger_structure_override or {},
                    "effective_parameter_patch": challenger_global_config_patch or {},
                    "node_param_patches": challenger_node_param_patches or [],
                    "diff_from_baseline": diff_from_baseline,
                    "feature_recipe_id": feature_recipe_id,
                    "source_run_id": source_run_id,
                    "source_iteration": source_iteration,
                }
                if summary.get("score_advantage") is not None:
                    entry["evaluation"] = {
                        "score_advantage": summary.get("score_advantage"),
                        "mape_improvement": summary.get("score_advantage"),
                    }
                requested_candidate_id = str(pool_candidate_id or "")
                stored_candidate_id = _append_candidate_pool_entry(entry)
                if stored_candidate_id:
                    pool_candidate_id = stored_candidate_id
                if pool_candidate_id:
                    pool_ids_collected.append(pool_candidate_id)
                if stored_candidate_id and requested_candidate_id and stored_candidate_id != requested_candidate_id:
                    _log(f"◇ 候选与历史配置重复，已合并到候选池记录: {stored_candidate_id}", "info")
                elif eligible_for_pool:
                    _log(f"✓ 已写入候选池（可 Promote）: {pool_candidate_id}", "success")
                else:
                    _log(f"◇ 已写入候选池（未达标，仅记录）: {pool_candidate_id}", "info")

            all_challenger_results.append({
                "challenger_workflow_id": challenger_workflow_id,
                "error": result_error,
                "summary": summary,
                "window_results": window_results,
                "pool_candidate_id": pool_candidate_id,
            })

        state["challenger_workflow_ids"] = deduped_challengers
        state["challenger_results"] = _sanitize_json_floats(all_challenger_results)

        if not all_challenger_results:
            raise ValueError("未产生任何 challenger 比对结果")
        if all(r.get("error") for r in all_challenger_results):
            raise ValueError(
                "全部 challenger 无效: "
                + "; ".join(str(r.get("error")) for r in all_challenger_results)
            )

        if len(deduped_challengers) == 1 and all_challenger_results:
            r0 = all_challenger_results[-1]
            if not r0.get("error"):
                state["summary"] = _sanitize_json_floats(r0.get("summary"))
                state["window_results"] = _sanitize_json_floats(r0.get("window_results"))
                state["pool_candidate_id"] = r0.get("pool_candidate_id")
        else:
            state["summary"] = _sanitize_json_floats({
                "mode": "multi_challenger",
                "challenger_count": len(all_challenger_results),
                "aggregate_method": agg_method,
                "pool_candidate_ids": pool_ids_collected,
                "rows": [
                    {
                        "challenger_workflow_id": r.get("challenger_workflow_id"),
                        "score_advantage": (r.get("summary") or {}).get("score_advantage")
                        if isinstance(r.get("summary"), dict)
                        else None,
                        "eligible_for_pool": (r.get("summary") or {}).get("eligible_for_pool")
                        if isinstance(r.get("summary"), dict)
                        else None,
                        "pool_candidate_id": r.get("pool_candidate_id"),
                        "error": r.get("error"),
                    }
                    for r in all_challenger_results
                ],
            })
            state["window_results"] = None
            state["pool_candidate_id"] = pool_ids_collected[-1] if len(pool_ids_collected) == 1 else None
            state["pool_candidate_ids"] = pool_ids_collected

        state["status"] = "cancelled" if cancel_event.is_set() else "success"
        if cancel_event.is_set():
            state["error"] = "比对已取消"
        state["finished_at"] = datetime.now().isoformat()
        if live_update_hook:
            try:
                live_update_hook({
                    "progress": dict(state.get("progress") or {}),
                    "live_summary": state.get("live_summary"),
                    "live_window_results": state.get("live_window_results"),
                    "summary": state.get("summary"),
                    "status": state.get("status"),
                })
            except Exception:
                pass
    except Exception as e:
        import traceback as _tb
        tb_str = _tb.format_exc()
        traceback.print_exc()
        state["status"] = "failed"
        state["error"] = str(e)
        state["error_traceback"] = tb_str
        state["finished_at"] = datetime.now().isoformat()
        _log(f"✗ 比对失败: {e}", "error")
        _log(f"[traceback] {tb_str}", "error")
    finally:
        _comparison_cancel_events.pop(comparison_id, None)


def _run_compare_async_thread(
    comparison_id: str,
    baseline_workflow_id: str,
    challenger_workflow_ids: List[str],
    windows: List[dict],
    evaluation_contract: dict,
    score_margin: float,
    add_to_candidate_pool: bool,
    cancel_event: threading.Event,
    aggregate_method: str = "mean",
    min_windows_challenger_better: Optional[int] = None,
    challenger_config_override: Optional[dict] = None,
    baseline_config_override: Optional[dict] = None,
) -> None:
    try:
        asyncio.run(
            _run_compare_backtest_batch_task(
                comparison_id,
                baseline_workflow_id,
                challenger_workflow_ids,
                windows,
                evaluation_contract,
                score_margin,
                add_to_candidate_pool,
                cancel_event,
                aggregate_method,
                min_windows_challenger_better,
                challenger_config_override,
                baseline_config_override,
            )
        )
    except Exception as e:
        state = _comparison_store.get(comparison_id) or {}
        state["status"] = "failed"
        state["error"] = str(e)
        state["finished_at"] = datetime.now().isoformat()
        _comparison_store[comparison_id] = state
        _comparison_cancel_events.pop(comparison_id, None)


def _finalize_verification_item(item_id: str, comparison_id: str) -> None:
    state = _comparison_store.get(comparison_id) or {}
    status = str(state.get("status") or "")
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
    windows_total = int(summary.get("windows_total") or 0)
    windows_better = int(summary.get("windows_challenger_better") or 0)
    eligible = bool(summary.get("eligible_for_pool"))
    final_status = "passed" if status == "success" and eligible else "failed"
    if status == "cancelled":
        final_status = "cancelled"
    elif status == "failed":
        final_status = "failed"
    source_run_id = ""
    source_iteration = 0
    candidate_signature = ""
    candidate_id = ""
    with _AUTO_RESEARCH_FILE_LOCK:
        items = _load_verification_queue()
        for row in items:
            if str(row.get("id") or "") != item_id:
                continue
            row["status"] = final_status
            row["updated_at"] = datetime.now().isoformat()
            row["finished_at"] = datetime.now().isoformat()
            row["result"] = _sanitize_json_floats({
                "comparison_id": comparison_id,
                "comparison_status": status,
                "summary": summary,
                "window_results": state.get("window_results"),
            })
            row["failure_reason"] = None if final_status == "passed" else (
                state.get("error")
                or f"verification_not_passed: windows_better={windows_better}/{windows_total}, eligible={eligible}"
            )
            source_run_id = str(row.get("source_run_id") or "")
            source_iteration = int(row.get("source_iteration") or 0)
            candidate_signature = str(row.get("candidate_signature") or "")
            candidate_id = str(row.get("candidate_id") or "")
            break
        _save_verification_queue(items)
    global _verification_active_job_id
    if _verification_active_job_id == item_id:
        _verification_active_job_id = None

    # ── Evidence 反写闭环：复验 passed → multi_window_confirmed ──
    if final_status == "passed" and source_run_id and source_iteration > 0:
        try:
            evidence = _sanitize_json_floats({
                "run_id": source_run_id,
                "iteration": source_iteration,
                "group_idx": None,
                "evidence_strength": "multi_window_confirmed",
                "needs_multi_window_confirmation": False,
                "status": "success",
                "windows_total": int(summary.get("windows_total") or 0),
                "windows_success": int(summary.get("windows_success") or 0),
                "windows_challenger_better": int(summary.get("windows_challenger_better") or 0),
                "mape_improvement": float(summary.get("score_advantage") or 0.0),
                "baseline_metric": summary.get("aggregate_baseline_score"),
                "challenger_metric": summary.get("aggregate_challenger_score"),
                "patch_fingerprint": candidate_signature,
                "verified_by": item_id,
                "verified_at": datetime.now().isoformat(),
                "failure_reason": None,
                "target_direction": str(summary.get("target_direction") or ""),
                "target_layer": str(summary.get("target_layer") or ""),
            })
            # 追加到源 run（内存 + 磁盘 snapshot），并同步候选池 evidence
            _append_verification_evidence_to_run(
                source_run_id,
                evidence,
                candidate_id=candidate_id or None,
            )
            logger.info(
                "verification backfill: item=%s candidate_signature=%s source_run=%s iter=%s → multi_window_confirmed",
                item_id, candidate_signature[:12], source_run_id, source_iteration,
            )
        except Exception as _bf_err:
            logger.warning("verification backfill failed: %s", _bf_err)


def _run_verification_item_thread(item_id: str) -> None:
    global _verification_active_job_id
    with _AUTO_RESEARCH_FILE_LOCK:
        items = _load_verification_queue()
        item = next((row for row in items if str(row.get("id") or "") == item_id), None)
    if not item:
        _verification_active_job_id = None
        return
    comparison_id = f"cmp-ver-{uuid.uuid4().hex[:10]}"
    cancel_event = threading.Event()
    _init_comparison_state(comparison_id)
    _comparison_cancel_events[comparison_id] = cancel_event
    with _AUTO_RESEARCH_FILE_LOCK:
        items = _load_verification_queue()
        for row in items:
            if str(row.get("id") or "") == item_id:
                row["status"] = "running"
                row["comparison_id"] = comparison_id
                row["started_at"] = datetime.now().isoformat()
                row["updated_at"] = row["started_at"]
                row["failure_reason"] = None
                break
        _save_verification_queue(items)
    loop = asyncio.new_event_loop()
    try:
        loop._verification_pool = _VERIFICATION_BACKTEST_POOL  # type: ignore[attr-defined]
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            _run_compare_backtest_batch_task(
                comparison_id,
                str(item.get("baseline_workflow_id") or ""),
                [str(item.get("challenger_workflow_id") or "")],
                item.get("windows") if isinstance(item.get("windows"), list) else [],
                item.get("evaluation_contract") if isinstance(item.get("evaluation_contract"), dict) else {},
                float(item.get("score_margin") or 0.0),
                False,
                cancel_event,
                str(item.get("aggregate_method") or "mean"),
                int(item.get("min_windows_challenger_better") or 2),
                item.get("challenger_config_override") if isinstance(item.get("challenger_config_override"), dict) else None,
                None,
                item.get("challenger_structure_override") if isinstance(item.get("challenger_structure_override"), dict) else None,
                item.get("challenger_global_config_patch") if isinstance(item.get("challenger_global_config_patch"), dict) else None,
                item.get("challenger_node_param_patches") if isinstance(item.get("challenger_node_param_patches"), list) else None,
            )
        )
    finally:
        try:
            asyncio.set_event_loop(None)
            loop.close()
        except Exception as _loop_close_err:
            logger.warning("verification event loop close failed: %s", _loop_close_err)
        _finalize_verification_item(item_id, comparison_id)


def _start_verification_item(item_id: Optional[str] = None, *, force: bool = False) -> Dict[str, Any]:
    global _verification_active_job_id
    if _has_active_autoresearch_run():
        logger.warning("verification: AutoResearch run active, proceeding with independent verification pool")
    resource_block = _verification_resource_block(force=force)
    if resource_block:
        return resource_block
    with _AUTO_RESEARCH_FILE_LOCK:
        items = _load_verification_queue()
        active = _verification_active_item(items)
        if active:
            return {"started": False, "reason": "verification_already_running", "item": active}
        target: Optional[Dict[str, Any]] = None
        for row in items:
            if item_id and str(row.get("id") or "") != item_id:
                continue
            if str(row.get("status") or "") in {"queued", "failed", "cancelled"}:
                target = row
                break
        if target is None:
            return {"started": False, "reason": "no_queued_item"}
        _verification_active_job_id = str(target.get("id") or "")
    thread = threading.Thread(
        target=_run_verification_item_thread,
        args=(_verification_active_job_id,),
        daemon=True,
    )
    thread.start()
    return {"started": True, "item_id": _verification_active_job_id}


async def _run_tuning_batch(
    workflow,
    start_date: str,
    end_date: str,
    base_params: dict,
    global_config: dict,
    tuning_candidates: List[dict],
    cancel_event: Optional[threading.Event],
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> dict:
    ranked_candidates = []
    for idx, candidate in enumerate(tuning_candidates):
        if cancel_event is not None and cancel_event.is_set():
            break
        candidate_dict = candidate if isinstance(candidate, dict) else {}
        candidate_name = str(candidate_dict.get("name") or f"candidate_{idx + 1}")
        candidate_params = dict(base_params)
        candidate_params.pop("tuning_candidates", None)
        candidate_overrides = candidate_dict.get("params") if isinstance(candidate_dict.get("params"), dict) else {
            k: v for k, v in candidate_dict.items() if k not in ("name", "params")
        }
        candidate_params.update(candidate_overrides)

        candidate_mode = str(
            candidate_params.get("backtest_mode")
            or global_config.get("backtest_mode")
            or "rolling_retrain"
        ).strip().lower()
        candidate_model_ref = (
            candidate_params.get("model_ref")
            or candidate_params.get("backtest_model_ref")
            or global_config.get("backtest_model_ref")
        )
        if candidate_mode not in ("rolling_retrain", "inference_only"):
            if log_fn:
                log_fn(f"✗ 候选 {candidate_name} 失败: invalid backtest_mode={candidate_mode}", "error")
            ranked_candidates.append({
                "rank": None,
                "name": candidate_name,
                "candidate_index": idx,
                "status": "failed",
                "error": f"invalid backtest_mode: {candidate_mode}",
                "applied_params": candidate_overrides,
            })
            continue
        if candidate_mode == "inference_only" and not candidate_model_ref:
            if log_fn:
                log_fn(f"✗ 候选 {candidate_name} 失败: inference_only requires model_ref", "error")
            ranked_candidates.append({
                "rank": None,
                "name": candidate_name,
                "candidate_index": idx,
                "status": "failed",
                "error": "inference_only requires model_ref",
                "applied_params": candidate_overrides,
            })
            continue

        try:
            if log_fn:
                log_fn(f"▶ 开始候选 {candidate_name} ({idx + 1}/{len(tuning_candidates)})", "start")
            if _should_use_reference_rolling_engine(workflow, candidate_params, global_config):
                candidate_result = await asyncio.to_thread(
                    _execute_backtest_reference,
                    workflow,
                    start_date,
                    end_date,
                    candidate_params,
                    global_config,
                    cancel_event,
                )
            else:
                candidate_result = await asyncio.to_thread(
                    _execute_backtest,
                    workflow,
                    start_date,
                    end_date,
                    candidate_params.get("training_node_ids"),
                    candidate_params.get("prediction_node_ids"),
                    int(candidate_params.get("train_days") or global_config.get("backtest_train_days") or 30),
                    bool(
                        candidate_params.get("apply_window_filter")
                        if candidate_params.get("apply_window_filter") is not None
                        else global_config.get("backtest_apply_window_filter", True)
                    ),
                    bool(
                        candidate_params.get("mask_target_values")
                        if candidate_params.get("mask_target_values") is not None
                        else global_config.get("backtest_mask_target_values", True)
                    ),
                    candidate_mode,
                    candidate_model_ref,
                    cancel_event,
                    None,
                    None,
                    int(candidate_params.get("gap_days") if candidate_params.get("gap_days") is not None else global_config.get("backtest_gap_days", 1)),
                )
            ranked_candidates.append({
                "rank": None,
                "name": candidate_name,
                "candidate_index": idx,
                "status": "success" if not candidate_result.get("error") else "failed",
                "error": candidate_result.get("error"),
                "candidate_score": candidate_result.get("candidate_score"),
                "avg_metrics": candidate_result.get("avg_metrics"),
                "summary": {
                    "success_days": candidate_result.get("success_days"),
                    "failed_days": candidate_result.get("failed_days"),
                    "skipped_days": candidate_result.get("skipped_days"),
                    "total_duration": candidate_result.get("total_duration"),
                },
                "backtest_mode": candidate_mode,
                "model_ref": candidate_model_ref,
                "applied_params": candidate_overrides,
            })
            if log_fn:
                if candidate_result.get("error"):
                    log_fn(f"✗ 候选 {candidate_name} 执行失败: {candidate_result.get('error')}", "error")
                else:
                    score = ((candidate_result.get("candidate_score") or {}).get("score"))
                    score_text = f", score={round(float(score), 4)}" if score is not None else ""
                    log_fn(f"✓ 候选 {candidate_name} 完成{score_text}", "success")
        except Exception as e:
            if log_fn:
                log_fn(f"✗ 候选 {candidate_name} 异常: {e}", "error")
            ranked_candidates.append({
                "rank": None,
                "name": candidate_name,
                "candidate_index": idx,
                "status": "failed",
                "error": str(e),
                "applied_params": candidate_overrides,
            })

    successful = [c for c in ranked_candidates if c.get("status") == "success"]
    successful_sorted = sorted(successful, key=_candidate_sort_key)
    for rank, item in enumerate(successful_sorted, start=1):
        item["rank"] = rank
    failed = [c for c in ranked_candidates if c.get("status") != "success"]
    return {
        "mode": "tuning_batch",
        "total_candidates": len(ranked_candidates),
        "successful_candidates": len(successful_sorted),
        "failed_candidates": len(failed),
        "ranked_candidates": successful_sorted + failed,
        "best_recommendation": successful_sorted[0] if successful_sorted else None,
        "cancelled": bool(cancel_event is not None and cancel_event.is_set()),
    }


def _execute_backtest_reference(
    workflow,
    start_date: str,
    end_date: str,
    backtest_params: dict,
    global_config: dict,
    cancel_event: Optional[threading.Event] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """
    與 load_forecast_refactored/run_weihai_backtest.py 對齊的滾動日多模型回測（內建於 backend，不依賴倉庫外路徑）。
    時間範圍與圖中回測一致：end_date 為**閉區間**最後一個預測日，內部轉為參考腳本用的 exclusive 右端點。
    """
    import time

    import pandas as pd
    from services.reference_rolling_backtest.config import ReferenceBacktestConfig
    from services.reference_rolling_backtest.engine import run_from_file, to_platform_daily_results

    t0 = time.time()
    if log_fn:
        log_fn(f"▶ 使用参考回测引擎执行: {start_date} ~ {end_date}", "start")
    csv_cfg = _load_csv_config_from_workflow(workflow)
    file_path = (
        backtest_params.get("reference_csv_path")
        or backtest_params.get("csv_path")
        or global_config.get("backtest_reference_csv")
    )
    if not file_path:
        file_path = csv_cfg.get("file_path")
    if not file_path:
        return {
            "total_days": 0,
            "success_days": 0,
            "skipped_days": 0,
            "failed_days": 1,
            "total_duration": 0.0,
            "daily_results": [],
            "cancelled": False,
            "error": "參考回測需數據路徑：請在節點 load_csv 配置 file_path，或請求體中傳 reference_csv_path。",
            "avg_metrics": None,
            "cv_fold_metrics": [],
        }
    pred_start = str(pd.to_datetime(start_date).date())
    pred_end = (pd.to_datetime(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    train_days = int(backtest_params.get("train_days") or global_config.get("backtest_train_days") or 30)
    daily_horizon = int(
        backtest_params.get("daily_horizon") or global_config.get("backtest_daily_horizon") or 96
    )
    bo_n_iter = int(backtest_params.get("bo_n_iter") or global_config.get("backtest_bo_n_iter", 12))
    use_bayes = backtest_params.get("use_bayesian_tuning")
    if use_bayes is None:
        use_bayes = global_config.get("backtest_use_bayesian_tuning", True)
    # @AI_GENERATED
    # gap_days: 训练截止到 pred_day - 1 - gap_days，默认 1（D-2）
    gap_days = int(
        backtest_params.get("gap_days")
        if backtest_params.get("gap_days") is not None
        else global_config.get("backtest_gap_days", 1)
    )
    # @AI_GENERATED: end
    ref_cfg = ReferenceBacktestConfig(
        train_days=train_days,
        daily_horizon=daily_horizon,
        bo_n_iter=bo_n_iter,
        use_bayesian_tuning=bool(use_bayes),
        parent_id=backtest_params.get("parent_id") or csv_cfg.get("parent_id"),
        child_id=backtest_params.get("child_id") or csv_cfg.get("child_id"),
        gap_days=gap_days,
    )
    try:
        rdf = run_from_file(
            file_path, _BACKEND_DIR, pred_start, pred_end, ref_cfg, cancel_event=cancel_event
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "total_days": 0,
            "success_days": 0,
            "skipped_days": 0,
            "failed_days": 1,
            "total_duration": round(time.time() - t0, 3),
            "daily_results": [],
            "cancelled": bool(cancel_event is not None and cancel_event.is_set()),
            "error": str(e),
            "avg_metrics": None,
            "cv_fold_metrics": [],
        }
    daily = to_platform_daily_results(rdf)
    dr = pd.date_range(start=start_date, end=end_date, freq="D")
    total_days = len(dr)
    success = len(daily)
    avg_metrics = {}
    if daily:
        for key in ("smape", "rmse", "mae"):
            vals = [r.get("metrics", {}).get(key) for r in daily if r.get("metrics", {}).get(key) is not None]
            if vals:
                avg_metrics[f"avg_{key}"] = round(sum(vals) / len(vals), 4)
        # 任务 13.2：参考引擎同样新增 avg_bias 和 avg_p95_ape
        bias_vals = [r.get("metrics", {}).get("bias") for r in daily if r.get("metrics", {}).get("bias") is not None]
        if bias_vals:
            avg_metrics["avg_bias"] = round(sum(bias_vals) / len(bias_vals), 4)
        p95_vals = [r.get("metrics", {}).get("p95_ape") for r in daily if r.get("metrics", {}).get("p95_ape") is not None]
        if p95_vals:
            avg_metrics["avg_p95_ape"] = round(sum(p95_vals) / len(p95_vals), 4)
    candidate_score = _build_candidate_score(avg_metrics or None)
    cv_fold_metrics = _aggregate_cv_fold_metrics(daily)
    result = {
        "total_days": total_days,
        "success_days": success,
        "skipped_days": max(0, total_days - success),
        "failed_days": 0,
        "total_duration": round(time.time() - t0, 3),
        "daily_results": daily,
        "cancelled": bool(cancel_event is not None and cancel_event.is_set()),
        "engine": "reference_rolling_weihai",
        "avg_metrics": avg_metrics or None,
        "candidate_score": candidate_score,
        "cv_fold_metrics": cv_fold_metrics,
    }
    if log_fn:
        log_fn(
            f"✓ 参考回测完成: success={result.get('success_days')}, skipped={result.get('skipped_days')}, failed={result.get('failed_days')}",
            "success",
        )
    return result


def _execute_backtest(
    workflow,
    start_date: str,
    end_date: str,
    training_node_ids: Optional[List[str]] = None,
    prediction_node_ids: Optional[List[str]] = None,
    train_days: int = 30,
    apply_window_filter: bool = True,
    mask_target_values: bool = True,
    backtest_mode: str = "rolling_retrain",
    model_ref: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
    log_fn: Optional[Callable[[str, str], None]] = None,
    progress_fn: Optional[Callable[[int, int, str], None]] = None,
    gap_days: int = 1,
):
    print(f"[DEBUG] _execute_backtest CALLED: start={start_date}, end={end_date}, train_days={train_days}, mask={mask_target_values}, gap={gap_days}")
    """
    Execute backtest by looping over a date range.

    For each day:
      1. Set nowtime in global config to the current backtest date
      2. Execute the full pipeline (training + prediction sub-pipelines)
      3. Collect results

    Args:
        workflow: EnhancedWorkflow instance
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        training_node_ids: Optional list of node IDs for training sub-pipeline
        prediction_node_ids: Optional list of node IDs for prediction sub-pipeline

    Returns:
        dict: Backtest aggregated results
    """
    import pandas as pd

    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    total_days = len(dates)
    success_days = 0
    skipped_days = 0
    failed_days = 0
    daily_results = []
    backtest_start = time.time()

    for day in dates:
        if cancel_event is not None and cancel_event.is_set():
            break
        day_index = len(daily_results) + 1
        day_str = day.strftime("%Y-%m-%d")
        if progress_fn:
            progress_fn(day_index, total_days, day_str)
        if log_fn:
            log_fn(f"▶ 回测日 {day_index}/{total_days}: {day_str}", "start")
        pred_start_dt = pd.to_datetime(day_str)
        pred_end_dt = pred_start_dt + pd.Timedelta(days=1)
        # gap_days: 训练数据截止到 pred_day - 1 - gap_days（默认 1，即 D-2 00:00:00）
        # 与 reference_rolling_backtest/engine.py 和 run_weihai_backtest.py 对齐：
        # train_end = pred_day - timedelta(days=1 + gap_days)
        # gap_days=0 退化为原始逻辑（训练截止到 D-1 00:00:00）
        _gap = int(gap_days)
        train_end_dt = pred_start_dt - pd.Timedelta(days=1 + _gap)
        train_start_dt = train_end_dt - pd.Timedelta(days=max(1, int(train_days)))
        nowtime_str = f"{day_str} 00:00:00"
        day_start = time.time()

        # Update global config with current backtest date
        metadata = workflow.metadata or {}
        global_config = dict(metadata.get("global_config", {}))
        global_config["nowtime"] = nowtime_str
        global_config["operate_status"] = "backtest"
        # rolling backtest window controls (used by row_filter / split operators)
        global_config["backtest_train_days"] = int(train_days)
        global_config["backtest_train_start"] = train_start_dt.strftime("%Y-%m-%d %H:%M:%S")
        global_config["backtest_train_end"] = train_end_dt.strftime("%Y-%m-%d %H:%M:%S")
        global_config["backtest_pred_start"] = pred_start_dt.strftime("%Y-%m-%d %H:%M:%S")
        global_config["backtest_pred_end"] = pred_end_dt.strftime("%Y-%m-%d %H:%M:%S")
        global_config["backtest_split_date"] = train_end_dt.strftime("%Y-%m-%d %H:%M:%S")
        global_config["backtest_gap_days"] = _gap
        global_config["backtest_apply_window_filter"] = bool(apply_window_filter)
        global_config["backtest_mask_target_values"] = bool(mask_target_values)
        global_config["backtest_mode"] = backtest_mode
        if model_ref:
            global_config["backtest_model_ref"] = model_ref

        # Create a modified workflow copy with updated metadata
        workflow_dict = workflow.dict()
        if workflow_dict.get("metadata") is None:
            workflow_dict["metadata"] = {}
        workflow_dict["metadata"]["global_config"] = global_config

        # 支持通过 global_config 里的 auto_tune_n_trials 覆盖节点级贝叶斯轮数
        # 这样比对时可以通过 evaluation_contract 或 config_override 快速减少搜索轮数
        _override_n_trials = global_config.get("auto_tune_n_trials")
        if _override_n_trials is not None:
            try:
                _n = int(_override_n_trials)
                for _node in (workflow_dict.get("nodes") or []):
                    _nd = _node.get("data") or {}
                    _cfg = _nd.get("config") or {}
                    if _cfg.get("functionId") == "auto_tune_xgboost":
                        _cfg["n_trials"] = _n
                        _nd["config"] = _cfg
                        _node["data"] = _nd
            except (TypeError, ValueError):
                pass

        day_workflow = EnhancedWorkflow(**workflow_dict)

        try:
            try:
                result = _execute_pipeline_sync(day_workflow, cancel_event=cancel_event)
            except TypeError as te:
                if "cancel_event" not in str(te):
                    raise
                result = _execute_pipeline_sync(day_workflow)
            day_duration = time.time() - day_start
            if cancel_event is not None and cancel_event.is_set():
                if log_fn:
                    log_fn(f"⊘ {day_str} 回测已取消", "error")
                break

            if result["success"]:
                success_days += 1
                # @AI_GENERATED
                # Extract metrics and prediction values from pipeline result
                raw_m = result.get("metrics")
                day_metrics = raw_m if isinstance(raw_m, dict) else {}
                y_true = result.get("y_true")
                y_pred = result.get("y_pred")
                cv_fold_metrics = result.get("cv_fold_metrics") or []
                if not _normalize_metrics_dict(day_metrics) and y_true is not None and y_pred is not None:
                    fb = _metrics_from_y_true_pred(y_true, y_pred)
                    if fb:
                        day_metrics = {**day_metrics, **fb}
                # @AI_GENERATED: end

                # @AI_GENERATED: debug logging for backtest y_true/y_pred
                import numpy as _np
                _yt_len = len(y_true) if y_true is not None else 0
                _yp_len = len(y_pred) if y_pred is not None else 0
                _yt_nan = int(_np.isnan(_np.array(y_true, dtype=float)).sum()) if y_true is not None and _yt_len > 0 else 0
                _yt_sample = y_true[:3] if y_true is not None and _yt_len > 0 else []
                _yt_arr = _np.array(y_true, dtype=float) if y_true is not None and _yt_len > 0 else _np.array([])
                _yp_arr = _np.array(y_pred, dtype=float) if y_pred is not None and _yp_len > 0 else _np.array([])
                print(f"[Backtest DEBUG] day={day_str} y_true: len={_yt_len}, nan={_yt_nan}, "
                      f"range=[{_yt_arr[_np.isfinite(_yt_arr)].min():.0f}~{_yt_arr[_np.isfinite(_yt_arr)].max():.0f}]" if _yt_len > 0 and _np.isfinite(_yt_arr).any() else f"[Backtest DEBUG] day={day_str} y_true: len={_yt_len}, ALL NaN or empty")
                print(f"[Backtest DEBUG] day={day_str} y_pred: len={_yp_len}, "
                      f"range=[{_yp_arr[_np.isfinite(_yp_arr)].min():.0f}~{_yp_arr[_np.isfinite(_yp_arr)].max():.0f}]" if _yp_len > 0 and _np.isfinite(_yp_arr).any() else f"[Backtest DEBUG] day={day_str} y_pred: len={_yp_len}, ALL NaN or empty")
                print(f"[Backtest DEBUG] day={day_str} metrics={day_metrics}")
                # @AI_GENERATED: end

                daily_results.append({
                    "date": day_str,
                    "status": "success",
                    "duration": round(day_duration, 3),
                    "metrics": day_metrics,
                    "y_true": y_true,
                    "y_pred": y_pred,
                    "point_count": len(y_pred) if y_pred else 0,
                    "cv_fold_metrics": cv_fold_metrics,
                })
                if log_fn:
                    smape_value = day_metrics.get("smape") if isinstance(day_metrics, dict) else None
                    if smape_value is not None:
                        log_fn(f"✓ {day_str} 完成: SMAPE={smape_value}", "success")
                    else:
                        log_fn(f"✓ {day_str} 完成", "success")
            else:
                # Check if failure is due to insufficient data
                error_msg = result.get("error", "")
                if "insufficient" in error_msg.lower() or "不足" in error_msg:
                    skipped_days += 1
                    daily_results.append({
                        "date": day_str,
                        "status": "skipped",
                        "duration": round(day_duration, 3),
                        "error": error_msg,
                    })
                    if log_fn:
                        log_fn(f"⚠ {day_str} 跳过: {error_msg}", "info")
                else:
                    failed_days += 1
                    daily_results.append({
                        "date": day_str,
                        "status": "failed",
                        "duration": round(day_duration, 3),
                        "error": error_msg,
                    })
                    if log_fn:
                        log_fn(f"✗ {day_str} 失败: {error_msg}", "error")
        except Exception as e:
            day_duration = time.time() - day_start
            failed_days += 1
            daily_results.append({
                "date": day_str,
                "status": "failed",
                "duration": round(day_duration, 3),
                "error": str(e),
            })
            if log_fn:
                log_fn(f"✗ {day_str} 异常: {e}", "error")

    total_duration = time.time() - backtest_start
    # @AI_GENERATED
    # Compute average metrics across successful days
    avg_metrics = {}
    successful_metrics = [
        _normalize_metrics_dict(r.get("metrics"))
        for r in daily_results
        if r.get("status") == "success" and r.get("metrics")
    ]
    successful_metrics = [m for m in successful_metrics if m]
    if successful_metrics:
        for key in ["smape", "rmse", "mae", "mse"]:
            values = [m.get(key) for m in successful_metrics if m.get(key) is not None]
            if values:
                avg_metrics[f"avg_{key}"] = round(sum(values) / len(values), 4)
        # 任务 13.1：新增 avg_bias（平均预测偏差）和 avg_p95_ape（平均第95百分位绝对百分误差）
        bias_vals = [m.get("bias") for m in successful_metrics if m.get("bias") is not None]
        if bias_vals:
            avg_metrics["avg_bias"] = round(sum(bias_vals) / len(bias_vals), 4)
        p95_vals = [m.get("p95_ape") for m in successful_metrics if m.get("p95_ape") is not None]
        if p95_vals:
            avg_metrics["avg_p95_ape"] = round(sum(p95_vals) / len(p95_vals), 4)
    candidate_score = _build_candidate_score(avg_metrics if avg_metrics else None)
    cv_fold_metrics = _aggregate_cv_fold_metrics(daily_results)
    # @AI_GENERATED: end

    # 任务 11.3：记录各子模型单独指标（集成模式下从 daily_results 提取）
    per_model_metrics: Dict[str, Any] = {}
    for r in daily_results:
        if r.get("status") != "success":
            continue
        # 各子模型预测结果通常以 y_pred_xgb / y_pred_lgb 等 key 存在于 result 中
        # 若流水线输出了 per_model_metrics 字段则直接合并
        pmm = r.get("per_model_metrics")
        if isinstance(pmm, dict):
            for model_key, model_m in pmm.items():
                if not isinstance(model_m, dict):
                    continue
                if model_key not in per_model_metrics:
                    per_model_metrics[model_key] = {"smape_vals": [], "rmse_vals": []}
                for mk, mv in model_m.items():
                    per_model_metrics[model_key].setdefault(f"{mk}_vals", []).append(mv)
    # 聚合各模型指标
    per_model_avg: Dict[str, Any] = {}
    for model_key, acc in per_model_metrics.items():
        entry: Dict[str, Any] = {}
        for metric_key in ("smape", "rmse", "mae"):
            vals = acc.get(f"{metric_key}_vals") or []
            if vals:
                entry[f"avg_{metric_key}"] = round(sum(vals) / len(vals), 4)
        if entry:
            per_model_avg[model_key] = entry

    result = {
        "total_days": total_days,
        "success_days": success_days,
        "skipped_days": skipped_days,
        "failed_days": failed_days,
        "total_duration": round(total_duration, 3),
        "daily_results": daily_results,
        "cancelled": bool(cancel_event is not None and cancel_event.is_set()),
        # @AI_GENERATED
        "avg_metrics": avg_metrics if avg_metrics else None,
        "candidate_score": candidate_score,
        "cv_fold_metrics": cv_fold_metrics,
        # @AI_GENERATED: end
        "per_model_metrics": per_model_avg if per_model_avg else None,  # 任务 11.3：各子模型指标
    }
    if log_fn:
        log_fn(
            f"✓ 回测结束: success={success_days}, skipped={skipped_days}, failed={failed_days}",
            "success",
        )
    return result


def _init_async_backtest_state(execution_id: str, workflow_id: str) -> None:
    _execution_store[execution_id] = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "status": "pending",
        "stage": "preparing",
        "logs": [],
        "backtest_progress": {"currentDay": 0, "totalDays": 0, "currentDate": ""},
        "backtest_result": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "finished_at": None,
    }


async def _run_backtest_async_task(
    execution_id: str,
    workflow,
    workflow_id: str,
    backtest_params: dict,
    global_config: dict,
    cancel_event: threading.Event,
) -> None:
    state = _execution_store[execution_id]
    state["status"] = "running"
    state["stage"] = "running"
    state["started_at"] = datetime.now().isoformat()

    def _log(message: str, log_type: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        logs = state.get("logs") or []
        logs.append({"timestamp": ts, "message": message, "type": log_type})
        state["logs"] = logs[-2000:]

    def _update_progress(current_day: int, total_days: int, current_date: str) -> None:
        state["backtest_progress"] = {
            "currentDay": int(current_day),
            "totalDays": int(total_days),
            "currentDate": str(current_date),
        }

    start_date = backtest_params.get("start_date") or global_config.get("backtest_start_date")
    end_date = backtest_params.get("end_date") or global_config.get("backtest_end_date")
    if not start_date or not end_date:
        raise ValueError("回测参数需要 start_date 和 end_date")

    backtest_mode = str(
        backtest_params.get("backtest_mode")
        or global_config.get("backtest_mode")
        or "rolling_retrain"
    ).strip().lower()
    model_ref = (
        backtest_params.get("model_ref")
        or backtest_params.get("backtest_model_ref")
        or global_config.get("backtest_model_ref")
    )
    if backtest_mode not in ("rolling_retrain", "inference_only"):
        raise ValueError("backtest_mode 仅支持 rolling_retrain / inference_only")
    if backtest_mode == "inference_only" and not model_ref:
        raise ValueError("inference_only 回测需要提供 model_ref")

    tuning_candidates = _resolve_tuning_candidates(backtest_params, global_config)
    _log(f"▶ 开始回测任务: {start_date} ~ {end_date}", "start")

    if tuning_candidates:
        result = await _run_tuning_batch(
            workflow,
            start_date,
            end_date,
            dict(backtest_params),
            global_config,
            tuning_candidates,
            cancel_event,
            log_fn=_log,
        )
    else:
        if _should_use_reference_rolling_engine(workflow, backtest_params, global_config):
            result = await asyncio.to_thread(
                _execute_backtest_reference,
                workflow,
                start_date,
                end_date,
                backtest_params,
                global_config,
                cancel_event,
                _log,
            )
        else:
            result = await asyncio.to_thread(
                _execute_backtest,
                workflow,
                start_date,
                end_date,
                backtest_params.get("training_node_ids"),
                backtest_params.get("prediction_node_ids"),
                int(backtest_params.get("train_days") or global_config.get("backtest_train_days") or 30),
                bool(
                    backtest_params.get("apply_window_filter")
                    if backtest_params.get("apply_window_filter") is not None
                    else global_config.get("backtest_apply_window_filter", True)
                ),
                bool(
                    backtest_params.get("mask_target_values")
                    if backtest_params.get("mask_target_values") is not None
                    else global_config.get("backtest_mask_target_values", True)
                ),
                backtest_mode,
                model_ref,
                cancel_event,
                _log,
                _update_progress,
                int(backtest_params.get("gap_days") if backtest_params.get("gap_days") is not None else global_config.get("backtest_gap_days", 1)),
            )

        generate_artifacts = backtest_params.get("generate_artifacts")
        if generate_artifacts is None:
            generate_artifacts = global_config.get("backtest_generate_artifacts", True)
        out_subdir = _safe_subdir(
            backtest_params.get("output_dir") or global_config.get("backtest_output_dir")
        )
        output_base = os.path.join(_BACKTEST_ARTIFACTS_ROOT, out_subdir)
        run_id = f"{workflow_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        output_dir = os.path.join(output_base, run_id)
        artifact_paths: List[str] = []
        artifact_urls: List[str] = []
        if generate_artifacts:
            try:
                artifact_paths = await asyncio.to_thread(
                    _save_backtest_artifacts, result.get("daily_results", []), output_dir
                )
                artifact_urls = [
                    f"/api/workflows/enhanced/backtest-artifacts/{run_id}/{os.path.basename(p)}"
                    for p in artifact_paths
                ]
            except Exception as e:
                traceback.print_exc()
                artifact_paths = []
                artifact_urls = []
                result["artifact_error"] = str(e)
        result["output_dir"] = output_dir
        result["artifact_paths"] = artifact_paths
        result["artifact_urls"] = artifact_urls
        result["backtest_mode"] = backtest_mode
        result["model_ref"] = model_ref

    state["backtest_result"] = _sanitize_json_floats(result)
    state["stage"] = "finalizing"
    if cancel_event.is_set() or result.get("cancelled"):
        state["status"] = "failed"
        state["error"] = "回测已取消"
        _log("✗ 回测已取消", "error")
    else:
        state["status"] = "success"
        state["error"] = None
        _log("✓ 回测任务完成", "success")
    state["finished_at"] = datetime.now().isoformat()
    state["stage"] = "finished"
    _backtest_async_cancel_events.pop(execution_id, None)


def _run_async_backtest(
    execution_id: str,
    workflow,
    workflow_id: str,
    backtest_params: dict,
    global_config: dict,
    cancel_event: threading.Event,
) -> None:
    try:
        asyncio.run(
            _run_backtest_async_task(
                execution_id,
                workflow,
                workflow_id,
                backtest_params,
                global_config,
                cancel_event,
            )
        )
    except Exception as e:
        state = _execution_store.get(execution_id) or {}
        state["status"] = "failed"
        state["stage"] = "finished"
        state["error"] = str(e)
        logs = state.get("logs") or []
        logs.append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "message": f"✗ 回测任务异常: {e}",
            "type": "error",
        })
        state["logs"] = logs[-2000:]
        state["finished_at"] = datetime.now().isoformat()
        _execution_store[execution_id] = state
        _backtest_async_cancel_events.pop(execution_id, None)


def _init_comparison_state(comparison_id: str) -> None:
    _comparison_store[comparison_id] = {
        "comparison_id": comparison_id,
        "status": "pending",
        "progress": {"current": 0, "total": 0, "window_index": -1},
        "logs": [],
        "window_results": None,
        "summary": None,
        "pool_candidate_id": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "finished_at": None,
    }


def _init_autoresearch_state(run_id: str) -> None:
    _auto_research_store[run_id] = {
        "run_id": run_id,
        "status": "pending",
        "progress": {"iteration": 0, "total_iterations": 0},
        "logs": [],
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "finished_at": None,
        "error": None,
        "best_candidate": None,
        "top_candidates": [],
        "iterations": [],
        "dataset_profile": None,
        "dataset_profiles": [],
        "tri_dataset_diagnosis": None,
        "research_questions": [],
        "evidence_records": [],
        "evidence_summary": {},
        "exploration_health": {},
        "research_state": {"state": "warmup", "reason": "run_initialized"},
        "knowledge_governance": {},
        "experiment_quality": None,
        "periodic_reflections": [],
        "iteration_plot_data": [],
        "agent_traces": [],
        "current_research_focus": None,
        "force_activate": [],
        "search_space": {},
        "evaluation_contract": {},
        "compare_config": {},
        "runtime_patch": {"search_space_patch": {}, "evaluation_contract_patch": {}, "structure_patch": {}, "global_config_patch": {}, "node_param_patches": []},
        "scenario_tags": [],
        "auto_adjust_stats": {},
        "latest_auto_adjustment": None,
        "config_alignment": {},
    }


def _snapshot_autoresearch_state(run_id: str) -> None:
    state = _auto_research_store.get(run_id)
    if not isinstance(state, dict):
        return
    try:
        state["updated_at"] = datetime.now().isoformat()
        _auto_research_persister.save_snapshot(run_id, state)
    except Exception as e:
        logger.warning("autoresearch snapshot failed for %s: %s", run_id, e)


def _record_autoresearch_trial(run_id: str, candidate: Dict[str, Any]) -> None:
    if not isinstance(candidate, dict):
        return
    try:
        _auto_research_persister.record_trial_from_candidate(run_id, candidate)
    except Exception as e:
        logger.warning("autoresearch trial ledger append failed for %s: %s", run_id, e)


def _record_autoresearch_decision(run_id: str, decision_type: str, payload: Dict[str, Any]) -> None:
    try:
        _auto_research_persister.record_decision(run_id, decision_type, payload)
    except Exception as e:
        logger.warning("autoresearch decision ledger append failed for %s/%s: %s", run_id, decision_type, e)


def _compact_autoresearch_run_row(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    out = {
        "run_id": row.get("run_id"),
        "status": row.get("status"),
        "progress": row.get("progress"),
        "baseline_workflow_id": row.get("baseline_workflow_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "snapshot_source": row.get("snapshot_source"),
        "snapshot_path": row.get("snapshot_path"),
        "current_iteration": row.get("current_iteration"),
        "recoverable": row.get("recoverable"),
        "error": row.get("error"),
        "last_failed_trial": row.get("last_failed_trial"),
        "job_status": row.get("job_status"),
        "job_updated_at": row.get("job_updated_at"),
        "job": row.get("job"),
    }
    live = row.get("current_iteration_live") if isinstance(row.get("current_iteration_live"), dict) else {}
    live_summary = live.get("live_summary") if isinstance(live.get("live_summary"), dict) else None
    live_progress = live.get("progress") if isinstance(live.get("progress"), dict) else None
    compact_live: Dict[str, Any] = {}
    if live_summary:
        compact_live["live_summary"] = {
            k: live_summary.get(k)
            for k in (
                "windows_done",
                "windows_total",
                "current_window",
                "current_phase",
                "aggregate_baseline_score",
                "aggregate_challenger_score",
                "score_advantage",
                "windows_challenger_better",
                "windows_comparable",
            )
            if k in live_summary
        }
    if live_progress:
        compact_live["progress"] = {
            k: live_progress.get(k)
            for k in ("window_index", "window_total", "challenger_index", "challenger_total", "current_phase", "current_window")
            if k in live_progress
        }
    if compact_live:
        out["current_iteration_live"] = compact_live
    batch_status = row.get("batch_eval_status") if isinstance(row.get("batch_eval_status"), dict) else {}
    if batch_status:
        groups = []
        for group in batch_status.get("groups") or []:
            if not isinstance(group, dict):
                continue
            groups.append({
                "group_idx": group.get("group_idx"),
                "status": group.get("status"),
                "window_index": group.get("window_index"),
                "window_total": group.get("window_total"),
                "windows_done": group.get("windows_done"),
                "windows_total": group.get("windows_total"),
                "current_phase": group.get("current_phase"),
                "current_window": group.get("current_window"),
            })
        out["batch_eval_status"] = {
            "iteration": batch_status.get("iteration"),
            "running": batch_status.get("running"),
            "total_groups": batch_status.get("total_groups"),
            "groups": groups,
        }
    return {k: v for k, v in out.items() if v not in (None, {}, [])}


def _refresh_autoresearch_control_plane(
    run_id: str,
    state: Dict[str, Any],
    *,
    iteration: Optional[int] = None,
    batch_groups: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if not isinstance(state, dict):
        return
    try:
        groups = batch_groups if batch_groups is not None else state.get("latest_batch_groups") or []
        evidence_rows = _auto_research_evidence_builder.build_many_for_groups(run_id=run_id, groups=groups)
        scenario_fingerprint = _compute_scenario_fingerprint(state, windows=state.get("windows") or [])
        for row in evidence_rows:
            if isinstance(row, dict):
                row["scenario_fingerprint"] = scenario_fingerprint
        state.setdefault("evidence_records", [])
        if evidence_rows:
            existing_keys = {
                (
                    str(row.get("iteration")),
                    str(row.get("group_idx")),
                    str(row.get("patch_fingerprint")),
                )
                for row in state.get("evidence_records") or []
                if isinstance(row, dict)
            }
            for row in evidence_rows:
                key = (str(row.get("iteration")), str(row.get("group_idx")), str(row.get("patch_fingerprint")))
                if key not in existing_keys:
                    state["evidence_records"].append(row)
                    existing_keys.add(key)
            state["evidence_records"] = state["evidence_records"][-500:]
        state["evidence_summary"] = _auto_research_evidence_builder.summarize(state.get("evidence_records") or [])
        state["exploration_health"] = _sanitize_json_floats(
            _auto_research_candidate_planner.exploration_health(state, active_layers=state.get("active_layers") or [])
        )
        state["research_state"] = _derive_autoresearch_research_state(state)
        _ingest_autoresearch_evidence_to_knowledge(state.get("evidence_records") or [])
        state["knowledge_governance"] = _summarize_autoresearch_knowledge_governance(run_id, state)
    except Exception as e:
        logger.warning("autoresearch control plane refresh failed for %s: %s", run_id, e)


def _derive_autoresearch_research_state(state: Dict[str, Any]) -> Dict[str, Any]:
    status = str(state.get("status") or "").lower()
    if status == "interrupted":
        return {"state": "interrupted", "reason": "run_interrupted"}
    if status in {"failed", "cancelled"}:
        return {"state": "stalled", "reason": status}
    progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
    iteration = int(progress.get("iteration") or state.get("current_iteration") or 0)
    if iteration <= 1:
        return {"state": "warmup", "reason": "first_iteration_or_baseline"}
    summary = state.get("evidence_summary") if isinstance(state.get("evidence_summary"), dict) else {}
    by_strength = summary.get("by_strength") if isinstance(summary.get("by_strength"), dict) else {}
    if int(summary.get("needs_multi_window_confirmation") or 0) > 0:
        return {"state": "confirm", "reason": "single_window_positive_waiting_confirmation"}
    if int(by_strength.get("multi_window_confirmed") or 0) > 0:
        return {"state": "exploit", "reason": "multi_window_confirmed_evidence"}
    health = state.get("exploration_health") if isinstance(state.get("exploration_health"), dict) else {}
    if bool(health.get("parameter_overdominance")):
        return {"state": "shift_focus", "reason": "parameter_overdominance"}
    failed = len([
        row for row in state.get("latest_batch_groups") or []
        if isinstance(row, dict) and str(row.get("status") or "").lower() in {"failed", "error", "cancelled"}
    ])
    if failed >= 2:
        return {"state": "stalled", "reason": "multiple_group_failures"}
    return {"state": "explore", "reason": "default_exploration"}


def _ingest_autoresearch_evidence_to_knowledge(evidence_rows: List[Dict[str, Any]]) -> None:
    if not evidence_rows:
        return
    try:
        from services.knowledge_layer import KnowledgeLayer
        layer = KnowledgeLayer()
        for row in evidence_rows[-50:]:
            if isinstance(row, dict):
                layer.ingest_evidence(row)
    except Exception as e:
        logger.warning("autoresearch evidence knowledge ingest failed: %s", e)


def _summarize_autoresearch_knowledge_governance(run_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from services.knowledge_layer import KnowledgeLayer
        rows = KnowledgeLayer().get_injection_candidates(
            scenario_fingerprint=_compute_scenario_fingerprint(state, windows=state.get("windows") or []),
            min_confidence=0.0,
        )
    except Exception:
        rows = []
    counts: Dict[str, int] = {}
    for row in rows or []:
        status = str(row.get("status") or "candidate")
        counts[status] = counts.get(status, 0) + 1
    return {
        "run_id": run_id,
        "status_counts": counts,
        "injection_candidates": len(rows or []),
        "active_or_candidate": len([r for r in rows or [] if str(r.get("status") or "") in {"active", "candidate"}]),
    }


def _load_autoresearch_state_for_view(run_id: str) -> Tuple[Dict[str, Any], str]:
    job = _jq.get_job(run_id)
    disk_state = _auto_research_persister.load_snapshot(run_id)
    mem_state = _auto_research_store.get(run_id)
    # 运行中的 run 优先从内存读，避免磁盘 snapshot 延迟导致前端拿到旧数据
    if isinstance(mem_state, dict) and str(mem_state.get("status") or "").lower() == "running":
        state = dict(mem_state)
        state["snapshot_source"] = "memory"
    elif isinstance(job, dict) and isinstance(disk_state, dict):
        state = dict(disk_state)
        state["snapshot_source"] = "disk+job"
    elif isinstance(mem_state, dict):
        state = dict(mem_state)
        state["snapshot_source"] = "memory"
    else:
        loaded = _auto_research_persister.load_for_status(run_id, active_in_memory=False)
        if not isinstance(loaded, dict):
            raise HTTPException(status_code=404, detail=f"自动实验任务不存在: {run_id}")
        state = dict(loaded)
        state["snapshot_source"] = "disk"
    if isinstance(job, dict):
        job_view = dict(job)
        job_view.pop("payload", None)
        state["job"] = job_view
        state["job_status"] = job_view.get("status")
        if str(job_view.get("status") or "").lower() == "interrupted" and str(state.get("status") or "").lower() in ("running", "pending", "waiting_review", "cancelling"):
            state["status"] = "interrupted"
            state["recoverable"] = True
            state["error"] = state.get("error") or "AutoResearch worker 心跳超时或已中断"
    return state, str(state.get("snapshot_source") or "")


def _report_autoresearch_optuna_result(run_id: str, state: Dict[str, Any], candidate: Dict[str, Any]) -> None:
    trial_number = state.pop("_current_optuna_trial_number", None)
    if trial_number is None:
        return
    try:
        evaluation = candidate.get("evaluation") if isinstance(candidate.get("evaluation"), dict) else {}
        value = evaluation.get("mape_improvement")
        failed = str(candidate.get("status") or "").lower() != "success" or value is None
        _auto_research_optuna_sampler.report(
            run_id,
            int(trial_number),
            float(value) if value is not None else None,
            failed=failed,
        )
    except Exception as e:
        logger.warning("autoresearch optuna report failed for %s trial=%s: %s", run_id, trial_number, e)


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _maybe_apply_autoresearch_self_heal(
    state: Dict[str, Any],
    all_candidates: List[Dict[str, Any]],
    current_iteration: int,
) -> Optional[Dict[str, Any]]:
    return _auto_research_self_heal.maybe_apply(
        state=state,
        all_candidates=all_candidates,
        current_iteration=current_iteration,
    )


async def _run_autoresearch_task(
    run_id: str,
    baseline_workflow_id: str,
    windows: List[dict],
    evaluation_contract: Dict[str, Any],
    search_space: Dict[str, Any],
    max_iterations: int,
    top_k: int,
    policy: Dict[str, Any],
    compare_config: Dict[str, Any],
    cancel_event: threading.Event,
    start_iteration: int = 1,
    total_iterations: Optional[int] = None,
) -> None:
    state = _auto_research_store[run_id]
    state["status"] = "running"
    state["started_at"] = datetime.now().isoformat()
    # 从 compare_config 读取 force_activate，允许前端指定强制激活层
    state["force_activate"] = [
        str(x).strip() for x in (compare_config.get("force_activate") or []) if str(x).strip()
    ]
    _snapshot_autoresearch_state(run_id)
    anchor_evaluation_contract = dict(evaluation_contract or {})
    total_iterations = int(total_iterations or max_iterations)
    start_iteration = max(1, int(start_iteration or 1))

    def _log(message: str, log_type: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        logs = state.get("logs") or []
        logs.append({"timestamp": ts, "message": message, "type": log_type})
        state["logs"] = logs[-3000:]

    existing_iterations = state.get("iterations") if isinstance(state.get("iterations"), list) else []
    all_candidates: List[Dict[str, Any]] = [dict(x) for x in existing_iterations if isinstance(x, dict)]
    state["progress"] = {"iteration": max(0, start_iteration - 1), "total_iterations": int(total_iterations)}
    try:
        if total_iterations <= 0:
            raise ValueError("max_iterations 必须大于 0")
        if not windows:
            raise ValueError("windows 不能为空")
        if start_iteration > total_iterations:
            state["status"] = "success"
            state["finished_at"] = datetime.now().isoformat()
            _snapshot_autoresearch_state(run_id)
            return

        _log(
            f"自动实验启动：baseline={baseline_workflow_id}，iterations={total_iterations}，start_iteration={start_iteration}",
            "start",
        )
        _existing_profile = state.get("dataset_profile") if isinstance(state.get("dataset_profile"), dict) else {}
        _existing_tp = _existing_profile.get("train_profile") if isinstance(_existing_profile.get("train_profile"), dict) else {}
        _existing_pq = _existing_tp.get("profile_quality") if isinstance(_existing_tp.get("profile_quality"), dict) else {}
        if str(_existing_pq.get("source") or "") != "full_training_dataset":
            _boot_profile = _bootstrap_train_profile_at_run_start(
                baseline_workflow_id,
                windows,
                evaluation_contract,
            )
            if _boot_profile is not None:
                _boot_dict = _boot_profile.to_dict()
                state["train_profile"] = _boot_dict
                state["dataset_profile"] = {
                    "train_profile": _boot_dict,
                    "source": "full_training_dataset",
                    "created_at": datetime.now().isoformat(),
                }
                _pq = (_boot_dict.get("profile_quality") or {}) if isinstance(_boot_dict, dict) else {}
                _log(
                    "已加载完整训练集画像: source=full_training_dataset "
                    f"points={_pq.get('point_count')} days={_pq.get('source_days')}",
                    "info",
                )
        manual_gate = bool(compare_config.get("manual_gate", False))
        anchor_baseline_contract = bool(compare_config.get("anchor_baseline_contract", True))
        auto_full_automation = bool(compare_config.get("auto_full_automation", False))
        auto_generate_proposal = bool(compare_config.get("auto_generate_proposal", auto_full_automation))
        auto_apply_recommended = bool(compare_config.get("auto_apply_recommended", auto_full_automation))
        auto_apply_risk_level_max = str(compare_config.get("auto_apply_risk_level_max") or "medium").lower()
        state["glm_questioner_runtime"] = _glm_questioner_runtime_status()
        if not bool((state.get("glm_questioner_runtime") or {}).get("ready")):
            _log(
                "GLM Questioner 未就绪: "
                + str((state.get("glm_questioner_runtime") or {}).get("disabled_reason") or "unknown"),
                "warning",
            )
        try:
            auto_memory_top_k = max(1, min(8, int(compare_config.get("memory_top_k", 3))))
        except (TypeError, ValueError):
            auto_memory_top_k = 3
        for iteration in range(start_iteration, total_iterations + 1):
            if cancel_event.is_set():
                break
            state["progress"] = {"iteration": iteration, "total_iterations": int(total_iterations)}
            _snapshot_autoresearch_state(run_id)
            # 每轮开始时立即更新 iterations，让前端能看到进行中的状态
            if not state.get("iterations"):
                state["iterations"] = []

            # 任务 3.3：每轮开始时检测参数层是否饱和，饱和则自动引入结构搜索
            _sat_k = int(compare_config.get("saturation_k", 4))
            _sat_threshold = float(compare_config.get("saturation_threshold", 0.05))
            if (
                _is_parameter_saturated(state.get("iterations") or [], k=_sat_k, threshold=_sat_threshold)
                and state.get("phase") != "structure_exploration"
            ):
                state["phase"] = "structure_exploration"
                # 将 feature_recipe_id 加入当前 search_space（若未有）
                if "feature_recipe_id" not in search_space:
                    try:
                        rk = known_recipe_ids()
                        if rk:
                            search_space["feature_recipe_id"] = list(rk)[:3]
                    except Exception:
                        pass
                _log(
                    f"参数层已饱和（连续 {_sat_k} 轮改善 < {_sat_threshold}），开始引入结构搜索",
                    "warning",
                )

            runtime_patch = state.get("runtime_patch") or {}
            search_space_patch = runtime_patch.get("search_space_patch") or {}
            eval_patch = runtime_patch.get("evaluation_contract_patch") or {}
            structure_patch_runtime = dict(runtime_patch.get("structure_patch") or {})
            discovery_ctx = state.get("discovery_context") or {}
            preferred_raw = discovery_ctx.get("preferred_model_operator_ids") or []
            preferred_list: List[str] = []
            if isinstance(preferred_raw, list):
                preferred_list = [str(x).strip() for x in preferred_raw if str(x).strip()]
            model_focus_patch: Dict[str, Any] = (
                _build_model_focus_structure_patch(baseline_workflow_id, preferred_list) if preferred_list else {}
            )
            if model_focus_patch.get("node_switches"):
                _log(
                    f"第 {iteration} 轮：关注模型生效（合并结构补丁 node_switches={len(model_focus_patch.get('node_switches') or [])}）",
                    "info",
                )
            effective_search_space = dict(search_space or {})
            if isinstance(search_space_patch, dict):
                effective_search_space.update(search_space_patch)
            effective_contract = dict(evaluation_contract or {})
            if isinstance(eval_patch, dict):
                effective_contract.update(eval_patch)
            state["effective_search_space"] = _sanitize_json_floats(effective_search_space)
            state["effective_evaluation_contract"] = _sanitize_json_floats(effective_contract)

            # 任务 7.1 / 7.2：带历史先验的采样 + 失败模式回避集
            _mem_cases = _retrieve_memory_cases(
                baseline_workflow_id,
                state.get("scenario_tags") or [],
                limit=8,
                query_fingerprint=_compute_scenario_fingerprint(state, windows=windows),
            )
            # 回避集：历史失败（improved=False）且 mape_delta <= 0 的 override
            _avoid_set: List[Dict[str, Any]] = []
            for _mc in _mem_cases:
                _mc_out = _mc.get("outcome") or {}
                if not bool(_mc_out.get("improved")):
                    _bad_patch = (_mc.get("applied_patch") or {}).get("override") or {}
                    if isinstance(_bad_patch, dict) and _bad_patch:
                        _avoid_set.append({k: v for k, v in _bad_patch.items() if k in effective_search_space})
            state["avoid_set_size"] = len(_avoid_set)

            # 任务 9.5：注册表模式采样（有 registry_id 时替代旧逻辑）
            _batch_size = int(compare_config.get("batch_size", 1))
            _registry_id = str(state.get("registry_id") or "").strip()
            _registry_patches: Dict[str, Any] = {}
            _sampled_layers: List[str] = []
            _registry: Optional[Dict[str, Any]] = None
            _cur_diag: Dict[str, Any] = {}
            _early_slots: List[Dict[str, Any]] = []
            # v3 planner 启用条件：显式开关 OR 选中的 registry 本身带 actions 字段
            _v3_planner_enabled = bool(compare_config.get("v3_planner_enabled", False))
            _v3_plan_items: List[Dict[str, Any]] = []
            _v3_runtime_patches: List[Dict[str, Any]] = []
            if _registry_id:
                try:
                    from services.autoresearch_registry_service import (
                        load_registry as _load_registry,
                        get_active_layers as _get_active_layers,
                    )
                    _registry = _load_registry(_registry_id)
                    # 选中的 registry 自带 actions（如 load_forecast_v3）→ 自动启用 v3 planner
                    if isinstance((_registry or {}).get("actions"), list):
                        _v3_planner_enabled = True
                    # 显式开关启用但当前 registry 无 actions → 自动切到 v3 registry
                    elif _v3_planner_enabled:
                        _v3_registry_id = str(compare_config.get("v3_registry_id") or "load_forecast_v3").strip()
                        _v3_registry_candidate = _load_registry(_v3_registry_id)
                        if isinstance(_v3_registry_candidate.get("actions"), list):
                            _log(f"第 {iteration} 轮：v3 planner 启用，从 {_registry_id} 切换到 {_v3_registry_id}", "info")
                            _registry = _v3_registry_candidate
                    if _registry.get("registry_id") != "__empty__":
                        if _v3_planner_enabled and isinstance(_registry.get("actions"), list):
                            try:
                                _v3_plan_items, _v3_runtime_patches = _prepare_v3_autoresearch_plans(
                                    registry=_registry,
                                    state=state,
                                    baseline_workflow_id=baseline_workflow_id,
                                    batch_size=_batch_size,
                                )
                                if _v3_plan_items:
                                    _early_slots = [
                                        {
                                            "target_direction": ((p.get("action") or {}).get("target_direction")),
                                            "target_layer": ((p.get("action") or {}).get("target_layer")),
                                            "exploration_role": "v3_action",
                                            "planner_reason": p.get("reason"),
                                        }
                                        for p in _v3_plan_items
                                        if isinstance(p, dict)
                                    ]
                                    _log(
                                        f"第 {iteration} 轮：v3 planner 生成 {len(_v3_plan_items)} 个 action plans "
                                        f"actions={[p.get('action_id') for p in _v3_plan_items]}",
                                        "info",
                                    )
                            except Exception as _v3_plan_err:
                                _log(f"第 {iteration} 轮：v3 planner 失败，降级旧采样: {_v3_plan_err}", "warning")
                                _v3_plan_items = []
                                _v3_runtime_patches = []
                        _k_sat = int(compare_config.get("saturation_k", 4))
                        _t_sat = float(compare_config.get("saturation_threshold", 0.05))
                        _active_layers = _get_active_layers(_registry, state, k=_k_sat, threshold=_t_sat)
                        _forced_layers = [
                            str(x).strip()
                            for x in (state.get("force_activate") or [])
                            if str(x).strip()
                        ]
                        try:
                            _pre_health = _auto_research_candidate_planner.exploration_health(
                                state,
                                active_layers=_active_layers,
                            )
                            _recommended_direction = str(_pre_health.get("recommended_primary_direction") or "")
                            _recommended_layer = AutoResearchCandidatePlanner.DIRECTION_TO_LAYER.get(_recommended_direction)
                            if bool(_pre_health.get("parameter_overdominance")) and _recommended_layer:
                                _forced_layers.append(_recommended_layer)
                                state["layer_activation_adjustment"] = {
                                    "iteration": iteration,
                                    "reason": "parameter_overdominance",
                                    "recommended_direction": _recommended_direction,
                                    "forced_layer": _recommended_layer,
                                    "created_at": datetime.now().isoformat(),
                                }
                        except Exception as _layer_bias_err:
                            logger.warning("autoresearch layer de-bias check failed: %s", _layer_bias_err)
                        if _forced_layers:
                            _active_layers = list(dict.fromkeys(list(_active_layers) + _forced_layers))
                        _sampled_layers = list(_active_layers)
                        state["active_layers"] = _sampled_layers
                        # 获取当前诊断
                        _cur_diag = _compute_error_diagnosis(_build_autoresearch_report(state))
                        import random as _random_mod
                        _rng = _random_mod.Random(int(compare_config.get("seed", 20260428)) + iteration * 7919)
                        # 任务 29.3：首轮时注入历史 insight 推荐配置作为采样偏好
                        if iteration == 1:
                            try:
                                _cur_fp = _compute_scenario_fingerprint(state, windows=windows)
                                _similar = _match_similar_run_insights(_cur_fp, _registry_id, top_k=1)
                                if _similar:
                                    _rec = _similar[0].get("recommended_starting_config_for_similar") or {}
                                    if _rec:
                                        _rng._insight_prior = _rec
                                        _log(
                                            f"第 1 轮：注入历史 insight 推荐配置作为采样偏好: {_rec}",
                                            "info",
                                        )
                            except Exception as _insight_prior_err:
                                logger.warning("insight prior injection failed: %s", _insight_prior_err)

                        # ── Primary 聚焦策略：提前获取 planner 的第一个 slot，
                        # 让 primary 组只从 target_layer 采样，而不是全部 active_layers ──
                        _primary_target_layer = ""
                        if _v3_plan_items and _early_slots:
                            _primary_target_layer = str(_early_slots[0].get("target_layer") or "")
                        else:
                            try:
                                _early_slots = _auto_research_candidate_planner.build_slots(
                                    batch_size=_batch_size,
                                    iteration=iteration,
                                    run_state=state,
                                    active_layers=_active_layers,
                                )
                                if _early_slots:
                                    _primary_target_layer = str(_early_slots[0].get("target_layer") or "")
                            except Exception:
                                pass

                        # 确定 primary 组的采样层：如果 planner 有明确方向，只从该层采样；
                        # 否则回退到全部 active_layers（兼容旧行为）
                        _primary_sample_layers = _active_layers
                        if _primary_target_layer and _primary_target_layer in ((_registry.get("layers") or {}).keys()):
                            _primary_sample_layers = [_primary_target_layer]
                            _log(
                                f"第 {iteration} 轮：Primary 聚焦采样 target_layer={_primary_target_layer}",
                                "info",
                            )

                        _sample = _sample_from_registry(
                            _registry,
                            _primary_sample_layers,
                            diagnosis=_cur_diag,
                            memory_cases=_mem_cases,
                            avoid_set=_avoid_set,
                            rng=_rng,
                            # 任务 30：从 runtime_patch 构造已锁定参数集合
                            locked_params=_build_locked_params_from_runtime_patch(
                                state.get("runtime_patch") or {}
                            ),
                            research_focus=state.get("current_research_focus") or None,
                        )
                        _registry_patches = _sample_to_patches(
                            _sample,
                            _registry,
                            workflow_id=baseline_workflow_id,
                        )
                        if _v3_runtime_patches:
                            _registry_patches = dict(_v3_runtime_patches[0])
                            _sampled_layers = list(dict.fromkeys([
                                str(((p.get("action") or {}).get("target_layer") or "")).strip()
                                for p in _v3_plan_items
                                if isinstance(p, dict) and str(((p.get("action") or {}).get("target_layer") or "")).strip()
                            ]))
                            state["active_layers"] = _sampled_layers
                        state["_current_sampled_layers"] = _sampled_layers
                        _log(
                            f"第 {iteration} 轮：注册表采样 registry={_registry_id} "
                            f"active_layers={_active_layers} sample_keys={list(_sample.keys())}",
                            "info",
                        )
                except Exception as _reg_err:
                    _log(f"第 {iteration} 轮：注册表采样失败（降级为旧逻辑）: {_reg_err}", "warning")
                    _registry_patches = {}
                    _sampled_layers = []
            else:
                state["_current_sampled_layers"] = []

            if _registry_patches:
                # 注册表模式：用注册表产出的 patches 替代旧采样
                override = dict(_registry_patches.get("global_config_patch") or {})
                override_full = dict(override)
                override_body = dict(override)
                # 注册表的 node_param_patches 和 structure_patch 合并到后续流程
                _reg_npp = list(_registry_patches.get("node_param_patches") or [])
                _reg_sp = dict(_registry_patches.get("structure_patch") or {})
                _reg_model_focus = list(_registry_patches.get("model_focus") or [])

                # ── Primary 组聚焦策略：限制同时变更的参数数量 ──
                # 当 primary 组从多层采样时，参数过多会导致无法归因。
                # 策略：保留最多 max_primary_override_keys 个 override key，
                # 最多 max_primary_node_patches 个 node_param_patches。
                _max_primary_override_keys = int(compare_config.get("max_primary_override_keys", 3))
                _max_primary_node_patches = int(compare_config.get("max_primary_node_patches", 3))

                # 限制 override keys（保留诊断权重最高的或随机选取）
                _override_keys_to_keep = list(override.keys())
                if len(_override_keys_to_keep) > _max_primary_override_keys:
                    # 优先保留 ensemble_mode（模型方向核心参数）
                    _priority_keys = [k for k in _override_keys_to_keep if k in ("ensemble_mode", "train_days", "daily_horizon")]
                    _other_keys = [k for k in _override_keys_to_keep if k not in _priority_keys]
                    import random as _trim_random
                    _trim_rng = _trim_random.Random(int(compare_config.get("seed", 20260428)) + iteration * 3571)
                    _trim_rng.shuffle(_other_keys)
                    _kept = (_priority_keys + _other_keys)[:_max_primary_override_keys]
                    _removed = [k for k in _override_keys_to_keep if k not in _kept]
                    for _rk in _removed:
                        override.pop(_rk, None)
                    override_full = dict(override)
                    override_body = dict(override)
                    if _removed:
                        _log(
                            f"第 {iteration} 轮：Primary 聚焦策略裁剪 override "
                            f"保留={_kept} 移除={_removed}",
                            "info",
                        )

                # 限制 node_param_patches 数量
                if len(_reg_npp) > _max_primary_node_patches:
                    # 优先保留 ensemble_forecast（集成方向）和 sliding_window（数据方向）
                    _npp_priority = [p for p in _reg_npp if p.get("functionId") in ("ensemble_forecast", "sliding_window")]
                    _npp_other = [p for p in _reg_npp if p.get("functionId") not in ("ensemble_forecast", "sliding_window")]
                    _reg_npp = (_npp_priority + _npp_other)[:_max_primary_node_patches]
                    _log(
                        f"第 {iteration} 轮：Primary 聚焦策略裁剪 node_param_patches "
                        f"保留={[p.get('functionId') for p in _reg_npp]}",
                        "info",
                    )
                # ensemble_mode 联动
                _ensemble_mode = str(override.get("ensemble_mode") or "").strip()
                if _ensemble_mode and _ensemble_mode != "single_best":
                    _em_patches = _build_ensemble_mode_patches(
                        baseline_workflow_id,
                        _ensemble_mode,
                        active_models=_reg_model_focus or None,
                        weight_strategy="oof_rmse_inverse",
                    )
                    _reg_sp = _merge_structure_patch_bundle(_reg_sp, _em_patches.get("structure_patch") or {})
                    _reg_npp = _reg_npp + list(_em_patches.get("node_param_patches") or [])
                    override.pop("ensemble_mode", None)
                    override_full.pop("ensemble_mode", None)
                    override_body.pop("ensemble_mode", None)
            else:
                # 旧逻辑
                _sampler_backend = str(compare_config.get("sampler_backend") or "").strip().lower()
                state.pop("_current_optuna_trial_number", None)
                if _sampler_backend == "optuna":
                    try:
                        _optuna_suggestion = _auto_research_optuna_sampler.suggest(
                            run_id,
                            effective_search_space,
                            seed=int(compare_config.get("seed", 20260428)),
                        )
                        override = dict(_optuna_suggestion.params or {})
                        state["_current_optuna_trial_number"] = int(_optuna_suggestion.trial_number)
                        state["_current_sampler_backend"] = "optuna"
                        _log(
                            f"第 {iteration} 轮：Optuna sampler 生成候选 trial={_optuna_suggestion.trial_number}",
                            "info",
                        )
                    except Exception as _optuna_err:
                        _log(f"第 {iteration} 轮：Optuna sampler 失败，降级为 memory-random: {_optuna_err}", "warning")
                        override = _sample_override_with_memory_prior(
                            effective_search_space,
                            iteration=iteration,
                            seed=int(compare_config.get("seed", 20260428)),
                            memory_cases=_mem_cases,
                            avoid_set=_avoid_set,
                            prior_weight=float(compare_config.get("memory_prior_weight", 0.4)),
                        )
                        state["_current_sampler_backend"] = "memory_random"
                else:
                    override = _sample_override_with_memory_prior(
                        effective_search_space,
                        iteration=iteration,
                        seed=int(compare_config.get("seed", 20260428)),
                        memory_cases=_mem_cases,
                        avoid_set=_avoid_set,
                        prior_weight=float(compare_config.get("memory_prior_weight", 0.4)),
                    )
                    state["_current_sampler_backend"] = "memory_random"
                _reg_npp = []
                _reg_sp = {}
                _reg_model_focus = []

            if not (_reg_npp or _reg_sp or _reg_model_focus):
                override = _force_override_diff_from_contract(
                    override=override,
                    search_space=effective_search_space,
                    contract=effective_contract,
                    iteration=iteration,
                    seed=int(compare_config.get("seed", 20260428)),
                    # 任务 31.1：传入注册表，从选项中重新选值
                    registry=_registry if _registry_id else None,
                )
            override_full = dict(override or {})
            sampled_rid_str = str(override_full.get("feature_recipe_id") or "").strip()
            override_body = dict(override_full)
            for mk in _AUTORESEARCH_META_OVERRIDE_KEYS:
                override_body.pop(mk, None)

            rp_fixed = str(runtime_patch.get("feature_recipe_id") or "").strip()
            recipe_patch: Dict[str, Any] = {}
            chosen_rid = rp_fixed or sampled_rid_str
            if chosen_rid:
                recipe_patch = resolve_recipe_structure_patch(
                    baseline_workflow_id, chosen_rid, load_workflow_from_file
                ) or {}
                _log(f"第 {iteration} 轮：特征配方生效 recipe={chosen_rid}", "info")

            merged_mid = _merge_structure_patches(model_focus_patch, recipe_patch)
            # 注册表模式：合并注册表产出的 structure_patch
            if _reg_sp:
                # Primary 聚焦策略：限制 node_switches 数量，避免同时开关太多节点
                _max_primary_switches = int(compare_config.get("max_primary_node_switches", 3))
                _sp_switches = _reg_sp.get("node_switches") or []
                if isinstance(_sp_switches, list) and len(_sp_switches) > _max_primary_switches:
                    # 只保留前 N 个开关变更
                    _reg_sp["node_switches"] = _sp_switches[:_max_primary_switches]
                merged_mid = _merge_structure_patch_bundle(merged_mid, _reg_sp)
            structure_patch = _merge_structure_patch_bundle(merged_mid, structure_patch_runtime)
            state["effective_structure_patch"] = _sanitize_json_floats(structure_patch)

            rgc = dict(runtime_patch.get("global_config_patch") or {})
            rnpp_raw = runtime_patch.get("node_param_patches")
            rnpp = list(rnpp_raw) if isinstance(rnpp_raw, list) else []
            # 注册表模式：合并注册表产出的 node_param_patches
            if _reg_npp:
                rnpp = rnpp + _reg_npp
            state["effective_parameter_patch"] = _sanitize_json_floats({
                "global_config_patch": rgc,
                "node_param_patches": rnpp,
            })

            _log(f"第 {iteration}/{max_iterations} 轮：覆盖参数 {override_full}", "info")

            # 任务 27.4：对照组机制——每 N 轮强制跑一次空覆盖回测
            _control_interval = int(compare_config.get("control_group_interval", 5))
            _is_control_round = (iteration % _control_interval == 0) and iteration > 0
            if _is_control_round:
                override_full = {}
                override_body = {}
                _log(f"第 {iteration} 轮：对照组回测（空覆盖，验证基线稳定性）", "info")
            state["current_iteration"] = iteration
            state["current_override"] = _sanitize_json_floats(dict(override_full))
            state["current_iteration_live"] = {
                "progress": {"window_index": 0, "window_total": len(windows or [])},
                "live_summary": {
                    "windows_done": 0,
                    "windows_total": len(windows or []),
                    "current_phase": "preparing",
                    "current_window": "",
                },
                "live_window_results": [],
            }
            _snapshot_autoresearch_state(run_id)

            # 默认锚定 baseline 合同参数，保证 baseline 作为固定参照。
            # challenger 在该锚点之上叠加"运行时 contract 变化 + 本轮 sampled override"。
            # 只允许模型参数相关的 key 进入 challenger override；backtest_train_days 等评估配置
            # 不应污染各方向的 override。
            _CONTRACT_DELTA_OVERRIDE_KEYS = {"train_days", "auto_tune_n_trials", "cv_folds"}
            baseline_contract_for_iter = anchor_evaluation_contract if anchor_baseline_contract else effective_contract
            challenger_contract_delta: Dict[str, Any] = {}
            for kk, vv in effective_contract.items():
                if kk not in _CONTRACT_DELTA_OVERRIDE_KEYS:
                    continue
                if anchor_evaluation_contract.get(kk) != vv:
                    challenger_contract_delta[kk] = vv
            challenger_override_for_iter = dict(challenger_contract_delta)
            challenger_override_for_iter.update(dict(override_body))
            baseline_cache_key = _baseline_cache_key(
                baseline_workflow_id,
                windows,
                baseline_contract_for_iter,
            )

            comparison_id = f"cmp-{uuid.uuid4().hex[:12]}"
            _init_comparison_state(comparison_id)
            _comparison_store[comparison_id]["source_autoresearch_run_id"] = run_id
            _comparison_store[comparison_id]["source_iteration"] = iteration
            _comparison_store[comparison_id]["source_structure_patch"] = _sanitize_json_floats(structure_patch)
            _comparison_store[comparison_id]["source_global_config_patch"] = _sanitize_json_floats(rgc)
            _comparison_store[comparison_id]["source_node_param_patches"] = _sanitize_json_floats(rnpp)
            # 让自动实验的 cancel 能直接中断当前 compare 子任务
            _comparison_cancel_events[comparison_id] = cancel_event
            # Baseline 结果缓存：anchor_baseline_contract=True 时 Baseline 每轮完全相同，
            # 第 1 轮跑完后缓存到 state["_baseline_cache"]，后续轮次直接注入，跳过 Baseline 回测。
            if anchor_baseline_contract and state.get("_baseline_cache"):
                _cache_ok, _cache_reason, _cache_age = _baseline_cache_is_valid(state, baseline_cache_key)
                if _cache_ok:
                    _comparison_store[comparison_id]["_cached_baseline_results"] = state["_baseline_cache"]
                    _comparison_store[comparison_id]["_cached_baseline_metadata"] = {
                        "cache_key": baseline_cache_key,
                        "cache_age_seconds": round(_cache_age, 3),
                        "cache_hit": True,
                    }
                    _log(f"第 {iteration} 轮：复用 Baseline 缓存（key={baseline_cache_key}，age={_cache_age/3600:.1f}h，跳过回测）", "info")
                else:
                    _log(f"第 {iteration} 轮：Baseline 缓存失效（reason={_cache_reason}，age={_cache_age/3600:.1f}h），重新运行", "info")
                    state.pop("_baseline_cache", None)
                    state.pop("_baseline_cache_ts", None)
                    state.pop("_baseline_cache_key", None)
                    state.pop("_baseline_cache_metadata", None)


            _is_baseline_warmup_phase = False  # 标记当前是否在 Baseline 缓存建立阶段

            def _on_compare_live(payload: Dict[str, Any]) -> None:
                live_data = _sanitize_json_floats(dict(payload or {}))
                # Baseline 缓存阶段：标记 phase 并清除 challenger 数值
                if _is_baseline_warmup_phase:
                    live_summary = live_data.get("live_summary")
                    if isinstance(live_summary, dict):
                        live_summary["current_phase"] = "baseline_warmup"
                        live_summary.pop("aggregate_challenger_score", None)
                        live_summary.pop("score_advantage", None)
                    # 清除 window_results 里的 challenger_score
                    win_results = live_data.get("live_window_results")
                    if isinstance(win_results, list):
                        for wr in win_results:
                            if isinstance(wr, dict):
                                wr.pop("challenger_score", None)
                state["current_iteration_live"] = live_data
                state["current_comparison_id"] = comparison_id
                now = time.time()
                last_snapshot_ts = float(state.get("_last_live_snapshot_ts") or 0)
                if now - last_snapshot_ts >= 1.5:
                    state["_last_live_snapshot_ts"] = now
                    _snapshot_autoresearch_state(run_id)

            _batch_size = int(compare_config.get("batch_size", 1))
            base_for_iter = baseline_wf_id = baseline_workflow_id
            _batch_group_records: List[Dict[str, Any]] = []

            if _batch_size > 1 and not _is_control_round:
                # ── 真正的并发模式：先跑 Baseline，再 N 组 Challenger 并发 ──────────
                if anchor_baseline_contract and not state.get("_baseline_cache"):
                    state["_baseline_cache_ts"] = time.time()
                    state["_baseline_cache_key"] = baseline_cache_key
                    state["_baseline_cache_metadata"] = {
                        "cache_key": baseline_cache_key,
                        "windows": windows,
                        "baseline_contract": baseline_contract_for_iter,
                        "created_iteration": iteration,
                    }
                    state["current_iteration_live"] = {
                        "progress": {"window_index": 0, "window_total": len(windows or [])},
                        "live_summary": {
                            "windows_done": 0,
                            "windows_total": len(windows or []),
                            "current_phase": "baseline_warmup",
                            "current_window": "正在建立 Baseline 缓存",
                        },
                        "live_window_results": [],
                    }
                    _snapshot_autoresearch_state(run_id)
                    _log(f"第 {iteration} 轮（批量模式）：先跑 Baseline 建立缓存…", "info")
                    _is_baseline_warmup_phase = True
                    _baseline_cmp_id = f"cmp-baseline-{uuid.uuid4().hex[:10]}"
                    _init_comparison_state(_baseline_cmp_id)
                    _comparison_store[_baseline_cmp_id]["source_autoresearch_run_id"] = run_id
                    _comparison_cancel_events[_baseline_cmp_id] = cancel_event
                    await _run_compare_backtest_batch_task(
                        comparison_id=_baseline_cmp_id,
                        baseline_workflow_id=base_for_iter,
                        challenger_workflow_ids=[base_for_iter],
                        windows=windows,
                        evaluation_contract=effective_contract,
                        score_margin=0.0,
                        add_to_candidate_pool=False,
                        cancel_event=cancel_event,
                        aggregate_method=str(compare_config.get("aggregate_method", "mean")),
                        challenger_config_override={},
                        baseline_config_override=baseline_contract_for_iter if anchor_baseline_contract else None,
                        live_update_hook=_on_compare_live,
                    )
                    _cmp_for_cache = _comparison_store.get(_baseline_cmp_id) or {}
                    _cached_wr = _cmp_for_cache.get("window_results")
                    if isinstance(_cached_wr, list) and _cached_wr:
                        _cache_dict = {}
                        for _wr in _cached_wr:
                            if not isinstance(_wr, dict):
                                continue
                            _sd = str(_wr.get("start_date") or "")
                            _ed = str(_wr.get("end_date") or "")
                            if _sd and _ed:
                                _b_data = _wr.get("baseline") or {}
                                _cache_dict[f"{_sd}~{_ed}"] = {
                                    "avg_metrics": _b_data.get("avg_metrics"),
                                    "candidate_score": _b_data.get("candidate_score"),
                                    "success_days": _b_data.get("success_days"),
                                    "failed_days": _b_data.get("failed_days"),
                                    "skipped_days": _b_data.get("skipped_days"),
                                    "total_duration": _b_data.get("total_duration"),
                                    "error": _b_data.get("error"),
                                }
                        state["_baseline_cache"] = _cache_dict
                        state["_baseline_cache_key"] = baseline_cache_key
                        _log(f"第 {iteration} 轮：Baseline 缓存建立（key={baseline_cache_key}，{len(_cached_wr)} 个窗口）", "info")
                    _is_baseline_warmup_phase = False

                _primary_proposal_id = str(state.get("last_applied_proposal_id") or "")
                _primary_proposal = _auto_research_proposals_store.get(_primary_proposal_id) if _primary_proposal_id else None
                if not isinstance(_primary_proposal, dict):
                    _primary_proposal = state.get("last_applied_proposal") if isinstance(state.get("last_applied_proposal"), dict) else {}
                _primary_hypothesis_type = str(
                    (_primary_proposal or {}).get("hypothesis_type")
                    or _infer_hypothesis_type_from_patch(
                        override=challenger_override_for_iter,
                        structure_patch=structure_patch,
                        node_param_patches=rnpp,
                        global_config_patch=rgc,
                    )
                )
                _all_overrides = [challenger_override_for_iter]
                _all_group_specs: List[Dict[str, Any]] = [{
                    "candidate_source": "primary",
                    "proposal_id": _primary_proposal_id or None,
                    "hypothesis": (_primary_proposal or {}).get("hypothesis"),
                    "hypothesis_type": _primary_hypothesis_type,
                    "primary_variable": (_primary_proposal or {}).get("primary_variable"),
                    "selected_layer": _layer_from_hypothesis_type(_primary_hypothesis_type),
                    "structure_patch": structure_patch,
                    "global_config_patch": rgc,
                    "node_param_patches": rnpp,
                }]
                if _v3_plan_items:
                    _v3_primary_plan = _v3_plan_items[0]
                    _v3_primary_action = (
                        _v3_primary_plan.get("action")
                        if isinstance(_v3_primary_plan.get("action"), dict)
                        else {}
                    )
                    _all_group_specs[0].update({
                        "candidate_source": "v3_action",
                        "action_id": _v3_primary_plan.get("action_id"),
                        "v3_plan_item": _v3_primary_plan,
                        "patch_fingerprint": _v3_primary_plan.get("patch_fingerprint"),
                        "hypothesis": _v3_primary_action.get("description"),
                        "hypothesis_type": _v3_primary_action.get("target_direction") or _primary_hypothesis_type,
                        "selected_layer": _v3_primary_action.get("target_layer"),
                        "target_direction": _v3_primary_action.get("target_direction"),
                        "target_layer": _v3_primary_action.get("target_layer"),
                        "exploration_role": "v3_action",
                        "planner_reason": _v3_primary_plan.get("reason"),
                        "variant_index": _v3_primary_plan.get("variant_index"),
                    })
                _planner_slots = _early_slots if _early_slots else _auto_research_candidate_planner.build_slots(
                    batch_size=_batch_size,
                    iteration=iteration,
                    run_state=state,
                    active_layers=state.get("active_layers") or [],
                )
                if _planner_slots:
                    _all_group_specs[0].update({
                        "target_direction": _planner_slots[0].get("target_direction"),
                        "target_layer": _planner_slots[0].get("target_layer"),
                        "exploration_role": _planner_slots[0].get("exploration_role"),
                        "planner_reason": _planner_slots[0].get("planner_reason"),
                    })
                    state["candidate_planner_slots"] = _sanitize_json_floats(_planner_slots)
                    state["candidate_planner_scoreboard"] = _sanitize_json_floats(
                        _auto_research_candidate_planner.build_scoreboard(state)
                    )
                    _log(
                        f"第 {iteration} 轮：候选规划器生成 {_batch_size} 个槽位 "
                        f"directions={[s.get('target_direction') for s in _planner_slots]}",
                        "info",
                    )
                _seen_override_keys: Set[str] = {_canonical_json_key(challenger_override_for_iter)}
                _glm_alt_overrides: List[Dict[str, Any]] = []
                _glm_alt_specs: List[Dict[str, Any]] = []
                _last_proposals = state.get("_last_glm_proposals") or []
                _last_recommended_id = str((state.get("latest_auto_proposal") or {}).get("recommended_proposal_id") or "")
                for _prop in _last_proposals:
                    if not isinstance(_prop, dict):
                        continue
                    if str(_prop.get("_source") or "") != "glm":
                        continue
                    _prop_id = str(_prop.get("proposal_id") or "")
                    if _prop_id == _last_recommended_id or not bool((_prop.get("validation") or {}).get("valid")):
                        continue
                    _alt_ov = dict(challenger_contract_delta)
                    _alt_ov.update(_sample_override_from_search_space_patch(
                        _prop.get("search_space_patch") if isinstance(_prop.get("search_space_patch"), dict) else {},
                        iteration=iteration * 1000 + len(_glm_alt_overrides),
                        seed=int(compare_config.get("seed", 20260428)),
                    ))
                    _alt_ov.update(dict(_prop.get("evaluation_contract_patch") or {}))
                    _alt_key = _canonical_json_key(_alt_ov)
                    if _alt_key in _seen_override_keys:
                        continue
                    _alt_hypothesis_type = str(
                        _prop.get("hypothesis_type")
                        or _infer_hypothesis_type_from_patch(
                            override=_alt_ov,
                            structure_patch=_prop.get("structure_patch") if isinstance(_prop.get("structure_patch"), dict) else {},
                            node_param_patches=_prop.get("node_param_patches") if isinstance(_prop.get("node_param_patches"), list) else [],
                            global_config_patch=_prop.get("global_config_patch") if isinstance(_prop.get("global_config_patch"), dict) else {},
                        )
                    )
                    _glm_alt_overrides.append(_alt_ov)
                    _glm_alt_specs.append({
                        "candidate_source": "glm",
                        "proposal_id": _prop_id or None,
                        "hypothesis": _prop.get("hypothesis"),
                        "hypothesis_type": _alt_hypothesis_type,
                        "primary_variable": _prop.get("primary_variable"),
                        "selected_layer": _layer_from_hypothesis_type(_alt_hypothesis_type),
                        "structure_patch": dict(_prop.get("structure_patch") or {}),
                        "global_config_patch": dict(_prop.get("global_config_patch") or {}),
                        "node_param_patches": list(_prop.get("node_param_patches") or []),
                    })
                    _seen_override_keys.add(_alt_key)

                _used_glm_alt_indices: Set[int] = set()
                for _bi in range(1, _batch_size):
                    _slot = _planner_slots[_bi] if _bi < len(_planner_slots) else {}
                    _target_direction = str(_slot.get("target_direction") or "").strip()
                    _target_layer = str(_slot.get("target_layer") or "").strip()
                    if _v3_runtime_patches and _bi < len(_v3_runtime_patches) and _bi < len(_v3_plan_items):
                        _b_group_spec, _b_challenger_override = _build_v3_group_spec(
                            plan=_v3_plan_items[_bi],
                            runtime_patch=_v3_runtime_patches[_bi],
                            baseline_workflow_id=baseline_workflow_id,
                            challenger_contract_delta=challenger_contract_delta,
                            slot=_slot,
                        )
                        _seen_override_keys.add(_canonical_json_key(_b_challenger_override))
                        _all_overrides.append(_b_challenger_override)
                        _all_group_specs.append(_b_group_spec)
                        _log(
                            f"第 {iteration} 轮：组 {_bi + 1} 使用 v3 action "
                            f"action_id={_b_group_spec.get('action_id')} variant={_b_group_spec.get('variant_index')}",
                            "info",
                        )
                        continue
                    _matched_glm_idx: Optional[int] = None
                    for _gi, _glm_spec in enumerate(_glm_alt_specs):
                        if _gi in _used_glm_alt_indices:
                            continue
                        _glm_direction = _auto_research_candidate_planner.direction_for_layer(
                            _glm_spec.get("selected_layer") or _glm_spec.get("hypothesis_type")
                        )
                        if _target_direction and _glm_direction == _target_direction:
                            _matched_glm_idx = _gi
                            break
                    if _matched_glm_idx is not None:
                        _used_glm_alt_indices.add(_matched_glm_idx)
                        _b_challenger_override = _glm_alt_overrides[_matched_glm_idx]
                        _b_group_spec = dict(_glm_alt_specs[_matched_glm_idx])
                        _b_group_spec.update({
                            "candidate_source": "glm",
                            "target_direction": _target_direction,
                            "target_layer": _target_layer,
                            "exploration_role": _slot.get("exploration_role"),
                            "planner_reason": _slot.get("planner_reason"),
                        })
                        _log(
                            f"第 {iteration} 轮：组 {_bi + 1} 使用方向匹配 GLM 候选 "
                            f"direction={_target_direction}",
                            "info",
                        )
                    else:
                        _b_ov = None
                        _b_ov_candidate: Dict[str, Any] = {}
                        _b_structure_patch: Dict[str, Any] = {}
                        _b_global_patch: Dict[str, Any] = {}
                        _b_node_patches: List[Dict[str, Any]] = []
                        for _retry in range(5):
                            if _registry_id and isinstance(locals().get("_registry"), dict) and _registry.get("registry_id") != "__empty__" and _target_layer:
                                import random as _planner_random
                                _planner_rng = _planner_random.Random(
                                    int(compare_config.get("seed", 20260428)) + iteration * 7919 + _bi * 9973 + _retry * 131
                                )
                                _target_layers = [_target_layer] if _target_layer in ((_registry.get("layers") or {}).keys()) else list(state.get("active_layers") or [])
                                _target_sample = _sample_from_registry(
                                    _registry,
                                    _target_layers,
                                    diagnosis=_cur_diag,
                                    memory_cases=_mem_cases,
                                    avoid_set=_avoid_set,
                                    rng=_planner_rng,
                                    locked_params=_build_locked_params_from_runtime_patch(
                                        state.get("runtime_patch") or {}
                                    ),
                                    research_focus=state.get("current_research_focus") or None,
                                )
                                _target_patches = _sample_to_patches(
                                    _target_sample,
                                    _registry,
                                    workflow_id=baseline_workflow_id,
                                )
                                _b_ov_candidate = dict(_target_patches.get("global_config_patch") or {})
                                _b_structure_patch = dict(_target_patches.get("structure_patch") or {})
                                _b_global_patch = dict(_target_patches.get("global_config_patch") or {})
                                _b_node_patches = list(_target_patches.get("node_param_patches") or [])
                                # B1: 非 parameter 方向不应携带 train_days 等训练参数
                                if _target_direction and _target_direction != "parameter":
                                    for _td_key in ("train_days", "backtest_train_days"):
                                        _b_ov_candidate.pop(_td_key, None)
                                        _b_global_patch.pop(_td_key, None)
                                # B2: feature 方向限制每次最多 2 个节点参数变更
                                if _target_direction == "feature" and len(_b_node_patches) > 2:
                                    _b_node_patches = _b_node_patches[:2]
                            else:
                                _b_ov_candidate = _sample_override_with_memory_prior(
                                    effective_search_space,
                                    iteration=iteration * 10000 + _bi * 1000 + _retry * 37,
                                    seed=int(compare_config.get("seed", 20260428)) + iteration * 7919 + _bi * 9973 + _retry * 131,
                                    memory_cases=_mem_cases,
                                    avoid_set=_avoid_set,
                                    prior_weight=float(compare_config.get("memory_prior_weight", 0.4)),
                                )
                            # B1: 非 parameter 方向跳过 force diff（已有结构/节点差异足够）
                            # B1: 非 registry 路径也同样剔除 train_days
                            if _target_direction and _target_direction != "parameter":
                                for _td_key in ("train_days", "backtest_train_days"):
                                    _b_ov_candidate.pop(_td_key, None)
                            _needs_force_diff = not (_b_node_patches or _b_structure_patch)
                            if _needs_force_diff and _target_direction and _target_direction != "parameter":
                                _needs_force_diff = False
                            if _needs_force_diff:
                                _b_ov_candidate = _force_override_diff_from_contract(
                                    override=_b_ov_candidate,
                                    search_space=effective_search_space,
                                    contract=effective_contract,
                                    iteration=iteration * 10000 + _bi * 1000 + _retry * 37,
                                    seed=int(compare_config.get("seed", 20260428)) + iteration * 7919 + _bi * 9973 + _retry * 131,
                                    registry=_registry if _registry_id else None,
                                )
                            _ov_key = _canonical_json_key(_b_ov_candidate)
                            if _ov_key not in _seen_override_keys:
                                _b_ov = _b_ov_candidate
                                _seen_override_keys.add(_ov_key)
                                break
                        if _b_ov is None:
                            _log(f"第 {iteration} 轮：组 {_bi + 1} 采样去重困难，使用最后一次采样结果", "warning")
                            _b_ov = _b_ov_candidate
                        _b_challenger_override = dict(challenger_contract_delta)
                        _b_challenger_override.update(dict(_b_ov))
                        _fallback_hypothesis_type = _infer_hypothesis_type_from_patch(
                            override=_b_challenger_override,
                            structure_patch=_b_structure_patch,
                            node_param_patches=_b_node_patches,
                            global_config_patch=_b_global_patch,
                        )
                        _b_group_spec = {
                            "candidate_source": "registry_targeted" if _registry_id and _target_layer else "memory_random",
                            "proposal_id": None,
                            "hypothesis": None,
                            "hypothesis_type": _fallback_hypothesis_type,
                            "primary_variable": _infer_primary_variable({
                                "search_space_patch": _b_challenger_override,
                                "evaluation_contract_patch": {},
                                "structure_patch": _b_structure_patch,
                                "global_config_patch": _b_global_patch,
                                "node_param_patches": _b_node_patches,
                            }),
                            "selected_layer": _target_layer or _layer_from_hypothesis_type(_fallback_hypothesis_type),
                            "target_direction": _target_direction,
                            "target_layer": _target_layer,
                            "exploration_role": _slot.get("exploration_role"),
                            "planner_reason": _slot.get("planner_reason"),
                            "structure_patch": _b_structure_patch,
                            "global_config_patch": _b_global_patch,
                            "node_param_patches": _b_node_patches,
                        }
                    _all_overrides.append(_b_challenger_override)
                    _all_group_specs.append(_b_group_spec)

                _all_cmp_ids = [(comparison_id, _all_overrides[0])]
                for _b_ov in _all_overrides[1:]:
                    _b_cmp_id = f"cmp-batch-{uuid.uuid4().hex[:10]}"
                    _init_comparison_state(_b_cmp_id)
                    _comparison_store[_b_cmp_id]["_cached_baseline_results"] = state.get("_baseline_cache") or {}
                    _comparison_store[_b_cmp_id]["_cached_baseline_metadata"] = state.get("_baseline_cache_metadata") or {}
                    _comparison_cancel_events[_b_cmp_id] = cancel_event
                    _all_cmp_ids.append((_b_cmp_id, _b_ov))
                for _gi, (_cid, _) in enumerate(_all_cmp_ids):
                    _spec = _all_group_specs[_gi] if _gi < len(_all_group_specs) else {}
                    _comparison_store[_cid]["source_autoresearch_run_id"] = run_id
                    _comparison_store[_cid]["source_iteration"] = iteration
                    _comparison_store[_cid]["source_candidate_source"] = _spec.get("candidate_source")
                    _comparison_store[_cid]["source_hypothesis"] = _spec.get("hypothesis")
                    _comparison_store[_cid]["source_hypothesis_type"] = _spec.get("hypothesis_type")
                    _comparison_store[_cid]["source_structure_patch"] = _sanitize_json_floats(dict(_spec.get("structure_patch") or {}))
                    _comparison_store[_cid]["source_global_config_patch"] = _sanitize_json_floats(dict(_spec.get("global_config_patch") or {}))
                    _comparison_store[_cid]["source_node_param_patches"] = _sanitize_json_floats(list(_spec.get("node_param_patches") or []))
                _comparison_store[comparison_id]["_cached_baseline_results"] = state.get("_baseline_cache") or {}
                _comparison_store[comparison_id]["_cached_baseline_metadata"] = state.get("_baseline_cache_metadata") or {}

                state["batch_eval_status"] = {
                    "iteration": iteration,
                    "total_groups": _batch_size,
                    "running": True,
                    "groups": [
                        {
                            "group_idx": i,
                            "comparison_id": cid,
                            "status": "pending",
                            "override": _sanitize_json_floats(dict(bov)),
                            "candidate_source": (_all_group_specs[i] if i < len(_all_group_specs) else {}).get("candidate_source"),
                            "selected_layer": (_all_group_specs[i] if i < len(_all_group_specs) else {}).get("selected_layer"),
                            "target_direction": (_all_group_specs[i] if i < len(_all_group_specs) else {}).get("target_direction"),
                            "target_layer": (_all_group_specs[i] if i < len(_all_group_specs) else {}).get("target_layer"),
                            "exploration_role": (_all_group_specs[i] if i < len(_all_group_specs) else {}).get("exploration_role"),
                            "planner_reason": (_all_group_specs[i] if i < len(_all_group_specs) else {}).get("planner_reason"),
                            "hypothesis": (_all_group_specs[i] if i < len(_all_group_specs) else {}).get("hypothesis"),
                            "hypothesis_type": (_all_group_specs[i] if i < len(_all_group_specs) else {}).get("hypothesis_type"),
                            "structure_patch": _sanitize_json_floats(dict((_all_group_specs[i] if i < len(_all_group_specs) else {}).get("structure_patch") or {})),
                            "global_config_patch": _sanitize_json_floats(dict((_all_group_specs[i] if i < len(_all_group_specs) else {}).get("global_config_patch") or {})),
                            "node_param_patches": _sanitize_json_floats(list((_all_group_specs[i] if i < len(_all_group_specs) else {}).get("node_param_patches") or [])),
                        }
                        for i, (cid, bov) in enumerate(_all_cmp_ids)
                    ],
                }
                _snapshot_autoresearch_state(run_id)

                _max_concurrent = min(_batch_size, int(compare_config.get("max_concurrent_batches", _batch_size)))
                _sem = asyncio.Semaphore(_max_concurrent)
                _log(f"第 {iteration} 轮：{_batch_size} 组 Challenger 并发启动（最大并发={_max_concurrent}）", "info")

                async def _run_one_batch(
                    group_idx: int,
                    cmp_id: str,
                    b_override: Dict[str, Any],
                    is_main: bool,
                    run_windows: List[dict],
                    fidelity_stage: str = "full",
                ) -> None:
                    async with _sem:
                        _groups = None
                        try:
                            _group_status = state.get("batch_eval_status") or {}
                            _groups = _group_status.get("groups") if isinstance(_group_status, dict) else None
                            _group_spec = _all_group_specs[group_idx] if 0 <= group_idx < len(_all_group_specs) else {}
                            _group_structure_patch = dict(_group_spec.get("structure_patch") or {})
                            _group_global_patch = dict(_group_spec.get("global_config_patch") or {})
                            _group_node_patches = list(_group_spec.get("node_param_patches") or [])
                            if isinstance(_groups, list) and 0 <= group_idx < len(_groups):
                                _groups[group_idx]["status"] = "running"
                                _groups[group_idx]["started_at"] = datetime.now().isoformat()
                                _groups[group_idx]["fidelity_stage"] = fidelity_stage
                                _groups[group_idx]["windows_used"] = len(run_windows or [])
                                _groups[group_idx]["windows_done"] = 0
                                _groups[group_idx]["windows_total"] = len(run_windows or [])
                                _snapshot_autoresearch_state(run_id)
                            _group_timeout = _get_autoresearch_batch_group_timeout_s(compare_config, windows_count=len(run_windows or []))

                            def _on_group_live(payload: Dict[str, Any]) -> None:
                                if isinstance(_groups, list) and 0 <= group_idx < len(_groups):
                                    live_summary = (payload or {}).get("live_summary") if isinstance(payload, dict) else {}
                                    live_progress = (payload or {}).get("progress") if isinstance(payload, dict) else {}
                                    if isinstance(live_summary, dict):
                                        _groups[group_idx]["windows_done"] = live_summary.get("windows_done", _groups[group_idx].get("windows_done"))
                                        _groups[group_idx]["windows_total"] = live_summary.get("windows_total", _groups[group_idx].get("windows_total"))
                                        _groups[group_idx]["current_window"] = live_summary.get("current_window", _groups[group_idx].get("current_window"))
                                        _groups[group_idx]["current_phase"] = live_summary.get("current_phase", _groups[group_idx].get("current_phase"))
                                    if isinstance(live_progress, dict):
                                        _groups[group_idx]["window_index"] = live_progress.get("window_index", _groups[group_idx].get("window_index"))
                                        _groups[group_idx]["window_total"] = live_progress.get("window_total", _groups[group_idx].get("window_total"))
                                    _groups[group_idx]["updated_at"] = datetime.now().isoformat()
                                if is_main:
                                    _on_compare_live(payload)
                                else:
                                    now = time.time()
                                    last_snapshot_ts = float(state.get("_last_batch_group_snapshot_ts") or 0)
                                    if now - last_snapshot_ts >= 1.5:
                                        state["_last_batch_group_snapshot_ts"] = now
                                        _snapshot_autoresearch_state(run_id)

                            await asyncio.wait_for(
                                _run_compare_backtest_batch_task(
                                    comparison_id=cmp_id,
                                    baseline_workflow_id=baseline_workflow_id,
                                    challenger_workflow_ids=[baseline_workflow_id],
                                    windows=run_windows,
                                    evaluation_contract=effective_contract,
                                    score_margin=float(compare_config.get("score_margin", 0.0)),
                                    add_to_candidate_pool=bool(compare_config.get("add_to_candidate_pool", True)),
                                    cancel_event=cancel_event,
                                    aggregate_method=str(compare_config.get("aggregate_method", "mean")),
                                    challenger_config_override=b_override,
                                    baseline_config_override=baseline_contract_for_iter if anchor_baseline_contract else None,
                                    challenger_structure_override=_group_structure_patch,
                                    challenger_global_config_patch=_group_global_patch if _group_global_patch else None,
                                    challenger_node_param_patches=_group_node_patches if _group_node_patches else None,
                                    live_update_hook=_on_group_live,
                                ),
                                timeout=_group_timeout,
                            )
                            _bs = _comparison_store.get(cmp_id) or {}
                            if isinstance(_groups, list) and 0 <= group_idx < len(_groups):
                                _groups[group_idx]["status"] = str(_bs.get("status") or "success")
                                _groups[group_idx]["score_advantage"] = (_bs.get("summary") or {}).get("score_advantage")
                                _groups[group_idx]["fidelity_stage"] = fidelity_stage
                                _groups[group_idx]["windows_used"] = len(run_windows or [])
                                _groups[group_idx]["windows_done"] = len(run_windows or [])
                                _groups[group_idx]["windows_total"] = len(run_windows or [])
                                _groups[group_idx]["finished_at"] = datetime.now().isoformat()
                                _snapshot_autoresearch_state(run_id)
                        except asyncio.TimeoutError:
                            _log(f"第 {iteration} 轮：组 {cmp_id} 超时（>{int(_group_timeout // 60)}min），标记为失败", "error")
                            if cmp_id in _comparison_store:
                                _comparison_store[cmp_id]["status"] = "failed"
                                _comparison_store[cmp_id]["error"] = "batch_eval_timeout"
                            if isinstance(_groups, list) and 0 <= group_idx < len(_groups):
                                _groups[group_idx]["status"] = "failed"
                                _groups[group_idx]["error"] = "batch_eval_timeout"
                                _groups[group_idx]["finished_at"] = datetime.now().isoformat()
                                _snapshot_autoresearch_state(run_id)
                        except Exception as _be:
                            _log(f"第 {iteration} 轮：组 {cmp_id} 异常: {_be}", "error")
                            if cmp_id in _comparison_store:
                                _comparison_store[cmp_id]["status"] = "failed"
                                _comparison_store[cmp_id]["error"] = str(_be)
                            if isinstance(_groups, list) and 0 <= group_idx < len(_groups):
                                _groups[group_idx]["status"] = "failed"
                                _groups[group_idx]["error"] = str(_be)
                                _groups[group_idx]["finished_at"] = datetime.now().isoformat()
                                _snapshot_autoresearch_state(run_id)

                _multi_fidelity_enabled = _auto_research_multifidelity_scheduler.enabled(compare_config, _batch_size, windows)
                _promoted_group_indices: Optional[List[int]] = None
                if _multi_fidelity_enabled:
                    _mf_windows = _auto_research_multifidelity_scheduler.initial_windows(
                        windows,
                        min_windows=int(compare_config.get("multi_fidelity_min_windows", 1)),
                        fraction=float(compare_config.get("multi_fidelity_initial_fraction", 0.5)),
                    )
                    state["multi_fidelity_status"] = {
                        "enabled": True,
                        "iteration": iteration,
                        "stage": "rung_0",
                        "total_windows": len(windows),
                        "initial_windows": len(_mf_windows),
                        "reduction_factor": int(compare_config.get("multi_fidelity_reduction_factor", 2)),
                    }
                    _log(
                        f"第 {iteration} 轮：多保真 ASHA 启动，先用 {len(_mf_windows)}/{len(windows)} 个窗口筛选",
                        "info",
                    )
                    await asyncio.gather(*[
                        _run_one_batch(i, cid, bov, i == 0, _mf_windows, "rung_0")
                        for i, (cid, bov) in enumerate(_all_cmp_ids)
                    ])
                    _rung_rows = [
                        {
                            "group_idx": i,
                            "comparison_id": cid,
                            "override": bov,
                            "state": dict(_comparison_store.get(cid) or {}),
                        }
                        for i, (cid, bov) in enumerate(_all_cmp_ids)
                    ]
                    _promoted_group_indices = _auto_research_multifidelity_scheduler.select_promotions(
                        _rung_rows,
                        reduction_factor=int(compare_config.get("multi_fidelity_reduction_factor", 2)),
                        min_promotions=int(compare_config.get("multi_fidelity_min_promotions", 1)),
                    )
                    state["multi_fidelity_status"]["promoted_groups"] = list(_promoted_group_indices)
                    _promoted_set = set(_promoted_group_indices)
                    for _i, (_cid, _) in enumerate(_all_cmp_ids):
                        if _i in _promoted_set:
                            continue
                        _st = _comparison_store.get(_cid)
                        if isinstance(_st, dict) and str(_st.get("status") or "") == "success":
                            _st["status"] = "pruned"
                            _st["pruned_by"] = "asha"
                            _st["pruned_at_iteration"] = iteration
                    if isinstance(state.get("batch_eval_status"), dict):
                        _groups = state["batch_eval_status"].get("groups")
                        if isinstance(_groups, list):
                            for _g in _groups:
                                if not isinstance(_g, dict):
                                    continue
                                _gi = int(_g.get("group_idx") or 0)
                                if _gi not in _promoted_set and str(_g.get("status") or "") == "success":
                                    _g["status"] = "pruned"
                                    _g["pruned_by"] = "asha"
                    if _promoted_group_indices:
                        state["multi_fidelity_status"]["stage"] = "full"
                        _log(
                            f"第 {iteration} 轮：ASHA 晋级组 {list(_promoted_group_indices)}，进入全窗口复验",
                            "info",
                        )
                        await asyncio.gather(*[
                            _run_one_batch(i, cid, bov, i == 0, windows, "full")
                            for i, (cid, bov) in enumerate(_all_cmp_ids)
                            if i in _promoted_set
                        ])
                    else:
                        _log(f"第 {iteration} 轮：ASHA 无成功组晋级，跳过全窗口复验", "warning")
                else:
                    await asyncio.gather(*[
                        _run_one_batch(i, cid, bov, i == 0, windows, "full")
                        for i, (cid, bov) in enumerate(_all_cmp_ids)
                    ])

                # 更新并发状态。先对原始组结果做快照，避免后面把最优组写回
                # 主 comparison_id 后，组 0 的失败/成功事实被覆盖。
                _batch_rows: List[Dict[str, Any]] = []
                for i, (cid, bov) in enumerate(_all_cmp_ids):
                    _bs = dict(_comparison_store.get(cid) or {})
                    _group_spec = _all_group_specs[i] if i < len(_all_group_specs) else {}
                    _batch_rows.append({
                        "group_idx": i,
                        "comparison_id": cid,
                        "override": bov,
                        "state": _bs,
                        "group_spec": _group_spec,
                    })
                    _bs_adv = (_bs.get("summary") or {}).get("score_advantage")
                    state["batch_eval_status"]["groups"][i]["status"] = str(_bs.get("status") or "unknown")
                    state["batch_eval_status"]["groups"][i]["score_advantage"] = _bs_adv
                state["batch_eval_status"]["running"] = False

                # 选最优组替换主组结果
                best_idx = 0
                best_row = _select_autoresearch_batch_best(_batch_rows)
                has_successful_batch = best_row is not None
                if best_row:
                    best_batch = best_row.get("state") or {}
                    best_idx = int(best_row.get("group_idx") or 0)
                    _log(
                        f"第 {iteration} 轮：{_batch_size} 组并发完成，最优为第 {best_idx + 1} 组"
                        f"（score_advantage={float((best_batch.get('summary') or {}).get('score_advantage') or 0):.4f}）",
                        "success",
                    )
                    if best_idx > 0:
                        _comparison_store[comparison_id] = best_batch
                    override_full = dict(_all_cmp_ids[best_idx][1])
                    _best_group_spec = best_row.get("group_spec") if isinstance(best_row.get("group_spec"), dict) else {}
                    structure_patch = dict(_best_group_spec.get("structure_patch") or {})
                    rgc = dict(_best_group_spec.get("global_config_patch") or {})
                    rnpp = list(_best_group_spec.get("node_param_patches") or [])
                    state["current_override"] = _sanitize_json_floats(dict(override_full))
                    try:
                        _best_eval = _evaluate_autoresearch_candidate(best_batch, policy)
                        _best_mi = _best_eval.get("mape_improvement")
                        if _best_mi is not None:
                            _append_memory_case({
                                "case_id": f"mem-{uuid.uuid4().hex[:10]}",
                                "created_at": datetime.now().isoformat(),
                                "run_id": run_id,
                                "iteration": iteration,
                                "baseline_workflow_id": baseline_workflow_id,
                                "scenario_tags": state.get("scenario_tags") or [],
                                "fingerprint": _compute_scenario_fingerprint(state, windows=windows),
                                "selected_group_idx": best_idx,
                                "applied_patch": {"override": override_full},
                                "outcome": {
                                    "improved": float(_best_mi) > 0,
                                    "mape_delta": _best_mi,
                                    "score_advantage": _best_eval.get("score_advantage"),
                                    "selected": True,
                                },
                            })
                    except Exception as _mem_err:
                        logger.warning("batch best memory append failed: %s", _mem_err)
                else:
                    failed_count = 0
                    for _row in _batch_rows:
                        _st = _row.get("state") if isinstance(_row.get("state"), dict) else {}
                        if str(_st.get("status") or "") in {"failed", "error", "cancelled"}:
                            failed_count += 1
                    _log(
                        f"第 {iteration} 轮：{_batch_size} 组并发无成功结果"
                        f"（失败/取消 {failed_count} 组），跳过最优组选择",
                        "error",
                    )
                    _comparison_store[comparison_id]["status"] = "failed"
                    _comparison_store[comparison_id]["error"] = f"all_batch_groups_failed: {failed_count}/{_batch_size} groups failed_or_cancelled"
                    state["error"] = _comparison_store[comparison_id]["error"]

                # 把所有组的结果摘要写入 state，供 GLM 下一轮学习
                _batch_results_for_glm: List[Dict[str, Any]] = []
                _parallel_research_for_glm: List[Dict[str, Any]] = []
                for row in _batch_rows:
                    i = int(row.get("group_idx") or 0)
                    cid = str(row.get("comparison_id") or "")
                    bov = row.get("override") or {}
                    _bs = row.get("state") if isinstance(row.get("state"), dict) else {}
                    _group_spec = row.get("group_spec") if isinstance(row.get("group_spec"), dict) else {}
                    _bs_summ = _bs.get("summary") or {}
                    _bs_eval = _evaluate_autoresearch_candidate(_bs, policy) if str(_bs.get("status") or "") == "success" else {}
                    _batch_group_records.append(_build_autoresearch_batch_group_record(
                        iteration=iteration,
                        group_idx=i,
                        comparison_id=cid,
                        override=dict(bov),
                        compare_state=_bs,
                        policy=policy,
                        group_spec=_group_spec,
                        is_best=bool(has_successful_batch and i == best_idx),
                        is_primary=bool(i == 0),
                        runtime_patch_snapshot=state.get("runtime_patch") or {},
                        effective_search_space=state.get("effective_search_space") or {},
                        effective_evaluation_contract=state.get("effective_evaluation_contract") or {},
                    ))
                    _bs_windows = _bs.get("window_results") or []
                    _profile = _compute_iteration_error_profile(_bs_windows) if isinstance(_bs_windows, list) else {}
                    _err_profile = _profile.get("error_profile") or {}
                    _data_coverage = _profile.get("data_coverage") or {}
                    _diag_source = "unknown"
                    _evidence: List[str] = []
                    try:
                        _mi_val = float(_bs_eval.get("mape_improvement")) if _bs_eval.get("mape_improvement") is not None else None
                    except (TypeError, ValueError):
                        _mi_val = None
                    if _mi_val is not None:
                        _evidence.append(f"mape_improvement={_mi_val}")
                        _diag_source = "promising_direction" if _mi_val > 0 else "ineffective_direction"
                    if _err_profile.get("avg_mape") is not None:
                        _evidence.append(f"avg_mape={_err_profile.get('avg_mape')}")
                    if _data_coverage:
                        _evidence.append(f"data_coverage={json.dumps(_data_coverage, ensure_ascii=False)}")
                    _research_question = (
                        f"组{i + 1}（override={json.dumps(bov, ensure_ascii=False)[:120]}）"
                        + (
                            f"以 mape_improvement={_mi_val:.4f} 成为最优，其参数方向中哪些因素是关键贡献？是否应在此基础上微调深化？"
                            if bool(has_successful_batch and i == best_idx and _mi_val is not None)
                            else f"mape_improvement={_mi_val if _mi_val is not None else '无数据'}，未胜出。"
                            f"与最优组的参数差异中，哪个变量最可能导致了劣势？应排除还是换方向？"
                        )
                    )
                    _batch_results_for_glm.append({
                        "group_idx": i,
                        "override": bov,
                        "status": str(_bs.get("status") or "unknown"),
                        "score_advantage": _bs_summ.get("score_advantage"),
                        "mape_improvement": _bs_eval.get("mape_improvement"),
                        "challenger_mape": _bs_eval.get("challenger_mape"),
                        "is_best": bool(has_successful_batch and i == best_idx),
                    })
                    # 从 GLM proposals 中提取该组对应的假设（如果有）
                    _group_hypothesis = None
                    _last_props = state.get("_last_glm_proposals") or []
                    # 组 0 对应推荐候选（ranked[0]），组 1/2 对应后续有效 GLM 候选
                    _glm_valid_props = [p for p in _last_props if isinstance(p, dict)
                                        and p.get("_source") == "glm"
                                        and bool((p.get("validation") or {}).get("valid"))]
                    if i < len(_glm_valid_props):
                        _group_hypothesis = _glm_valid_props[i].get("hypothesis")
                    _parallel_research_for_glm.append({
                        "group_idx": i,
                        "comparison_id": cid,
                        "override": bov,
                        "status": str(_bs.get("status") or "unknown"),
                        "is_best": bool(has_successful_batch and i == best_idx),
                        "original_hypothesis": _group_hypothesis,
                        "hypothesis_verified": (
                            True if (_group_hypothesis and _mi_val is not None and _mi_val > 0)
                            else False if (_group_hypothesis and _mi_val is not None and _mi_val <= 0)
                            else None
                        ),
                        "diagnosis": {
                            "primary_cause": _diag_source,
                            "evidence": _evidence,
                            "error_profile": _err_profile,
                            "data_coverage": _data_coverage,
                        },
                        "research_question_seed": _research_question,
                        "candidate_hypothesis_seed": (
                            f"组{i + 1}验证了假设「{_group_hypothesis or '随机探索'}」，"
                            f"结果 mape_improvement={_mi_val if _mi_val is not None else 'N/A'}。"
                            + (f"假设成立，应在 {list(bov.keys())[:3]} 方向继续深化。" if (_mi_val is not None and _mi_val > 0)
                               else f"假设不成立，应排除 {list(bov.keys())[:3]} 的当前取值方向。")
                        ),
                    })
                state["last_batch_results"] = _sanitize_json_floats(_batch_results_for_glm)
                state["parallel_research_results"] = _sanitize_json_floats(_parallel_research_for_glm)
                state["latest_batch_groups"] = _sanitize_json_floats(_batch_group_records)
                _refresh_autoresearch_control_plane(run_id, state, iteration=iteration, batch_groups=_batch_group_records)
                if _v3_plan_items:
                    _commit_v3_successful_batch_plans(state, _batch_group_records)
                    state["v3_action_variant_cursor"] = _sanitize_json_floats(
                        state.get("action_variant_cursor") or {}
                    )
                    _snapshot_autoresearch_state(run_id)

                # FIX C2: cleanup cancel events for all comparison IDs from this iteration
                for _cleanup_cid in _all_cmp_ids:
                    _comparison_cancel_events.pop(_cleanup_cid[0], None)

            else:
                # ── 单组模式（原有逻辑）────────────────────────────────────────────
                # FIX C2: zombie guard - catch cancel/silent failures to ensure cleanup
                try:
                    await _run_compare_backtest_batch_task(
                        comparison_id=comparison_id,
                        baseline_workflow_id=base_for_iter,
                        challenger_workflow_ids=[base_for_iter],
                        windows=windows,
                        evaluation_contract=effective_contract,
                        score_margin=float(compare_config.get("score_margin", 0.0)),
                        add_to_candidate_pool=bool(compare_config.get("add_to_candidate_pool", True)),
                        cancel_event=cancel_event,
                        aggregate_method=str(compare_config.get("aggregate_method", "mean")),
                        min_windows_challenger_better=compare_config.get("min_windows_challenger_better"),
                        challenger_config_override=challenger_override_for_iter,
                        baseline_config_override=baseline_contract_for_iter if anchor_baseline_contract else None,
                        challenger_structure_override=structure_patch,
                        challenger_global_config_patch=rgc if rgc else None,
                        challenger_node_param_patches=rnpp if rnpp else None,
                        live_update_hook=_on_compare_live,
                    )
                except asyncio.CancelledError:
                    _comparison_store[comparison_id]["status"] = "cancelled"
                    _log(f"第 {iteration} 轮：compare 被 cancel，已标记 cancelled", "warning")
                    raise
                except Exception as _cmp_err:
                    _comparison_store[comparison_id]["status"] = "error"
                    _comparison_store[comparison_id]["error"] = str(_cmp_err)[:500]
                    _log(f"第 {iteration} 轮：compare 异常 {type(_cmp_err).__name__}: {str(_cmp_err)[:200]}", "error")
                    traceback.print_exc()
                # 第 1 轮跑完后，把 Baseline 各窗口结果缓存起来
                if anchor_baseline_contract and not state.get("_baseline_cache"):
                    state["_baseline_cache_ts"] = time.time()  # H4: record timestamp
                    state["_baseline_cache_key"] = baseline_cache_key
                    state["_baseline_cache_metadata"] = {
                        "cache_key": baseline_cache_key,
                        "windows": windows,
                        "baseline_contract": baseline_contract_for_iter,
                        "created_iteration": iteration,
                    }
                    _cmp_for_cache = _comparison_store.get(comparison_id) or {}
                    _cached_wr = _cmp_for_cache.get("window_results")
                    if isinstance(_cached_wr, list) and _cached_wr:
                        _cache_dict = {}
                        for _wr in _cached_wr:
                            if not isinstance(_wr, dict):
                                continue
                            _sd = str(_wr.get("start_date") or "")
                            _ed = str(_wr.get("end_date") or "")
                            if _sd and _ed:
                                _b_data = _wr.get("baseline") or {}
                                _cache_dict[f"{_sd}~{_ed}"] = {
                                    "avg_metrics": _b_data.get("avg_metrics"),
                                    "candidate_score": _b_data.get("candidate_score"),
                                    "success_days": _b_data.get("success_days"),
                                    "failed_days": _b_data.get("failed_days"),
                                    "skipped_days": _b_data.get("skipped_days"),
                                    "total_duration": _b_data.get("total_duration"),
                                    "error": _b_data.get("error"),
                                }
                        state["_baseline_cache"] = _cache_dict
                        state["_baseline_cache_key"] = baseline_cache_key
                        _log(f"第 {iteration} 轮：Baseline 结果已缓存（key={baseline_cache_key}，{len(_cached_wr)} 个窗口），后续轮次将跳过 Baseline 回测", "info")

            cmp_state = _comparison_store.get(comparison_id) or {}
            cmp_status = str(cmp_state.get("status") or "")
            _last_applied_proposal_id = str(state.get("last_applied_proposal_id") or "")
            _last_proposal = _auto_research_proposals_store.get(_last_applied_proposal_id) if _last_applied_proposal_id else None
            if not isinstance(_last_proposal, dict):
                _last_proposal = state.get("last_applied_proposal") if isinstance(state.get("last_applied_proposal"), dict) else None
            _candidate_hypothesis_type = str(
                ((_last_proposal or {}).get("hypothesis_type") if isinstance(_last_proposal, dict) else None)
                or _infer_hypothesis_type_from_patch(
                    override=override_full,
                    structure_patch=structure_patch,
                    node_param_patches=rnpp,
                    global_config_patch=rgc,
                )
                or "parameter"
            )
            _candidate_primary_variable = (
                (_last_proposal or {}).get("primary_variable") if isinstance(_last_proposal, dict) else None
            ) or _infer_primary_variable({
                "search_space_patch": (state.get("runtime_patch") or {}).get("search_space_patch") or {},
                "evaluation_contract_patch": (state.get("runtime_patch") or {}).get("evaluation_contract_patch") or {},
                "structure_patch": structure_patch,
                "global_config_patch": rgc,
                "node_param_patches": rnpp,
            })
            if cmp_status == "failed":
                err = cmp_state.get("error")
                _log(f"第 {iteration} 轮失败：{err}", "error")
                all_candidates.append({
                    "iteration": iteration,
                    "comparison_id": comparison_id,
                    "status": "failed",
                    "override": override_full,
                    "structure_patch": structure_patch,
                    "global_config_patch": rgc,
                    "node_param_patches": rnpp,
                    "runtime_patch": state.get("runtime_patch") or {},
                    "effective_search_space": state.get("effective_search_space") or {},
                    "effective_evaluation_contract": state.get("effective_evaluation_contract") or {},
                    "hypothesis_type": _candidate_hypothesis_type,
                    "primary_variable": _candidate_primary_variable,
                    "model_focus_patch": model_focus_patch,
                    "error": err,
                    "sampled_layers": list(state.get("_current_sampled_layers") or []),
                    "batch_groups": _batch_group_records,
                    "applied_patch_fingerprint": _build_applied_patch_fingerprint(
                        override=override_full,
                        structure_patch=structure_patch,
                        global_config_patch=rgc,
                        node_param_patches=rnpp,
                    ),
                })
                state["last_failed_trial"] = _sanitize_json_floats(all_candidates[-1])
                # 失败轮也要写入 iterations，让前端能看到
                state["iterations"] = _sanitize_json_floats(all_candidates)
                _failed_group_spec = {
                    "candidate_source": "single",
                    "hypothesis_type": _candidate_hypothesis_type,
                    "selected_layer": _layer_from_hypothesis_type(_candidate_hypothesis_type),
                    "structure_patch": structure_patch,
                    "global_config_patch": rgc,
                    "node_param_patches": rnpp,
                }
                if _v3_plan_items:
                    _v3_single_plan = _v3_plan_items[0]
                    _v3_single_action = (
                        _v3_single_plan.get("action")
                        if isinstance(_v3_single_plan.get("action"), dict)
                        else {}
                    )
                    _failed_group_spec.update({
                        "candidate_source": "v3_action",
                        "action_id": _v3_single_plan.get("action_id"),
                        "v3_plan_item": _v3_single_plan,
                        "patch_fingerprint": _v3_single_plan.get("patch_fingerprint"),
                        "hypothesis": _v3_single_action.get("description"),
                        "hypothesis_type": _v3_single_action.get("target_direction") or _candidate_hypothesis_type,
                        "selected_layer": _v3_single_action.get("target_layer"),
                        "target_direction": _v3_single_action.get("target_direction"),
                        "target_layer": _v3_single_action.get("target_layer"),
                        "exploration_role": "v3_action",
                        "planner_reason": _v3_single_plan.get("reason"),
                        "variant_index": _v3_single_plan.get("variant_index"),
                    })
                _failed_group = _build_autoresearch_batch_group_record(
                    iteration=iteration,
                    group_idx=0,
                    comparison_id=comparison_id,
                    override=dict(override_full),
                    compare_state=cmp_state,
                    policy=policy,
                    group_spec=_failed_group_spec,
                    is_best=False,
                    is_primary=True,
                    runtime_patch_snapshot=state.get("runtime_patch") or {},
                    effective_search_space=state.get("effective_search_space") or {},
                    effective_evaluation_contract=state.get("effective_evaluation_contract") or {},
                )
                all_candidates[-1]["evidence"] = _auto_research_evidence_builder.build_for_group(run_id=run_id, group=_failed_group).to_dict()
                _refresh_autoresearch_control_plane(run_id, state, iteration=iteration, batch_groups=[_failed_group])
                _report_autoresearch_optuna_result(run_id, state, all_candidates[-1])
                _record_autoresearch_trial(run_id, all_candidates[-1])
                # 失败轮也触发人工闸门（让用户决定是否继续）
                if manual_gate and (not auto_full_automation) and not cancel_event.is_set() and (iteration < max_iterations):
                    state["status"] = "waiting_review"
                    state["gate"] = {
                        "iteration": iteration,
                        "opened_at": datetime.now().isoformat(),
                        "released": False,
                        "release_reason": None,
                    }
                    _log(f"第 {iteration} 轮失败，进入等待审核（waiting_review）", "warning")
                    while True:
                        if cancel_event.is_set():
                            break
                        gate = state.get("gate") or {}
                        if bool(gate.get("released")):
                            break
                        await asyncio.sleep(0.5)
                    if cancel_event.is_set():
                        break
                    state["status"] = "running"
                # Fix B1: 失败轮也生成 GLM proposal，让下一轮并发组有候选可用
                if auto_generate_proposal and not cancel_event.is_set():
                    try:
                        _glm_start_time = time.time()
                        auto_pack = await _generate_ranked_proposals_for_run(
                            run_id=run_id,
                            state=state,
                            count=3,
                            memory_top_k=auto_memory_top_k,
                        )
                        _glm_duration = round(time.time() - _glm_start_time, 2)
                        state["_last_glm_proposals"] = auto_pack.get("proposals") or []
                        _log(
                            f"第 {iteration} 轮（失败轮）：仍生成 GLM 建议 {int(auto_pack.get('generated_count') or 0)} 条"
                            f"（耗时 {_glm_duration}s），供下一轮并发组使用",
                            "info",
                        )
                    except Exception as _glm_fail_err:
                        _log(f"第 {iteration} 轮（失败轮）：GLM 建议生成失败: {_glm_fail_err}", "warning")
                continue
            eval_info = _evaluate_autoresearch_candidate(cmp_state, policy)
            summary = cmp_state.get("summary") or {}
            candidate = {
                "iteration": iteration,
                "comparison_id": comparison_id,
                "status": cmp_status or "success",
                "override": override_full,
                "structure_patch": structure_patch,
                "global_config_patch": rgc,
                "node_param_patches": rnpp,
                "runtime_patch": state.get("runtime_patch") or {},
                "effective_search_space": state.get("effective_search_space") or {},
                "effective_evaluation_contract": state.get("effective_evaluation_contract") or {},
                "hypothesis_type": _candidate_hypothesis_type,
                "primary_variable": _candidate_primary_variable,
                    "model_focus_patch": model_focus_patch,
                    "pool_candidate_id": cmp_state.get("pool_candidate_id"),
                    "summary": summary,
                    "evaluation": eval_info,
                    "batch_groups": _batch_group_records,
                    "applied_patch_fingerprint": _build_applied_patch_fingerprint(
                        override=override_full,
                        structure_patch=structure_patch,
                        global_config_patch=rgc,
                        node_param_patches=rnpp,
                    ),
                    # 任务 10.3：记录本轮采样涉及的层（注册表模式下由 9.5 填充，旧模式为空列表）
                "sampled_layers": list(state.get("_current_sampled_layers") or []),
                # 任务 27.4：标记对照组轮次
                "is_control_round": _is_control_round,
                # 提取 evaluation 关键字段到顶层，方便前端直接读取
                "challenger_mape": eval_info.get("challenger_mape"),
                "baseline_mape": eval_info.get("baseline_mape"),
                "mape_improvement": eval_info.get("mape_improvement"),
            }
            all_candidates.append(candidate)
            _report_autoresearch_optuna_result(run_id, state, candidate)

            # 任务 27.4：对照组结果记录 + 漂移检测
            if _is_control_round and candidate.get("status") == "success":
                ev_ctrl = candidate.get("evaluation") or {}
                ctrl_mape = ev_ctrl.get("challenger_mape")
                if not isinstance(state.get("control_group_results"), list):
                    state["control_group_results"] = []
                state["control_group_results"].append({
                    "iteration": iteration,
                    "challenger_mape": ctrl_mape,
                    "created_at": datetime.now().isoformat(),
                })
                # 与第一轮对比，检测漂移
                first_mape = None
                for c in all_candidates:
                    if c.get("status") == "success" and not c.get("is_control_round"):
                        ev_first = c.get("evaluation") or {}
                        first_mape = ev_first.get("challenger_mape")
                        break
                if ctrl_mape is not None and first_mape is not None:
                    try:
                        drift = abs(float(ctrl_mape) - float(first_mape))
                        if drift > 0.01:  # > 1%
                            _log(
                                f"⚠️ 对照组检测到数据漂移：当前 MAPE={float(ctrl_mape):.4f}，"
                                f"首轮 MAPE={float(first_mape):.4f}，差异={drift:.4f}（> 1%）",
                                "warning",
                            )
                    except (TypeError, ValueError):
                        pass
            # 写入经验库（轻量）：只记录成功轮、含可用 mape_improvement
            try:
                if candidate.get("status") == "success":
                    ev = candidate.get("evaluation") or {}
                    mi = ev.get("mape_improvement")
                    if mi is not None:
                        case_id = f"mem-{uuid.uuid4().hex[:10]}"
                        improved = False
                        try:
                            improved = float(mi) > 0
                        except Exception:
                            improved = False
                        _append_memory_case({
                            "case_id": case_id,
                            "created_at": datetime.now().isoformat(),
                            "run_id": run_id,
                            "iteration": iteration,
                            "baseline_workflow_id": baseline_workflow_id,
                            "scenario_tags": state.get("scenario_tags") or [],
                            "context_fingerprint": _memory_context_fingerprint(state),
                            # 任务 8.2：新增结构化场景指纹
                            "fingerprint": _compute_scenario_fingerprint(state, windows=windows),
                            "applied_patch": {
                                "override": override_full,
                                "structure_patch": structure_patch,
                                "model_focus_patch": model_focus_patch,
                                "runtime_patch": state.get("runtime_patch") or {},
                            },
                            "outcome": {
                                "improved": improved,
                                "mape_delta": mi,
                                "score_advantage": ev.get("score_advantage"),
                                "meets_constraints": ev.get("meets_constraints"),
                            },
                        })
            except Exception as _mem_err:
                logger.warning("single-run memory append failed: %s", _mem_err)
            mape_impr = eval_info.get("mape_improvement")
            if mape_impr is not None:
                _log(f"第 {iteration} 轮完成：mape_improvement={round(float(mape_impr), 4)}", "success")
            else:
                _log(f"第 {iteration} 轮完成：指标不足，未计算 mape_improvement", "info")

            try:
                _pool_for_novelty = _load_candidate_pool_list()
                for _cand in all_candidates:
                    if not isinstance(_cand, dict):
                        continue
                    _entry_like = {
                        "id": _cand.get("pool_candidate_id") or _cand.get("comparison_id"),
                        "source_run_id": run_id,
                        "source_iteration": _cand.get("iteration"),
                        "challenger_override": _cand.get("override") or {},
                        "effective_structure_patch": _cand.get("structure_patch") or {},
                        "effective_parameter_patch": _cand.get("global_config_patch") or {},
                        "node_param_patches": _cand.get("node_param_patches") or [],
                        "summary": _cand.get("summary") or {},
                        "evaluation": _cand.get("evaluation") or {},
                    }
                    _cand["novelty_audit"] = _build_candidate_novelty_audit(_entry_like, _pool_for_novelty)
                state["novelty_summary"] = _summarize_candidate_novelty(all_candidates)
            except Exception as _nov_err:
                logger.warning("candidate novelty audit failed: %s", _nov_err)

            ranked = sorted(
                [c for c in all_candidates if c.get("status") == "success"],
                key=_autoresearch_rank_key,
            )
            state["best_candidate"] = _sanitize_json_floats(ranked[0]) if ranked else None
            state["top_candidates"] = _sanitize_json_floats(ranked[: max(1, int(top_k))]) if ranked else []
            # 任务 5.3：计算多目标 Pareto 前沿（Top-3），写入 state
            state["pareto_frontier"] = _sanitize_json_floats(
                _compute_pareto_frontier(all_candidates, top_k=3)
            )
            state["iterations"] = _sanitize_json_floats(all_candidates)
            try:
                await _update_autoresearch_nextgen_artifacts(
                    run_id=run_id,
                    state=state,
                    candidate=all_candidates[-1],
                    compare_config=compare_config,
                )
                _log(f"第 {iteration} 轮：已生成研究问题/诊断/实验质量记录", "info")
            except Exception as _ng_err:
                _log(f"第 {iteration} 轮：next-gen 研究产物生成失败（不影响主流程）: {_ng_err}", "warning")
            if not _batch_group_records:
                _single_group_spec = {
                    "candidate_source": "single",
                    "hypothesis_type": _candidate_hypothesis_type,
                    "selected_layer": _layer_from_hypothesis_type(_candidate_hypothesis_type),
                    "structure_patch": structure_patch,
                    "global_config_patch": rgc,
                    "node_param_patches": rnpp,
                }
                if _v3_plan_items:
                    _v3_single_plan = _v3_plan_items[0]
                    _v3_single_action = (
                        _v3_single_plan.get("action")
                        if isinstance(_v3_single_plan.get("action"), dict)
                        else {}
                    )
                    _single_group_spec.update({
                        "candidate_source": "v3_action",
                        "action_id": _v3_single_plan.get("action_id"),
                        "v3_plan_item": _v3_single_plan,
                        "patch_fingerprint": _v3_single_plan.get("patch_fingerprint"),
                        "hypothesis": _v3_single_action.get("description"),
                        "hypothesis_type": _v3_single_action.get("target_direction") or _candidate_hypothesis_type,
                        "selected_layer": _v3_single_action.get("target_layer"),
                        "target_direction": _v3_single_action.get("target_direction"),
                        "target_layer": _v3_single_action.get("target_layer"),
                        "exploration_role": "v3_action",
                        "planner_reason": _v3_single_plan.get("reason"),
                        "variant_index": _v3_single_plan.get("variant_index"),
                    })
                _single_group = _build_autoresearch_batch_group_record(
                    iteration=iteration,
                    group_idx=0,
                    comparison_id=comparison_id,
                    override=dict(override_full),
                    compare_state=cmp_state,
                    policy=policy,
                    group_spec=_single_group_spec,
                    is_best=True,
                    is_primary=True,
                    runtime_patch_snapshot=state.get("runtime_patch") or {},
                    effective_search_space=state.get("effective_search_space") or {},
                    effective_evaluation_contract=state.get("effective_evaluation_contract") or {},
                )
                candidate["batch_groups"] = [_single_group]
                _batch_group_records = [_single_group]
            candidate["evidence"] = _auto_research_evidence_builder.build_for_candidate(
                run_id=run_id,
                candidate=candidate,
                comparison_state=cmp_state,
            ).to_dict()
            _pool_cid = str(candidate.get("pool_candidate_id") or "").strip()
            if _pool_cid:
                try:
                    _sync_candidate_pool_evidence(_pool_cid, candidate["evidence"])
                except Exception as _pool_ev_err:
                    logger.warning("sync pool evidence failed for %s: %s", _pool_cid, _pool_ev_err)
            _refresh_autoresearch_control_plane(run_id, state, iteration=iteration, batch_groups=_batch_group_records)
            if _v3_plan_items:
                _commit_v3_successful_batch_plans(state, _batch_group_records)
                state["v3_action_variant_cursor"] = _sanitize_json_floats(
                    state.get("action_variant_cursor") or {}
                )
                _snapshot_autoresearch_state(run_id)
            # 任务 21.2：每轮结束后验证上一轮假设，更新洞察和否证集
            _current_candidate = all_candidates[-1] if all_candidates else {}
            _hv_result = _verify_hypothesis(_current_candidate, _last_proposal)
            if _hv_result is not None:
                state["last_hypothesis_verification"] = _sanitize_json_floats(_hv_result)
                if all_candidates:
                    all_candidates[-1]["hypothesis_verification"] = _hv_result
                _update_hypothesis_state(state, iteration, _hv_result)
                _auto_research_hypothesis_tracker.update_chain(
                    state,
                    _last_applied_proposal_id,
                    iteration,
                    _sanitize_json_floats(_hv_result),
                )
                _log(
                    f"第 {iteration} 轮假设验证：{'✓ 成立' if _hv_result.get('verified') else '✗ 未成立'} — {_hv_result.get('conclusion', '')}",
                    "success" if _hv_result.get("verified") else "warning",
                )
            else:
                state["last_hypothesis_verification_skip"] = _sanitize_json_floats({
                    "iteration": iteration,
                    "last_applied_proposal_id": _last_applied_proposal_id or None,
                    "reason": (
                        "no_applied_proposal"
                        if not _last_applied_proposal_id else
                        "proposal_missing_or_no_expected_outcome"
                    ),
                })
            if all_candidates:
                _record_autoresearch_trial(run_id, all_candidates[-1])

            # 任务 27.3：实验预算管理——更新连续类型计数
            _current_type = str(
                (all_candidates[-1].get("hypothesis_type") if all_candidates else None) or "parameter"
            )
            _ctc = _auto_research_hypothesis_tracker.update_consecutive_type_count(state, _current_type)
            _max_consecutive = int(compare_config.get("max_consecutive_type", 3))
            if _ctc.get(_current_type, 0) >= _max_consecutive:
                _log(
                    f"{_current_type} 类型已连续验证 {_ctc[_current_type]} 轮，强制切换到其他方向",
                    "warning",
                )
            # 任务 6.2：收敛检测，写入 convergence_status
            _conv_window = int(compare_config.get("convergence_window", 5))
            _conv_threshold = float(compare_config.get("convergence_var_threshold", 0.01))
            conv_result = _check_convergence(all_candidates, window=_conv_window, var_threshold=_conv_threshold)
            state["convergence_status"] = _sanitize_json_floats(conv_result)
            if conv_result.get("converged"):
                _log(f"收敛检测：{conv_result.get('reason')}", "warning")
            adj = _maybe_apply_autoresearch_self_heal(
                state=state,
                all_candidates=all_candidates,
                current_iteration=iteration,
            )
            if isinstance(adj, dict):
                _log(str(adj.get("message") or "已自动纠偏"), "warning")

            if auto_generate_proposal and not cancel_event.is_set():
                try:
                    _glm_start_time = time.time()
                    auto_pack = await _generate_ranked_proposals_for_run(
                        run_id=run_id,
                        state=state,
                        count=3,
                        memory_top_k=auto_memory_top_k,
                    )
                    _glm_duration = round(time.time() - _glm_start_time, 2)
                    auto_recommended_id = str(auto_pack.get("recommended_proposal_id") or "")

                    # 保存所有 GLM 候选到 state，供下一轮并发组使用（验证不同假设）
                    state["_last_glm_proposals"] = auto_pack.get("proposals") or []

                    _recommended_proposal = _auto_research_proposals_store.get(auto_recommended_id) or {}
                    state["latest_auto_proposal"] = _auto_research_auto_apply_policy.build_latest_auto_proposal(
                        auto_pack=auto_pack,
                        recommended_id=auto_recommended_id,
                        proposal=_recommended_proposal,
                        auto_apply=auto_apply_recommended,
                        risk_max=auto_apply_risk_level_max,
                        duration_s=_glm_duration,
                    )
                    _auto_research_auto_apply_policy.append_history(
                        state,
                        iteration=iteration,
                        latest=state["latest_auto_proposal"],
                    )

                    _log(
                        f"第 {iteration} 轮：自动生成建议 {int(auto_pack.get('generated_count') or 0)} 条"
                        f"（耗时 {_glm_duration}s）"
                        + (f"，推荐 {auto_recommended_id}" if auto_recommended_id else ""),
                        "info",
                    )
                    if auto_apply_recommended and auto_recommended_id:
                        p = _auto_research_proposals_store.get(auto_recommended_id) or {}
                        decision = _auto_research_auto_apply_policy.evaluate_application(
                            recommended_id=auto_recommended_id,
                            proposal=p,
                            auto_apply=auto_apply_recommended,
                            risk_max=auto_apply_risk_level_max,
                        )
                        valid = bool(decision.get("valid"))
                        risk = str(decision.get("risk") or "low").lower()
                        if decision.get("can_apply"):
                            await apply_auto_research_proposal(auto_recommended_id, {"reviewer": "system:auto"})
                            _log(f"第 {iteration} 轮：已自动应用建议 {auto_recommended_id}（risk={risk}）", "success")
                            _auto_research_auto_apply_policy.mark_latest_applied(state)
                        else:
                            escalation = _auto_research_auto_apply_policy.record_blocked_application(
                                state,
                                risk_max=auto_apply_risk_level_max,
                            )
                            auto_apply_risk_level_max = str(escalation.get("risk_max") or auto_apply_risk_level_max)
                            if escalation.get("escalated"):
                                _log(
                                    f"第 {iteration} 轮：连续 {int(escalation.get('skip_count') or 0)} 次建议被风险阈值拦截，"
                                    f"自动提升 auto_apply_risk_level_max 到 medium",
                                    "warning",
                                )
                                # 重新检查当前 proposal 是否可以应用
                                decision = _auto_research_auto_apply_policy.evaluate_application(
                                    recommended_id=auto_recommended_id,
                                    proposal=p,
                                    auto_apply=auto_apply_recommended,
                                    risk_max=auto_apply_risk_level_max,
                                )
                                if decision.get("can_apply"):
                                    await apply_auto_research_proposal(auto_recommended_id, {"reviewer": "system:auto"})
                                    _log(f"第 {iteration} 轮：阈值提升后已自动应用建议 {auto_recommended_id}（risk={risk}）", "success")
                                    _auto_research_auto_apply_policy.mark_latest_applied(state)
                                else:
                                    _log(
                                        f"第 {iteration} 轮：跳过自动应用（valid={valid}, risk={risk}, risk_max={auto_apply_risk_level_max}）",
                                        "warning",
                                    )
                            else:
                                _log(
                                    f"第 {iteration} 轮：跳过自动应用（valid={valid}, risk={risk}, risk_max={auto_apply_risk_level_max}）",
                                    "warning",
                                )
                except Exception as e:
                    _log(f"第 {iteration} 轮：自动生成/应用建议失败: {e}", "warning")
                finally:
                    _snapshot_autoresearch_state(run_id)

            # 人工闸门：每轮结束后等待审核/继续指令
            if manual_gate and (not auto_full_automation) and not cancel_event.is_set() and (iteration < total_iterations):
                state["status"] = "waiting_review"
                state["gate"] = {
                    "iteration": iteration,
                    "opened_at": datetime.now().isoformat(),
                    "released": False,
                    "release_reason": None,
                }
                _log(f"第 {iteration} 轮结束：进入等待审核（waiting_review）", "info")
                _snapshot_autoresearch_state(run_id)
                # 等待直到 proposal apply/reject 或 continue，或取消
                while True:
                    if cancel_event.is_set():
                        break
                    gate = state.get("gate") or {}
                    if bool(gate.get("released")):
                        break
                    await asyncio.sleep(0.5)
                if cancel_event.is_set():
                    break
                # 继续下一轮
                state["status"] = "running"
            # ── 自动入复验池：扫描 novel + single_window_positive 的候选 ──
            try:
                _n = _auto_enqueue_candidates_for_verification(
                    run_id,
                    max_batch=2,
                    logger_fn=_log,
                )
                if _n > 0:
                    _log(f"第 {iteration} 轮：自动入复验池 {_n} 条", "info")
            except Exception as _ve:
                _log(f"第 {iteration} 轮：自动入复验池失败: {_ve}", "warning")
            _snapshot_autoresearch_state(run_id)

        state["status"] = "cancelled" if cancel_event.is_set() else "success"
        if cancel_event.is_set():
            state["error"] = "自动实验已取消"
        state["finished_at"] = datetime.now().isoformat()
        _record_autoresearch_decision(run_id, "run_finished", {
            "actor": "system",
            "reason": state["status"],
            "payload": {
                "status": state.get("status"),
                "progress": state.get("progress"),
                "best_candidate": state.get("best_candidate"),
            },
        })
        _snapshot_autoresearch_state(run_id)
    except Exception as e:
        import traceback as _tb
        tb_str = _tb.format_exc()
        traceback.print_exc()
        state["status"] = "failed"
        state["error"] = str(e)
        state["error_traceback"] = tb_str  # 完整堆栈，前端可展示
        state["finished_at"] = datetime.now().isoformat()
        _log(f"✗ 自动实验失败: {e}", "error")
        _log(f"[traceback] {tb_str}", "error")
        _record_autoresearch_decision(run_id, "run_failed", {
            "actor": "system",
            "reason": str(e),
            "payload": {"traceback": tb_str},
        })
        _snapshot_autoresearch_state(run_id)
    finally:
        _auto_research_cancel_events.pop(run_id, None)
        # 任务 28.3：run 结束时自动生成 insight（success / cancelled / failed 都触发）
        try:
            final_status = str((state or {}).get("status") or "")
            if final_status in ("success", "cancelled", "failed"):
                insight = _generate_run_insight(run_id)
                if "error" not in insight:
                    _save_run_insight(run_id, insight)
                    _log(f"✓ run insight 已生成并保存: {run_id}", "info")
                    # C3 FIX: ingest insight into knowledge layer for cross-run learning
                    try:
                        from services.knowledge_layer import KnowledgeLayer
                        ingested = KnowledgeLayer().ingest_run_insight(insight)
                        if ingested:
                            _log(f"✓ knowledge layer: {len(ingested)} claims ingested from run insight", "info")
                    except Exception as _kl_err:
                        _log(f"knowledge layer ingestion failed (non-fatal): {_kl_err}", "warning")
        except Exception as _ie:
            _log(f"run insight 生成失败（不影响主流程）: {_ie}", "warning")
        _snapshot_autoresearch_state(run_id)


def _run_autoresearch_thread(
    run_id: str,
    baseline_workflow_id: str,
    windows: List[dict],
    evaluation_contract: Dict[str, Any],
    search_space: Dict[str, Any],
    max_iterations: int,
    top_k: int,
    policy: Dict[str, Any],
    compare_config: Dict[str, Any],
    cancel_event: threading.Event,
) -> None:
    try:
        asyncio.run(
            _run_autoresearch_task(
                run_id=run_id,
                baseline_workflow_id=baseline_workflow_id,
                windows=windows,
                evaluation_contract=evaluation_contract,
                search_space=search_space,
                max_iterations=max_iterations,
                top_k=top_k,
                policy=policy,
                compare_config=compare_config,
                cancel_event=cancel_event,
            )
        )
    except Exception as e:
        state = _auto_research_store.get(run_id) or {}
        state["status"] = "failed"
        state["error"] = str(e)
        state["finished_at"] = datetime.now().isoformat()
        _auto_research_store[run_id] = state
        _snapshot_autoresearch_state(run_id)
        _auto_research_cancel_events.pop(run_id, None)


@router.post("/compare-backtest-batch-async", summary="Baseline/Challenger 多窗回测比对（异步）")
async def compare_backtest_batch_async(payload: dict):
    """
    对 baseline_workflow_id 与 一个或多个 challenger 在多个时间窗上执行相同 evaluation_contract 的回测，
    聚合 candidate_score，可选写入候选池。支持 challenger_workflow_ids 数组批量比对。
    """
    baseline_id = str(payload.get("baseline_workflow_id") or "").strip()
    windows = payload.get("windows")
    raw_multi = payload.get("challenger_workflow_ids")
    challenger_id_single = str(payload.get("challenger_workflow_id") or "").strip()
    challenger_ids: List[str] = []
    if isinstance(raw_multi, list) and len(raw_multi) > 0:
        challenger_ids = [str(x).strip() for x in raw_multi if str(x).strip()]
    elif challenger_id_single:
        challenger_ids = [challenger_id_single]

    if not baseline_id:
        raise HTTPException(status_code=400, detail="需要 baseline_workflow_id")
    if not challenger_ids:
        raise HTTPException(
            status_code=400,
            detail="需要 challenger_workflow_id 或 challenger_workflow_ids（非空数组）",
        )
    if not isinstance(windows, list) or len(windows) == 0:
        raise HTTPException(status_code=400, detail="windows 必须为非空数组")

    evaluation_contract = payload.get("evaluation_contract")
    if evaluation_contract is not None and not isinstance(evaluation_contract, dict):
        raise HTTPException(status_code=400, detail="evaluation_contract 必须为对象")
    evaluation_contract = dict(evaluation_contract or {})

    try:
        score_margin = float(payload.get("score_margin", 0.0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="score_margin 必须为数字")
    add_to_candidate_pool = bool(payload.get("add_to_candidate_pool", True))

    aggregate_method = str(payload.get("aggregate_method") or "mean").strip().lower()
    if aggregate_method not in ("mean", "median", "trimmed_mean"):
        raise HTTPException(
            status_code=400,
            detail="aggregate_method 仅支持 mean / median / trimmed_mean",
        )

    min_windows_challenger_better: Optional[int] = None
    raw_min_w = payload.get("min_windows_challenger_better")
    if raw_min_w is not None and raw_min_w != "":
        try:
            min_windows_challenger_better = int(raw_min_w)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="min_windows_challenger_better 必须为整数")
        if min_windows_challenger_better < 0:
            raise HTTPException(status_code=400, detail="min_windows_challenger_better 不能为负")

    # baseline 专属参数覆盖
    baseline_config_override = payload.get("baseline_config_override")
    if baseline_config_override is not None and not isinstance(baseline_config_override, dict):
        raise HTTPException(status_code=400, detail="baseline_config_override 必须为对象")
    baseline_config_override = dict(baseline_config_override or {}) or None

    # challenger 专属参数覆盖（只影响 challenger，不影响 baseline）
    challenger_config_override = payload.get("challenger_config_override")
    if challenger_config_override is not None and not isinstance(challenger_config_override, dict):
        raise HTTPException(status_code=400, detail="challenger_config_override 必须为对象")
    challenger_config_override = dict(challenger_config_override or {}) or None

    comparison_id = f"cmp-{uuid.uuid4().hex[:12]}"
    _init_comparison_state(comparison_id)
    cancel_event = threading.Event()
    _comparison_cancel_events[comparison_id] = cancel_event

    thread = threading.Thread(
        target=_run_compare_async_thread,
        args=(
            comparison_id,
            baseline_id,
            challenger_ids,
            windows,
            evaluation_contract,
            score_margin,
            add_to_candidate_pool,
            cancel_event,
            aggregate_method,
            min_windows_challenger_better,
            challenger_config_override,
            baseline_config_override,
        ),
        daemon=True,
    )
    thread.start()
    return {"comparison_id": comparison_id, "status": "pending"}


@router.get("/compare-backtest-status/{comparison_id}", summary="查询 Baseline/Challenger 比对状态")
async def get_compare_backtest_status(comparison_id: str):
    state = _comparison_store.get(comparison_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"比对任务不存在: {comparison_id}")
    return _sanitize_json_floats(dict(state))


@router.post("/compare-backtest-cancel/{comparison_id}", summary="取消 Baseline/Challenger 比对")
async def cancel_compare_backtest(comparison_id: str):
    event = _comparison_cancel_events.get(comparison_id)
    if event is None:
        return {"success": False, "message": "没有正在运行的比对任务或已结束"}
    event.set()
    return {"success": True, "message": "已发送比对取消信号"}


@router.post("/auto-research-async", summary="自动持续实验（参数搜索 + 自动择优）")
async def start_auto_research(payload: dict):
    baseline_id = str(payload.get("baseline_workflow_id") or "").strip()
    windows = payload.get("windows")
    if not baseline_id:
        raise HTTPException(status_code=400, detail="需要 baseline_workflow_id")
    if not isinstance(windows, list) or len(windows) == 0:
        raise HTTPException(status_code=400, detail="windows 必须为非空数组")

    # @AI_GENERATED: 启动时打印所有参数，方便调试确认
    print("\n" + "=" * 60)
    print("  [AutoResearch] 启动参数汇总")
    print("=" * 60)
    print(f"  baseline_workflow_id: {baseline_id}")
    print(f"  windows ({len(windows)} 个):")
    for w in windows:
        print(f"    {w.get('start_date', '?')} ~ {w.get('end_date', '?')}")
    print(f"  evaluation_contract: {payload.get('evaluation_contract')}")
    print(f"  max_iterations: {payload.get('max_iterations')}")
    print(f"  top_k: {payload.get('top_k')}")
    print(f"  search_space: {payload.get('search_space')}")
    print(f"  registry_id: {payload.get('registry_id', '(auto)')}")
    print(f"  compare_config: {payload.get('compare_config')}")
    print("=" * 60 + "\n")
    # @AI_GENERATED: end

    evaluation_contract = payload.get("evaluation_contract")
    if evaluation_contract is not None and not isinstance(evaluation_contract, dict):
        raise HTTPException(status_code=400, detail="evaluation_contract 必须为对象")
    evaluation_contract = dict(evaluation_contract or {})

    search_space = payload.get("search_space")
    if search_space is not None and not isinstance(search_space, dict):
        raise HTTPException(status_code=400, detail="search_space 必须为对象")
    search_space = dict(search_space or {})
    if not search_space:
        search_space = {
            "train_days": [30, 45, 60],
            "auto_tune_n_trials": [3, 5, 8],
            "backtest_train_days": [30, 45, 60],
        }

    try:
        max_iterations = int(payload.get("max_iterations", 12))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="max_iterations 必须为整数")
    if max_iterations <= 0 or max_iterations > 200:
        raise HTTPException(status_code=400, detail="max_iterations 范围必须在 1..200")

    try:
        top_k = int(payload.get("top_k", 10))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="top_k 必须为整数")
    if top_k <= 0 or top_k > 100:
        raise HTTPException(status_code=400, detail="top_k 范围必须在 1..100")

    ranking_policy = payload.get("ranking_policy")
    if ranking_policy is not None and not isinstance(ranking_policy, dict):
        raise HTTPException(status_code=400, detail="ranking_policy 必须为对象")
    policy = {
        "min_mape_improvement": 0.0,
        "max_abs_bias": None,
        "max_p95_ape": None,
    }
    policy.update(dict(ranking_policy or {}))

    compare_config = payload.get("compare_config")
    if compare_config is not None and not isinstance(compare_config, dict):
        raise HTTPException(status_code=400, detail="compare_config 必须为对象")
    compare_cfg = {
        "score_margin": 0.0,
        "aggregate_method": "mean",
        "min_windows_challenger_better": None,
        "add_to_candidate_pool": True,
        "anchor_baseline_contract": True,
        "reflection_interval": 5,
        "seed": int(time.time()),
    }
    compare_cfg.update(dict(compare_config or {}))
    agent_mode = str(payload.get("agent_mode") or compare_cfg.get("agent_mode") or "single_agent").strip()
    if agent_mode not in ("single_agent", "multi_agent"):
        agent_mode = "single_agent"
    compare_cfg["agent_mode"] = agent_mode
    # Top-level overrides (frontend sends a duplicated safety copy to avoid nested drop issues)
    if "auto_full_automation" in payload:
        compare_cfg["auto_full_automation"] = bool(payload.get("auto_full_automation"))
    if "auto_apply_risk_level_max" in payload:
        risk_max = str(payload.get("auto_apply_risk_level_max") or "medium").lower()
        compare_cfg["auto_apply_risk_level_max"] = "medium" if risk_max == "medium" else "low"
    if "memory_top_k" in payload:
        try:
            compare_cfg["memory_top_k"] = max(1, min(8, int(payload.get("memory_top_k", 3))))
        except (TypeError, ValueError):
            compare_cfg["memory_top_k"] = 3
    # Backend safety: when full automation is enabled, never block on manual gate.
    if bool(compare_cfg.get("auto_full_automation", False)):
        compare_cfg["manual_gate"] = False
        compare_cfg.setdefault("auto_generate_proposal", True)
        compare_cfg.setdefault("auto_apply_recommended", True)
    expected_cfg = payload.get("_client_expected_compare_config")
    expected_search_space = payload.get("_client_expected_search_space")
    alignment = {
        "checked": False,
        "matched": True,
        "mismatches": [],
        "expected": {},
        "effective": {},
        "search_space_checked": False,
        "search_space_matched": True,
        "search_space_mismatches": [],
    }
    if isinstance(expected_cfg, dict):
        alignment["checked"] = True
        keys = [
            "manual_gate",
            "auto_full_automation",
            "auto_generate_proposal",
            "auto_apply_recommended",
            "auto_apply_risk_level_max",
            "memory_top_k",
            "multi_fidelity_enabled",
            "asha_enabled",
            "multi_fidelity_initial_fraction",
            "multi_fidelity_min_windows",
            "multi_fidelity_reduction_factor",
            "multi_fidelity_min_promotions",
            "aggregate_method",
            "score_margin",
        ]
        mismatches: List[Dict[str, Any]] = []
        expected_view: Dict[str, Any] = {}
        effective_view: Dict[str, Any] = {}
        for k in keys:
            ev = expected_cfg.get(k)
            av = compare_cfg.get(k)
            expected_view[k] = ev
            effective_view[k] = av
            if ev != av:
                mismatches.append({"key": k, "expected": ev, "effective": av})
        alignment["expected"] = expected_view
        alignment["effective"] = effective_view
        alignment["mismatches"] = mismatches
        alignment["matched"] = len(mismatches) == 0
    if isinstance(expected_search_space, dict):
        alignment["search_space_checked"] = True
        ss_mismatches: List[Dict[str, Any]] = []
        for k in sorted(set(list(expected_search_space.keys()) + list(search_space.keys()))):
            ev = expected_search_space.get(k)
            av = search_space.get(k)
            if ev != av:
                ss_mismatches.append({"key": k, "expected": ev, "effective": av})
        alignment["search_space_mismatches"] = ss_mismatches
        alignment["search_space_matched"] = len(ss_mismatches) == 0
    alignment["matched"] = bool(alignment["matched"]) and bool(alignment["search_space_matched"])

    scenario_tags = payload.get("scenario_tags")
    if scenario_tags is None:
        scenario_tags = payload.get("scenario_tag")
    if scenario_tags is None:
        scenario_tags = []
    if isinstance(scenario_tags, str):
        scenario_tags = [scenario_tags]
    if not isinstance(scenario_tags, list):
        raise HTTPException(status_code=400, detail="scenario_tags 必须为数组/字符串")
    scenario_tags = [str(x).strip() for x in scenario_tags if str(x).strip()]

    discovery_snapshot = _discover_forecast_operators_payload()
    allowed_operator_ids = {str(x.get("function_id")) for x in (discovery_snapshot.get("operators") or []) if x.get("function_id")}

    skip_precheck = bool(payload.get("skip_workflow_precheck", False))
    structure_profile_id = str(payload.get("structure_profile_id") or "").strip()
    known_profiles = _known_structure_profile_ids()
    if not structure_profile_id and known_profiles:
        structure_profile_id = sorted(known_profiles)[0]
    if structure_profile_id and known_profiles and structure_profile_id not in known_profiles:
        raise HTTPException(status_code=400, detail=f"未知 structure_profile_id: {structure_profile_id}")

    preferred_models = payload.get("preferred_model_operator_ids")
    if preferred_models is None:
        preferred_models = payload.get("discovery_preferred_models")
    if preferred_models is not None:
        if not isinstance(preferred_models, list):
            raise HTTPException(status_code=400, detail="preferred_model_operator_ids 必须为数组")
        preferred_models = [str(x).strip() for x in preferred_models if str(x).strip()]
    else:
        preferred_models = []

    bad_pref = [x for x in preferred_models if x not in allowed_operator_ids]
    if bad_pref:
        raise HTTPException(
            status_code=400,
            detail=f"preferred_model_operator_ids 含不在可调清单内的条目: {bad_pref}",
        )

    startup_precheck_report: Optional[Dict[str, Any]] = None
    if not skip_precheck:
        pf = _workflow_preflight_report(baseline_id, max_rows=800)
        if pf.get("workflow_missing"):
            raise HTTPException(status_code=404, detail=str(pf.get("error")))
        startup_precheck_report = {k: v for k, v in pf.items() if k != "workflow_missing"}
        if not pf.get("success"):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "workflow_preflight_failed",
                    "message": "AutoResearch 启动前流水线预检未通过，请修正模板或数据后再试",
                    "preflight": startup_precheck_report,
                },
            )

    run_id = f"ares-{uuid.uuid4().hex[:12]}"
    _init_autoresearch_state(run_id)
    _auto_research_store[run_id]["baseline_workflow_id"] = baseline_id
    _auto_research_store[run_id]["windows"] = _sanitize_json_floats(windows)
    _auto_research_store[run_id]["search_space"] = _sanitize_json_floats(search_space)
    _auto_research_store[run_id]["evaluation_contract"] = _sanitize_json_floats(evaluation_contract)
    _auto_research_store[run_id]["compare_config"] = _sanitize_json_floats(compare_cfg)
    _auto_research_store[run_id]["policy"] = _sanitize_json_floats(policy)
    _auto_research_store[run_id]["top_k"] = top_k
    _auto_research_store[run_id]["max_iterations"] = max_iterations
    _auto_research_store[run_id]["agent_mode"] = agent_mode
    _auto_research_store[run_id]["config_alignment"] = _sanitize_json_floats(alignment)
    _auto_research_store[run_id]["scenario_tags"] = scenario_tags
    # 任务 9.5：支持传入 registry_id（搜索空间注册表 ID），启用注册表模式
    _registry_id_input = str(payload.get("registry_id") or "").strip()
    # 任务 25.1：未传 registry_id 时自动匹配最适合当前模板的注册表
    if not _registry_id_input:
        _registry_id_input = _auto_match_registry_for_workflow(baseline_id)
    if _registry_id_input:
        _auto_research_store[run_id]["registry_id"] = _registry_id_input
    _auto_research_store[run_id]["discovery_context"] = _sanitize_json_floats({
        "structure_profile_id": structure_profile_id,
        "preferred_model_operator_ids": preferred_models,
        "discovery_snapshot": {
            "operators_count": len(discovery_snapshot.get("operators") or []),
            "catalog_unavailable_count": len(discovery_snapshot.get("catalog_unavailable") or []),
            "discovery": discovery_snapshot.get("discovery"),
        },
        "startup_precheck": {
            "skipped": skip_precheck,
            "passed": None if skip_precheck else True,
            "execution_time": (startup_precheck_report or {}).get("executionTime"),
        },
    })
    _snapshot_autoresearch_state(run_id)
    _record_autoresearch_decision(run_id, "run_started", {
        "actor": "system",
        "baseline_workflow_id": baseline_id,
        "registry_id": _auto_research_store[run_id].get("registry_id"),
        "max_iterations": max_iterations,
        "top_k": top_k,
    })

    # Worker 模式：提交 job 到 SQLite 队列，由独立 worker 进程执行
    _jq.submit_job(run_id, {
        "baseline_workflow_id": baseline_id,
        "windows": windows,
        "evaluation_contract": evaluation_contract,
        "search_space": search_space,
        "max_iterations": max_iterations,
        "top_k": top_k,
        "policy": policy,
        "compare_config": compare_cfg,
        "resume": False,
    })

    return {"run_id": run_id, "status": "pending"}


@router.get("/auto-research-status/{run_id}", summary="查询自动实验状态")
async def get_auto_research_status(run_id: str):
    state, _source = _load_autoresearch_state_for_view(run_id)
    view = dict(state)
    _refresh_autoresearch_control_plane(run_id, view, batch_groups=view.get("latest_batch_groups") or [])
    if not view.get("last_failed_trial"):
        try:
            failed_trials = [
                row for row in _auto_research_persister.list_trials(run_id, limit=1000)
                if str(row.get("status") or "") in {"failed", "error"}
            ]
            if failed_trials:
                view["last_failed_trial"] = failed_trials[-1]
                view.setdefault("error", failed_trials[-1].get("error_message") or failed_trials[-1].get("error"))
        except Exception:
            pass
    cfg = (view.get("compare_config") or {}) if isinstance(view.get("compare_config"), dict) else {}
    risk_max = str(cfg.get("auto_apply_risk_level_max") or "medium").lower()
    auto_apply = bool(cfg.get("auto_apply_recommended"))
    enriched_history = _auto_research_auto_apply_policy.enrich_history(
        view.get("glm_call_history"),
        proposals=_auto_research_proposals_store,
        risk_max=risk_max,
        auto_apply=auto_apply,
    )
    if enriched_history:
        view["glm_call_history"] = enriched_history
    return _sanitize_json_floats(view)


@router.get("/auto-research-report/{run_id}", summary="查询自动实验结构化报告")
async def get_auto_research_report(run_id: str):
    state, _source = _load_autoresearch_state_for_view(run_id)
    return _build_autoresearch_report(state)


@router.post("/auto-research/{run_id}/generate-insight", summary="手动触发 run insight 生成")
async def generate_run_insight_api(run_id: str):
    """
    任务 28.5：手动触发 insight 生成（用于已完成但没自动生成的旧 run）。
    """
    state = _auto_research_store.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"自动实验任务不存在: {run_id}")
    insight = await _generate_run_insight_with_glm(run_id)
    if "error" in insight:
        raise HTTPException(status_code=400, detail=insight["error"])
    _save_run_insight(run_id, insight)
    return _sanitize_json_floats({"success": True, "run_id": run_id, "insight": insight})


async def _generate_ranked_proposals_for_run(
    run_id: str,
    state: Dict[str, Any],
    count: int = 3,
    memory_top_k: int = 3,
) -> Dict[str, Any]:
    report = _build_autoresearch_report(state)
    baseline_wf_id = str(report.get("baseline_workflow_id") or "")
    scenario_tags = report.get("scenario_tags") if isinstance(report.get("scenario_tags"), list) else []
    memory_refs = _retrieve_memory_cases(
        baseline_wf_id,
        scenario_tags,
        limit=max(1, min(8, int(memory_top_k))),
        query_fingerprint=_compute_scenario_fingerprint(state),
        query_diagnosis=str((_compute_error_diagnosis(_build_autoresearch_report(state)) or {}).get("primary_error_source") or ""),
    ) if baseline_wf_id else []
    report["memory_references"] = memory_refs
    report["memory_retrieval_meta"] = {
        "enabled": True,
        "top_k": memory_top_k,
        "hit_count": len(memory_refs),
    }
    variants = _generate_proposal_variants(report, count=count)
    glm_pack = await _glm_generate_proposal_candidates(report)
    glm_candidates = glm_pack.get("candidates") if isinstance(glm_pack, dict) else []
    if str(report.get("agent_mode") or "single_agent") == "multi_agent":
        try:
            from services.agent_orchestrator import AgentOrchestrator
            from services.dataset_profiler_models import CrossWindowPattern, TestProfile, TrainProfile, TriDatasetDiagnosis

            latest_profile = (report.get("dataset_profiles") or [{}])[-1]
            if not isinstance(latest_profile, dict):
                latest_profile = {}
            train_profile = latest_profile.get("train_profile")
            if not isinstance(train_profile, dict):
                train_profile = {
                    "load_curve_stats": {},
                    "peak_valley_distribution": {},
                    "data_quality": {},
                    "periodicity_strength": {},
                    "period_distribution": {},
                    "dominant_pattern": "unknown",
                    "weekday_weekend_gap": None,
                    "train_fit_mape": None,
                }
            test_profile = latest_profile.get("test_profile")
            if not isinstance(test_profile, dict):
                test_profiles = latest_profile.get("test_profiles") if isinstance(latest_profile.get("test_profiles"), list) else []
                test_profile = test_profiles[-1] if test_profiles and isinstance(test_profiles[-1], dict) else {
                    "actual_vs_predicted": [],
                    "overall_mape": 0.0,
                    "overall_rmse": 0.0,
                    "max_single_point_error": {},
                    "period_error_breakdown": {},
                    "peak_error_ratio": 0.0,
                    "valley_error_ratio": 0.0,
                    "high_error_at_extremes": False,
                    "day_type": "unknown",
                }
            diagnosis = report.get("tri_dataset_diagnosis") or latest_profile.get("tri_dataset_diagnosis") or {
                "pattern_consistency": {"status": "unknown"},
                "overfit_detection": "not_confirmed",
                "generalization_assessment": "unknown",
                "diagnosis_conclusion": "",
            }
            cross_window = latest_profile.get("cross_window_pattern")
            agent_context = {
                "train_profile": TrainProfile.from_dict(train_profile),
                "test_profile": TestProfile.from_dict(test_profile),
                "tri_dataset_diagnosis": TriDatasetDiagnosis.from_dict(diagnosis),
                "cross_window_pattern": (
                    CrossWindowPattern.from_dict(cross_window)
                    if isinstance(cross_window, dict) else None
                ),
            }
            orchestrator = AgentOrchestrator(
                "multi_agent",
                glm_generate=lambda _: glm_candidates if isinstance(glm_candidates, list) else [],
            )
            agent_result = orchestrator.run_pipeline(agent_context, state)
            report["agent_orchestrator"] = {
                "mode": agent_result.get("mode"),
                "patch_count": len(agent_result.get("patches") or []),
            }
            state["agent_traces"] = (state.get("agent_traces") or [])[-300:]
        except Exception as exc:
            state.setdefault("agent_traces", []).append({
                "from_agent": "orchestrator",
                "to_agent": "single_agent",
                "message_type": "fallback",
                "payload": {"error": str(exc)},
                "timestamp": datetime.utcnow().isoformat(),
            })
            state["agent_traces"] = state["agent_traces"][-300:]
    # GLM 候选优先：先放 GLM 候选（保持 GLM 自身排序），规则候选作为兜底
    # 这样并发组验证的是 GLM 的假设，而不是被规则分数打乱顺序
    _ordered_variants: List[Dict[str, Any]] = []
    _glm_count = 0
    if isinstance(glm_candidates, list) and glm_candidates:
        for c in glm_candidates:
            if isinstance(c, dict):
                c["_source"] = "glm"
                _ordered_variants.append(c)
                _glm_count += 1
    # 规则候选作为兜底（当 GLM 候选不足时补位）
    for v in variants:
        if isinstance(v, dict):
            v["_source"] = "rule"
            _ordered_variants.append(v)
    proposals: List[Dict[str, Any]] = []
    for idx, generated in enumerate(_ordered_variants):
        proposal_id = f"prop-{uuid.uuid4().hex[:12]}"
        proposal = _auto_research_proposal_manager.build_proposal(
            generated,
            proposal_id=proposal_id,
            run_id=run_id,
            candidate_index=idx + 1,
            memory_references=memory_refs,
        )
        baseline_wf_for_val = str(state.get("baseline_workflow_id") or "").strip()
        validation = _validate_proposal_patch(proposal, baseline_workflow_id=baseline_wf_for_val or None)
        proposal["validation"] = validation
        proposal["experiment_quality"] = _score_proposal_experiment_quality(proposal)
        # 任务 27.2：注入 diagnosis confidence 供评分器使用
        _diag = _compute_error_diagnosis(report)
        proposal["_diagnosis_confidence"] = str((_diag or {}).get("confidence") or "medium")
        # 任务 27.3：注入连续类型计数，供评分器降分
        proposal["_consecutive_type_count"] = dict(state.get("consecutive_type_count") or {})
        proposal["score"] = _score_proposal_candidate(proposal)
        _auto_research_proposals_store[proposal_id] = proposal
        proposals.append(proposal)
    ranked = _auto_research_proposal_manager.rank_proposals(proposals)
    recommended = ranked[0] if ranked else None
    return _sanitize_json_floats({
        "run_id": run_id,
        "generated_count": len(proposals),
        "recommended_proposal_id": (recommended or {}).get("proposal_id"),
        "proposals": ranked,
        "glm_input_debug": glm_pack.get("glm_input_debug") if isinstance(glm_pack, dict) else {},
        "glm_meta": {
            "enabled": _env_bool("GLM_ENABLE", False),
            "llm_used": bool(glm_pack.get("llm_used")) if isinstance(glm_pack, dict) else False,
            "llm_error": glm_pack.get("llm_error") if isinstance(glm_pack, dict) else None,
            "candidates_count": len(glm_candidates) if isinstance(glm_candidates, list) else 0,
            "memory_hit_count": len(memory_refs),
            "memory_top_k": memory_top_k,
            "model": os.getenv("GLM_MODEL", "glm-5.1"),
            "base_url": os.getenv("GLM_BASE_URL", ""),
        },
    })


@router.post("/auto-research/proposal/generate", summary="生成自动实验建议草案（Diff）")
async def generate_auto_research_proposal(payload: dict):
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id 必填")
    state = _auto_research_store.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"自动实验任务不存在: {run_id}")
    try:
        memory_top_k = max(1, min(8, int(payload.get("memory_top_k", 3))))
    except (TypeError, ValueError):
        memory_top_k = 3
    try:
        count = int(payload.get("count", 3))
    except (TypeError, ValueError):
        count = 3
    return await _generate_ranked_proposals_for_run(
        run_id=run_id,
        state=state,
        count=count,
        memory_top_k=memory_top_k,
    )


@router.get("/auto-research/proposal/{proposal_id}", summary="查询建议草案详情")
async def get_auto_research_proposal(proposal_id: str):
    proposal = _auto_research_proposals_store.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"建议草案不存在: {proposal_id}")
    return _sanitize_json_floats(dict(proposal))


@router.post("/auto-research/proposal/{proposal_id}/apply", summary="应用建议草案")
async def apply_auto_research_proposal(proposal_id: str, payload: dict = None):
    proposal = _auto_research_proposals_store.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"建议草案不存在: {proposal_id}")
    if proposal.get("status") != "pending_review":
        raise HTTPException(status_code=400, detail="该建议草案已被处理")
    run_id = str(proposal.get("run_id") or "")
    state = _auto_research_store.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"自动实验任务不存在: {run_id}")
    baseline_wf = str(state.get("baseline_workflow_id") or "").strip()
    validation = _validate_proposal_patch(proposal, baseline_workflow_id=baseline_wf or None)
    if not validation.get("valid"):
        proposal["validation"] = validation
        _auto_research_proposals_store[proposal_id] = proposal
        raise HTTPException(status_code=400, detail={"message": "建议草案校验失败", "errors": validation.get("errors")})
    apply_result = _auto_research_proposal_manager.apply_to_state(
        state,
        proposal,
        proposal_id=proposal_id,
        allowed_global_config_keys=_ALLOWED_GLOBAL_CONFIG_PATCH_KEYS,
    )
    runtime_patch = apply_result["runtime_patch"]
    effective_from_iteration = apply_result["effective_from_iteration"]
    # 日志打印：确认三个字段都写入
    import logging as _logging
    _n_switches = len((runtime_patch.get("structure_patch") or {}).get("node_switches") or [])
    _n_npp = len(runtime_patch.get("node_param_patches") or [])
    _n_gcp = len((runtime_patch.get("global_config_patch") or {}).keys())
    _logging.getLogger(__name__).info(
        f"已应用建议 {proposal_id}: structure_switches={_n_switches}, node_params={_n_npp}, global_config_keys={_n_gcp}"
    )
    gate = state.get("gate")
    if isinstance(gate, dict) and not bool(gate.get("released")):
        gate["released"] = True
        gate["release_reason"] = "proposal_applied"
        gate["released_at"] = datetime.now().isoformat()
        state["gate"] = gate
    reviewer = None
    if isinstance(payload, dict):
        reviewer = payload.get("reviewer")
    _auto_research_proposal_manager.mark_applied(
        proposal,
        reviewer=reviewer,
        validation=validation,
    )
    _auto_research_store[run_id] = state
    _auto_research_proposals_store[proposal_id] = proposal
    _record_autoresearch_decision(run_id, "proposal_applied", {
        "actor": reviewer or "system",
        "proposal_id": proposal_id,
        "risk_level": proposal.get("risk_level"),
        "validation": validation,
        "reason": "proposal applied",
        "payload": {
            "runtime_patch": runtime_patch,
            "hypothesis": proposal.get("hypothesis"),
            "effective_from_iteration": effective_from_iteration,
        },
    })
    _snapshot_autoresearch_state(run_id)
    return _sanitize_json_floats({
        "success": True,
        "proposal_id": proposal_id,
        "run_id": run_id,
        "runtime_patch": runtime_patch,
    })


@router.post("/auto-research/proposal/{proposal_id}/reject", summary="拒绝建议草案")
async def reject_auto_research_proposal(proposal_id: str, payload: dict = None):
    proposal = _auto_research_proposals_store.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"建议草案不存在: {proposal_id}")
    if proposal.get("status") != "pending_review":
        raise HTTPException(status_code=400, detail="该建议草案已被处理")
    reviewer = None
    reason = None
    if isinstance(payload, dict):
        reviewer = payload.get("reviewer")
        reason = payload.get("reason")
    _auto_research_proposal_manager.mark_rejected(
        proposal,
        reviewer=reviewer,
        reason=reason,
    )
    _auto_research_proposals_store[proposal_id] = proposal
    run_id = str(proposal.get("run_id") or "")
    if run_id:
        _record_autoresearch_decision(run_id, "proposal_rejected", {
            "actor": reviewer or "user",
            "proposal_id": proposal_id,
            "reason": reason or "proposal rejected",
            "risk_level": proposal.get("risk_level"),
        })
    state = _auto_research_store.get(run_id)
    if isinstance(state, dict):
        gate = state.get("gate")
        if isinstance(gate, dict) and not bool(gate.get("released")):
            gate["released"] = True
            gate["release_reason"] = "proposal_rejected"
            gate["released_at"] = datetime.now().isoformat()
            state["gate"] = gate
            if str(state.get("status")) == "waiting_review":
                state["status"] = "running"
            _auto_research_store[run_id] = state
            _snapshot_autoresearch_state(run_id)
    return _sanitize_json_floats({"success": True, "proposal_id": proposal_id})


@router.post("/auto-research-continue/{run_id}", summary="人工闸门：继续下一轮")
async def continue_auto_research(run_id: str, payload: dict = None):
    state = _auto_research_store.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"自动实验任务不存在: {run_id}")
    reviewer = payload.get("reviewer") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and bool(payload.get("enable_full_automation")):
        cfg = dict(state.get("compare_config") or {})
        cfg["auto_full_automation"] = True
        cfg["auto_generate_proposal"] = True
        cfg["auto_apply_recommended"] = True
        risk_max = str(payload.get("auto_apply_risk_level_max") or "medium").lower()
        cfg["auto_apply_risk_level_max"] = "medium" if risk_max == "medium" else "low"
        cfg["manual_gate"] = False
        try:
            cfg["memory_top_k"] = max(1, min(8, int(payload.get("memory_top_k", cfg.get("memory_top_k", 3)))))
        except (TypeError, ValueError):
            cfg["memory_top_k"] = int(cfg.get("memory_top_k", 3) or 3)
        state["compare_config"] = cfg
    gate = state.get("gate")
    if isinstance(gate, dict) and not bool(gate.get("released")):
        gate["released"] = True
        gate["release_reason"] = "manual_continue"
        gate["released_at"] = datetime.now().isoformat()
        state["gate"] = gate
    if str(state.get("status")) == "waiting_review":
        state["status"] = "running"
    _auto_research_store[run_id] = state
    _record_autoresearch_decision(run_id, "manual_continue", {
        "actor": reviewer or "user",
        "reason": "manual continue",
        "payload": payload or {},
    })
    _snapshot_autoresearch_state(run_id)
    return _sanitize_json_floats({"success": True, "run_id": run_id, "reviewer": reviewer})


@router.get("/auto-research-memory", summary="查看自动实验经验库（最近 N 条）")
async def list_auto_research_memory(limit: int = 50):
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 50
    n = max(1, min(n, 500))
    rows = _load_memory_cases()
    return _sanitize_json_floats({
        "total": len(rows),
        "cases": rows[-n:],
    })


@router.get("/auto-research-selfcheck/{run_id}", summary="自动实验一键自检")
async def auto_research_selfcheck(run_id: str):
    state = _auto_research_store.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"自动实验任务不存在: {run_id}")
    status = str(state.get("status") or "")
    cfg = (state.get("compare_config") or {}) if isinstance(state.get("compare_config"), dict) else {}
    alignment = (state.get("config_alignment") or {}) if isinstance(state.get("config_alignment"), dict) else {}
    latest_auto = (state.get("latest_auto_proposal") or {}) if isinstance(state.get("latest_auto_proposal"), dict) else {}
    latest_adjust = (state.get("latest_auto_adjustment") or {}) if isinstance(state.get("latest_auto_adjustment"), dict) else {}
    report = _build_autoresearch_report(state)
    summary = (report.get("summary") or {}) if isinstance(report.get("summary"), dict) else {}
    failure_stats = (summary.get("failure_stats") or {}) if isinstance(summary.get("failure_stats"), dict) else {}

    checks: List[Dict[str, Any]] = []
    auto_full = bool(cfg.get("auto_full_automation"))
    manual_gate = bool(cfg.get("manual_gate"))
    checks.append({
        "item": "全自动模式与人工闸门",
        "status": "pass" if (not auto_full or not manual_gate) else "warn",
        "detail": f"auto_full_automation={auto_full}, manual_gate={manual_gate}",
        "suggestion": "全自动开启时建议 manual_gate=false"
        if (auto_full and manual_gate) else "配置正常",
    })

    align_checked = bool(alignment.get("checked"))
    align_ok = bool(alignment.get("matched"))
    checks.append({
        "item": "前后端参数对齐",
        "status": "pass" if (align_checked and align_ok) else ("warn" if align_checked else "info"),
        "detail": (
            "checked=true, matched=true" if (align_checked and align_ok)
            else f"checked={align_checked}, matched={align_ok}, mismatches={len((alignment.get('mismatches') or []))}, search_space_mismatches={len((alignment.get('search_space_mismatches') or []))}"
        ),
        "suggestion": "检查前端开关与搜索空间字段；以状态卡对齐提示为准",
    })

    no_test = int(failure_stats.get("no_test_data") or 0)
    no_train = int(failure_stats.get("insufficient_train_data") or 0)
    checks.append({
        "item": "数据覆盖健康度",
        "status": "pass" if (no_test == 0 and no_train == 0) else "warn",
        "detail": f"no_test_data={no_test}, insufficient_train_data={no_train}",
        "suggestion": "前移时间窗或下调 train_days/backtest_train_days；必要时关闭 window_filter/mask",
    })

    rec_generated = bool(latest_auto.get("generated_at"))
    rec_id = str(latest_auto.get("recommended_proposal_id") or "")
    applied_id = str(state.get("latest_applied_proposal_id") or "")
    checks.append({
        "item": "建议链路（生成/应用）",
        "status": "pass" if (not auto_full or rec_generated) else "warn",
        "detail": f"generated={rec_generated}, recommended={rec_id or '-'}, applied={applied_id or '-'}",
        "suggestion": "若持续未生成，检查 GLM 配置或自动生成开关",
    })

    checks.append({
        "item": "自动纠偏状态",
        "status": "info" if latest_adjust else "pass",
        "detail": str(latest_adjust.get("message") or "暂无自动纠偏触发"),
        "suggestion": "出现数据问题时自动纠偏会写入 latest_auto_adjustment",
    })

    return _sanitize_json_floats({
        "run_id": run_id,
        "status": status,
        "checked_at": datetime.now().isoformat(),
        "checks": checks,
    })


@router.post("/auto-research-cancel/{run_id}", summary="取消自动实验")
async def cancel_auto_research(run_id: str):
    # Worker 模式：通过 job queue 标记取消
    _jq.request_cancel(run_id)
    # 兼容：如果内存中有 cancel event（旧线程模式残留），也设置
    event = _auto_research_cancel_events.get(run_id)
    if event is not None:
        event.set()
    state = _auto_research_store.get(run_id) or {}
    if str(state.get("status") or "").lower() == "running":
        state["status"] = "cancelling"
    current_cmp_id = state.get("current_comparison_id")
    if current_cmp_id:
        cmp_event = _comparison_cancel_events.get(str(current_cmp_id))
        if cmp_event is not None:
            cmp_event.set()
        cmp_state = _comparison_store.get(str(current_cmp_id))
        if isinstance(cmp_state, dict) and str(cmp_state.get("status") or "").lower() == "running":
            cmp_state["status"] = "cancelling"
            cmp_state["error"] = "收到取消请求，正在中断当前任务"
            _comparison_store[str(current_cmp_id)] = cmp_state
    state["cancel_requested_at"] = datetime.now().isoformat()
    state["cancel_requested"] = True
    state["error"] = "收到取消请求，正在停止当前任务"
    _auto_research_store[run_id] = state
    _record_autoresearch_decision(run_id, "cancel_requested", {
        "actor": "user",
        "reason": "cancel requested",
        "payload": {"current_comparison_id": current_cmp_id},
    })
    _snapshot_autoresearch_state(run_id)
    return {"success": True, "message": "已发送自动实验取消信号（含当前比对子任务）"}


@router.post("/auto-research-resume/{run_id}", summary="从中断处恢复自动实验")
async def resume_auto_research(run_id: str, payload: dict = None):
    """
    恢复一个 interrupted / failed / cancelled 状态的 AutoResearch run。
    从最后完整 trial 的下一轮继续，不重复已完成轮次。
    """
    payload = payload or {}

    # 1. 检查内存中是否已有该 run（正在跑）
    job = _jq.get_job(run_id)
    job_status = str((job or {}).get("status") or "").lower()
    job_cancel_requested = bool((job or {}).get("cancel_requested"))
    if run_id in _auto_research_store:
        mem_status = str(_auto_research_store[run_id].get("status") or "").lower()
        if mem_status in ("running", "waiting_review"):
            raise HTTPException(status_code=409, detail=f"run {run_id} 当前状态为 {mem_status}，无需恢复")
        if mem_status == "pending" and job_status in ("pending", "running") and not job_cancel_requested:
            raise HTTPException(status_code=409, detail=f"run {run_id} 当前状态为 pending，等待 worker 领取，无需恢复")

    # 2. 从磁盘加载 snapshot
    snapshot = _auto_research_persister.load_snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"找不到 run: {run_id}")

    status = str(snapshot.get("status") or "").lower()
    if status not in ("interrupted", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"run 状态为 {status}，只有 interrupted/failed/cancelled 状态可恢复",
        )

    recoverable = snapshot.get("recoverable", True)
    if not recoverable:
        raise HTTPException(status_code=400, detail="该 run 标记为不可恢复（recoverable=false）")

    # 3. 确定恢复起始轮次
    # @AI_GENERATED: Phase 2 — 读开关开启时优先走 SQL 取 completed_iterations
    completed_iterations = set()
    _used_db_for_completed = False
    try:
        from services.db.repositories import get_autoresearch_repo, is_db_read_enabled
        if is_db_read_enabled():
            _resume_repo = get_autoresearch_repo()
            if _resume_repo is not None:
                completed_iterations = _resume_repo.get_completed_iterations(run_id)
                _used_db_for_completed = True
    except Exception as _db_exc:
        logger.warning("resume: DB get_completed_iterations failed (fallback to trials): %s", _db_exc)
        completed_iterations = set()
        _used_db_for_completed = False

    if not _used_db_for_completed:
        # 兜底：走原来 trials 列表逻辑
        trials = _auto_research_persister.list_trials(run_id, limit=10000)
        for trial in trials:
            it_no = trial.get("iteration_no")
            trial_status = str(trial.get("status") or "").lower()
            if it_no is not None and trial_status in ("success", "failed", "pruned"):
                completed_iterations.add(int(it_no))
    # @AI_GENERATED: end

    max_completed = max(completed_iterations) if completed_iterations else 0
    resume_from_iteration = max_completed + 1

    # 4. 恢复关键参数
    baseline_workflow_id = str(snapshot.get("baseline_workflow_id") or "").strip()
    if not baseline_workflow_id:
        raise HTTPException(status_code=400, detail="snapshot 中缺少 baseline_workflow_id")

    search_space = snapshot.get("search_space") or {}
    evaluation_contract = snapshot.get("evaluation_contract") or {}
    compare_cfg = snapshot.get("compare_config") or {}
    progress = snapshot.get("progress") or {}
    total_iterations = int(snapshot.get("max_iterations") or progress.get("total_iterations") or 12)
    remaining_iterations = total_iterations - max_completed
    if remaining_iterations <= 0:
        raise HTTPException(status_code=400, detail=f"所有 {total_iterations} 轮已完成，无需恢复")

    top_k = int(snapshot.get("top_k") or compare_cfg.get("top_k") or 10)
    policy = snapshot.get("policy") if isinstance(snapshot.get("policy"), dict) else {
        "min_mape_improvement": 0.0,
        "max_abs_bias": None,
        "max_p95_ape": None,
    }

    # 5. 恢复 windows（从 snapshot 的 compare_config 或 iterations 中提取）
    windows = snapshot.get("windows") or compare_cfg.get("windows")
    if not windows:
        # 尝试从前端 payload 获取
        windows = (payload or {}).get("windows")
    if not isinstance(windows, list) or len(windows) == 0:
        raise HTTPException(
            status_code=400,
            detail="无法从 snapshot 恢复 windows，请在请求 body 中提供 windows 数组",
        )

    # 6. 恢复内存状态
    _auto_research_store[run_id] = snapshot
    _auto_research_store[run_id]["status"] = "running"
    _auto_research_store[run_id]["error"] = None
    _auto_research_store[run_id]["resumed_at"] = datetime.now().isoformat()
    _auto_research_store[run_id]["resume_from_iteration"] = resume_from_iteration
    _auto_research_store[run_id]["progress"] = {"iteration": max_completed, "total_iterations": total_iterations}
    _auto_research_store[run_id]["max_iterations"] = total_iterations
    _auto_research_store[run_id]["top_k"] = top_k
    _auto_research_store[run_id]["policy"] = _sanitize_json_floats(policy)
    _auto_research_store[run_id]["windows"] = _sanitize_json_floats(windows)
    # 保留已有的 runtime_patch、top_candidates、best_candidate 等
    _snapshot_autoresearch_state(run_id)

    # 7. 记录 decision
    _record_autoresearch_decision(run_id, "run_resumed", {
        "actor": "user",
        "resume_from_iteration": resume_from_iteration,
        "completed_iterations": sorted(completed_iterations),
        "remaining_iterations": remaining_iterations,
    })

    # 8. Worker 模式：提交 resume job 到 SQLite 队列
    _jq.submit_job(run_id, {
        "baseline_workflow_id": baseline_workflow_id,
        "windows": windows,
        "evaluation_contract": evaluation_contract,
        "search_space": search_space,
        "max_iterations": total_iterations,
        "top_k": top_k,
        "policy": policy,
        "compare_config": compare_cfg,
        "resume": True,
        "start_iteration": resume_from_iteration,
        "total_iterations": total_iterations,
    })

    return {
        "run_id": run_id,
        "status": "resumed",
        "resume_from_iteration": resume_from_iteration,
        "remaining_iterations": remaining_iterations,
        "total_iterations": total_iterations,
    }


@router.post("/{workflow_id}/backtest-async", summary="异步回测执行")
async def backtest_workflow_async(workflow_id: str, backtest_params: dict):
    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"算法模板不存在: {workflow_id}")
    metadata = workflow.metadata or {}
    global_config = dict(metadata.get("global_config", {}))

    execution_id = f"btexec-{uuid.uuid4().hex[:12]}"
    _init_async_backtest_state(execution_id, workflow_id)
    cancel_event = threading.Event()
    _backtest_async_cancel_events[execution_id] = cancel_event

    thread = threading.Thread(
        target=_run_async_backtest,
        args=(execution_id, workflow, workflow_id, dict(backtest_params), global_config, cancel_event),
        daemon=True,
    )
    thread.start()
    return {"execution_id": execution_id, "status": "pending"}


@router.get("/{workflow_id}/backtest-status/{execution_id}", summary="查询异步回测状态")
async def get_backtest_async_status(workflow_id: str, execution_id: str):
    state = _execution_store.get(execution_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"执行记录不存在: {execution_id}")
    if state.get("workflow_id") != workflow_id:
        raise HTTPException(status_code=404, detail="执行记录不属于该工作流")
    return _sanitize_json_floats({
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "status": state.get("status"),
        "stage": state.get("stage"),
        "logs": state.get("logs") or [],
        "backtest_progress": state.get("backtest_progress") or {"currentDay": 0, "totalDays": 0, "currentDate": ""},
        "backtest_result": state.get("backtest_result"),
        "error": state.get("error"),
        "created_at": state.get("created_at"),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
    })


@router.post("/{workflow_id}/backtest-cancel/{execution_id}", summary="取消异步回测")
async def cancel_backtest_workflow_async(workflow_id: str, execution_id: str):
    state = _execution_store.get(execution_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"执行记录不存在: {execution_id}")
    if state.get("workflow_id") != workflow_id:
        raise HTTPException(status_code=404, detail="执行记录不属于该工作流")
    event = _backtest_async_cancel_events.get(execution_id)
    if event is None:
        return {"success": False, "message": "没有正在运行的异步回测任务"}
    event.set()
    return {"success": True, "message": "已发送异步回测中止信号"}


@router.post("/{workflow_id}/backtest", summary="回测执行")
async def backtest_workflow(
    workflow_id: str,
    backtest_params: dict,
    request: Request,
):
    """
    按日期范围执行回测。

    Args:
        workflow_id: 算法模板ID
        backtest_params: 回测参数，包含 start_date, end_date

    Returns:
        dict: 回测汇总结果
    """
    workflow = load_workflow_from_file(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"算法模板不存在: {workflow_id}")

    metadata = workflow.metadata or {}
    global_config = dict(metadata.get("global_config", {}))

    start_date = backtest_params.get("start_date") or global_config.get("backtest_start_date")
    end_date = backtest_params.get("end_date") or global_config.get("backtest_end_date")
    if not start_date or not end_date:
        raise HTTPException(status_code=400, detail="回测参数需要 start_date 和 end_date")

    backtest_mode = str(
        backtest_params.get("backtest_mode")
        or global_config.get("backtest_mode")
        or "rolling_retrain"
    ).strip().lower()
    model_ref = (
        backtest_params.get("model_ref")
        or backtest_params.get("backtest_model_ref")
        or global_config.get("backtest_model_ref")
    )
    if backtest_mode not in ("rolling_retrain", "inference_only"):
        raise HTTPException(status_code=400, detail="backtest_mode 仅支持 rolling_retrain / inference_only")
    if backtest_mode == "inference_only" and not model_ref:
        raise HTTPException(status_code=400, detail="inference_only 回测需要提供 model_ref")

    tuning_candidates = _resolve_tuning_candidates(backtest_params, global_config)

    cancel_event = threading.Event()
    with _backtest_cancel_lock:
        _backtest_cancel_events[workflow_id] = cancel_event

    async def _disconnect_watcher():
        try:
            while True:
                if await request.is_disconnected():
                    cancel_event.set()
                    return
                await asyncio.sleep(0.25)
        except Exception:
            cancel_event.set()

    watcher = asyncio.create_task(_disconnect_watcher())
    try:
        if tuning_candidates:
            result = await _run_tuning_batch(
                workflow,
                start_date,
                end_date,
                dict(backtest_params),
                global_config,
                tuning_candidates,
                cancel_event,
            )
        else:
            if _should_use_reference_rolling_engine(workflow, backtest_params, global_config):
                result = await asyncio.to_thread(
                    _execute_backtest_reference,
                    workflow,
                    start_date,
                    end_date,
                    backtest_params,
                    global_config,
                    cancel_event,
                )
            else:
                result = await asyncio.to_thread(
                    _execute_backtest,
                    workflow,
                    start_date,
                    end_date,
                    backtest_params.get("training_node_ids"),
                    backtest_params.get("prediction_node_ids"),
                    int(backtest_params.get("train_days") or global_config.get("backtest_train_days") or 30),
                    bool(
                        backtest_params.get("apply_window_filter")
                        if backtest_params.get("apply_window_filter") is not None
                        else global_config.get("backtest_apply_window_filter", True)
                    ),
                    bool(
                        backtest_params.get("mask_target_values")
                        if backtest_params.get("mask_target_values") is not None
                        else global_config.get("backtest_mask_target_values", True)
                    ),
                    backtest_mode,
                    model_ref,
                    cancel_event,
                    None,
                    None,
                    int(backtest_params.get("gap_days") if backtest_params.get("gap_days") is not None else global_config.get("backtest_gap_days", 1)),
                )
            generate_artifacts = backtest_params.get("generate_artifacts")
            if generate_artifacts is None:
                generate_artifacts = global_config.get("backtest_generate_artifacts", True)
            out_subdir = _safe_subdir(
                backtest_params.get("output_dir") or global_config.get("backtest_output_dir")
            )
            output_base = os.path.join(_BACKTEST_ARTIFACTS_ROOT, out_subdir)
            run_id = f"{workflow_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            output_dir = os.path.join(output_base, run_id)
            artifact_paths: List[str] = []
            artifact_urls: List[str] = []
            if generate_artifacts:
                try:
                    artifact_paths = await asyncio.to_thread(
                        _save_backtest_artifacts, result.get("daily_results", []), output_dir
                    )
                    artifact_urls = [
                        f"/api/workflows/enhanced/backtest-artifacts/{run_id}/{os.path.basename(p)}"
                        for p in artifact_paths
                    ]
                except Exception as e:
                    traceback.print_exc()
                    artifact_paths = []
                    artifact_urls = []
                    result["artifact_error"] = str(e)
            result["output_dir"] = output_dir
            result["artifact_paths"] = artifact_paths
            result["artifact_urls"] = artifact_urls
            result["backtest_mode"] = backtest_mode
            result["model_ref"] = model_ref
        return _sanitize_json_floats(result)
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        with _backtest_cancel_lock:
            if _backtest_cancel_events.get(workflow_id) is cancel_event:
                _backtest_cancel_events.pop(workflow_id, None)


@router.post("/{workflow_id}/backtest/cancel", summary="中止回测")
async def cancel_backtest_workflow(workflow_id: str):
    """
    Explicitly cancel a currently running backtest for the workflow.
    """
    with _backtest_cancel_lock:
        event = _backtest_cancel_events.get(workflow_id)
        if event is None:
            return {"success": False, "message": "没有正在运行的回测任务"}
        event.set()
    return {"success": True, "message": "已发送回测中止信号"}


@router.get("/backtest-artifacts/{run_id}/{filename}", summary="回测产物文件")
async def get_backtest_artifact(run_id: str, filename: str):
    safe_run = _safe_subdir(run_id).replace("/", "")
    safe_name = os.path.basename(filename)
    file_path = os.path.abspath(os.path.join(_BACKTEST_ARTIFACTS_ROOT, "default", safe_run, safe_name))
    # Also support custom subdir layouts: scan one level under root
    if not os.path.exists(file_path):
        for sub in os.listdir(_BACKTEST_ARTIFACTS_ROOT):
            cand = os.path.abspath(os.path.join(_BACKTEST_ARTIFACTS_ROOT, sub, safe_run, safe_name))
            if os.path.exists(cand):
                file_path = cand
                break
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="artifact not found")
    root_abs = os.path.abspath(_BACKTEST_ARTIFACTS_ROOT)
    if not file_path.startswith(root_abs):
        raise HTTPException(status_code=403, detail="forbidden")
    return FileResponse(file_path)
# @AI_GENERATED: end
