# @AI_GENERATED
"""数据来源解析（数据集切片第 1 步）。

职责：把用户/前端给的**相对引用**解析成后端可读的**真实数据文件路径**，并提供
「磁盘上现在有哪些可挂载的数据」的发现能力。

红线（与 `services/timeseries_profiles/path_guard.py` 同源语义）：
- 拒绝机器绝对路径、URI / UNC、`..` 越界、符号链接；
- 只允许 `SOURCE_ROOTS` 白名单内的来源根；
- 只允许 `SUPPORTED_EXTENSIONS`；
- 解析结果必须**真实存在且是文件**——这一点区别于 pv_projects 现有的 `artifact_ref`：
  后者是版本元数据路径（`<version_id>.json`），**不保证落盘**，误当数据路径用会直接报文件不存在。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from services.pv_projects.errors import ScopeError

#: 允许被发现 / 挂载的数据来源根（相对 backend-service，正斜杠）。
SOURCE_ROOTS: dict[str, str] = {
    "uploads": "data/uploads",
    "demo": "data/demo",
    "benchmark_raw": "data/benchmark_raw",
    "auto_located_segments": "data/auto_located_segments",
    # 三槽数据集体系：路径级累计入账 / 冻结快照 / 已发布标注版本都在这里。
    # 目录名用 `slot_datasets` 而非 `slot`，避免与语义上的 slot 概念混淆。
    "slot_datasets": "data/slot_datasets",
    # backend-service/datasets/：平台级累计合并与打标批次的落地目录。
    "datasets": "datasets",
}

#: 允许的数据文件扩展名。
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".csv", ".tsv", ".parquet")

#: 数据集单元规则：**「数据集」不等于「文件」**。
#:
#: - `mode="file"`：平铺目录，文件互不相关 → 一个文件 = 一个数据集（uploads / demo）。
#: - `mode="directory"`：同 schema 的分片目录 → 一个目录 = 一个数据集（`under` + `depth` 定层级）。
#: - `mode="file_glob"`：按 `pattern` 精确定位文件（根下还有大量非数据集目录时用它，
#:   不能整棵树递归）。
#:
#: 只收**被治理的数据目录**，刻意排除研究工作产物。实测 `data/benchmark_raw` 下有
#: 220 个含数据的目录 / 2863 个数据文件，其中绝大多数是派生物：
#: `pvdaq/metrics__system_*__part000.parquet`（指标）、`pvdaq/analysis/*`（特征矩阵）、
#: `pvdaq/cohort_scan_samples/**`（75 个单文件日分区）、`pvdaq/reruns/**`（实验重跑）。
#: 若把它们都当数据集，目录窗口会被噪音淹没——清单从 2863 收敛到约 31 个真数据集。
DATASET_UNIT_SPECS: tuple[dict[str, Any], ...] = (
    {"alias": "uploads", "mode": "file"},
    {"alias": "demo", "mode": "file"},
    {"alias": "benchmark_raw", "mode": "directory", "under": "pvdaq/converted", "depth": 1},
    # @AI_GENERATED
    # 三路径累计训练冻结快照：`slot_datasets/<slot>/snapshots/<file>`。
    # 此前 `CANDIDATE_ROOT_ALIASES`（feed_sources.py）已把 `slot_datasets` / `datasets`
    # 列进喂数候选白名单，但这里没有对应 spec，`discover_datasets` 压根不扫这两个根，
    # 于是前端喂数下拉永远看不到项目挂载的累计快照 —— 两张表口径不一致。
    # 用 file_glob 而不是 file：`data/slot_datasets` 根下还有 loop_demo / observability /
    # projects 等大量运行产物，整树递归会把清单淹掉。
    {"alias": "slot_datasets", "mode": "file_glob", "pattern": "*/snapshots/*"},
    # `backend-service/datasets/` 顶层的喂数源（如 pv_mock_feed_unseen.parquet）。
    # 只取顶层：该目录下还有「相关数据」等原始训练目录，不是喂数单元。
    {"alias": "datasets", "mode": "file_glob", "pattern": "*"},
    # @AI_GENERATED: end
)

#: 测试用的来源根重定向（None = backend-service 目录）。
_SOURCE_BASE_OVERRIDE: Optional[Path] = None


def source_base() -> Path:
    """来源解析的基目录；默认 backend-service，可被测试重定向。"""
    if _SOURCE_BASE_OVERRIDE is not None:
        return _SOURCE_BASE_OVERRIDE
    from services.pv_projects.paths import backend_dir

    return backend_dir()


def set_source_base(path: Any) -> None:
    """仅供测试：重定向来源根（传 None 复位）。"""
    global _SOURCE_BASE_OVERRIDE
    _SOURCE_BASE_OVERRIDE = Path(path) if path else None


def to_source_alias_ref(ref: str) -> Optional[str]:
    """把「存储相对引用」归一化成「来源根别名引用」。

    `data/uploads/x.csv` → `uploads/x.csv` —— `resolve_source_ref` 与 `compute_dataset_facts`
    只认后者（首段必须是 `SOURCE_ROOTS` 的**别名**，而资产里存的 `upload_ref` 是存储相对路径）。
    已是别名形式则原样返回。

    既不是别名、也不落在白名单存储根下（如 `asset-1` / `conn-1` / 机器绝对路径）返回 None：
    「这份来源没有可读的本地数据文件」是**正常结果**，不是错误（连接器数据要物化后才有文件）。
    """
    normalized = str(ref or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or _looks_absolute(normalized):
        return None
    head = normalized.split("/", 1)[0]
    if head in SOURCE_ROOTS:
        return normalized
    for alias, root_rel in SOURCE_ROOTS.items():
        if normalized == root_rel:
            return alias
        if normalized.startswith(root_rel + "/"):
            rest = normalized[len(root_rel) + 1 :]
            return f"{alias}/{rest}" if rest else alias
    return None


def _looks_absolute(ref: str) -> bool:
    """是否像机器绝对路径。

    注意 Windows 上 `os.path.isabs('/etc/passwd')` 返回 False（盘符相对），
    因此必须额外判前导斜杠，否则 POSIX 风格绝对路径会漏网。
    """
    if os.path.isabs(ref):
        return True
    if ref.startswith("/") or ref.startswith("\\"):
        return True
    if len(ref) >= 2 and ref[1] == ":" and ref[0].isalpha():
        return True
    return False


def resolve_source_ref(source_ref: str) -> Path:
    """把相对引用解析成真实数据文件路径；任一红线被触碰即 fail-closed。

    允许的形状：`<root_alias>/<相对路径>`，例如 `uploads/pv_train_small.csv`。
    """
    ref = str(source_ref or "").strip()
    if not ref:
        raise ScopeError(
            "missing_source_ref",
            "缺少数据来源引用。",
            next_action="从平台数据集目录中选择一个数据来源",
        )

    if "://" in ref or ref.startswith("\\\\") or ref.startswith("//"):
        raise ScopeError(
            "unknown_scheme",
            f"不支持的数据来源协议：{ref!r}；只接受来源根内的相对引用。",
            next_action=f"使用 {sorted(SOURCE_ROOTS)} 之一开头的相对引用",
        )

    if _looks_absolute(ref):
        raise ScopeError(
            "absolute_path_forbidden",
            f"不接受机器绝对路径：{ref!r}。",
            next_action="使用相对引用，例如 uploads/xxx.csv",
        )

    normalized = Path(ref.replace("\\", "/"))
    if ".." in normalized.parts:
        raise ScopeError(
            "path_traversal_forbidden",
            f"来源引用不得包含 '..'：{ref!r}。",
        )

    parts = normalized.parts
    if not parts or parts[0] not in SOURCE_ROOTS:
        raise ScopeError(
            "unknown_root_alias",
            f"来源根必须是 {sorted(SOURCE_ROOTS)} 之一，收到 {(parts[0] if parts else ref)!r}。",
            next_action="从平台数据集目录中选择一个数据来源",
        )

    base = source_base()
    # alias → 真实来源根（与 services/timeseries_profiles/path_guard.py 的 root_alias 同模式）：
    # 引用首段是**逻辑别名**，不是目录名。`uploads/x.csv` → `<base>/data/uploads/x.csv`。
    root_rel = SOURCE_ROOTS[parts[0]]
    raw = base / Path(root_rel) / Path(*parts[1:])

    # 符号链接必须在 resolve 之前判：resolve 会跟随链接，判不出来。
    if raw.is_symlink():
        raise ScopeError(
            "symlink_forbidden",
            f"不接受符号链接作为数据来源：{ref!r}。",
        )

    candidate = raw.resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ScopeError(
            "path_outside_root",
            f"解析结果越出来源根：{ref!r}。",
        ) from exc

    ext = candidate.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ScopeError(
            "unsupported_extension",
            f"只支持 {list(SUPPORTED_EXTENSIONS)}，收到 {ext or '（无扩展名）'!r}。",
            next_action="转换为 CSV / TSV / Parquet 后再挂载",
        )

    if not candidate.is_file():
        raise ScopeError(
            "source_not_found",
            f"找不到数据文件：{ref!r}。",
            next_action="确认文件已落到来源根内，或刷新来源列表",
        )
    return candidate


def discover_sources(*, limit: int = 500) -> list[dict[str, Any]]:
    """扫描 `SOURCE_ROOTS`，返回可挂载候选。

    不跟随符号链接；只收 `SUPPORTED_EXTENSIONS`；结果按相对引用字典序稳定排序。
    """
    base = source_base()
    out: list[dict[str, Any]] = []
    for alias in sorted(SOURCE_ROOTS):
        root = base / SOURCE_ROOTS[alias]
        if not root.is_dir():
            continue
        for cur, dirs, files in os.walk(root, followlinks=False):
            cur_path = Path(cur)
            dirs[:] = [d for d in dirs if not (cur_path / d).is_symlink()]
            dirs.sort()
            for name in sorted(files):
                p = cur_path / name
                try:
                    if p.is_symlink() or not p.is_file():
                        continue
                    st = p.stat()
                except OSError:
                    continue
                ext = p.suffix.lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                try:
                    rel_inside = p.relative_to(root).as_posix()
                except ValueError:
                    continue
                out.append(
                    {
                        # 以 **alias 形式**回引用，使「发现 → 解析」可往返
                        # （`discover_sources` 的产出可直接喂给 `resolve_source_ref`）。
                        "source_ref": f"{alias}/{rel_inside}",
                        "root_alias": alias,
                        "size_bytes": int(st.st_size),
                        "extension": ext,
                        "modified_at": datetime.fromtimestamp(
                            st.st_mtime, tz=timezone.utc
                        ).replace(microsecond=0).isoformat(),
                    }
                )
                if len(out) >= limit:
                    return sorted(out, key=lambda item: item["source_ref"])
    return sorted(out, key=lambda item: item["source_ref"])


def _spec_for_ref(ref: str) -> Optional[dict[str, Any]]:
    """找出该引用命中的数据集单元规则；未命中返回 None（按单文件处理）。"""
    normalized = ref.replace("\\", "/")
    alias = normalized.split("/", 1)[0]
    for spec in DATASET_UNIT_SPECS:
        if spec["alias"] != alias:
            continue
        under = spec.get("under")
        if spec["mode"] == "directory" and under:
            if normalized.startswith(f"{alias}/{under}/"):
                return spec
            continue
        return spec
    return None


def _shards_in(dir_path: Path) -> list[Path]:
    """目录下**直接**包含的受支持分片，稳定排序（保证聚合结果可复现）。"""
    return sorted(
        p
        for p in dir_path.iterdir()
        if p.is_file() and not p.is_symlink() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _unit_payload(
    alias: str, dataset_ref: str, unit_kind: str, shards: list[Path], base: Path
) -> dict[str, Any]:
    # 两侧都必须 resolve 后再比：Windows 上 `Path.relative_to` 是**字符串比较**，
    # 8.3 短名（`XIAOKA~1.ZHA`）与长名（`xiaokang.zhao`）对不上，
    # 只要 storage 落在带 8.3 别名的路径下就会误报"not in the subpath of"。
    root = (base / SOURCE_ROOTS[alias]).resolve()
    resolved_shards = [p.resolve() for p in shards]
    size = 0
    for p in resolved_shards:
        try:
            size += p.stat().st_size
        except OSError:
            pass
    return {
        "dataset_ref": dataset_ref,
        "unit_kind": unit_kind,
        "root_alias": alias,
        "shard_count": len(resolved_shards),
        "shard_refs": sorted(
            f"{alias}/{p.relative_to(root).as_posix()}" for p in resolved_shards
        ),
        "size_bytes": size,
        "extensions": sorted({p.suffix.lower() for p in resolved_shards}),
    }


def discover_datasets(*, limit: int = 500) -> list[dict[str, Any]]:
    """按 `DATASET_UNIT_SPECS` 列出**数据集单元**（文件 或 目录分片组），不是原始文件清单。

    结果按 `dataset_ref` 字典序稳定排序。
    """
    base = source_base()
    out: list[dict[str, Any]] = []

    for spec in DATASET_UNIT_SPECS:
        alias = spec["alias"]
        root = base / SOURCE_ROOTS[alias]
        if not root.is_dir():
            continue

        if spec["mode"] == "file":
            for cur, dirs, files in os.walk(root, followlinks=False):
                cur_path = Path(cur)
                dirs[:] = [d for d in dirs if not (cur_path / d).is_symlink()]
                dirs.sort()
                for name in sorted(files):
                    p = cur_path / name
                    try:
                        if p.is_symlink() or not p.is_file():
                            continue
                    except OSError:
                        continue
                    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                        continue
                    ref = f"{alias}/{p.relative_to(root).as_posix()}"
                    out.append(_unit_payload(alias, ref, "file", [p], base))
                    if len(out) >= limit:
                        return sorted(out, key=lambda item: item["dataset_ref"])
            continue

        # @AI_GENERATED
        if spec["mode"] == "file_glob":
            # 按 pattern 精确取文件；不跟随符号链接，不递归到 pattern 之外。
            for p in sorted(root.glob(str(spec.get("pattern") or "*"))):
                try:
                    if p.is_symlink() or not p.is_file():
                        continue
                except OSError:
                    continue
                if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                ref = f"{alias}/{p.relative_to(root).as_posix()}"
                out.append(_unit_payload(alias, ref, "file", [p], base))
                if len(out) >= limit:
                    return sorted(out, key=lambda item: item["dataset_ref"])
            continue
        # @AI_GENERATED: end

        # directory 模式：在 `under` 的 `depth` 层收集目录，每个目录 = 一个分片组
        sub = root / Path(*str(spec["under"]).split("/")) if spec.get("under") else root
        if not sub.is_dir():
            continue
        depth = int(spec.get("depth") or 1)
        candidates: list[Path] = []
        _collect_dirs(sub, 0, depth, candidates)
        for cdir in candidates:
            shards = _shards_in(cdir)
            if not shards:
                continue
            ref = f"{alias}/{cdir.relative_to(root).as_posix()}"
            out.append(_unit_payload(alias, ref, "shard_group", shards, base))
            if len(out) >= limit:
                return sorted(out, key=lambda item: item["dataset_ref"])

    return sorted(out, key=lambda item: item["dataset_ref"])


def _collect_dirs(cur: Path, level: int, depth: int, acc: list[Path]) -> None:
    """收集恰好位于 `depth` 层的目录（不跟随符号链接）。"""
    if level >= depth:
        if cur.is_dir():
            acc.append(cur)
        return
    try:
        names = sorted(cur.iterdir())
    except OSError:
        return
    for nxt in names:
        if nxt.is_dir() and not nxt.is_symlink():
            _collect_dirs(nxt, level + 1, depth, acc)


def resolve_dataset_unit(dataset_ref: str) -> dict[str, Any]:
    """把数据集引用解析成单元：`{unit_kind, shard_paths, shard_refs, root_alias}`。

    - 命中 `directory` 规则 → 目录分片组（目录下无受支持分片即拒 `no_shards_in_directory`）；
    - 其余 → 单文件单元（走 `resolve_source_ref` 的全部安全校验）。
    """
    ref = str(dataset_ref or "").strip()
    base = source_base()
    spec = _spec_for_ref(ref)
    alias = ref.replace("\\", "/").split("/", 1)[0]

    if spec is not None and spec["mode"] == "directory":
        parts = ref.replace("\\", "/").split("/")
        raw = base / Path(SOURCE_ROOTS[alias]) / Path(*parts[1:])
        if ref.replace("\\", "/").endswith("/") or ".." in parts:
            raise ScopeError("path_traversal_forbidden", f"数据集引用非法：{ref!r}。")
        if raw.is_symlink():
            raise ScopeError("symlink_forbidden", f"不接受符号链接作为数据集目录：{ref!r}。")
        resolved = raw.resolve()
        try:
            resolved.relative_to(base.resolve())
        except ValueError as exc:
            raise ScopeError("path_outside_root", f"解析结果越出来源根：{ref!r}。") from exc
        if not resolved.is_dir():
            raise ScopeError(
                "source_not_found",
                f"数据集目录不存在：{ref!r}。",
                next_action="刷新数据集清单后重新选择",
            )
        shards = _shards_in(resolved)
        if not shards:
            raise ScopeError(
                "no_shards_in_directory",
                f"目录下没有受支持的数据分片：{ref!r}。",
                next_action=f"目录内需有 {list(SUPPORTED_EXTENSIONS)} 之一的数据文件",
            )
        payload = _unit_payload(alias, ref, "shard_group", shards, base)
        payload["shard_paths"] = shards
        return payload

    path = resolve_source_ref(ref)
    payload = _unit_payload(alias, ref, "file", [path], base)
    payload["shard_paths"] = [path]
    return payload


# @AI_GENERATED: end
