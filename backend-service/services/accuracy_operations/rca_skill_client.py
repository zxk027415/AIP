# @AI_GENERATED
"""
accuracy_operations/rca_skill_client.py — RCA Skill 子进程调用封装

封装对 operation_skill 的两阶段调用：
  1. 写入 rca_input.json 到 skill_dir
  2. conda run -n cp_web python scripts/run_collect.py（超时 900s，重试 2 次）
  3. conda run -n cp_web python scripts/run_report.py（超时 900s，重试 2 次）
  4. 读取 artifacts 下最新运行目录中的 rca_decision.json
  5. 拷贝产物到 data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}/
  6. 返回 RCAReport（status=succeeded）

失败时直接 re-raise 异常，由调用方负责设置 status=failed/timeout。

类：
  RCASkillClient
    __init__(project_root=None)
    run_rca(slot, alert, rca_report_id, trigger_type) -> RCAReport
    _run_subprocess(cmd, cwd, timeout, max_retries=2) -> subprocess.CompletedProcess
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from services.accuracy_operations.models import (
    AccuracyAlert,
    RCAReport,
    RCAStatus,
)

logger = logging.getLogger(__name__)


class RCASkillClient:
    """封装 operation_skill 子进程调用，产出 RCAReport。

    依赖 operation_skill 的两个脚本：
      - scripts/run_collect.py — 数据采集 + 候选策略评估，产出 rca_input.json
      - scripts/run_report.py  — 基于 rca_decision.json 生成 HTML 报告

    产物拷贝路径：
      data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}/
      （相对 backend-service/ 的相对路径）
    """

    def __init__(self, project_root: Optional[str] = None) -> None:
        """
        :param project_root: 项目根目录（backend-service 的父目录）。
            若为 None，自动从本文件位置向上推导：
            services/accuracy_operations/rca_skill_client.py
            → services/accuracy_operations/
            → services/
            → backend-service/
            → project root
        """
        if project_root is not None:
            self._project_root = Path(project_root).resolve()
        else:
            # Path(__file__) = .../backend-service/services/accuracy_operations/rca_skill_client.py
            # .parent.parent.parent.parent = project root
            self._project_root = Path(__file__).resolve().parent.parent.parent.parent

        self._skill_dir: Path = self._project_root / "operation_skill"
        self._backend_service_dir: Path = self._project_root / "backend-service"

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def run_rca(
        self,
        slot: str,
        alert: AccuracyAlert,
        rca_report_id: str,
        trigger_type: str,
    ) -> RCAReport:
        """执行完整 RCA 流程并返回 RCAReport（status=succeeded）。

        流程：
          1. 构造 rca_input dict 并写入 skill_dir/rca_input.json
          2. 运行 run_collect.py（采集 + 候选策略评估）
          3. 运行 run_report.py（生成 HTML 报告）
          4. 读取最新 artifacts 目录下的 rca_decision.json
          5. 拷贝产物到 data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}/
          6. 解析 rca_decision.json → RCAReport

        :param slot: 槽位名称（分区键）
        :param alert: 触发本次 RCA 的 AccuracyAlert 实体
        :param rca_report_id: 报告 ID（格式 rca-{8hex}）
        :param trigger_type: 触发方式字符串（scheduled/alert/manual）
        :raises subprocess.TimeoutExpired: run_collect 或 run_report 超时
        :raises subprocess.CalledProcessError: 子进程非零退出且重试耗尽
        :raises FileNotFoundError: rca_decision.json 找不到
        :raises ValueError: rca_decision.json 格式不符合预期
        :returns: RCAReport（status=succeeded）
        """
        from services.accuracy_operations.experiment_rca import try_build_experiment_inject_rca

        local_report = try_build_experiment_inject_rca(slot, alert, rca_report_id, trigger_type)
        if local_report is not None:
            logger.info(
                "[RCASkillClient] 使用实验劣化本地 RCA 路径 alert_id=%s",
                alert.alert_id,
            )
            return local_report

        # 1. 构建 rca_input dict
        rca_input = self._build_rca_input(slot, alert, trigger_type)

        # 2. 写入 skill_dir/rca_input.json
        rca_input_path = self._skill_dir / "rca_input.json"
        logger.info("[RCASkillClient] 写入 rca_input.json: %s", rca_input_path)
        with open(rca_input_path, "w", encoding="utf-8") as f:
            json.dump(rca_input, f, ensure_ascii=False, indent=2)

        # 3. 运行 run_collect.py
        collect_cmd = [
            "conda", "run", "-n", "cp_web",
            "python", "scripts/run_collect.py",
        ]
        logger.info("[RCASkillClient] 运行 run_collect.py ...")
        self._run_subprocess(
            cmd=collect_cmd,
            cwd=str(self._skill_dir),
            timeout=900,
            max_retries=2,
        )

        # 4. 运行 run_report.py
        report_cmd = [
            "conda", "run", "-n", "cp_web",
            "python", "scripts/run_report.py",
        ]
        logger.info("[RCASkillClient] 运行 run_report.py ...")
        self._run_subprocess(
            cmd=report_cmd,
            cwd=str(self._skill_dir),
            timeout=900,
            max_retries=2,
        )

        # 5. 读取 artifacts 下最新运行目录的 rca_decision.json
        artifacts_run_dir = self._find_latest_artifacts_dir()
        rca_decision_path = artifacts_run_dir / "rca_decision.json"
        logger.info("[RCASkillClient] 读取 rca_decision.json: %s", rca_decision_path)
        if not rca_decision_path.exists():
            raise FileNotFoundError(
                f"rca_decision.json 不存在: {rca_decision_path}"
            )
        with open(rca_decision_path, "r", encoding="utf-8") as f:
            rca_decision: dict = json.load(f)

        # 6. 拷贝产物到 data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}/
        dest_dir = self._copy_artifacts(slot, rca_report_id, artifacts_run_dir)

        # 7. 计算 artifacts_dir 相对路径（相对 backend-service/）
        artifacts_dir_rel = os.path.relpath(str(dest_dir), start=str(self._backend_service_dir))

        # 8. 解析 rca_decision.json → RCAReport 字段
        rca_section = rca_decision.get("rca", {})
        strategy_section = rca_decision.get("strategy", {})

        report = RCAReport(
            rca_report_id=rca_report_id,
            alert_id=alert.alert_id,
            trigger_type=trigger_type,
            root_cause=rca_section.get("root_cause", ""),
            confidence=float(rca_section.get("confidence", 0.0)),
            reasoning=rca_section.get("reasoning", ""),
            supporting_evidence=rca_section.get("supporting_evidence", []),
            undetermined=bool(rca_section.get("undetermined", False)),
            # error_profile / data_quality_diagnosis / actionable_insights:
            # operation_skill 当前未产出这些字段，留 None/空列表，
            # 由编排器视需要后续增强
            error_profile=None,
            data_quality_diagnosis=None,
            actionable_insights=[],
            candidate_strategies=rca_input.get("candidate_strategies", []),
            recommended_strategy_id=strategy_section.get("selected_strategy_id"),
            artifacts_dir=artifacts_dir_rel,
            status=RCAStatus.succeeded,
        )

        logger.info(
            "[RCASkillClient] RCA 完成: report_id=%s root_cause=%s confidence=%.2f",
            rca_report_id,
            report.root_cause[:60] if report.root_cause else "",
            report.confidence,
        )
        return report

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _build_rca_input(
        self,
        slot: str,
        alert: AccuracyAlert,
        trigger_type: str,
    ) -> dict:
        """按 examples/rca_input_sample.json schema 构造 rca_input dict。

        :param slot: 槽位名称
        :param alert: 触发本次 RCA 的 AccuracyAlert
        :param trigger_type: 触发方式
        :returns: rca_input dict（含 _comment/_comment_end 标记）
        """
        return {
            "_comment": "@AI_GENERATED",
            "loop_id": f"accuracy_ops_{slot}_{alert.workflow_id}",
            "asset": alert.slot,
            "fault_type": "accuracy_degradation",
            "baseline_accuracy": round(100 - alert.baseline_mape, 4),
            "degraded_accuracy": round(100 - alert.current_rolling_mape, 4),
            "recovery_target": round(100 - alert.baseline_mape * 0.95, 4),
            "evidence": {
                "slot": alert.slot,
                "model_form": alert.model_form,
                "workflow_id": alert.workflow_id,
                "version_tag": alert.version_tag,
                "degradation_pct": alert.degradation_pct,
                "degradation_trend": alert.degradation_trend,
                "severity": alert.severity,
                "baseline_mape": alert.baseline_mape,
                "current_rolling_mape": alert.current_rolling_mape,
                "alert_id": alert.alert_id,
                "trigger_type": trigger_type,
            },
            "candidate_strategies": [],
            "_comment_end": "@AI_GENERATED: end",
        }

    def _find_latest_artifacts_dir(self) -> Path:
        """读取 _active_run.json 获取当前运行目录；若不存在则选最新子目录。

        operation_skill 执行后会在 artifacts/ 下创建以日期时间命名的子目录，
        并通过 _active_run.json 记录当前活跃运行路径。

        :returns: 包含 rca_decision.json 的运行目录 Path
        :raises FileNotFoundError: 找不到任何 artifacts 子目录
        """
        artifacts_dir = self._skill_dir / "artifacts"
        active_run_file = artifacts_dir / "_active_run.json"

        if active_run_file.exists():
            try:
                with open(active_run_file, "r", encoding="utf-8") as f:
                    active_info = json.load(f)
                run_dir_str = active_info.get("run_dir", "")
                if run_dir_str:
                    run_dir = Path(run_dir_str)
                    if run_dir.exists():
                        return run_dir
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "[RCASkillClient] 读取 _active_run.json 失败: %s，回退到最新子目录", exc
                )

        # 回退：选取 artifacts/ 下最新的子目录（按名称/mtime 排序）
        sub_dirs = sorted(
            [d for d in artifacts_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name,
            reverse=True,
        )
        if not sub_dirs:
            raise FileNotFoundError(
                f"artifacts 目录下没有任何运行子目录: {artifacts_dir}"
            )
        return sub_dirs[0]

    def _copy_artifacts(
        self,
        slot: str,
        rca_report_id: str,
        source_dir: Path,
    ) -> Path:
        """拷贝 rca_decision.json 和所有 .html 文件到目标目录。

        目标路径：
          backend-service/data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}/

        :param slot: 槽位名称
        :param rca_report_id: RCA 报告 ID
        :param source_dir: artifacts 中当前运行目录
        :returns: 目标目录 Path（绝对路径，供后续 relpath 计算）
        """
        dest_dir = (
            self._backend_service_dir
            / "data"
            / "precision_ops"
            / slot
            / "accuracy_ops"
            / "rca"
            / rca_report_id
        )
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 拷贝 rca_decision.json
        src_decision = source_dir / "rca_decision.json"
        if src_decision.exists():
            shutil.copy2(src_decision, dest_dir / "rca_decision.json")
            logger.debug("[RCASkillClient] 拷贝 rca_decision.json → %s", dest_dir)

        # 拷贝所有 .html 文件
        for html_file in source_dir.glob("*.html"):
            shutil.copy2(html_file, dest_dir / html_file.name)
            logger.debug("[RCASkillClient] 拷贝 %s → %s", html_file.name, dest_dir)

        return dest_dir

    def _run_subprocess(
        self,
        cmd: List[str],
        cwd: str,
        timeout: int,
        max_retries: int = 2,
    ) -> subprocess.CompletedProcess:
        """执行子进程，失败时按退避策略重试。

        重试策略：
          - 第 1 次失败：等待 5s 后重试
          - 第 2 次失败：等待 15s 后重试
          - 超过 max_retries 次后 re-raise 最后异常

        超时（subprocess.TimeoutExpired）直接 re-raise，不重试。

        :param cmd: 命令列表（如 ["conda", "run", "-n", "cp_web", "python", ...]）
        :param cwd: 子进程工作目录
        :param timeout: 超时秒数
        :param max_retries: 最大重试次数，默认 2
        :returns: subprocess.CompletedProcess（returncode == 0）
        :raises subprocess.TimeoutExpired: 子进程超时
        :raises subprocess.CalledProcessError: 重试耗尽后仍非零退出
        """
        _BACKOFF_DELAYS = [5, 15]
        last_exc: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    logger.warning(
                        "[RCASkillClient] 子进程退出码 %d (attempt %d/%d)\n"
                        "  cmd: %s\n  stdout: %s\n  stderr: %s",
                        result.returncode,
                        attempt + 1,
                        max_retries + 1,
                        " ".join(cmd),
                        result.stdout[-500:] if result.stdout else "",
                        result.stderr[-500:] if result.stderr else "",
                    )
                    last_exc = subprocess.CalledProcessError(
                        result.returncode, cmd,
                        output=result.stdout,
                        stderr=result.stderr,
                    )
                    if attempt < max_retries:
                        delay = _BACKOFF_DELAYS[attempt] if attempt < len(_BACKOFF_DELAYS) else 15
                        logger.info(
                            "[RCASkillClient] 等待 %ds 后重试 (attempt %d/%d) ...",
                            delay, attempt + 1, max_retries,
                        )
                        time.sleep(delay)
                        continue
                    else:
                        raise last_exc
                # returncode == 0
                logger.info(
                    "[RCASkillClient] 子进程成功: %s",
                    " ".join(cmd[:4]),
                )
                return result

            except subprocess.TimeoutExpired:
                # 超时直接 re-raise，不重试
                logger.error(
                    "[RCASkillClient] 子进程超时 (%ds): %s", timeout, " ".join(cmd)
                )
                raise

        # 理论上不会到这里，但为类型安全加上
        raise last_exc  # type: ignore[misc]
# @AI_GENERATED: end
