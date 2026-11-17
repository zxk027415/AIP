# @AI_GENERATED
"""喂数数据集注册：候选发现 / 指纹 / 真值标注 / 当前选中。

设计意图（用户原话）：

    "喂数据得数据集也能显式展示出来"
    "mock 得有真值得也可以接，真实的没有真值得也可以接……用哪个数据集其实无所谓"

因此数据集是可替换的**验证集**，链路本身不绑定具体文件。本模块只负责三件事：
候选有哪些、当前选的是哪个、以及每个候选的关键事实（指纹 / 是否有真值）。

**复用而非重写**（避免造第二份事实来源）：

  - 候选发现：``services/pv_projects/source_resolver.py::discover_datasets``
    —— 已内置「数据集 ≠ 文件」的治理规则（``DATASET_UNIT_SPECS``），
    能把 ``data/benchmark_raw`` 下 2863 个数据文件收敛到约 31 个真数据集。
  - 路径解析：同模块 ``resolve_source_ref`` / ``resolve_dataset_unit``
    —— 只认 ``SOURCE_ROOTS`` 白名单别名，天然挡掉机器绝对路径与越界。
  - 指纹：``services/db/datasources/pv_fault_mock.py::compute_pv_source_fingerprint``
    —— 同一口径，避免「观测页一个指纹、喂数器另一个指纹」。
  - 到达语义：``services/slot_datasets/feed_semantics.py``

本模块写盘仅限两处：每 slot 的 ``feed_source.json``（当前选中）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[2]

#: 与喂数回放相关的来源根别名。其余根（benchmark_raw 等）是研究派生数据，不进候选。
CANDIDATE_ROOT_ALIASES: tuple[str, ...] = ("slot_datasets", "datasets", "uploads", "demo")

#: 当前选中的喂数集落在 slot 自己的目录下，与观测 ledger 同级、互不干扰。
_SELECTION_REL_TEMPLATE = "data/slot_datasets/{slot}/feed_source.json"

#: 真值列名（gold 判定）。与 gold_bootstrap / mock_gold_scoring 消费的列名一致。
_TRUTH_COLUMNS: tuple[str, ...] = ("label", "label_id", "gold_label")
TRUTH_COLUMNS: tuple[str, ...] = _TRUTH_COLUMNS


class FeedSourceError(ValueError):
    """数据集引用非法或不可解析。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class FeedSourceFacts:
    """一个候选喂数集的关键事实（列表页要与详情页区分：这里只装已算好的值）。"""

    dataset_ref: str
    root_alias: str
    unit_kind: str
    shard_count: int
    exists: bool
    row_count: Optional[int] = None
    date_min: Optional[str] = None
    date_max: Optional[str] = None
    fingerprint: Optional[str] = None
    has_gold: Optional[bool] = None
    gold_column: Optional[str] = None
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dataset_ref": self.dataset_ref,
            "root_alias": self.root_alias,
            "unit_kind": self.unit_kind,
            "shard_count": self.shard_count,
            "exists": self.exists,
            "row_count": self.row_count,
            "date_min": self.date_min,
            "date_max": self.date_max,
            "fingerprint": self.fingerprint,
            "has_gold": self.has_gold,
            "gold_column": self.gold_column,
            "error": self.error,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _selection_path(slot: str, *, backend_dir: Optional[Path] = None) -> Path:
    base = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    return base / _SELECTION_REL_TEMPLATE.format(slot=slot)


def _assert_slot(slot: str) -> str:
    from services.slot_datasets.feed_semantics import SUPPORTED_SLOTS

    key = str(slot or "").strip()
    if key not in SUPPORTED_SLOTS:
        raise FeedSourceError("invalid_slot", f"slot must be one of {sorted(SUPPORTED_SLOTS)!r}, got {key!r}")
    return key


