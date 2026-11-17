# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/scheduler/pv_dual_path/path_isolation.py — 双路径持久化分区约定层

PathIsolationRegistry（路径隔离登记）不是新的统一存储；它只把既有权威介质收敛为
``slot + modeling_path`` 先分区、再读写的约定，并通过依赖注入连接仍在独立演进的
Epoch、Ledger 与事务实现。持久化登记矩阵共八类：

1. Cursor — 设备预测游标
   - 存什么：Legacy 路径事件时间水位，或 Seq 连续完成前沿摘要。
   - 为何独立：两条路径进度语义不同，Cursor 也不能替代 Seq 设备日 Ledger。
   - 分区维度：``slot + modeling_path + device``。
   - 介质：项目数据库；ORM 的 ``slot`` 列合入后自动进入本模块物理主键与 upsert。
2. Record — 预测记录
   - 存什么：设备日输入摘要、预测标签、置信度与批次引用。
   - 为何独立：消费方必须唯一识别记录来自哪条生产路径。
   - 分区维度：``slot + modeling_path + device + business_date``。
   - 介质：项目数据库。
3. Batch — 不可变审核批次
   - 存什么：预测事实、输入指纹与 ``supersedes_batch_id`` 修订链。
   - 为何独立：审核和失败恢复必须保留旧批次，修订不得覆盖历史。
   - 分区维度：``slot + modeling_path + business_date + batch_id``。
   - 介质：部署配置目录下的 JSON；持久化引用只使用相对路径。
4. Ledger — Seq 设备日账本
   - 存什么：Seq 每个设备日的状态、输入指纹、尝试次数与批次引用。
   - 为何独立：它是 Seq 是否处理完成的权威，Cursor 只可保存前沿摘要。
   - 分区维度：``slot + modeling_path + device + business_date`` 六元组。
   - 介质：项目数据库；本模块只通过注入的 ``ledger_writer`` 委托写入。
5. Epoch/DeviceScope — 路径启用周期及逐设备责任边界
   - 存什么：启用模式、启用时刻，以及每台设备的 ``effective_from_date``。
   - 为何独立：路径切换不等于重放全部历史，责任边界必须精确到设备。
   - 分区维度：``slot + modeling_path + activation_epoch_id``，DeviceScope 再加 device。
   - 介质：项目数据库或部署配置决定的登记介质；本模块只注入读取边界。
6. LaneClaim — 生产/历史回放车道认领
   - 存什么：lane、排他日期范围、任务与状态。
   - 为何独立：防止生产和 full_backfill 重复认领同一设备日期范围。
   - 分区维度：Epoch + device + lane + ``range_start + range_end``。
   - 介质：项目数据库，并与 Epoch/DeviceScope 在所属服务内同事务维护。
7. PVModelRegistry — 光伏生产路径与模型生命周期登记
   - 存什么：当前生产路径、fallback，以及各路径 champion/challenger/retired。
   - 为何独立：调度器必须有唯一可写真相；ProductionPathPointer 只是无状态门面。
   - 分区维度：``slot + modeling_path``。
   - 介质：部署配置决定的数据库或相对目录登记文件。
8. DualEvents — PromotionEvent / PathSwitchEvent 双事件
   - 存什么：路径内换将与跨路径切换两类不可变审计事实。
   - 为何独立：事件只服务追加审计，不冒充 Registry、Epoch 或运行进度真相。
   - 分区维度：``slot + event_id``，并记录相关 modeling_path。
   - 介质：项目数据库或部署配置决定的相对目录追加式介质。

核心不变式：缺 Cursor 时只读取调用方指定当前 Epoch 对当前设备的边界；记录和批次
必带分区/业务日字段；批次修订使用新 batch_id 且旧文件不变；任一失败异常都携带
slot、path 与设备或设备日诊断；本模块不 import 尚在并行实现的 path_activation.py。

