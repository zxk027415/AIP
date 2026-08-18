# @AI_GENERATED
# -*- coding: utf-8 -*-
"""
路径启用周期服务：计算并持久化逐设备生产责任边界与排他车道认领。

本模块只负责 PathActivationEpoch（启用周期）、DeviceScope（设备责任范围）与
LaneClaim（车道日期认领）；不执行历史回放，也不实现容量仲裁。预览是纯计算，
持久化写入统一复用调用方注入的 DBAdapter 事务。

字段（英文名 — 中文含义）：
- ``activation_epoch_id`` — 每次启用生成的新周期标识，不复用旧周期。
- ``effective_from_date`` — 本周期开始承担责任的设备自然日。
- ``production_cutover_date`` — 生产车道开始接管的自然日。
- ``range_start`` / ``range_end`` — 车道半开区间起点 / 不含的终点。
- ``device_scope_digest`` — 按设备与车道稳定排序后计算的 SHA-256 审计摘要。

Requirements: 5.6, 5.8, 14.1-14.5, 14.8-14.13
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, delete, or_, select

from services.db.adapter import DBAdapter
from services.db.models.pv_fault import (
    PathActivationDeviceScope,
    PathActivationEpoch,
    PathActivationLaneClaim,
)
from services.scheduler.pv_dual_path.config import DualPathConfig

CUTOVER_ONLY = "cutover_only"
RECENT_WINDOW = "recent_window"
FULL_BACKFILL = "full_backfill"
PRODUCTION_LANE = "production"
HISTORICAL_BACKFILL_LANE = "historical_backfill"
_ALLOWED_MODES = frozenset({CUTOVER_ONLY, RECENT_WINDOW, FULL_BACKFILL})


class PathActivationValidationError(ValueError):
    """启用请求字段或边界组合非法，调用方不得建立 Epoch。"""


@dataclass(frozen=True, order=True)
class DeviceScope:
    """设备三元组（``site_id`` — 站点、``device_id`` — 设备、``branch_id`` — 支路）。"""

    site_id: str
    device_id: str
    branch_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("site_id", self.site_id),
            ("device_id", self.device_id),
            ("branch_id", self.branch_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise PathActivationValidationError(f"{field_name} — 设备分区字段不能为空")


@dataclass(frozen=True)
class DeviceActivationInput:
    """单设备计算输入：设备三元组、启用水位与最早到达自然日。"""

    scope: DeviceScope
    device_watermark: Optional[datetime]
    earliest_arrival: Optional[date]


@dataclass(frozen=True)
class LaneClaimSpec:
    """车道认领规格；日期范围采用 ``[range_start, range_end)`` 半开区间。"""

    scope: DeviceScope
    lane: str
    range_start: date
    range_end: Optional[date]
    claim_status: str = "claimed"
    backfill_task_id: Optional[str] = None

    def contains(self, business_date: date) -> bool:
        """判断自然日是否落在本认领的半开区间内。"""
        return self.range_start <= business_date and (
            self.range_end is None or business_date < self.range_end
        )


@dataclass(frozen=True)
class DeviceActivationScope:
    """单设备启用结果，包含水位、责任边界与该设备的车道认领。"""

    scope: DeviceScope
    activation_watermark: Optional[datetime]
    effective_from_date: Optional[date]
    production_cutover_date: Optional[date]
    claims: Tuple[LaneClaimSpec, ...]


@dataclass(frozen=True)
class ActivationRequest:
    """启用请求；``devices`` — 逐设备输入，其他字段对应周期级 ORM 字段。"""

    modeling_path: str
    activation_mode: str
    devices: Sequence[DeviceActivationInput]
    slot: str = "pv_fault"
    backfill_days: Optional[int] = None
    note: Optional[str] = None
    comparison_id: Optional[str] = None
    operator: Optional[str] = None


@dataclass(frozen=True)
class ActivationPreview:
    """无副作用预览：逐设备边界、全部 claims、稳定摘要与设备数量。"""

    slot: str
    modeling_path: str
    activation_mode: str
    backfill_days: Optional[int]
    device_scopes: Tuple[DeviceActivationScope, ...]
    claims: Tuple[LaneClaimSpec, ...]
    effective_from_date: Optional[date]
    device_scope_digest: str
    device_scope_count: int


class PathActivationService:
    """路径启用服务：纯计算预览、单事务建周期、首次到达补边界及当前边界查询。"""

    def __init__(
        self,
        adapter: DBAdapter,
        config: DualPathConfig,
        *,
        epoch_id_factory: Optional[Callable[[], str]] = None,
        now_factory: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._adapter = adapter
        self._config = config
        self._epoch_id_factory = epoch_id_factory or (
            lambda: f"pae-{uuid.uuid4().hex}"
        )
        self._now_factory = now_factory or datetime.utcnow

    def effective_from(
        self,
        mode: str,
        device_watermark: Optional[date | datetime],
        earliest_arrival: Optional[date | datetime],
        backfill_days: Optional[int],
    ) -> Optional[date]:
        """按模式计算设备责任起点；无水位一律返回空边界。

        ``cutover_only`` 从水位日前一日开始；``recent_window`` 含最近结束日在内
        共 ``backfill_days`` 个自然日，因此再向前移动 ``backfill_days - 1`` 天；
        ``full_backfill`` 从最早到达日开始。
        """
        normalized_days = self._validate_mode_and_backfill(mode, backfill_days)
        watermark_date = _as_date(device_watermark)
        if watermark_date is None:
            return None
        latest_closed_date = watermark_date - timedelta(days=1)
        if mode == CUTOVER_ONLY:
            return latest_closed_date
        if mode == RECENT_WINDOW:
            assert normalized_days is not None
            return latest_closed_date - timedelta(days=normalized_days - 1)
        return _as_date(earliest_arrival)

    def preview(self, request: ActivationRequest) -> ActivationPreview:
        """纯计算逐设备边界、claims 与摘要；不打开数据库事务、不产生写副作用。"""
        normalized_days = self._validate_request(request)
        device_scopes = []
        all_claims = []
        for device in sorted(request.devices, key=lambda item: item.scope):
            effective_from_date = self.effective_from(
                request.activation_mode,
                device.device_watermark,
                device.earliest_arrival,
                normalized_days,
            )
            production_cutover_date = self._production_cutover(
                request.activation_mode,
                device.device_watermark,
                effective_from_date,
            )
            claims = self._build_claims(
                device.scope,
                request.activation_mode,
                effective_from_date,
                production_cutover_date,
            )
            all_claims.extend(claims)
            device_scopes.append(
                DeviceActivationScope(
                    scope=device.scope,
                    activation_watermark=device.device_watermark,
                    effective_from_date=effective_from_date,
                    production_cutover_date=production_cutover_date,
                    claims=claims,
                )
            )

        scopes_tuple = tuple(device_scopes)
        claims_tuple = tuple(all_claims)
        non_empty_boundaries = [
            item.effective_from_date
            for item in scopes_tuple
            if item.effective_from_date is not None
        ]
        return ActivationPreview(
            slot=request.slot,
            modeling_path=request.modeling_path,
            activation_mode=request.activation_mode,
            backfill_days=normalized_days if request.activation_mode == RECENT_WINDOW else None,
            device_scopes=scopes_tuple,
            claims=claims_tuple,
            effective_from_date=min(non_empty_boundaries) if non_empty_boundaries else None,
            device_scope_digest=_scope_digest(scopes_tuple),
            device_scope_count=len(scopes_tuple),
        )

    def create_epoch(self, request: ActivationRequest) -> PathActivationEpoch:
        """在一个数据库事务内写入 Epoch、全部 DeviceScope 与 LaneClaim。

        每次调用都由 ``epoch_id_factory`` 生成新标识；即使目标路径相同，也不覆盖或
        复用旧周期。校验与预览先完成，非法模式或超限回看不会打开写事务。
        """
        preview = self.preview(request)
        epoch_id = self._epoch_id_factory()
        epoch = PathActivationEpoch(
            activation_epoch_id=epoch_id,
            slot=preview.slot,
            modeling_path=preview.modeling_path,
            activation_mode=preview.activation_mode,
            backfill_days=preview.backfill_days,
            activated_at=self._now_factory(),
            note=request.note,
            comparison_id=request.comparison_id,
            operator=request.operator,
        )
        scope_rows = [
            PathActivationDeviceScope(
                activation_epoch_id=epoch_id,
                site_id=item.scope.site_id,
                device_id=item.scope.device_id,
                branch_id=item.scope.branch_id,
                activation_watermark=item.activation_watermark,
                effective_from_date=item.effective_from_date,
                production_cutover_date=item.production_cutover_date,
            )
            for item in preview.device_scopes
        ]
        claim_rows = [self._claim_row(epoch_id, item) for item in preview.claims]

        with self._adapter.get_sync_session() as session:
            session.add(epoch)
            session.add_all(scope_rows)
            session.add_all(claim_rows)
        return epoch

    def complete_empty_boundary_on_first_arrival(
        self,
        activation_epoch_id: str,
        scope: DeviceScope,
        first_arrival: date | datetime,
        *,
        activation_watermark: Optional[datetime] = None,
    ) -> DeviceActivationScope:
        """首次数据到达后原子补齐空边界与 production claim。

        首次到达是 Req14.9 的特殊规则：责任起点直接取该次到达自然日，不再套用
        常规的“水位日前一日”公式。行锁与条件检查保证并发调用只补一次；已有边界时
        幂等返回当前值，不改写既有事实。
        """
        arrival_date = _as_date(first_arrival)
        if arrival_date is None:
            raise PathActivationValidationError("first_arrival — 首次到达时间不能为空")
        watermark = activation_watermark
        if watermark is None:
            watermark = (
                first_arrival
                if isinstance(first_arrival, datetime)
                else datetime.combine(first_arrival, time.min)
            )

        with self._adapter.get_sync_session() as session:
            epoch = session.get(PathActivationEpoch, activation_epoch_id)
            if epoch is None:
                raise LookupError(f"未找到 activation_epoch_id={activation_epoch_id!r}")
            primary_key = _scope_primary_key(activation_epoch_id, scope)
            row = session.get(
                PathActivationDeviceScope,
                primary_key,
                with_for_update=True,
            )
            if row is None:
                raise LookupError(
                    f"未找到周期设备范围 activation_epoch_id={activation_epoch_id!r}, "
                    f"device={scope!r}"
                )
            if row.effective_from_date is None:
                existing_claim = session.execute(
                    select(PathActivationLaneClaim).where(
                        PathActivationLaneClaim.activation_epoch_id == activation_epoch_id,
                        PathActivationLaneClaim.site_id == scope.site_id,
                        PathActivationLaneClaim.device_id == scope.device_id,
                        PathActivationLaneClaim.branch_id == scope.branch_id,
                    )
                ).scalars().first()
                if existing_claim is not None:
                    raise RuntimeError("空设备边界已存在 LaneClaim，拒绝产生不一致的部分补齐")
                row.activation_watermark = watermark
                row.effective_from_date = arrival_date
                row.production_cutover_date = arrival_date
                session.add(
                    self._claim_row(
                        activation_epoch_id,
                        LaneClaimSpec(
                            scope=scope,
                            lane=PRODUCTION_LANE,
                            range_start=arrival_date,
                            range_end=None,
                        ),
                    )
                )
            claims = self._read_claims_in_session(session, activation_epoch_id, scope)
            result = _scope_from_rows(row, claims)
        return result

    def current_device_boundary(
        self,
        activation_epoch_id: str,
        scope: DeviceScope,
    ) -> Optional[DeviceActivationScope]:
        """按当前 Registry 提供的 Epoch ID 精确查询设备边界，不猜测其他路径或旧周期。"""
        with self._adapter.get_sync_session() as session:
            row = session.get(
                PathActivationDeviceScope,
                _scope_primary_key(activation_epoch_id, scope),
            )
            if row is None:
                return None
            claims = self._read_claims_in_session(session, activation_epoch_id, scope)
            return _scope_from_rows(row, claims)

    def current_claim(
        self,
        activation_epoch_id: str,
        scope: DeviceScope,
        business_date: date,
        *,
        lane: Optional[str] = None,
    ) -> Optional[LaneClaimSpec]:
        """查询某设备日当前所属 claim；可指定 production 或 historical_backfill 车道。"""
        if lane is not None and lane not in {PRODUCTION_LANE, HISTORICAL_BACKFILL_LANE}:
            raise PathActivationValidationError(f"非法 lane={lane!r}")
        conditions = [
            PathActivationLaneClaim.activation_epoch_id == activation_epoch_id,
            PathActivationLaneClaim.site_id == scope.site_id,
            PathActivationLaneClaim.device_id == scope.device_id,
            PathActivationLaneClaim.branch_id == scope.branch_id,
            PathActivationLaneClaim.range_start <= business_date,
            or_(
                PathActivationLaneClaim.range_end.is_(None),
                PathActivationLaneClaim.range_end > business_date,
            ),
        ]
        if lane is not None:
            conditions.append(PathActivationLaneClaim.lane == lane)
        with self._adapter.get_sync_session() as session:
            rows = session.execute(
                select(PathActivationLaneClaim).where(and_(*conditions))
            ).scalars().all()
            if len(rows) > 1:
                raise RuntimeError("同一设备日命中多个 LaneClaim，排他区间已损坏")
            return _claim_from_row(rows[0]) if rows else None

    def list_epochs(
        self,
        *,
        slot: str,
        modeling_path: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """只读分页返回 Epoch、DeviceScope 与 LaneClaim。"""
        normalized_page = max(1, int(page))
        normalized_size = max(1, min(int(page_size), 200))
        offset = (normalized_page - 1) * normalized_size
        filters = [PathActivationEpoch.slot == slot]
        if modeling_path:
            filters.append(PathActivationEpoch.modeling_path == modeling_path)
        with self._adapter.get_sync_session() as session:
            total = session.execute(
                select(PathActivationEpoch).where(*filters)
            ).scalars().all()
            total_count = len(total)
            rows = sorted(total, key=lambda item: item.activated_at or datetime.min, reverse=True)
            page_rows = rows[offset : offset + normalized_size]
            items: List[Dict[str, Any]] = []
            for epoch in page_rows:
                scopes = session.execute(
                    select(PathActivationDeviceScope).where(
                        PathActivationDeviceScope.activation_epoch_id == epoch.activation_epoch_id
                    )
                ).scalars().all()
                claims = session.execute(
                    select(PathActivationLaneClaim).where(
                        PathActivationLaneClaim.activation_epoch_id == epoch.activation_epoch_id
                    )
                ).scalars().all()
                items.append(
                    {
                        "activation_epoch_id": epoch.activation_epoch_id,
                        "slot": epoch.slot,
                        "modeling_path": epoch.modeling_path,
                        "activation_mode": epoch.activation_mode,
                        "backfill_days": epoch.backfill_days,
                        "activated_at": epoch.activated_at.isoformat() if epoch.activated_at else None,
                        "note": epoch.note,
                        "comparison_id": epoch.comparison_id,
                        "operator": epoch.operator,
                        "device_scopes": [
                            {
                                "site_id": scope.site_id,
                                "device_id": scope.device_id,
                                "branch_id": scope.branch_id,
                                "effective_from_date": (
                                    scope.effective_from_date.isoformat()
                                    if scope.effective_from_date
                                    else None
                                ),
                                "production_cutover_date": (
                                    scope.production_cutover_date.isoformat()
                                    if scope.production_cutover_date
                                    else None
                                ),
                            }
                            for scope in scopes
                        ],
                        "lane_claims": [
                            {
                                "site_id": claim.site_id,
                                "device_id": claim.device_id,
                                "branch_id": claim.branch_id,
                                "lane": claim.lane,
                                "range_start": claim.range_start.isoformat() if claim.range_start else None,
                                "range_end": claim.range_end.isoformat() if claim.range_end else None,
                                "claim_status": claim.claim_status,
                                "backfill_task_id": claim.backfill_task_id,
                            }
                            for claim in claims
                        ],
                    }
                )
            return {
                "page": normalized_page,
                "page_size": normalized_size,
                "total": total_count,
                "items": items,
            }

    def delete_epoch(self, activation_epoch_id: str) -> None:
        """补偿回滚：同一事务删除 Epoch 及其 DeviceScope/LaneClaim。"""
        epoch_id = str(activation_epoch_id or "").strip()
        if not epoch_id:
            return
        with self._adapter.get_sync_session() as session:
            session.execute(
                delete(PathActivationLaneClaim).where(
                    PathActivationLaneClaim.activation_epoch_id == epoch_id
                )
            )
            session.execute(
                delete(PathActivationDeviceScope).where(
                    PathActivationDeviceScope.activation_epoch_id == epoch_id
                )
            )
            session.execute(
                delete(PathActivationEpoch).where(
                    PathActivationEpoch.activation_epoch_id == epoch_id
                )
            )

    def _validate_request(self, request: ActivationRequest) -> Optional[int]:
        if not isinstance(request.slot, str) or not request.slot.strip():
            raise PathActivationValidationError("slot — 槽位不能为空")
        if not isinstance(request.modeling_path, str) or not request.modeling_path.strip():
            raise PathActivationValidationError("modeling_path — 建模路径不能为空")
        normalized_days = self._validate_mode_and_backfill(
            request.activation_mode,
            request.backfill_days,
        )
        scopes = [item.scope for item in request.devices]
        if len(scopes) != len(set(scopes)):
            raise PathActivationValidationError("devices — 设备三元组不得重复")
        return normalized_days

    def _validate_mode_and_backfill(
        self,
        mode: str,
        backfill_days: Optional[int],
    ) -> Optional[int]:
        if mode not in _ALLOWED_MODES:
            raise PathActivationValidationError(
                f"非法 activation_mode={mode!r}，仅允许 {sorted(_ALLOWED_MODES)}"
            )
        if backfill_days is not None:
            if isinstance(backfill_days, bool) or not isinstance(backfill_days, int):
                raise PathActivationValidationError("backfill_days — 回看天数必须为整数")
            if backfill_days < 1:
                raise PathActivationValidationError("backfill_days — 回看天数必须至少为 1")
            if backfill_days > self._config.max_backfill_days:
                raise PathActivationValidationError(
                    "backfill_days — 请求回看天数超限："
                    f"requested={backfill_days}, maximum={self._config.max_backfill_days}"
                )
        if mode == RECENT_WINDOW and backfill_days is None:
            raise PathActivationValidationError(
                "backfill_days — recent_window 模式必须显式提供回看天数"
            )
        return backfill_days

    @staticmethod
    def _production_cutover(
        mode: str,
        device_watermark: Optional[date | datetime],
        effective_from_date: Optional[date],
    ) -> Optional[date]:
        if effective_from_date is None:
            return None
        if mode == FULL_BACKFILL:
            watermark_date = _as_date(device_watermark)
            return watermark_date - timedelta(days=1) if watermark_date is not None else None
        return effective_from_date

    @staticmethod
    def _build_claims(
        scope: DeviceScope,
        mode: str,
        effective_from_date: Optional[date],
        production_cutover_date: Optional[date],
    ) -> Tuple[LaneClaimSpec, ...]:
        if effective_from_date is None or production_cutover_date is None:
            return ()
        if mode == FULL_BACKFILL:
            if effective_from_date > production_cutover_date:
                raise PathActivationValidationError(
                    "full_backfill 边界非法：effective_from_date 晚于 production_cutover_date"
                )
            claims = []
            if effective_from_date < production_cutover_date:
                claims.append(
                    LaneClaimSpec(
                        scope=scope,
                        lane=HISTORICAL_BACKFILL_LANE,
                        range_start=effective_from_date,
                        range_end=production_cutover_date,
                    )
                )
            claims.append(
                LaneClaimSpec(
                    scope=scope,
                    lane=PRODUCTION_LANE,
                    range_start=production_cutover_date,
                    range_end=None,
                )
            )
            return tuple(claims)
        return (
            LaneClaimSpec(
                scope=scope,
                lane=PRODUCTION_LANE,
                range_start=effective_from_date,
                range_end=None,
            ),
        )

    @staticmethod
    def _claim_row(epoch_id: str, claim: LaneClaimSpec) -> PathActivationLaneClaim:
        return PathActivationLaneClaim(
            activation_epoch_id=epoch_id,
            site_id=claim.scope.site_id,
            device_id=claim.scope.device_id,
            branch_id=claim.scope.branch_id,
            lane=claim.lane,
            range_start=claim.range_start,
            range_end=claim.range_end,
            claim_status=claim.claim_status,
            backfill_task_id=claim.backfill_task_id,
        )

    @staticmethod
    def _read_claims_in_session(
        session,
        activation_epoch_id: str,
        scope: DeviceScope,
    ) -> Tuple[PathActivationLaneClaim, ...]:
        rows = session.execute(
            select(PathActivationLaneClaim)
            .where(
                PathActivationLaneClaim.activation_epoch_id == activation_epoch_id,
                PathActivationLaneClaim.site_id == scope.site_id,
                PathActivationLaneClaim.device_id == scope.device_id,
                PathActivationLaneClaim.branch_id == scope.branch_id,
            )
            .order_by(
                PathActivationLaneClaim.range_start,
                PathActivationLaneClaim.lane,
            )
        ).scalars().all()
        return tuple(rows)


def _as_date(value: Optional[date | datetime]) -> Optional[date]:
    """把 datetime/date 统一成自然日；datetime 必须先判断，因为它继承 date。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise PathActivationValidationError(f"日期字段类型非法：{type(value).__name__}")


