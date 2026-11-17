# @AI_GENERATED
"""槽位治理记录 → 项目归属解析。

**为什么需要这一层**：「模型部署」页读的是平台级候选池
（`data/slot_governance/<slot>/model_candidates.json`），「精度运营」的按日精度读的是
`data/slot_datasets/<slot>/loop_demo/daily_accuracy.json`。两份文件都**只按 slot 分区**，
都不带项目维度，所以页面上看不出「这个模型 / 这条精度是哪个项目训练出来的」。

归属链（每一环的数据本来就在，此前没有代码去走）：

    daily_accuracy.by_day[].model_id   →  mc-*        （池内候选 ID）
    model_candidates[].model_ref       →  cand-*      （项目侧候选 ID）
    项目候选 model_candidates.json     →  project_id  （产出该模型的项目）

解析优先级：

1. 池记录上的显式 `project_id` / `source_project_candidate_id`（新记录由领域桥写入）；
2. 回落到按 `model_ref` 反查项目候选（老记录没有那两个字段，桥当时只搬了 5 个字段）。

刻意**不做数据回填**：老记录靠第 2 条也能正确显示，不必改写既有产物。第 1 条只是让新记录
不用扫全部项目，是性能优化而非正确性前提。

本模块所有函数**只读、永不抛错**：归属解析失败只意味着「显示不出来源项目」，
不能让候选列表或精度总览整页失败。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

#: 项目侧候选 ID 前缀（`services/pv_projects/governance.py` 里铸的是 `cand-<hex12>`）。
_PROJECT_CANDIDATE_PREFIX = "cand-"

#: 合成的只读兼容项目，不是真实项目，反查时跳过。
_LEGACY_PROJECT_ID = "legacy"


def _looks_like_project_candidate(value: Any) -> bool:
    return str(value or "").strip().startswith(_PROJECT_CANDIDATE_PREFIX)


def build_project_candidate_index(slot: str) -> dict[str, dict[str, Any]]:
    """`cand-*` → 项目候选摘要 的索引（限定该 slot）。

    跨所有真实项目读一遍该 slot 下的项目候选。项目数量是个位数、每个项目一个小 JSON，
    页面级调用可以接受；调用方若要连续解析多条，请复用同一份索引而不是逐条反查。

    任何一个项目读失败只跳过该项目，不影响其余（存储脏是这个仓库的常态）。
    """
    index: dict[str, dict[str, Any]] = {}
    key = str(slot or "").strip()
    if not key:
        return index
    try:
        from services.pv_projects.governance import list_candidates  # noqa: PLC0415
        from services.pv_projects.projects import list_projects  # noqa: PLC0415
        from services.pv_projects.scope import ScopeContext  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — 壳不可用时退化成「无归属」，不炸调用方
        logger.debug("项目归属索引：pv_projects 不可用，跳过", exc_info=True)
        return index

    for project in list_projects(include_legacy=False) or []:
        project_id = str((project or {}).get("project_id") or "").strip()
        if not project_id or project_id == _LEGACY_PROJECT_ID:
            continue
        try:
            scope = ScopeContext.create(project_id, key)
            rows = list_candidates(scope)
        except Exception:  # noqa: BLE001 — 单个项目读失败不影响其它项目
            logger.debug("项目归属索引：读项目 %s/%s 候选失败", project_id, key, exc_info=True)
            continue
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            cand_id = str(row.get("model_candidate_id") or "").strip()
            if not cand_id:
                continue
            index[cand_id] = {
                "project_id": project_id,
                "project_name": (project or {}).get("project_name"),
                "project_candidate_id": cand_id,
                "source_workflow_id": row.get("source_workflow_id"),
                "source_execution_id": row.get("source_execution_id"),
                "source_dataset_version_id": row.get("source_dataset_version_id"),
                "governance_eligible": row.get("governance_eligible"),
            }
    return index


def _attribution_from_index(
    project_candidate_id: str, index: dict[str, dict[str, Any]]
) -> Optional[dict[str, Any]]:
    hit = index.get(str(project_candidate_id or "").strip())
    if not hit:
        return None
    return {**hit, "resolved_by": "model_ref_lookup"}


def _project_name(project_id: str) -> Optional[str]:
    """项目名（只读项目索引）。取不到返回 None，由前端回落显示 project_id。"""
    target = str(project_id or "").strip()
    if not target:
        return None
    try:
        from services.pv_projects.projects import get_project  # noqa: PLC0415

        record = get_project(target)
    except Exception:  # noqa: BLE001 — 拿不到名字不影响归属本身
        logger.debug("项目归属：读项目名 %s 失败", target, exc_info=True)
        return None
    name = str((record or {}).get("project_name") or "").strip()
    return name or None


def resolve_candidate_project(
    record: dict[str, Any],
    *,
    slot: Optional[str] = None,
    index: Optional[dict[str, dict[str, Any]]] = None,
) -> Optional[dict[str, Any]]:
    """单条池候选 → 项目归属；解析不出返回 None（不猜）。

    `index` 可选：批量解析时由调用方预先 `build_project_candidate_index(slot)` 传入，
    避免每条候选都重扫一遍项目。
    """
    if not isinstance(record, dict):
        return None

    explicit_project = str(record.get("project_id") or "").strip()
    explicit_candidate = str(record.get("source_project_candidate_id") or "").strip()
    if explicit_project:
        # 新记录：桥已显式写入归属，不必扫全部项目反查；只补一次项目名供展示。
        return {
            "project_id": explicit_project,
            "project_name": _project_name(explicit_project),
            "project_candidate_id": explicit_candidate or None,
            "resolved_by": "explicit_field",
        }

    # 老记录：桥当时只把项目候选 ID 塞进了 model_ref。
    project_candidate_id = explicit_candidate
    if not project_candidate_id and _looks_like_project_candidate(record.get("model_ref")):
        project_candidate_id = str(record.get("model_ref")).strip()
    if not project_candidate_id:
        return None

    lookup = index
    if lookup is None:
        lookup = build_project_candidate_index(str(slot or record.get("slot") or ""))
    return _attribution_from_index(project_candidate_id, lookup)


def annotate_candidates_with_project(
    slot: str, records: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """给一批池候选补 `project_attribution` 字段（原记录不改，返回浅拷贝）。

    索引只建一次。解析不出归属的候选**保留 `project_attribution: None`**——
    显式的「无归属」比缺键更好读，前端不用区分 undefined 与 null。
    """
    items = [row for row in (records or []) if isinstance(row, dict)]
    if not items:
        return []
    needs_lookup = any(
        not str(row.get("project_id") or "").strip()
        and (
            _looks_like_project_candidate(row.get("model_ref"))
            or str(row.get("source_project_candidate_id") or "").strip()
        )
        for row in items
    )
    index = build_project_candidate_index(slot) if needs_lookup else {}
    out: list[dict[str, Any]] = []
    for row in items:
        out.append(
            {**row, "project_attribution": resolve_candidate_project(row, slot=slot, index=index)}
        )
    return out


def resolve_model_project(slot: str, model_id: Optional[str]) -> Optional[dict[str, Any]]:
    """`model_id`（按日精度里记的产出模型）→ 项目归属。

    `daily_accuracy.by_day[].model_id` 记的可能是：
    - `mc-*`：池内候选 ID，可沿 `model_ref` → `cand-*` → 项目 解析；
    - `loop_demo_rule`：内置规则回落，**没有模型**，返回 None（不是错误）。
    """
    target = str(model_id or "").strip()
    if not target or not target.startswith("mc-"):
        return None
    try:
        from services.slot_governance.model_candidates import list_model_candidates  # noqa: PLC0415

        pool = list_model_candidates(slot)
    except Exception:  # noqa: BLE001 — 非产品槽位 / 文件缺失都退化成「无归属」
        logger.debug("按日精度归属：读 %s 候选池失败", slot, exc_info=True)
        return None
    for row in pool or []:
        if isinstance(row, dict) and str(row.get("model_candidate_id") or "").strip() == target:
            return resolve_candidate_project(row, slot=slot)
    return None


# @AI_GENERATED: end