对应设计：.kiro/specs/pv-fault-dual-path-serving/design.md §6。
需求：5.1–5.9、10.1、10.5、10.7、13.1、13.6、14.1、14.2、15.1。
"""

from __future__ import annotations

import json
import logging
from contextlib import nullcontext
from datetime import date, datetime
from pathlib import Path, PurePath
from typing import (
    Any,
    Callable,
    ContextManager,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from sqlalchemy.dialects.mysql import insert as mysql_insert

from services.db.adapter import DBAdapter
from services.db.models.pv_fault import DevicePredictionCursor
from services.scheduler.pv_dual_path.persistence_utils import (
    atomic_write_json,
    require_strict_json_boolean,
    to_relative_path,
)

logger = logging.getLogger(__name__)

DeviceIdentity = Union[Mapping[str, Any], Sequence[str], Any]
BoundaryReader = Callable[[str, DeviceIdentity], Optional[date]]
LedgerWriter = Callable[[Dict[str, Any], Any], Any]
TransactionHook = Callable[[Dict[str, Any]], ContextManager[Any]]

_LEGACY_DAY = "legacy_day"
_SEQ_ANNOTATION = "seq_annotation"
_TSC = "tsc"
_ALLOWED_MODELING_PATHS = frozenset({_LEGACY_DAY, _SEQ_ANNOTATION, _TSC})
_DEFAULT_SLOT = "pv_fault"
_BACKEND_SERVICE_DIR = Path(__file__).resolve().parents[3]

_AUDIT_BOOLEAN_KEYS = frozenset({
    "trained_full_day",
    "is_complete",
    "is_measured",
    "is_recovery",
    "include_night",
    "set_as_production",
    "eligible_for_pool",
    "meets_score_margin",
    "meets_win_count",
})

# 可机读矩阵用于防止后续文档再次退化为只登记 Cursor/Record/Batch 三类。
PERSISTENCE_REGISTRATION_MATRIX: Dict[str, Dict[str, str]] = {
    "Cursor": {
        "stores": "Legacy 事件水位或 Seq 连续完成前沿摘要",
        "why_independent": "两条路径进度语义不同，且 Cursor 不替代 Ledger",
        "partition_dimensions": "slot + modeling_path + device",
        "medium": "项目数据库",
    },
    "Record": {
        "stores": "设备日输入摘要、预测标签、置信度与批次引用",
        "why_independent": "消费方需要唯一识别预测记录来源路径",
        "partition_dimensions": "slot + modeling_path + device + business_date",
        "medium": "项目数据库",
    },
    "Batch": {
        "stores": "不可变预测事实、输入指纹与 supersedes_batch_id 修订链",
        "why_independent": "审核与恢复必须保留旧批次",
        "partition_dimensions": "slot + modeling_path + business_date + batch_id",
        "medium": "部署配置目录下的相对路径 JSON",
    },
    "Ledger": {
        "stores": "Seq 设备日状态、输入指纹、尝试次数与批次引用",
        "why_independent": "Ledger 是 Seq 设备日处理权威",
        "partition_dimensions": "slot + modeling_path + device + business_date",
        "medium": "项目数据库，由注入 ledger_writer 委托",
    },
    "Epoch/DeviceScope": {
        "stores": "启用周期及逐设备 effective_from_date 责任边界",
        "why_independent": "路径切换不能自动重放全部历史",
        "partition_dimensions": "slot + modeling_path + activation_epoch_id + device",
        "medium": "项目数据库或部署配置决定的登记介质",
    },
    "LaneClaim": {
        "stores": "车道、排他日期范围、任务与状态",
        "why_independent": "防止生产与历史回放重复认领",
        "partition_dimensions": "activation_epoch_id + device + lane + date_range",
        "medium": "项目数据库，与 Epoch 所属服务同事务",
    },
    "PVModelRegistry": {
        "stores": "生产路径、fallback 与各路径模型生命周期",
        "why_independent": "为调度提供唯一可写真相",
        "partition_dimensions": "slot + modeling_path",
        "medium": "部署配置决定的数据库或相对目录登记文件",
    },
    "DualEvents": {
        "stores": "PromotionEvent 路径内换将与 PathSwitchEvent 跨路径切换审计",
        "why_independent": "双事件只追加审计，不冒充其他权威介质",
        "partition_dimensions": "slot + event_id",
        "medium": "项目数据库或部署配置决定的相对目录追加式介质",
    },
}


class PartitionBoundaryError(LookupError):
    """当前 Epoch 缺少设备初始边界，且禁止跨路径或历史回退。"""

    def __init__(
        self,
        slot: str,
        modeling_path: str,
        activation_epoch_id: str,
        device: Tuple[str, str, str],
        reason: str,
    ) -> None:
        self.slot = slot
        self.modeling_path = modeling_path
        self.activation_epoch_id = activation_epoch_id
        self.device = device
        self.reason = reason
        super().__init__(
            "缺少当前 Epoch 设备边界 "
            f"(slot={slot!r}, modeling_path={modeling_path!r}, "
            f"activation_epoch_id={activation_epoch_id!r}, device={device!r}): {reason}"
        )


class PartitionWriteError(RuntimeError):
    """目标分区写入失败；``partition_key`` 和 ``reason`` 可供结构化诊断。"""

    def __init__(
        self,
        slot: str,
        modeling_path: str,
        message: str,
        *,
        partition_key: Optional[Mapping[str, Any]] = None,
        reason: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        self.slot = slot
        self.modeling_path = modeling_path
        self.partition_key = {
            "slot": slot,
            "modeling_path": modeling_path,
            **dict(partition_key or {}),
        }
        self.reason = reason or message
        super().__init__(
            f"分区写入失败 partition_key={self.partition_key!r}: {self.reason}"
        )
        if cause is not None:
            self.__cause__ = cause


def _validate_modeling_path(modeling_path: str) -> str:
    if modeling_path not in _ALLOWED_MODELING_PATHS:
        raise ValueError(
            f"非法 modeling_path={modeling_path!r}，仅允许 {sorted(_ALLOWED_MODELING_PATHS)}"
        )
    return modeling_path


def _validate_path_segment(value: str, field_name: str) -> str:
    raw = str(value or "").strip()
    path = PurePath(raw)
    if (
        not raw
        or path.is_absolute()
        or raw in {".", ".."}
        or len(path.parts) != 1
        or "/" in raw
        or "\\" in raw
    ):
        raise ValueError(f"{field_name} 必须是非空单一路径段，收到 {value!r}")
    return raw


def _device_tuple(device: DeviceIdentity) -> Tuple[str, str, str]:
    if isinstance(device, Mapping):
        values = (device.get("site_id"), device.get("device_id"), device.get("branch_id"))
    elif isinstance(device, Sequence) and not isinstance(device, (str, bytes)):
        if len(device) != 3:
            raise ValueError("device 序列必须为 (site_id, device_id, branch_id) 三元组")
        values = tuple(device)
    else:
        values = (
            getattr(device, "site_id", None),
            getattr(device, "device_id", None),
            getattr(device, "branch_id", None),
        )
    normalized = tuple(str(value or "").strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"device 必须包含非空 site_id/device_id/branch_id，收到 {device!r}")
    return normalized  # type: ignore[return-value]


def _business_date_from_record(record: Mapping[str, Any]) -> date:
    raw = record.get("business_date")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if raw not in (None, ""):
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError as exc:
            raise ValueError(f"business_date 不是合法 ISO 日期：{raw!r}") from exc

    features = record.get("input_feature_json")
    time_window = features.get("time_window") if isinstance(features, Mapping) else None
    if time_window not in (None, ""):
        try:
            return date.fromisoformat(str(time_window)[:10])
        except ValueError as exc:
            raise ValueError(
                f"business_date 为空且 input_feature_json.time_window 无法解析：{time_window!r}"
            ) from exc
    raise ValueError("business_date 不可为空，且没有可解析的 input_feature_json.time_window")


def _assert_strict_audit_booleans(payload: Any, *, _path: str = "") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            field_path = f"{_path}.{key}".lstrip(".")
            if key in _AUDIT_BOOLEAN_KEYS and value is not None:
                require_strict_json_boolean(value, field_path)
            _assert_strict_audit_booleans(value, _path=field_path)
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            _assert_strict_audit_booleans(item, _path=f"{_path}[{index}]")


def _normalize_persisted_paths(payload: Any, *, base_dir: Path) -> Any:
    """递归把 ``*_path`` 绝对路径转换为相对路径，并拒绝 ``..`` 逃逸。"""
    if isinstance(payload, dict):
        normalized: Dict[str, Any] = {}
        for key, value in payload.items():
            if key.endswith("_path") and isinstance(value, (str, Path)) and str(value).strip():
                raw = Path(value)
                if raw.is_absolute():
                    normalized[key] = to_relative_path(raw, base_dir=base_dir)
                else:
                    relative = PurePath(str(value))
                    if ".." in relative.parts:
                        raise ValueError(f"持久化路径字段 {key!r} 不允许包含 '..'：{value!r}")
                    normalized[key] = relative.as_posix()
            else:
                normalized[key] = _normalize_persisted_paths(value, base_dir=base_dir)
        return normalized
    if isinstance(payload, list):
        return [_normalize_persisted_paths(item, base_dir=base_dir) for item in payload]
    return payload


class PathIsolationRegistry:
    """按 ``slot + modeling_path`` 分区访问既有持久化介质的约定层。"""

    def __init__(
        self,
        adapter: DBAdapter,
        *,
        backend_service_dir: Optional[Path] = None,
        boundary_reader: Optional[BoundaryReader] = None,
        ledger_writer: Optional[LedgerWriter] = None,
        transaction_hook: Optional[TransactionHook] = None,
    ) -> None:
        """注入 DB adapter、Epoch 边界读取器及可选 Ledger/事务 hook。

        ``boundary_reader`` 只接收 ``activation_epoch_id`` 与原始 ``device``，从而不依赖
        尚在并行实现的 path_activation 模块；调用方负责传入当前 slot/path 的 Epoch ID。
        ``ledger_writer`` 接收已盖分区字段的 entry 与 transaction token。
        ``transaction_hook`` 接收 operation/partition_key 上下文并返回 context manager。
        """
        self._adapter = adapter
        self._backend_dir = (backend_service_dir or _BACKEND_SERVICE_DIR).resolve()
        self._boundary_reader = boundary_reader
        self._ledger_writer = ledger_writer
        self._transaction_hook = transaction_hook

    def _cursor_primary_key(
        self,
        slot: str,
        modeling_path: str,
        site_id: str,
        device_id: str,
        branch_id: str,
    ) -> Dict[str, str]:
        key = {
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "modeling_path": modeling_path,
        }
        # ORM 的 slot 列由并行任务负责；合入后无需再修改本模块即可进入物理主键。
        if "slot" in DevicePredictionCursor.__table__.columns:
            key["slot"] = slot
        return key

    def _partition_transaction(
        self,
        operation: str,
        partition_key: Mapping[str, Any],
    ) -> ContextManager[Any]:
        if self._transaction_hook is None:
            return nullcontext(None)
        scope = self._transaction_hook({
            "operation": operation,
            "partition_key": dict(partition_key),
        })
        if not hasattr(scope, "__enter__") or not hasattr(scope, "__exit__"):
            raise TypeError("transaction_hook 必须返回 context manager")
        return scope

    def read_cursor(
        self,
        slot: str,
        modeling_path: str,
        site_id: str,
        device_id: str,
        branch_id: str,
    ) -> Optional[datetime]:
        """只读取目标 slot/path/device 的 Cursor；缺行返回 None，不跨路径回退。"""
        _validate_path_segment(slot, "slot")
        _validate_modeling_path(modeling_path)
        with self._adapter.get_sync_session() as session:
            row = session.get(
                DevicePredictionCursor,
                self._cursor_primary_key(
                    slot, modeling_path, site_id, device_id, branch_id,
                ),
            )
            return None if row is None else row.last_predicted_time

    def get_cursor_or_initial(
        self,
        slot: str,
        modeling_path: str,
        device: DeviceIdentity,
        activation_epoch_id: str,
    ) -> Union[datetime, date]:
        """返回本分区 Cursor；缺 Cursor 时返回当前 Epoch 的设备责任起始日。

        该方法先且只查询目标分区 Cursor。缺失时调用注入的
        ``boundary_reader(activation_epoch_id, device)``，不读取另一条路径，也不查询设备
        最早历史。边界不存在时抛 ``PartitionBoundaryError`` 明确给出 slot/path/Epoch/device。
        """
        _validate_path_segment(slot, "slot")
        _validate_modeling_path(modeling_path)
        epoch_id = str(activation_epoch_id or "").strip()
        if not epoch_id:
            raise ValueError("activation_epoch_id 不可为空")
        site_id, device_id, branch_id = _device_tuple(device)
        cursor = self.read_cursor(
            slot, modeling_path, site_id, device_id, branch_id,
        )
        if cursor is not None:
            return cursor
        if self._boundary_reader is None:
            raise PartitionBoundaryError(
                slot,
                modeling_path,
                epoch_id,
                (site_id, device_id, branch_id),
                "boundary_reader_not_configured",
            )
        boundary = self._boundary_reader(epoch_id, device)
        if boundary is None:
            raise PartitionBoundaryError(
                slot,
                modeling_path,
                epoch_id,
                (site_id, device_id, branch_id),
                "effective_from_date_missing",
            )
        if isinstance(boundary, datetime):
            boundary = boundary.date()
        if not isinstance(boundary, date):
            raise PartitionBoundaryError(
                slot,
                modeling_path,
                epoch_id,
                (site_id, device_id, branch_id),
                f"invalid_effective_from_date_type:{type(boundary).__name__}",
            )
        return boundary

    def advance_cursor(
        self,
        slot: str,
        modeling_path: str,
        site_id: str,
        device_id: str,
        branch_id: str,
        event_time: datetime,
        *,
        model_version_id: Optional[str] = None,
        predicted_at: Optional[datetime] = None,
    ) -> datetime:
        """在目标 Cursor 分区推进水位；失败只回滚该事务并返回设备诊断。"""
        _validate_path_segment(slot, "slot")
        _validate_modeling_path(modeling_path)
        if not isinstance(event_time, datetime):
            raise ValueError(f"event_time 必须是 datetime，收到 {type(event_time).__name__}")
        now = predicted_at or datetime.utcnow()
        payload = {
            **self._cursor_primary_key(
                slot, modeling_path, site_id, device_id, branch_id,
            ),
            "last_predicted_time": event_time,
            "last_predicted_at": now,
            "model_version_id": model_version_id,
            "updated_at": now,
        }
        partition_key = {
            "device": {
                "site_id": site_id,
                "device_id": device_id,
                "branch_id": branch_id,
            },
        }
        try:
            with self._partition_transaction("advance_cursor", {
                "slot": slot,
                "modeling_path": modeling_path,
                **partition_key,
            }):
                with self._adapter.get_sync_session() as session:
                    stmt = mysql_insert(DevicePredictionCursor).values(**payload)
                    stmt = stmt.on_duplicate_key_update(**{
                        col: stmt.inserted[col]
                        for col in (
                            "last_predicted_time",
                            "last_predicted_at",
                            "model_version_id",
                            "updated_at",
                        )
                    })
                    session.execute(stmt)
        except Exception as exc:  # noqa: BLE001
            raise PartitionWriteError(
                slot,
                modeling_path,
                "游标推进失败",
                partition_key=partition_key,
                reason=f"cursor_advance_failed:{exc}",
                cause=exc,
            ) from exc
        return event_time

    def write_prediction_records(
        self,
        pv_repo: Any,
        slot: str,
        modeling_path: str,
        records: List[Dict[str, Any]],
    ) -> List[Any]:
        """强制每条记录写 slot/path/business_date；任一必填缺失则整批拒绝。"""
        _validate_path_segment(slot, "slot")
        _validate_modeling_path(modeling_path)
        stamped: List[Dict[str, Any]] = []
        device_days: List[Dict[str, Any]] = []
        try:
            for index, item in enumerate(records):
                if not isinstance(item, Mapping):
                    raise ValueError(f"第 {index} 条记录必须是 mapping")
                business_date = _business_date_from_record(item)
                record = {
                    **dict(item),
                    "slot": slot,
                    "modeling_path": modeling_path,
                    "business_date": business_date,
                }
                stamped.append(record)
                device_days.append({
                    "site_id": str(record.get("site_id") or ""),
                    "device_id": str(record.get("device_id") or ""),
                    "branch_id": str(record.get("branch_id") or ""),
                    "business_date": business_date.isoformat(),
                })
            partition_key = {"device_days": device_days}
            with self._partition_transaction("write_prediction_records", {
                "slot": slot,
                "modeling_path": modeling_path,
                **partition_key,
            }):
                return pv_repo.insert_prediction_records(stamped)
        except PartitionWriteError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PartitionWriteError(
                slot,
                modeling_path,
                "预测记录整批写入失败",
                partition_key={"device_days": device_days},
                reason=f"prediction_records_failed:{exc}",
                cause=exc,
            ) from exc

    def write_ledger_entry(
        self,
        slot: str,
        modeling_path: str,
        entry: Mapping[str, Any],
    ) -> Any:
        """通过注入 writer 委托写 Ledger，不让本模块耦合具体 ORM/仓储。"""
        _validate_path_segment(slot, "slot")
        _validate_modeling_path(modeling_path)
        stamped = {**dict(entry), "slot": slot, "modeling_path": modeling_path}
        partition_key = {
            "device_day": {
                key: stamped.get(key)
                for key in ("site_id", "device_id", "branch_id", "business_date")
            }
        }
        try:
            if self._ledger_writer is None:
                raise RuntimeError("ledger_writer_not_configured")
            with self._partition_transaction("write_ledger_entry", {
                "slot": slot,
                "modeling_path": modeling_path,
                **partition_key,
            }) as transaction:
                return self._ledger_writer(stamped, transaction)
        except Exception as exc:  # noqa: BLE001
            raise PartitionWriteError(
                slot,
                modeling_path,
                "Ledger 写入失败",
                partition_key=partition_key,
                reason=f"ledger_write_failed:{exc}",
                cause=exc,
            ) from exc

    def batch_dir(self, slot: str, modeling_path: str) -> Path:
        """返回目标分区本地读写目录；此绝对路径不进入持久化 payload。"""
        safe_slot = _validate_path_segment(slot, "slot")
        _validate_modeling_path(modeling_path)
        return (
            self._backend_dir
            / "data"
            / "iterative_labeling"
            / "prediction_batches"
            / safe_slot
            / modeling_path
        )

    def batch_relpath(self, slot: str, modeling_path: str, batch_id: str) -> str:
        """返回相对 backend-service 的批次引用，拒绝绝对路径持久化。"""
        safe_batch_id = _validate_path_segment(batch_id, "batch_id")
        absolute = self.batch_dir(slot, modeling_path) / f"{safe_batch_id}.json"
        return to_relative_path(absolute, base_dir=self._backend_dir)

    def write_batch(
        self,
        slot: str,
        modeling_path: str,
        batch_id: str,
        payload: Dict[str, Any],
    ) -> str:
        """写不可变批次；修订必须使用不同 batch_id 并指向旧批次。"""
        safe_slot = _validate_path_segment(slot, "slot")
        _validate_modeling_path(modeling_path)
        safe_batch_id = _validate_path_segment(batch_id, "batch_id")
        partition_key: Dict[str, Any] = {"batch_id": safe_batch_id}
        try:
            business_date = payload.get("business_date")
            input_fingerprint = str(payload.get("input_fingerprint") or "").strip()
            if business_date in (None, ""):
                raise ValueError("business_date 不可为空")
            if not input_fingerprint:
                raise ValueError("input_fingerprint 不可为空")
            if "supersedes_batch_id" not in payload:
                raise ValueError("supersedes_batch_id 字段必须存在；首批显式写 null")
            supersedes = payload.get("supersedes_batch_id")
            if supersedes not in (None, ""):
                supersedes = _validate_path_segment(str(supersedes), "supersedes_batch_id")
                if supersedes == safe_batch_id:
                    raise ValueError("修订批次 batch_id 必须与 supersedes_batch_id 不同")
            partition_key["business_date"] = str(business_date)
            out = {
                **dict(payload),
                "slot": safe_slot,
                "modeling_path": modeling_path,
                "business_date": business_date,
                "input_fingerprint": input_fingerprint,
                "supersedes_batch_id": supersedes,
            }
            out = _normalize_persisted_paths(out, base_dir=self._backend_dir)
            _assert_strict_audit_booleans(out)
            # persistence_utils.atomic_write_json 当前允许 NaN；预检确保本合同只落合法 JSON。
            json.dumps(out, ensure_ascii=False, allow_nan=False)

            batch_path = self.batch_dir(safe_slot, modeling_path) / f"{safe_batch_id}.json"
            if batch_path.exists():
                raise FileExistsError(
                    f"batch_id={safe_batch_id!r} 已存在；不可覆盖，请创建新批次并写 supersedes_batch_id"
                )
            relative = self.batch_relpath(safe_slot, modeling_path, safe_batch_id)
            with self._partition_transaction("write_batch", {
                "slot": safe_slot,
                "modeling_path": modeling_path,
                **partition_key,
            }):
                persisted = atomic_write_json(
                    relative,
                    out,
                    base_dir=self._backend_dir,
                )
            if Path(persisted).is_absolute():
                raise RuntimeError("atomic_write_json 返回了绝对路径，拒绝持久化")
            return persisted
        except PartitionWriteError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PartitionWriteError(
                safe_slot,
                modeling_path,
                "审核批次落盘失败",
                partition_key=partition_key,
                reason=f"batch_write_failed:{exc}",
                cause=exc,
            ) from exc

    def list_batch_ids(self, slot: str, modeling_path: str) -> List[str]:
        """稳定列出目标分区的不可变批次 ID，不跨槽位或路径扫描。

        返回值只含文件名 stem；隐藏文件、临时文件和非法路径段会被忽略。该枚举供启动及每轮
        恢复对账使用，不读取或修改批次内容。
        """

        directory = self.batch_dir(slot, modeling_path)
        if not directory.exists():
            return []
        batch_ids: List[str] = []
        for path in directory.glob("*.json"):
            if not path.is_file():
                continue
            try:
                batch_ids.append(_validate_path_segment(path.stem, "batch_id"))
            except ValueError:
                logger.warning("忽略非法不可变批次文件名：%s", path.name)
        return sorted(set(batch_ids))

    def read_batch(
        self,
        slot: str,
        modeling_path: str,
        batch_id: str,
    ) -> Optional[Dict[str, Any]]:
        """只读取目标分区批次，不跨 modeling_path 回退。"""
        safe_batch_id = _validate_path_segment(batch_id, "batch_id")
        batch_path = self.batch_dir(slot, modeling_path) / f"{safe_batch_id}.json"
        if not batch_path.exists():
            return None
        with open(batch_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
# @AI_GENERATED: end