def _scope_primary_key(epoch_id: str, scope: DeviceScope) -> dict[str, str]:
    return {
        "activation_epoch_id": epoch_id,
        "site_id": scope.site_id,
        "device_id": scope.device_id,
        "branch_id": scope.branch_id,
    }


def _claim_from_row(row: PathActivationLaneClaim) -> LaneClaimSpec:
    return LaneClaimSpec(
        scope=DeviceScope(row.site_id, row.device_id, row.branch_id),
        lane=row.lane,
        range_start=row.range_start,
        range_end=row.range_end,
        claim_status=row.claim_status,
        backfill_task_id=row.backfill_task_id,
    )


def _scope_from_rows(
    row: PathActivationDeviceScope,
    claims: Sequence[PathActivationLaneClaim],
) -> DeviceActivationScope:
    scope = DeviceScope(row.site_id, row.device_id, row.branch_id)
    return DeviceActivationScope(
        scope=scope,
        activation_watermark=row.activation_watermark,
        effective_from_date=row.effective_from_date,
        production_cutover_date=row.production_cutover_date,
        claims=tuple(_claim_from_row(item) for item in claims),
    )


def _scope_digest(scopes: Sequence[DeviceActivationScope]) -> str:
    """按设备与 claim 稳定序列化；空边界设备也进入摘要，避免范围遗漏。"""
    records = []
    for item in scopes:
        if item.claims:
            for claim in item.claims:
                records.append(
                    {
                        "site_id": item.scope.site_id,
                        "device_id": item.scope.device_id,
                        "branch_id": item.scope.branch_id,
                        "lane": claim.lane,
                        "range_start": claim.range_start.isoformat(),
                        "range_end": claim.range_end.isoformat() if claim.range_end else None,
                    }
                )
        else:
            records.append(
                {
                    "site_id": item.scope.site_id,
                    "device_id": item.scope.device_id,
                    "branch_id": item.scope.branch_id,
                    "lane": None,
                    "range_start": None,
                    "range_end": None,
                }
            )
    records.sort(
        key=lambda item: (
            item["site_id"],
            item["device_id"],
            item["branch_id"],
            item["lane"] or "",
            item["range_start"] or "",
            item["range_end"] or "",
        )
    )
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
# @AI_GENERATED: end
