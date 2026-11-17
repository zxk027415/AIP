# @AI_GENERATED
"""每次运营闭环运行的产物目录管理。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


ACTIVE_RUN_FILE = "_active_run.json"
RUN_ARTIFACT_NAMES = (
    "rca_input.json",
    "rca_decision.json",
    "operation_event_log.json",
    "_loop_state.json",
    "chart_curves.json",
    "loop_result.json",
)


def _now() -> datetime:
    return datetime.now()


def run_folder_name(ts: Optional[datetime] = None) -> str:
    ts = ts or _now()
    return ts.strftime("%Y-%m-%d_%H%M%S")


def report_filename(ts: Optional[datetime] = None) -> str:
    ts = ts or _now()
    return f"report_{ts.strftime('%Y-%m-%d')}.html"


def artifacts_root(skill_root: Path) -> Path:
    return Path(skill_root) / "artifacts"


def create_run_dir(skill_root: Path, ts: Optional[datetime] = None) -> Path:
    ts = ts or _now()
    root = artifacts_root(skill_root)
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / run_folder_name(ts)
    run_dir.mkdir(parents=True, exist_ok=True)
    set_active_run(skill_root, run_dir, ts)
    return run_dir


def set_active_run(skill_root: Path, run_dir: Path, ts: Optional[datetime] = None) -> None:
    ts = ts or _now()
    payload = {
        "run_dir": str(run_dir.resolve()),
        "run_id": run_dir.name,
        "created_at": ts.isoformat(timespec="seconds"),
        "report_file": report_filename(ts),
    }
    active_path = artifacts_root(skill_root) / ACTIVE_RUN_FILE
    active_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_active_run_info(skill_root: Path) -> Dict[str, Any]:
    active_path = artifacts_root(skill_root) / ACTIVE_RUN_FILE
    if not active_path.exists():
        raise FileNotFoundError(
            f"未找到 {active_path}，请先运行 run_collect.py 创建一次运行目录"
        )
    return json.loads(active_path.read_text(encoding="utf-8"))


def get_active_run_dir(skill_root: Path) -> Path:
    info = get_active_run_info(skill_root)
    run_dir = Path(info["run_dir"])
    if not run_dir.exists():
        raise FileNotFoundError(f"运行目录不存在: {run_dir}")
    return run_dir


def finalize_loop_result(run_dir: Path, result: Dict[str, Any]) -> Path:
    out = run_dir / "loop_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
# @AI_GENERATED: end
