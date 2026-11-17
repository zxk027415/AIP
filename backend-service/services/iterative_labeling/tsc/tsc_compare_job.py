# @AI_GENERATED
"""
异步任务入口 — 后台线程跑 TSC 多模型对比实验。

状态写入 data/tsc_experiments/{slot}/status.json。

设计文档: .kiro/specs/pv-fault-timeseries-diagnosis/design.md §三
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[3]
_EXPERIMENTS_DIR = _BACKEND / "data" / "tsc_experiments"
_COMPARE_LOCKS: Dict[str, threading.Lock] = {}
_RUNNING_JOBS: Dict[str, threading.Thread] = {}


def _slot_dir(slot: str) -> Path:
    return _EXPERIMENTS_DIR / slot


def _status_path(slot: str) -> Path:
    return _slot_dir(slot) / "status.json"


def _result_path(slot: str) -> Path:
    return _slot_dir(slot) / "latest_result.json"


def _atomic_write_json(
    path: Path,
    payload: Dict[str, Any],
    *,
    retries: int = 10,
    retry_delay: float = 0.05,
) -> None:
    """
    原子写 JSON。

    Windows 特有问题：若目标文件正被其他进程/线程打开读取（例如前端轮询
    GET /tsc/compare/status 的同时后台任务在写），os.replace 会抛
    PermissionError [WinError 5]。这类锁是瞬时的，重试即可。
    """
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", text=True)
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())

        last_err: Optional[BaseException] = None
        for attempt in range(retries):
            try:
                tmp_path.replace(path)
                return
            except PermissionError as e:  # Windows: 目标被读取方占用
                last_err = e
                time.sleep(retry_delay * (attempt + 1))
        raise last_err if last_err else RuntimeError("原子写失败")
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _write_status_safe(slot: str, payload: Dict[str, Any]) -> None:
    """
    写状态且绝不抛异常。

    状态上报是旁路，不能因为写盘失败（如 Windows 文件锁）就中断实验主流程，
    也不能在异常处理路径里掩盖原始错误。
    """
    try:
        _atomic_write_json(_status_path(slot), payload)
    except Exception:
        logger.warning("写 TSC 状态失败 slot=%s（已忽略，不影响实验）", slot, exc_info=True)


def start_tsc_compare_job(
    *,
    slot: str = "pv_fault",
    dataset_path: str,
    model_names: Optional[List[str]] = None,
    window_configs: Optional[List[Dict]] = None,
    n_repeats: int = 5,
    test_ratio: float = 0.2,
    random_state: int = 90,
    tier_filter: Optional[int] = None,
    preprocess_method: str = "per_sample_zscore",
    fault_oversample: bool = True,
    evaluation: str = "strict",
    split_mode: str = "strict",
    n_test_days: int = 3,
    held_device_ratio: float = 0.3,
    baseline_model: Optional[str] = "rocket_rf",
) -> str:
    """
    启动后台 TSC 对比实验。

    Parameters
    ----------
    evaluation : str
        'strict'（默认）—— 严格口径多次划分，输出 mean ± std，可用于对外汇报。
        'legacy'  —— 旧的单次按设备划分，仅供快速探索，**不可对外引用**。
    split_mode : str
        evaluation='strict' 时生效：strict（时间+设备双隔离）/ time / device。
    n_repeats : int
        strict 模式下是划分次数（建议 ≥10）；legacy 模式下是 CV 重复次数。

    Returns
    -------
    job_id : str
    """
    lock = _COMPARE_LOCKS.setdefault(slot, threading.Lock())
    if lock.locked():
        raise RuntimeError(f"槽位 {slot} 已有对比任务在运行中")

    job_id = f"tsc-job-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def _run():
        with lock:
            _write_status_safe(slot, {
                "status": "running",
                "job_id": job_id,
                "slot": slot,
                "dataset_path": dataset_path,
                "model_names": model_names,
                "window_configs": window_configs,
                "started_at": datetime.utcnow().isoformat(),
                "completed": 0,
                "total": None,
                "current_model": None,
                "error": None,
            })

            try:
                from .tsc_model_compare import run_model_comparison, run_strict_comparison

                def progress_cb(completed: int, total: int, current_model: str):
                    # 进度上报失败不能中断实验
                    _write_status_safe(slot, {
                        "status": "running",
                        "job_id": job_id,
                        "slot": slot,
                        "evaluation": evaluation,
                        "completed": completed,
                        "total": total,
                        "current_model": current_model,
                        "updated_at": datetime.utcnow().isoformat(),
                        "error": None,
                    })

                if evaluation == "strict":
                    wc = (window_configs or [{}])[0] or {}
                    result = run_strict_comparison(
                        dataset_path=dataset_path,
                        model_names=model_names,
                        window_length=int(wc.get("window_length", 288)),
                        stride=int(wc.get("stride", 72)),
                        min_std=float(wc.get("min_std", 1e-6)),
                        split_mode=split_mode,
                        n_repeats=n_repeats,
                        n_test_days=n_test_days,
                        held_device_ratio=held_device_ratio,
                        preprocess_method=preprocess_method,
                        baseline_model=baseline_model,
                        progress_callback=progress_cb,
                    )
                else:
                    result = run_model_comparison(
                        dataset_path=dataset_path,
                        model_names=model_names,
                        window_configs=window_configs,
                        n_repeats=n_repeats,
                        test_ratio=test_ratio,
                        random_state=random_state,
                        tier_filter=tier_filter,
                        preprocess_method=preprocess_method,
                        fault_oversample=fault_oversample,
                        progress_callback=progress_cb,
                    )

                # 结果必须落盘成功，故这里保留抛错语义（由外层 except 兜住并写 failed）
                _atomic_write_json(_result_path(slot), result)
                _write_status_safe(slot, {
                    "status": "completed",
                    "job_id": job_id,
                    "slot": slot,
                    "completed_at": datetime.utcnow().isoformat(),
                    "best_model": result.get("best_model"),
                    "error": None,
                })

            except Exception as e:
                logger.exception("TSC 对比任务失败: %s", e)
                _write_status_safe(slot, {
                    "status": "failed",
                    "job_id": job_id,
                    "slot": slot,
                    "error": str(e),
                    "failed_at": datetime.utcnow().isoformat(),
                })

    thread = threading.Thread(target=_run, name=f"tsc-compare-{slot}", daemon=True)
    _RUNNING_JOBS[slot] = thread
    thread.start()

    logger.info("TSC 对比任务已启动: job_id=%s, slot=%s", job_id, slot)
    return job_id


def _read_json_tolerant(
    path: Path,
    *,
    retries: int = 5,
    retry_delay: float = 0.05,
) -> Optional[Dict[str, Any]]:
    """
    容错读 JSON。

    轮询读取与后台原子替换可能撞上（文件短暂不可读/内容不完整），
    这类情况重试即可，不应把瞬时竞态暴露成接口错误。
    """
    for attempt in range(retries):
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, PermissionError, OSError):
            if attempt == retries - 1:
                logger.warning("读取 %s 失败（已重试 %d 次）", path, retries, exc_info=True)
                return None
            time.sleep(retry_delay * (attempt + 1))
    return None


def load_tsc_compare_status(slot: str = "pv_fault") -> Optional[Dict[str, Any]]:
    """读取当前对比任务状态。文件不存在或瞬时不可读时返回 None。"""
    return _read_json_tolerant(_status_path(slot))


def load_tsc_compare_result(slot: str = "pv_fault") -> Optional[Dict[str, Any]]:
    """读取最近一次对比结果。文件不存在或瞬时不可读时返回 None。"""
    return _read_json_tolerant(_result_path(slot))
# @AI_GENERATED: end
