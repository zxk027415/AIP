"""
precision_ops/version_registry.py — 工作流版本注册表

职责：
  - 工作流版本的注册、状态管理、生命周期转换
  - 单一生产版本不变式（同一 slot 最多一个 production）
  - 影子版本上限管理（超出 max_shadow_versions 时退役最老的）
  - 所有写操作通过 fcntl 文件锁 + _atomic_write_json 保证原子性

存储路径：{BASE_DATA_DIR}/{slot}/version_registry.json
"""
from __future__ import annotations

import logging
import threading
from typing import List, Optional, TypedDict

from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled, _parse_iso
from services.precision_ops.utils import (
    BASE_DATA_DIR,
    _atomic_write_json,
    ensure_data_dir,
    load_json_safe,
    now_iso,
)

logger = logging.getLogger(__name__)

# fcntl 在 Windows 上不可用，降级为无锁
try:
    import fcntl
    _FCNTL_AVAILABLE = True
except ImportError:
    _FCNTL_AVAILABLE = False
    logger.warning("fcntl 不可用，版本注册表写操作将不使用文件锁")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class VersionEntry(TypedDict):
    """版本注册条目数据模型"""
    workflow_id: str                    # 工作流模板 ID
    version_tag: str                    # 版本标签，最大 128 字符，同一 workflow_id 下唯一
    source_run_id: Optional[str]        # 来源 AutoResearch run ID（可选，用于审计追溯）
    source_candidate_id: Optional[str]  # 来源候选 ID（可选，用于审计追溯）
    registered_at: str                  # 注册时间 ISO 8601
    status: str                         # "production"（生产）| "shadow"（影子）| "retired"（退役）
    slot: str                           # 槽位（分区键），默认 "default"
    baseline_mape: Optional[float]      # 注册时的历史基线 MAPE（可选，供退化检测使用）


# ---------------------------------------------------------------------------
# 合法状态转换集合
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: set[tuple[str, str]] = {
    ("production", "shadow"),   # 被新版本取代 / 手动降级
    ("production", "retired"),  # 手动退役
    ("shadow", "production"),   # 自动择优切换 / 手动提升
    ("shadow", "retired"),      # 超出 max_shadow / 手动退役
}
"""
合法的版本状态转换集合。
retired 是终态，不允许从 retired 转换到任何状态。
"""

_VALID_STATUSES = {"production", "shadow", "retired"}
_REQUIRED_FIELDS = {"workflow_id", "version_tag", "status", "slot"}
_MAX_VERSION_TAG_LENGTH = 128
_DEFAULT_MAX_SHADOW_VERSIONS = 5


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _lock_file(f) -> None:
    """获取文件排他锁（fcntl 可用时）"""
    if _FCNTL_AVAILABLE:
        fcntl.flock(f, fcntl.LOCK_EX)


def _unlock_file(f) -> None:
    """释放文件锁（fcntl 可用时）"""
    if _FCNTL_AVAILABLE:
        fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# VersionRegistry
# ---------------------------------------------------------------------------