def _resolve_ref_path(dataset_ref: str) -> Path:
    """把别名引用解析成真实路径（复用 source_resolver 的白名单解析）。

    ``resolve_source_ref`` 对越界 / 不存在 / 非白名单的引用会抛 ``ScopeError``；
    这里统一收敛成 ``FeedSourceError``，让调用方只需处理一种异常类型。
    机器绝对路径、``..`` 越界、UNC 都在这一层被挡掉。
    """
    from services.pv_projects.errors import ScopeError
    from services.pv_projects.source_resolver import resolve_source_ref

    ref = str(dataset_ref or "").strip()
    if not ref:
        raise FeedSourceError("missing_dataset_ref", "dataset_ref 不能为空")
    try:
        resolved = resolve_source_ref(ref)
    except ScopeError as exc:
        code = str(getattr(exc, "code", "") or "scope_error")
        message = str(getattr(exc, "message", "") or exc)
        raise FeedSourceError(code, f"{ref!r} 无法解析：{message}") from exc
    return Path(resolved)


def list_candidates(*, limit: int = 400) -> List[Dict[str, Any]]:
    """候选喂数集清单（轻量：只列引用与结构，不算指纹、不读文件内容）。

    指纹与真值标注由 ``describe_source`` 按需计算，避免列表页把每个候选都读一遍。
    """
    from services.pv_projects.source_resolver import discover_datasets

    items = discover_datasets(limit=limit)
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("root_alias") or "")
        if alias not in CANDIDATE_ROOT_ALIASES:
            continue
        out.append(
            {
                "dataset_ref": item.get("dataset_ref"),
                "root_alias": alias,
                "unit_kind": item.get("unit_kind"),
                "shard_count": int(item.get("shard_count") or 0),
            }
        )
    return out


def _peek_columns(path: Path) -> List[str]:
    """读列名（不读全表）：用于判定是否自带真值。"""
    if not path.is_file():
        return []
    suffix = path.suffix.lower()
    try:
        if suffix == ".parquet":
            import pyarrow.parquet as pq

            return list(pq.ParquetFile(str(path)).schema_arrow.names)
        if suffix in {".csv", ".tsv"}:
            sep = "\t" if suffix == ".tsv" else ","
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                header = handle.readline().strip()
            return [part.strip() for part in header.split(sep) if part.strip()]
    except Exception:
        return []
    return []


def describe_source(dataset_ref: str, *, with_facts: bool = True) -> FeedSourceFacts:
    """单个候选的事实：指纹 / 日期范围 / 行数 / 是否自带真值。

    ``with_facts=False`` 时只做存在性与列探测（快路径）。
    """
    ref = str(dataset_ref or "").strip()
    alias = ref.split("/", 1)[0] if "/" in ref else ref
    try:
        path = _resolve_ref_path(ref)
    except FeedSourceError as exc:
        # 描述接口对失效/越界引用保持宽容：返回 exists=False + 原因，
        # 不抛异常——候选列表里允许存在失效项，不允许把列表页炸掉。
        return FeedSourceFacts(
            dataset_ref=ref,
            root_alias=alias,
            unit_kind="unknown",
            shard_count=0,
            exists=False,
            error=f"{exc.code}: {exc.message}",
        )
    exists = path.is_file()

    row_count: Optional[int] = None
    date_min: Optional[str] = None
    date_max: Optional[str] = None
    fingerprint: Optional[str] = None
    has_gold: Optional[bool] = None
    gold_column: Optional[str] = None
    error: Optional[str] = None

    if exists:
        columns = _peek_columns(path)
        for candidate in _TRUTH_COLUMNS:
            if candidate in columns:
                has_gold = True
                gold_column = candidate
                break
        else:
            if columns:
                has_gold = False
        if with_facts:
            try:
                from services.db.datasources.pv_fault_mock import compute_pv_source_fingerprint

                fp = compute_pv_source_fingerprint(str(path))
                row_count = int(fp.get("row_count") or 0)
                date_min = fp.get("date_min")
                date_max = fp.get("date_max")
                fingerprint = fp.get("fingerprint")
            except Exception as exc:  # 指纹失败不影响「有哪些候选」这件事
                error = f"{type(exc).__name__}: {exc}"

    return FeedSourceFacts(
        dataset_ref=ref,
        root_alias=alias,
        unit_kind="file" if path.suffix.lower() in {".csv", ".tsv", ".parquet"} else "unknown",
        shard_count=1,
        exists=exists,
        row_count=row_count,
        date_min=date_min,
        date_max=date_max,
        fingerprint=fingerprint,
        has_gold=has_gold,
        gold_column=gold_column,
        error=error,
    )


