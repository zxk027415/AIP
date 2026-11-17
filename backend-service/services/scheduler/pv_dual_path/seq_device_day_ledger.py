# @AI_GENERATED
# -*- coding: utf-8 -*-
"""序列设备日账本仓储。

本模块以 ``SeqDeviceDayLedger`` ORM 为唯一持久化模型，通过 ``DBAdapter`` 的同步
Session 完成逐设备日查询、状态推进和连续完成前沿派生。所有写操作均在单个 Session
事务内完成；异常由 ``DBAdapter`` 回滚后，再包装成包含完整六元组键的诊断错误。

关键英文字段说明：
- ``status`` — 处理状态；只允许设计规定的六态及其合法迁移。
- ``input_fingerprint`` — 设备日输入点集合的稳定 SHA-256 指纹。
- ``attempt_count`` — 实际处理失败次数；只有 ``mark_failed`` 增加。
- ``activation_epoch_id`` — 当前记录所属的生产启用周期标识。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from services.db.adapter import DBAdapter
from services.db.models.pv_fault import PathActivationDeviceScope, SeqDeviceDayLedger

_WAITING_DATA = "waiting_data"
_READY = "ready"
_RUNNING = "running"
_SUCCEEDED = "succeeded"
_FAILED = "failed"
_REVISION_PENDING = "revision_pending"
_RUNNABLE_STATUSES = (_READY, _REVISION_PENDING)
_ALLOWED_STATUSES = frozenset(
    {_WAITING_DATA, _READY, _RUNNING, _SUCCEEDED, _FAILED, _REVISION_PENDING}
)


@dataclass(frozen=True)
class DeviceDayKey:
    """设备日六元组键。

    字段依次为 ``slot`` — 槽位、``modeling_path`` — 建模路径、``site_id`` — 站点、
    ``device_id`` — 设备、``branch_id`` — 支路、``business_date`` — 业务日期。
    """

    slot: str
    modeling_path: str
    site_id: str
    device_id: str
    branch_id: str
    business_date: date

    def as_primary_key(self) -> Dict[str, Any]:
        """返回 SQLAlchemy ``Session.get`` 使用的复合主键字典。"""

        return {
            "slot": self.slot,
            "modeling_path": self.modeling_path,
            "site_id": self.site_id,
            "device_id": self.device_id,
            "branch_id": self.branch_id,
            "business_date": self.business_date,
        }

    def describe(self) -> str:
        """返回包含六个维度的稳定诊断文本。"""

        return (
            f"(slot={self.slot!r}, modeling_path={self.modeling_path!r}, "
            f"site_id={self.site_id!r}, device_id={self.device_id!r}, "
            f"branch_id={self.branch_id!r}, business_date={self.business_date!r})"
        )


@dataclass(frozen=True)
class DeviceKey:
    """不含日期的设备分区键，供连续完成前沿查询使用。"""

    slot: str
    modeling_path: str
    site_id: str
    device_id: str
    branch_id: str

    def diagnostic_key(self) -> DeviceDayKey:
        """构造 frontier 查询错误使用的完整六元组诊断键。"""

        return DeviceDayKey(
            slot=self.slot,
            modeling_path=self.modeling_path,
            site_id=self.site_id,
            device_id=self.device_id,
            branch_id=self.branch_id,
            business_date=date.min,
        )


@dataclass(frozen=True)
class LedgerRecord:
    """脱离 Session 后可安全返回的账本记录快照。

    ``batch_id`` — 最新成功不可变批次标识；``supersedes_batch_id`` — 当前修订批次
    所取代的上一批次标识；时间字段均按项目 ORM 约定保存 UTC 语义的朴素时间。
    """

    key: DeviceDayKey
    activation_epoch_id: str
    status: str
    input_fingerprint: Optional[str]
    batch_id: Optional[str]
    supersedes_batch_id: Optional[str]
    attempt_count: int
    last_error: Optional[str]
    processed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class LedgerOperationError(RuntimeError):
    """账本操作失败；错误文本始终携带完整六元组键和失败原因。"""

    def __init__(
        self,
        key: DeviceDayKey,
        reason: str,
        *,
        cause: Optional[BaseException] = None,
    ) -> None:
        self.key = key
        self.reason = reason
        super().__init__(f"SeqDeviceDayLedger 操作失败 key={key.describe()}: {reason}")
        if cause is not None:
            self.__cause__ = cause


def _row_to_record(row: SeqDeviceDayLedger) -> LedgerRecord:
    """把 ORM 行转换为不依赖 Session 生命周期的不可变快照。"""

    return LedgerRecord(
        key=DeviceDayKey(
            slot=row.slot,
            modeling_path=row.modeling_path,
            site_id=row.site_id,
            device_id=row.device_id,
            branch_id=row.branch_id,
            business_date=row.business_date,
        ),
        activation_epoch_id=row.activation_epoch_id,
        status=row.status,
        input_fingerprint=row.input_fingerprint,
        batch_id=row.batch_id,
        supersedes_batch_id=row.supersedes_batch_id,
        attempt_count=int(row.attempt_count or 0),
        last_error=row.last_error,
        processed_at=row.processed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _canonical_event_time(value: Any) -> str:
    """把事件时间规范化为可稳定排序和序列化的文本。"""

    if isinstance(value, datetime):
        normalized = value
        if normalized.tzinfo is not None:
            normalized = normalized.astimezone(timezone.utc).replace(tzinfo=None)
        return normalized.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return str(isoformat())
        except (TypeError, ValueError):
            pass
    return str(value)


def _canonical_measurement_value(value: Any) -> Dict[str, str]:
    """把测量值规范化为带类型标签的稳定 JSON 结构。"""

    if value is None:
        return {"type": "null", "value": ""}
    if isinstance(value, bool):
        return {"type": "bool", "value": "true" if value else "false"}
    if isinstance(value, float) and math.isnan(value):
        return {"type": "number", "value": "NaN"}
    if isinstance(value, float) and math.isinf(value):
        return {"type": "number", "value": "Infinity" if value > 0 else "-Infinity"}
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            number = Decimal(str(value))
            if number == 0:
                normalized = "0"
            else:
                normalized = format(number.normalize(), "f")
            return {"type": "number", "value": normalized}
        except (InvalidOperation, ValueError):
            pass
    return {"type": type(value).__name__, "value": str(value)}


def _point_pair(point: Any) -> Tuple[Any, Any]:
    """兼容二元序列、映射或带属性对象，提取 ``event_time`` 与 ``value``。"""

    if isinstance(point, Mapping):
        if "event_time" not in point or "value" not in point:
            raise ValueError("输入点映射必须同时包含 event_time — 事件时间和 value — 测量值")
        return point["event_time"], point["value"]
    if hasattr(point, "event_time") and hasattr(point, "value"):
        return point.event_time, point.value
    if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) == 2:
        return point[0], point[1]
    raise ValueError("输入点必须是 (event_time, value) 二元组、映射或同名属性对象")


def stable_input_fingerprint(points: Iterable[Any]) -> str:
    """计算设备日输入点集合的稳定 SHA-256 指纹。

    每个点先规范化为 ``event_time`` — 事件时间与 ``value`` — 测量值，再按两者完整
    规范值排序。排序保留重复点的数量，因此不依赖原输入顺序；相同时间戳的多点也会用
    完整值作为稳定次级顺序，任意增、删、改都会改变最终摘要。
    """

    normalized: List[Dict[str, Any]] = []
    for point in points:
        event_time, value = _point_pair(point)
        normalized.append(
            {
                "event_time": _canonical_event_time(event_time),
                "value": _canonical_measurement_value(value),
            }
        )
    normalized.sort(
        key=lambda item: (
            item["event_time"],
            item["value"]["type"],
            item["value"]["value"],
        )
    )
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SeqDeviceDayLedgerRepository:
    """使用 ``DBAdapter`` 同步 Session 的设备日账本仓储。

    Args:
        adapter: 已初始化的数据库适配器；仓储不自行创建连接池。
        activation_epoch_id: 可选默认启用周期。新增候选时必须由构造参数或方法关键字提供；
            ``list_runnable`` 在设置默认周期后只返回该周期，避免旧周期混入当前调度。
    """

    def __init__(
        self,
        adapter: DBAdapter,
        *,
        activation_epoch_id: Optional[str] = None,
    ) -> None:
        self._adapter = adapter
        self._activation_epoch_id = activation_epoch_id

    @staticmethod
    def _locked_row(session: Session, key: DeviceDayKey) -> Optional[SeqDeviceDayLedger]:
        """按完整六元组键锁定目标行，供状态检查与原子推进。"""

        statement = (
            select(SeqDeviceDayLedger)
            .where(
                SeqDeviceDayLedger.slot == key.slot,
                SeqDeviceDayLedger.modeling_path == key.modeling_path,
                SeqDeviceDayLedger.site_id == key.site_id,
                SeqDeviceDayLedger.device_id == key.device_id,
                SeqDeviceDayLedger.branch_id == key.branch_id,
                SeqDeviceDayLedger.business_date == key.business_date,
            )
            .with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    @staticmethod
    def _require_row(
        session: Session,
        key: DeviceDayKey,
    ) -> SeqDeviceDayLedger:
        """锁定并返回目标行；不存在时抛出含完整六元组键的错误。"""

        row = SeqDeviceDayLedgerRepository._locked_row(session, key)
        if row is None:
            raise LedgerOperationError(key, "账本记录不存在")
        return row

    @staticmethod
    def _assert_status(
        key: DeviceDayKey,
        row: SeqDeviceDayLedger,
        allowed: Sequence[str],
        target: str,
    ) -> None:
        """校验状态迁移来源，非法迁移返回完整六元组诊断。"""

        if row.status not in allowed:
            raise LedgerOperationError(
                key,
                f"非法状态迁移 {row.status!r} -> {target!r}，允许来源={list(allowed)!r}",
            )

    @staticmethod
    def _query_error_key(
        *,
        slot: Optional[str] = None,
        modeling_path: Optional[str] = None,
    ) -> DeviceDayKey:
        """为非单行查询构造含全部六维名称的诊断范围键。"""

        return DeviceDayKey(
            slot=slot or "<any>",
            modeling_path=modeling_path or "<any>",
            site_id="<any>",
            device_id="<any>",
            branch_id="<any>",
            business_date=date.min,
        )

    def _resolve_epoch(self, explicit_epoch_id: Optional[str], key: DeviceDayKey) -> str:
        """解析新增候选的启用周期，缺失时返回带六元组键的诊断错误。"""

        epoch_id = explicit_epoch_id or self._activation_epoch_id
        if not epoch_id:
            raise LedgerOperationError(key, "新增候选缺少 activation_epoch_id — 启用周期标识")
        return epoch_id

    def query(self, key: DeviceDayKey) -> Optional[LedgerRecord]:
        """按完整六元组键查询单条账本记录，不存在时返回 ``None``。"""

        try:
            with self._adapter.get_sync_session() as session:
                row = session.get(SeqDeviceDayLedger, key.as_primary_key())
                return None if row is None else _row_to_record(row)
        except LedgerOperationError:
            raise
        except Exception as exc:
            raise LedgerOperationError(key, f"查询失败：{exc}", cause=exc) from exc

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        slot: Optional[str] = None,
        modeling_path: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        activation_epoch_id: Optional[str] = None,
        site_id: Optional[str] = None,
        device_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """稳定分页列出账本记录。

        返回 ``page`` — 页码、``page_size`` — 每页条数、``total`` — 总条数、
        ``items`` — 当前页 ``LedgerRecord`` 快照。排序为业务日升序，再按稳定设备键排序。
        """

        normalized_page = max(1, int(page))
        normalized_size = max(1, min(int(page_size), 1000))
        offset = (normalized_page - 1) * normalized_size
        filters = []
        if slot is not None:
            filters.append(SeqDeviceDayLedger.slot == slot)
        if modeling_path is not None:
            filters.append(SeqDeviceDayLedger.modeling_path == modeling_path)
        if activation_epoch_id is not None:
            filters.append(SeqDeviceDayLedger.activation_epoch_id == activation_epoch_id)
        if site_id is not None:
            filters.append(SeqDeviceDayLedger.site_id == site_id)
        if device_id is not None:
            filters.append(SeqDeviceDayLedger.device_id == device_id)
        if branch_id is not None:
            filters.append(SeqDeviceDayLedger.branch_id == branch_id)
        if start_date is not None:
            filters.append(SeqDeviceDayLedger.business_date >= start_date)
        if end_date is not None:
            filters.append(SeqDeviceDayLedger.business_date <= end_date)
        if status is not None:
            statuses = [status]
        if statuses is not None:
            invalid = set(statuses) - _ALLOWED_STATUSES
            if invalid:
                key = self._query_error_key(slot=slot, modeling_path=modeling_path)
                raise LedgerOperationError(key, f"未知 status — 处理状态：{sorted(invalid)!r}")
            filters.append(SeqDeviceDayLedger.status.in_(tuple(statuses)))

        statement = (
            select(SeqDeviceDayLedger)
            .where(*filters)
            .order_by(
                SeqDeviceDayLedger.business_date.asc(),
                SeqDeviceDayLedger.site_id.asc(),
                SeqDeviceDayLedger.device_id.asc(),
                SeqDeviceDayLedger.branch_id.asc(),
                SeqDeviceDayLedger.slot.asc(),
                SeqDeviceDayLedger.modeling_path.asc(),
            )
            .offset(offset)
            .limit(normalized_size)
        )
        count_statement = select(func.count()).select_from(SeqDeviceDayLedger).where(*filters)
        key = self._query_error_key(slot=slot, modeling_path=modeling_path)
        try:
            with self._adapter.get_sync_session() as session:
                total = int(session.execute(count_statement).scalar_one())
                rows = session.execute(statement).scalars().all()
                return {
                    "page": normalized_page,
                    "page_size": normalized_size,
                    "total": total,
                    "items": [_row_to_record(row) for row in rows],
                }
        except LedgerOperationError:
            raise
        except Exception as exc:
            raise LedgerOperationError(key, f"分页查询失败：{exc}", cause=exc) from exc

    def upsert_candidate(
        self,
        key: DeviceDayKey,
        fingerprint: str,
        *,
        is_ready: bool = False,
        activation_epoch_id: Optional[str] = None,
    ) -> LedgerRecord:
        """新增候选或按指纹幂等更新候选。

        ``is_ready`` — 完整性门禁是否通过：新候选据此进入 ``ready`` 或
        ``waiting_data``；已有 waiting/failed 仅在其为真时推进到 ready。已成功记录同指纹
        保持 succeeded，指纹变化则进入 revision_pending，并保留旧成功指纹直到修订成功。
        """

        epoch_id = self._resolve_epoch(activation_epoch_id, key)
        now = datetime.utcnow()
        try:
            with self._adapter.get_sync_session() as session:
                row = self._locked_row(session, key)
                if row is None:
                    row = SeqDeviceDayLedger(
                        **key.as_primary_key(),
                        activation_epoch_id=epoch_id,
                        status=_READY if is_ready else _WAITING_DATA,
                        input_fingerprint=fingerprint,
                        attempt_count=0,
                        processed_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                else:
                    row.activation_epoch_id = epoch_id
                    if row.status == _SUCCEEDED:
                        if row.input_fingerprint == fingerprint:
                            return _row_to_record(row)
                        row.status = _REVISION_PENDING
                        row.supersedes_batch_id = row.batch_id
                        row.processed_at = now
                    elif row.status in (_WAITING_DATA, _FAILED) and is_ready:
                        row.status = _READY
                        row.input_fingerprint = fingerprint
                        row.processed_at = now
                    elif row.status in (_WAITING_DATA, _READY, _FAILED):
                        row.input_fingerprint = fingerprint
                    row.updated_at = now
                session.flush()
                return _row_to_record(row)
        except LedgerOperationError:
            raise
        except Exception as exc:
            raise LedgerOperationError(key, f"候选 upsert 失败：{exc}", cause=exc) from exc

    def mark_ready(self, key: DeviceDayKey, fingerprint: Optional[str] = None) -> LedgerRecord:
        """把 waiting_data 或 failed 候选推进到 ready，供后续轮次重试。"""

        now = datetime.utcnow()
        try:
            with self._adapter.get_sync_session() as session:
                row = self._require_row(session, key)
                self._assert_status(key, row, (_WAITING_DATA, _FAILED), _READY)
                row.status = _READY
                if fingerprint is not None:
                    row.input_fingerprint = fingerprint
                row.processed_at = now
                row.updated_at = now
                session.flush()
                return _row_to_record(row)
        except LedgerOperationError:
            raise
        except Exception as exc:
            raise LedgerOperationError(key, f"标记 ready 失败：{exc}", cause=exc) from exc

    def list_runnable(self, slot: str, limit: int) -> List[LedgerRecord]:
        """按业务日和稳定设备键列出可运行记录，最多返回 ``limit`` 条。

        查询只选择 ready/revision_pending，不扫描后遇到 waiting/failed 就停止，因此更早的
        未就绪或失败日期不会阻塞更晚 ready 日期。设置默认启用周期时会同时按周期过滤。
        """

        normalized_limit = max(0, min(int(limit), 1000))
        if normalized_limit == 0:
            return []
        filters = [
            SeqDeviceDayLedger.slot == slot,
            SeqDeviceDayLedger.status.in_(_RUNNABLE_STATUSES),
        ]
        if self._activation_epoch_id is not None:
            filters.append(SeqDeviceDayLedger.activation_epoch_id == self._activation_epoch_id)
        statement = (
            select(SeqDeviceDayLedger)
            .where(*filters)
            .order_by(
                SeqDeviceDayLedger.business_date.asc(),
                SeqDeviceDayLedger.site_id.asc(),
                SeqDeviceDayLedger.device_id.asc(),
                SeqDeviceDayLedger.branch_id.asc(),
                SeqDeviceDayLedger.modeling_path.asc(),
            )
            .limit(normalized_limit)
        )
        key = self._query_error_key(slot=slot)
        try:
            with self._adapter.get_sync_session() as session:
                return [_row_to_record(row) for row in session.execute(statement).scalars().all()]
        except Exception as exc:
            raise LedgerOperationError(key, f"查询 runnable 失败：{exc}", cause=exc) from exc

    def mark_running(self, key: DeviceDayKey) -> LedgerRecord:
        """原子领取 ready/revision_pending 记录并推进到 running。"""

        now = datetime.utcnow()
        try:
            with self._adapter.get_sync_session() as session:
                row = self._require_row(session, key)
                self._assert_status(key, row, _RUNNABLE_STATUSES, _RUNNING)
                row.status = _RUNNING
                row.processed_at = now
                row.updated_at = now
                session.flush()
                return _row_to_record(row)
        except LedgerOperationError:
            raise
        except Exception as exc:
            raise LedgerOperationError(key, f"标记 running 失败：{exc}", cause=exc) from exc

    def mark_succeeded(
        self,
        key: DeviceDayKey,
        batch_id: str,
        fingerprint: str,
    ) -> LedgerRecord:
        """把 running 记录推进到 succeeded 并保存成功批次与指纹。"""

        now = datetime.utcnow()
        try:
            with self._adapter.get_sync_session() as session:
                row = self._require_row(session, key)
                if (
                    row.status == _SUCCEEDED
                    and row.batch_id == batch_id
                    and row.input_fingerprint == fingerprint
                ):
                    return _row_to_record(row)
                self._assert_status(key, row, (_RUNNING,), _SUCCEEDED)
                if row.batch_id is not None and row.batch_id != batch_id:
                    row.supersedes_batch_id = row.batch_id
                row.status = _SUCCEEDED
                row.batch_id = batch_id
                row.input_fingerprint = fingerprint
                row.last_error = None
                row.processed_at = now
                row.updated_at = now
                session.flush()
                return _row_to_record(row)
        except LedgerOperationError:
            raise
        except Exception as exc:
            raise LedgerOperationError(key, f"标记 succeeded 失败：{exc}", cause=exc) from exc

    def reconcile_succeeded_from_batch(
        self,
        key: DeviceDayKey,
        *,
        batch_id: str,
        fingerprint: str,
        activation_epoch_id: str,
        supersedes_batch_id: Optional[str] = None,
    ) -> LedgerRecord:
        """以已原子落盘的不可变批次补齐 succeeded Ledger 事实。

        ``batch_id`` — 已确认存在的不可变批次标识；``fingerprint`` — 批次输入指纹；
        ``activation_epoch_id`` — 批次所属启用周期；``supersedes_batch_id`` — 修订所替代的
        旧批次。该入口专用于“批次落盘成功、Ledger 事务失败”的崩溃恢复，不要求记录先处于
        running；但拒绝用无关旧批次覆盖更新的 succeeded 事实。
        """

        normalized_batch_id = str(batch_id or "").strip()
        normalized_fingerprint = str(fingerprint or "").strip()
        normalized_epoch_id = str(activation_epoch_id or "").strip()
        normalized_supersedes = str(supersedes_batch_id or "").strip() or None
        if not normalized_batch_id:
            raise LedgerOperationError(key, "批次对账缺少 batch_id — 不可变批次标识")
        if not normalized_fingerprint:
            raise LedgerOperationError(key, "批次对账缺少 input_fingerprint — 输入指纹")
        if not normalized_epoch_id:
            raise LedgerOperationError(key, "批次对账缺少 activation_epoch_id — 启用周期标识")
        if normalized_supersedes == normalized_batch_id:
            raise LedgerOperationError(key, "batch_id 不得与 supersedes_batch_id 相同")

        now = datetime.utcnow()
        try:
            with self._adapter.get_sync_session() as session:
                row = self._locked_row(session, key)
                if row is None:
                    if normalized_supersedes is not None:
                        raise LedgerOperationError(
                            key,
                            "Ledger 不存在时不能接受带 supersedes_batch_id 的孤立修订批次",
                        )
                    row = SeqDeviceDayLedger(
                        **key.as_primary_key(),
                        activation_epoch_id=normalized_epoch_id,
                        status=_SUCCEEDED,
                        input_fingerprint=normalized_fingerprint,
                        batch_id=normalized_batch_id,
                        supersedes_batch_id=None,
                        attempt_count=0,
                        last_error=None,
                        processed_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    session.flush()
                    return _row_to_record(row)

                if (
                    row.status == _SUCCEEDED
                    and row.batch_id == normalized_batch_id
                    and row.input_fingerprint == normalized_fingerprint
                ):
                    return _row_to_record(row)

                current_batch_id = str(row.batch_id or "").strip() or None
                if current_batch_id is not None and current_batch_id != normalized_batch_id:
                    if normalized_supersedes != current_batch_id:
                        raise LedgerOperationError(
                            key,
                            "批次修订链不连续："
                            f"ledger_batch_id={current_batch_id!r}, "
                            f"supersedes_batch_id={normalized_supersedes!r}",
                        )
                elif row.status == _SUCCEEDED and current_batch_id is None:
                    raise LedgerOperationError(key, "succeeded Ledger 缺少 batch_id，拒绝猜测覆盖")

                row.activation_epoch_id = normalized_epoch_id
                row.status = _SUCCEEDED
                row.supersedes_batch_id = normalized_supersedes
                row.batch_id = normalized_batch_id
                row.input_fingerprint = normalized_fingerprint
                row.last_error = None
                row.processed_at = now
                row.updated_at = now
                session.flush()
                return _row_to_record(row)
        except LedgerOperationError:
            raise
        except Exception as exc:
            raise LedgerOperationError(key, f"不可变批次对账失败：{exc}", cause=exc) from exc

    def mark_failed(self, key: DeviceDayKey, error: str) -> LedgerRecord:
        """记录推理失败；修订失败时恢复旧 succeeded 事实。

        普通首跑失败进入 failed 并增加 ``attempt_count`` — 尝试次数。若 running 记录仍携带
        旧 ``batch_id`` 且 ``supersedes_batch_id`` 指向该旧批次，说明本轮是修订尝试；失败时
        恢复旧 succeeded 状态和旧批次/指纹，仅记录错误与次数，避免把已确认事实抹掉。
        """

        now = datetime.utcnow()
        try:
            with self._adapter.get_sync_session() as session:
                row = self._require_row(session, key)
                self._assert_status(key, row, (_RUNNING,), _FAILED)
                is_revision = bool(
                    row.batch_id
                    and row.supersedes_batch_id
                    and row.batch_id == row.supersedes_batch_id
                )
                row.status = _SUCCEEDED if is_revision else _FAILED
                if is_revision:
                    row.supersedes_batch_id = None
                row.attempt_count = int(row.attempt_count or 0) + 1
                row.last_error = str(error)
                row.processed_at = now
                row.updated_at = now
                session.flush()
                return _row_to_record(row)
        except LedgerOperationError:
            raise
        except Exception as exc:
            raise LedgerOperationError(key, f"标记 failed 失败：{exc}", cause=exc) from exc

    def compute_frontier(self, device_key: DeviceKey, epoch_id: str) -> Optional[date]:
        """派生同设备、同启用周期从责任起始日起连续 succeeded 的最后日期。

        起点取 ``PathActivationDeviceScope.effective_from_date`` — 设备责任起始日；起点缺失、
        首日缺失或首日非 succeeded 时返回 ``None``。扫描遇到任意日期缺口或非成功状态立即停止，
        不会用更晚的 succeeded 跨洞推进前沿。
        """

        error_key = device_key.diagnostic_key()
        try:
            with self._adapter.get_sync_session() as session:
                scope = session.get(
                    PathActivationDeviceScope,
                    {
                        "activation_epoch_id": epoch_id,
                        "site_id": device_key.site_id,
                        "device_id": device_key.device_id,
                        "branch_id": device_key.branch_id,
                    },
                )
                if scope is None or scope.effective_from_date is None:
                    return None
                rows = session.execute(
                    select(
                        SeqDeviceDayLedger.business_date,
                        SeqDeviceDayLedger.status,
                    )
                    .where(
                        SeqDeviceDayLedger.slot == device_key.slot,
                        SeqDeviceDayLedger.modeling_path == device_key.modeling_path,
                        SeqDeviceDayLedger.site_id == device_key.site_id,
                        SeqDeviceDayLedger.device_id == device_key.device_id,
                        SeqDeviceDayLedger.branch_id == device_key.branch_id,
                        SeqDeviceDayLedger.activation_epoch_id == epoch_id,
                        SeqDeviceDayLedger.business_date >= scope.effective_from_date,
                    )
                    .order_by(SeqDeviceDayLedger.business_date.asc())
                ).all()

                expected = scope.effective_from_date
                frontier: Optional[date] = None
                for business_date, status in rows:
                    if business_date != expected or status != _SUCCEEDED:
                        break
                    frontier = business_date
                    expected = expected + timedelta(days=1)
                return frontier
        except Exception as exc:
            raise LedgerOperationError(
                error_key,
                f"计算 frontier 失败 epoch_id={epoch_id!r}：{exc}",
                cause=exc,
            ) from exc


__all__ = [
    "DeviceDayKey",
    "DeviceKey",
    "LedgerRecord",
    "LedgerOperationError",
    "SeqDeviceDayLedgerRepository",
    "stable_input_fingerprint",
]
# @AI_GENERATED: end