class VersionRegistry:
    """
    工作流版本注册表。

    存储：{BASE_DATA_DIR}/{slot}/version_registry.json
    每个槽位（slot）独立一个 JSON 文件，写操作通过 fcntl 文件锁防止并发竞争。

    JSON 结构：
    {
      "slot": "default",
      "versions": [ ...VersionEntry... ],
      "max_shadow_versions": 5
    }
    """

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def register(self, entry: dict) -> dict:
        """
        注册一个新版本。

        校验顺序：
        1. 必填字段（workflow_id, version_tag, status, slot）
        2. version_tag 长度 ≤ 128
        3. status 必须是合法值
        4. (workflow_id, version_tag) 在同一 slot 内唯一

        若 status=production，原子降级现有 production 为 shadow，
        追加新条目，调用 _enforce_shadow_cap，原子写入。

        :param entry: 版本信息字典（至少含必填字段）
        :return: 完整的版本条目（含 registered_at 和可选字段默认值）
        :raises ValueError: 字段校验失败或 (workflow_id, version_tag) 重复
        """
        # 1. 必填字段校验
        missing = _REQUIRED_FIELDS - set(entry.keys())
        if missing:
            raise ValueError(f"注册版本缺少必填字段：{sorted(missing)}")

        workflow_id: str = entry["workflow_id"]
        version_tag: str = entry["version_tag"]
        status: str = entry["status"]
        slot: str = entry["slot"]

        # 2. version_tag 长度校验
        if len(version_tag) > _MAX_VERSION_TAG_LENGTH:
            raise ValueError(
                f"version_tag 超出最大长度 {_MAX_VERSION_TAG_LENGTH}，"
                f"当前长度：{len(version_tag)}"
            )

        # 3. status 合法性校验
        if status not in _VALID_STATUSES:
            raise ValueError(
                f"status 非法，允许值：{_VALID_STATUSES}，传入：{status!r}"
            )

        # 复制并补全可选字段
        entry = dict(entry)
        if not entry.get("registered_at"):
            entry["registered_at"] = now_iso()
        entry.setdefault("source_run_id", None)
        entry.setdefault("source_candidate_id", None)
        entry.setdefault("baseline_mape", None)

        # 4. 带文件锁执行写操作
        ensure_data_dir(slot)
        lock_path = BASE_DATA_DIR / slot / "version_registry.lock"
        lock_fd = open(str(lock_path), "w")
        try:
            _lock_file(lock_fd)
            data = self._load(slot)
            versions: list = data.get("versions", [])

            # 5. 唯一性校验
            for v in versions:
                if v["workflow_id"] == workflow_id and v["version_tag"] == version_tag:
                    raise ValueError(
                        f"(workflow_id={workflow_id!r}, version_tag={version_tag!r}) "
                        f"在 slot={slot!r} 中已存在"
                    )

            # 6. 若新注册为 production，降级现有 production → shadow
            if status == "production":
                for v in versions:
                    if v.get("status") == "production":
                        v["status"] = "shadow"
                        logger.info(
                            "register: 降级现有 production → shadow: "
                            "workflow_id=%s, version_tag=%s",
                            v["workflow_id"], v["version_tag"],
                        )

            # 7. 追加新条目
            versions.append(entry)
            data["versions"] = versions

            # 8. 影子版本上限检查（就地修改 data）
            self._enforce_shadow_cap(slot, data)

            # 9. 原子写入
            self._save(slot, data)

            # DB dual-write（异步，best-effort）
            if _is_db_enabled():
                _entry = dict(entry)

                def _db_write():
                    repo = _get_lf_repo()
                    if repo is None:
                        return
                    try:
                        repo.save_version_registry({
                            "slot": _entry.get("slot"),
                            "workflow_id": _entry.get("workflow_id"),
                            "version_tag": _entry.get("version_tag"),
                            "status": _entry.get("status"),
                            "source_run_id": _entry.get("source_run_id"),
                            "source_candidate_id": _entry.get("source_candidate_id"),
                            "baseline_mape": _entry.get("baseline_mape"),
                            "registered_at": _parse_iso(_entry.get("registered_at")),
                        })
                    except Exception as _exc:
                        logger.warning("DB 写入 version_registry 失败（忽略）: %s", _exc)

                threading.Thread(target=_db_write, daemon=True).start()

        finally:
            _unlock_file(lock_fd)
            lock_fd.close()

        logger.info(
            "register: 成功 workflow_id=%s, version_tag=%s, status=%s, slot=%s",
            workflow_id, version_tag, status, slot,
        )
        return entry

    def get_production(self, slot: str) -> Optional[dict]:
        """
        获取指定槽位当前生产版本。

        :param slot: 槽位名称
        :return: status=production 的版本条目，无则返回 None
        """
        data = self._load(slot)
        for v in data.get("versions", []):
            if v.get("status") == "production":
                return v
        return None

    def list_shadows(self, slot: str) -> List[dict]:
        """
        获取指定槽位所有影子版本列表。

        :param slot: 槽位名称
        :return: status=shadow 的版本条目列表
        """
        data = self._load(slot)
        return [v for v in data.get("versions", []) if v.get("status") == "shadow"]

    def list_all(self, slot: str) -> List[dict]:
        """
        获取指定槽位所有版本列表（含 production / shadow / retired）。

        :param slot: 槽位名称
        :return: 所有版本条目列表
        """
        data = self._load(slot)
        return list(data.get("versions", []))

    def transition_status(
        self, workflow_id: str, version_tag: str, new_status: str
    ) -> dict:
        """
        变更版本状态。

        校验：
        - new_status 必须是合法值
        - 目标版本必须存在（在任意 slot 下查找）
        - (当前状态, 目标状态) 必须在 ALLOWED_TRANSITIONS 中

        若 new_status=production，自动将现有 production 降级为 shadow。

        :param workflow_id: 工作流模板 ID
        :param version_tag: 版本标签
        :param new_status: 目标状态
        :return: 更新后的版本条目
        :raises ValueError: 版本不存在或转换不合法
        """
        if new_status not in _VALID_STATUSES:
            raise ValueError(
                f"目标状态非法，允许值：{_VALID_STATUSES}，传入：{new_status!r}"
            )

        slot = self._find_slot(workflow_id, version_tag)
        if slot is None:
            raise ValueError(
                f"未找到版本：workflow_id={workflow_id!r}, version_tag={version_tag!r}"
            )

        ensure_data_dir(slot)
        lock_path = BASE_DATA_DIR / slot / "version_registry.lock"
        lock_fd = open(str(lock_path), "w")
        try:
            _lock_file(lock_fd)
            data = self._load(slot)
            versions: list = data.get("versions", [])

            # 重新定位目标条目（锁内重读，防止并发修改）
            target = None
            for v in versions:
                if v["workflow_id"] == workflow_id and v["version_tag"] == version_tag:
                    target = v
                    break

            if target is None:
                raise ValueError(
                    f"未找到版本：workflow_id={workflow_id!r}, version_tag={version_tag!r}"
                )

            current_status = target["status"]

            # 幂等：已经是目标状态
            if current_status == new_status:
                return dict(target)

            if (current_status, new_status) not in ALLOWED_TRANSITIONS:
                raise ValueError(
                    f"非法状态转换：{current_status!r} → {new_status!r}，"
                    f"合法转换集合：{sorted(ALLOWED_TRANSITIONS)}"
                )

            # 若目标为 production，降级现有 production → shadow
            _demoted: list = []
            if new_status == "production":
                for v in versions:
                    if v is not target and v.get("status") == "production":
                        v["status"] = "shadow"
                        _demoted.append((v["workflow_id"], v["version_tag"]))
                        logger.info(
                            "transition_status: 降级现有 production → shadow: "
                            "workflow_id=%s, version_tag=%s",
                            v["workflow_id"], v["version_tag"],
                        )

            target["status"] = new_status
            data["versions"] = versions
            self._save(slot, data)
            result = dict(target)

        finally:
            _unlock_file(lock_fd)
            lock_fd.close()

        # DB sync（异步，best-effort）— 同步目标版本及被降级的 production 版本
        if _is_db_enabled():
            _slot = slot
            _result = result
            _demoted_copy = list(_demoted)
            def _sync():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    from sqlalchemy import update as sa_update
                    from services.db.models.load_forecast import VersionRegistry as VRModel
                    with repo._adapter.get_sync_session() as session:
                        session.execute(
                            sa_update(VRModel)
                            .where(
                                VRModel.slot == _slot,
                                VRModel.workflow_id == _result["workflow_id"],
                                VRModel.version_tag == _result["version_tag"],
                            )
                            .values(status=_result["status"])
                        )
                        for d_wf, d_vt in _demoted_copy:
                            session.execute(
                                sa_update(VRModel)
                                .where(
                                    VRModel.slot == _slot,
                                    VRModel.workflow_id == d_wf,
                                    VRModel.version_tag == d_vt,
                                )
                                .values(status="shadow")
                            )
                except Exception as exc:
                    logger.warning("version_registry transition_status DB sync failed: %s", exc)
            threading.Thread(target=_sync, daemon=True).start()

        logger.info(
            "transition_status: %s → %s: workflow_id=%s, version_tag=%s, slot=%s",
            current_status, new_status, workflow_id, version_tag, slot,
        )
        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _enforce_shadow_cap(self, slot: str, data: dict) -> None:
        """
        影子版本数量上限检查，就地修改 data，不写入文件。

        当影子版本数量超过 max_shadow_versions（默认 5）时，
        按 registered_at 升序退役最老的影子版本，直到数量 ≤ 上限。

        调用方在此方法返回后负责调用 _save 持久化。

        :param slot: 槽位名称（仅用于日志）
        :param data: 已加载的注册表字典（就地修改）
        """
        max_cap: int = data.get("max_shadow_versions", _DEFAULT_MAX_SHADOW_VERSIONS)
        versions: list = data.get("versions", [])

        shadows = [v for v in versions if v.get("status") == "shadow"]
        if len(shadows) <= max_cap:
            return

        # 按 registered_at 升序，退役最老的若干条
        shadows.sort(key=lambda v: v.get("registered_at", ""))
        to_retire_count = len(shadows) - max_cap
        retire_keys = {
            (v["workflow_id"], v["version_tag"])
            for v in shadows[:to_retire_count]
        }

        for v in versions:
            if (v["workflow_id"], v["version_tag"]) in retire_keys:
                v["status"] = "retired"
                logger.info(
                    "_enforce_shadow_cap: slot=%s 影子版本超限，退役 "
                    "workflow_id=%s, version_tag=%s, registered_at=%s",
                    slot, v["workflow_id"], v["version_tag"], v.get("registered_at"),
                )

        data["versions"] = versions

    def _load(self, slot: str) -> dict:
        """
        读取指定槽位的注册表 JSON 文件。

        文件不存在时返回空结构（含 slot、空 versions 列表和默认 max_shadow_versions）。

        :param slot: 槽位名称
        :return: 注册表字典
        """
        path = BASE_DATA_DIR / slot / "version_registry.json"
        data = load_json_safe(path, default=None)
        if data is None:
            return {
                "slot": slot,
                "versions": [],
                "max_shadow_versions": _DEFAULT_MAX_SHADOW_VERSIONS,
            }
        return data

    def _save(self, slot: str, data: dict) -> None:
        """
        原子写入指定槽位的注册表 JSON 文件。

        :param slot: 槽位名称
        :param data: 注册表字典
        """
        ensure_data_dir(slot)
        path = BASE_DATA_DIR / slot / "version_registry.json"
        _atomic_write_json(path, data)

    def _find_slot(self, workflow_id: str, version_tag: str) -> Optional[str]:
        """
        在所有已有槽位目录中查找包含指定版本的槽位名称。

        用于 transition_status 接口（接口签名不含 slot 参数）。

        :param workflow_id: 工作流模板 ID
        :param version_tag: 版本标签
        :return: 槽位名称，未找到返回 None
        """
        if not BASE_DATA_DIR.exists():
            return None
        for slot_dir in BASE_DATA_DIR.iterdir():
            if not slot_dir.is_dir():
                continue
            slot = slot_dir.name
            data = self._load(slot)
            for v in data.get("versions", []):
                if v["workflow_id"] == workflow_id and v["version_tag"] == version_tag:
                    return slot
        return None
