# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
services/scheduler/pv_dual_path/persistence_utils.py — 双路径通用持久化工具

本模块为 spec `pv-fault-dual-path-serving` 任务 16.1（相对路径策略）与 16.2
（严格 JSON boolean 与原子写工具）提供**共享实现**，供本 spec 后续新增的
所有持久化组件复用（Seq_Device_Day_Ledger — 序列设备日记账、
Path_Activation_Epoch — 路径启用周期、PV_Model_Registry — 光伏模型登记、
PromotionEvent — 路径内晋升事件仓储、PathSwitchEvent — 跨路径切换事件仓储、
CrossPathShadowReport — 跨路径 Shadow 报告、BackfillRunner — 历史回放执行器
等），避免每个组件各写一套相对路径校验和严格布尔校验逻辑。

对应需求：
  - Req10.1 — 所有持久化路径写相对路径（相对项目根或 backend-service/）。
  - Req10.2 — 绝对路径先安全转换为相对路径，不能安全转换则拒绝写入。
  - Req10.5 — 原子写（tempfile + fsync + os.replace 或数据库事务），
              不产生半成品落盘。
  - Req10.7 — 审计布尔字段（如 `confirm`）只接受 JSON boolean，拒绝字符串/
              数字真值形式。

提供的三个函数：
  - to_relative_path(path, base_dir=None)
      把可能是绝对路径的输入安全转换为相对路径字符串；无法安全转换则抛出
      ValueError，绝不静默接受绝对路径。
  - require_strict_json_boolean(value, field_name)
      严格校验布尔字段，只接受 Python bool 类型的 True/False。
  - atomic_write_json(target_path, data, base_dir=None)
      原子写 JSON 文件；写入前先调用 to_relative_path 校验/规整目标路径，
      物理落盘使用 tempfile + fsync + os.replace 模式，与
      services/iterative_labeling/storage/file_backend.py 的
      `_atomic_write_json` 保持相同的原子性保证（本模块不修改、不复用该
      私有函数，仅在 pv_dual_path 命名空间内实现一份等价版本）。

基准目录（base_dir）默认值计算方式：
  本文件位于 backend-service/services/scheduler/pv_dual_path/persistence_utils.py，
  与同目录下 config.py 计算 `_BACKEND_DIR` 的方式一致：
      parents[0] = pv_dual_path/
      parents[1] = scheduler/
      parents[2] = services/
      parents[3] = backend-service/
  即 Path(__file__).resolve().parents[3]。
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional, Union

# ---------------------------------------------------------------------------
# 基准目录 — backend-service/，与 config.py 的 _BACKEND_DIR 计算方式保持一致
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[3]  # backend-service/


PathLike = Union[str, Path]


def to_relative_path(path: PathLike, base_dir: Optional[PathLike] = None) -> str:
    """
    把可能是绝对路径或相对路径的输入，安全转换为相对路径字符串（Req10.1/10.2）。

    用途：
      供 Ledger 批次、PV_Model_Registry、PromotionEvent/PathSwitchEvent 仓储、
      CrossPathShadowReport、BackfillRunner 结果等所有新持久化组件，在把路径
      字段写入 JSON/数据库前调用，确保持久化字段永远是相对路径，不因不同开发
      机（如 macOS）与服务器（Linux）路径结构不同而失效或泄露本机目录结构。

    参数：
      - path — 待转换的路径，可以是 str 或 Path，可以是相对路径或绝对路径。
      - base_dir — 可选，绝对路径转换时使用的基准目录；缺省时使用
                   backend-service/ 目录（即 `_BACKEND_DIR`，与 config.py 的
                   `_BACKEND_DIR` 计算方式一致）。传入时应为绝对路径或可解析
                   为绝对路径的路径。

    返回：
      - str — 规范化后的相对路径字符串，统一使用正斜杠 `/` 分隔（便于跨
              macOS / Linux 部署环境一致存储和比较，不受运行平台原生分隔符
              影响）。

    行为：
      - 若 `path` 本身已是相对路径：仅做 `os.path.normpath` 规范化（折叠
        `.`/`..`、多余分隔符），不做任何基于文件系统的存在性检查或符号链接
        解析，直接返回规范化结果。
      - 若 `path` 是绝对路径：先用 `base_dir`（或默认 `_BACKEND_DIR`）解析
        后的绝对路径尝试 `relative_to()`；若 `path` 确实处于 `base_dir` 之
        内，返回相对路径；若不在其内（无法安全转换），**不静默接受**，而是
        抛出 `ValueError`，防止绝对路径悄悄写入持久化字段。

    异常：
      - ValueError — `path` 为空，或 `path` 是绝对路径但不在 `base_dir` 之
                      内、无法安全转换为相对路径。
    """
    if path is None or str(path).strip() == "":
        raise ValueError("path 不能为空，无法转换为相对路径")

    candidate = Path(path)

    if not candidate.is_absolute():
        # 已是相对路径：只做字面规范化，不接触文件系统、不基于 base_dir 重新定位。
        normalized = os.path.normpath(str(candidate))
        return Path(normalized).as_posix()

    base = Path(base_dir).resolve() if base_dir is not None else _BACKEND_DIR
    resolved = candidate.resolve()

    try:
        relative = resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(
            f"绝对路径 {candidate} 不在基准目录 {base} 之内，"
            "无法安全转换为相对路径；拒绝写入持久化字段（Req10.2）。"
        ) from exc

    return relative.as_posix()