def get_selection(slot: str, *, backend_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """读取该 slot 当前选中的喂数集；未选择返回 None（调用方回落到内置生成）。"""
    key = _assert_slot(slot)
    path = _selection_path(key, backend_dir=backend_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_date_column(frame: "pd.DataFrame") -> "pd.DataFrame":
    """保证喂数帧有 ``date`` 列（YYYY-MM-DD）。缺 date 时从 time/timestamp 推导。"""
    import pandas as pd

    df = frame.copy()
    if "date" in df.columns:
        df["date"] = df["date"].astype(str).str.slice(0, 10)
        return df
    for col in ("time", "timestamp", "datetime"):
        if col not in df.columns:
            continue
        df["date"] = pd.to_datetime(df[col], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
        return df
    raise FeedSourceError("missing_date", "喂数源缺少 date/time 列，无法按业务日回放")


def load_frame(dataset_ref: str) -> "pd.DataFrame":
    """按白名单引用读喂数源。文件不存在 / 越界 fail-closed。"""
    import pandas as pd

    ref = str(dataset_ref or "").strip()
    path = _resolve_ref_path(ref)
    if not path.is_file():
        raise FeedSourceError("dataset_not_found", f"数据集不存在或不在白名单来源根内: {ref!r}")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        frame = pd.read_parquet(path)
    elif suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        frame = pd.read_csv(path, sep=sep)
    else:
        raise FeedSourceError("unsupported_format", f"不支持的喂数文件类型: {path.suffix!r}")
    return _normalize_date_column(frame)


def truth_column_of(frame: Any) -> Optional[str]:
    columns = getattr(frame, "columns", None)
    if columns is None:
        return None
    for candidate in _TRUTH_COLUMNS:
        if candidate in columns:
            return candidate
    return None


def select_source(
    slot: str,
    dataset_ref: Optional[str],
    *,
    operator: str = "ui",
    backend_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """运行时切换该 slot 的喂数集。

    ``dataset_ref=None`` 表示清空选择，回落到内置生成（loop_demo.build_gold_frame）。
    写盘前校验引用可解析且文件真实存在——fail-closed，不写悬空引用。
    """
    key = _assert_slot(slot)
    path = _selection_path(key, backend_dir=backend_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    if dataset_ref is None or not str(dataset_ref).strip():
        payload = {
            "slot": key,
            "dataset_ref": None,
            "note": "未选择外部数据集，回落到内置生成",
            "operator": operator,
            "updated_at": _now_iso(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    facts = describe_source(str(dataset_ref), with_facts=False)
    if not facts.exists:
        raise FeedSourceError(
            "dataset_not_found",
            f"数据集不存在或不在白名单来源根内: {dataset_ref!r}",
        )
    payload = {
        "slot": key,
        "dataset_ref": facts.dataset_ref,
        "has_gold": facts.has_gold,
        "gold_column": facts.gold_column,
        "operator": operator,
        "updated_at": _now_iso(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def describe_current(
    slot: str,
    *,
    with_facts: bool = True,
    backend_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """该 slot 当前的喂数集事实 + 它的到达语义，供 API / 前端一次拿到。"""
    from services.slot_datasets.feed_semantics import describe_slot

    key = _assert_slot(slot)
    selection = get_selection(key, backend_dir=backend_dir)
    semantics = describe_slot(key)
    if not selection or not selection.get("dataset_ref"):
        return {
            "slot": key,
            "selected": False,
            "selection": selection,
            "source": None,
            "semantics": semantics,
            "note": "未选择外部数据集：回落到内置生成（loop_demo.build_gold_frame）",
        }
    try:
        facts = describe_source(str(selection["dataset_ref"]), with_facts=with_facts)
    except FeedSourceError as exc:
        return {
            "slot": key,
            "selected": True,
            "selection": selection,
            "source": None,
            "semantics": semantics,
            "note": f"已选数据集不可解析（{exc.code}）",
        }
    return {
        "slot": key,
        "selected": True,
        "selection": selection,
        "source": facts.as_dict(),
        "semantics": semantics,
        "note": None,
    }