def require_strict_json_boolean(value: Any, field_name: str) -> bool:
    """
    严格校验审计布尔字段，只接受 Python bool 类型（Req10.7）。

    用途：
      供 `confirm`（人工二次确认）等审计/门控布尔字段在写入前或使用前调用，
      确保只有真正的 JSON boolean `true`/`false`（在 Python 侧对应
      `True`/`False`）才被接受；字符串 `"true"`/`"1"`/`"yes"`、整数
      `1`/`0`、浮点数等各种"真值形式"一律拒绝，避免人工确认被弱类型判断
      误判为已确认。

    参数：
      - value — 待校验的原始值，可以是任意类型。
      - field_name — 字段名（如 `"confirm"`），仅用于异常信息，便于调用方
                     诊断是哪个字段传入了非法值。

    返回：
      - bool — 校验通过后原值本身（`True` 或 `False`）。

    异常：
      - TypeError — `value` 不是 Python `bool` 类型（包括但不限于字符串、
                    整数、浮点数、`None`、列表等）。异常信息包含
                    `field_name` 与 `value` 的实际类型，便于诊断。

    说明：
      `bool` 在 Python 中是 `int` 的子类，但 `isinstance(value, bool)` 只对
      真正的 `True`/`False` 返回 `True`；对 `1`/`0`（纯 int）返回 `False`，
      因此本函数天然拒绝整数真值形式，无需额外排除逻辑。
    """
    if isinstance(value, bool):
        return value

    raise TypeError(
        f"字段 {field_name!r} 必须是严格的 JSON boolean（true/false），"
        f"但收到类型 {type(value).__name__}，值为 {value!r}（Req10.7）。"
    )


def atomic_write_json(
    target_path: PathLike,
    data: Any,
    base_dir: Optional[PathLike] = None,
) -> str:
    """
    原子写 JSON 文件到相对路径位置，返回规范化后的相对路径字符串（Req10.1/10.2/10.5）。

    用途：
      供 pv_dual_path 包内所有新持久化组件（Ledger 批次、PV_Model_Registry、
      PromotionEvent/PathSwitchEvent、CrossPathShadowReport、BackfillRunner
      结果等）统一使用的原子写实现；写入模式与
      `services/iterative_labeling/storage/file_backend.py` 的
      `_atomic_write_json`（tempfile + fsync + os.replace）保持相同的原子性
      保证：目标文件要么是写入前的完整旧内容，要么是写入后的完整新内容，
      不会出现进程中断导致的半截 JSON。本模块不导入、不修改
      `file_backend.py`，仅在本命名空间内独立实现一份等价版本。

    参数：
      - target_path — 目标文件路径，可以是相对路径（推荐，调用方约定优先
                       直接传相对 base_dir 的路径）或绝对路径（若绝对路径
                       不在 `base_dir` 之内会被 `to_relative_path` 拒绝）。
      - data — 要写入的数据，必须可被 `json.dumps` 序列化。
      - base_dir — 可选，路径解析与合法性校验使用的基准目录；缺省时使用
                   backend-service/ 目录（`_BACKEND_DIR`）。物理写入的绝对
                   路径由 `base_dir / 相对路径` 拼接得到。

    返回：
      - str — 规范化后的相对路径字符串（正斜杠分隔）。调用方应把这个返回值
              （而不是任何绝对路径）写入持久化记录的路径字段，确保记账文件
              本身只保存相对路径（Req10.1/10.2）。

    行为约定：
      写入前**必须**先调用 `to_relative_path(target_path, base_dir)` 完成
      合法性校验与规范化；若 `target_path` 是绝对路径且不在 `base_dir` 之
      内，本函数不会执行任何文件系统写入，直接向上抛出
      `to_relative_path` 产生的 `ValueError`。

    异常：
      - ValueError — `target_path` 非法（参见 `to_relative_path`）。
      - IOError — 序列化失败、临时文件写入失败或原子替换失败时抛出，异常
                  信息包含目标路径与底层错误原因。
    """
    relative = to_relative_path(target_path, base_dir=base_dir)
    base = Path(base_dir).resolve() if base_dir is not None else _BACKEND_DIR
    absolute_target = (base / relative).resolve()

    # 确保父目录存在
    absolute_target.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path_str = tempfile.mkstemp(
        dir=str(absolute_target.parent),
        suffix=".tmp",
        text=True,
    )

    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())  # 确保写入磁盘

        # 原子替换（POSIX 保证原子性；Windows 上 Path.replace 同样是原子操作）
        Path(tmp_path_str).replace(absolute_target)

    except Exception as exc:  # noqa: BLE001
        try:
            Path(tmp_path_str).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        raise IOError(
            f"原子写 JSON 失败: {absolute_target}, 错误: {exc}"
        ) from exc

    return relative
# @AI_GENERATED: end
