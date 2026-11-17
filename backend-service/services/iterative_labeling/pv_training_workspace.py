# @AI_GENERATED
"""
services/iterative_labeling/pv_training_workspace.py — 光伏训练数据工作台服务

职责：
  - 从 PVFaultRepository 拉取候选训练观测，按诊断片段聚合特征并执行 KMeans 聚类。
  - 持久化聚类 run（pending_naming → pending_confirmation → confirmed）。
  - 人工命名簇、筛选成员、二次确认后生成不可变 labeled CSV。
  - 提供时间切片标注确认入口。
  - 提供 pv_fault 槽位运营总览聚合。

所有持久化路径使用相对于项目根目录的 POSIX 路径。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BACKEND_SERVICE_DIR = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_SERVICE_DIR.parent
_WORKSPACE_DIR = _BACKEND_SERVICE_DIR / "data" / "iterative_labeling" / "training_workspace" / "pv_fault"


def _to_project_relative(path: Path) -> str:
    return path.resolve().relative_to(_PROJECT_ROOT).as_posix()


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).replace(path)
    except Exception:
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass
        raise


_ENTITY_KEY_COLUMNS = frozenset({"site_id", "device_id", "branch_id"})
_EXCLUDED_FEATURE_COLUMNS = frozenset({"site_id", "device_id", "branch_id", "date", "member_key", "cluster_id"})
_DEFAULT_MEASURES = ("value", "i_cal")


def _to_backend_relative(path: Path) -> str:
    return path.resolve().relative_to(_BACKEND_SERVICE_DIR).as_posix()


def _zscore_features(feature_df: pd.DataFrame) -> pd.DataFrame:
    scaled = feature_df.astype(float).copy()
    for col in scaled.columns:
        mean = scaled[col].mean()
        std = scaled[col].std(ddof=0)
        if std == 0 or pd.isna(std):
            scaled[col] = 0.0
        else:
            scaled[col] = (scaled[col] - mean) / std
    return scaled


def _select_clustering_feature_columns(
    grouped: pd.DataFrame,
    measures: Optional[List[str]] = None,
) -> List[str]:
    measure_cols = [str(m).strip() for m in (measures or list(_DEFAULT_MEASURES)) if str(m).strip()]
    if not measure_cols:
        measure_cols = list(_DEFAULT_MEASURES)

    feature_cols: List[str] = []
    for col in grouped.columns:
        if col in _EXCLUDED_FEATURE_COLUMNS:
            continue
        if col in _ENTITY_KEY_COLUMNS:
            continue
        if not pd.api.types.is_numeric_dtype(grouped[col]):
            continue
        if col in measure_cols:
            feature_cols.append(col)
            continue
        if any(col.startswith(f"{measure}_") for measure in measure_cols):
            feature_cols.append(col)
            continue
    return feature_cols


class PVTrainingWorkspaceService:
    """光伏训练数据工作台：聚类、命名、确认、时间切片、运营聚合。"""

    def __init__(self) -> None:
        self._workspace_dir = _WORKSPACE_DIR
        self._workspace_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 聚类 run 生命周期
    # ------------------------------------------------------------------

    def create_clustering_run(
        self,
        samples: List[Dict[str, Any]],
        n_clusters: int = 5,
        reviewer: str = "operator",
        measures: Optional[List[str]] = None,
        slot: str = "pv_point",
    ) -> Dict[str, Any]:
        """从原始观测创建聚类 run。

        聚合逻辑：site_id + device_id + branch_id + 自然日 → 一个诊断片段。
        特征：value_mean/value_std/value_min/value_max/i_cal_mean/i_cal_std/i_cal_min/i_cal_max。
        """
        if not samples:
            raise ValueError("候选样本为空，无法创建聚类 run")

        df = pd.DataFrame(samples)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], errors="coerce")
            df["date"] = df["time"].dt.date.astype(str)
        else:
            df["date"] = "unknown"

        group_cols = [c for c in ["site_id", "device_id", "branch_id", "date"] if c in df.columns]
        if not group_cols:
            group_cols = ["date"]

        agg_dict: Dict[str, List] = {}
        for col in ["value", "i_cal"]:
            if col in df.columns:
                agg_dict[col] = ["mean", "std", "min", "max"]
        if not agg_dict:
            raise ValueError("候选样本缺少 value/i_cal 数值列")

        grouped = df.groupby(group_cols, dropna=False).agg(agg_dict)
        grouped.columns = ["_".join(c) for c in grouped.columns]
        grouped = grouped.reset_index()

        # 生成 member_key
        grouped["member_key"] = grouped.apply(
            lambda r: "|".join(str(r.get(c, "")) for c in group_cols), axis=1
        )

        feature_cols = _select_clustering_feature_columns(grouped, measures=measures)
        if not feature_cols:
            raise ValueError("候选样本缺少可用于聚类的测点特征列")

        from services.operator_backends.kmeans import execute as kmeans_execute

        feature_df = _zscore_features(grouped[feature_cols])
        n_clusters = min(n_clusters, len(feature_df))
        if n_clusters < 2:
            n_clusters = 2
        result = kmeans_execute(
            {"n_clusters": n_clusters, "random_state": 42},
            {"data": feature_df},
        )
        labels = result["labels"]
        grouped["cluster_id"] = [int(lbl) for lbl in labels]

        # 构建 run
        run_id = f"clust-{uuid.uuid4().hex[:12]}"
        clusters: Dict[str, Any] = {}
        for cid in sorted(set(int(x) for x in labels)):
            members = grouped[grouped["cluster_id"] == cid]
            clusters[str(cid)] = {
                "cluster_id": cid,
                "member_count": int(len(members)),
                "member_keys": members["member_key"].tolist(),
                "proposed_label_name": None,
                "selected_member_keys": None,
                "representative_stats": {
                    col: float(members[col].mean()) for col in feature_cols if col in members.columns
                },
            }

        # 保存原始特征 CSV
        run_dir = self._workspace_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        features_path = run_dir / "features.csv"
        grouped.to_csv(features_path, index=False, encoding="utf-8")

        # 保存源数据 CSV（仅保留必要列）
        source_cols = [c for c in ["time", "site_id", "device_id", "branch_id", "value", "i_cal", "label"] if c in df.columns]
        source_path = run_dir / "source_data.csv"
        df[source_cols].to_csv(source_path, index=False, encoding="utf-8")

        run_state = {
            "run_id": run_id,
            "status": "pending_naming",
            "slot": slot,
            "n_clusters": n_clusters,
            "total_members": int(len(grouped)),
            "clusters": clusters,
            "clustering_feature_columns": feature_cols,
            "features_path": _to_project_relative(features_path),
            "source_data_path": _to_project_relative(source_path),
            "reviewer": reviewer,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        _atomic_write_json(run_dir / "run.json", run_state)
        return run_state

    def get_clustering_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        run_path = self._workspace_dir / run_id / "run.json"
        if not run_path.exists():
            return None
        return json.loads(run_path.read_text(encoding="utf-8"))

    def update_cluster(
        self,
        run_id: str,
        cluster_id: str,
        proposed_label_name: Optional[str] = None,
        selected_member_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        run = self.get_clustering_run(run_id)
        if run is None:
            raise KeyError(f"聚类 run {run_id} 不存在")
        if run["status"] == "confirmed":
            raise ValueError("已确认的 run 不允许修改")

        cluster = run["clusters"].get(cluster_id)
        if cluster is None:
            raise KeyError(f"簇 {cluster_id} 不存在")

        if proposed_label_name is not None:
            cluster["proposed_label_name"] = proposed_label_name
        if selected_member_keys is not None:
            # 验证 member_keys 存在
            valid_keys = set(cluster["member_keys"])
            invalid = [k for k in selected_member_keys if k not in valid_keys]
            if invalid:
                raise ValueError(f"以下 member_key 不属于簇 {cluster_id}: {invalid[:5]}")
            cluster["selected_member_keys"] = selected_member_keys

        # 检查是否所有簇都已命名 → 推进到 pending_confirmation
        all_named = all(
            c.get("proposed_label_name") for c in run["clusters"].values()
        )
        if all_named and run["status"] == "pending_naming":
            run["status"] = "pending_confirmation"

        run["updated_at"] = datetime.utcnow().isoformat()
        _atomic_write_json(self._workspace_dir / run_id / "run.json", run)
        return run

    def confirm_clustering_run(
        self,
        run_id: str,
        label_id_map: Dict[str, int],
        slot: str = "pv_point",
    ) -> Dict[str, Any]:
        """二次确认：生成不可变 labeled CSV，发布确认箱并登记画布可训清单。"""
        run = self.get_clustering_run(run_id)
        if run is None:
            raise KeyError(f"聚类 run {run_id} 不存在")
        if run["status"] == "confirmed":
            raise ValueError("该 run 已被确认")
        if run["status"] not in ("pending_naming", "pending_confirmation"):
            raise ValueError(f"run 状态 {run['status']} 不允许确认")

        # 校验所有簇有名称和选中成员
        for cid, cluster in run["clusters"].items():
            if not cluster.get("proposed_label_name"):
                raise ValueError(f"簇 {cid} 缺少 proposed_label_name")
            if not cluster.get("selected_member_keys"):
                raise ValueError(f"簇 {cid} 缺少 selected_member_keys（人工未选择成员）")
            if cluster["proposed_label_name"] not in label_id_map:
                raise ValueError(
                    f"簇 {cid} 的标签名 '{cluster['proposed_label_name']}' "
                    f"不在 label_id_map 中"
                )

        # 读取源数据并匹配
        source_path = _PROJECT_ROOT / run["source_data_path"]
        if not source_path.exists():
            raise FileNotFoundError(f"源数据文件不存在: {run['source_data_path']}")
        source_df = pd.read_csv(source_path, encoding="utf-8")

        # 读取特征表获取 member_key → cluster_id 映射
        features_path = _PROJECT_ROOT / run["features_path"]
        feat_df = pd.read_csv(features_path, encoding="utf-8")

        # 构建 selected member_key → label_id 映射
        key_to_label: Dict[str, int] = {}
        for cid, cluster in run["clusters"].items():
            label_name = cluster["proposed_label_name"]
            label_id = label_id_map[label_name]
            for mk in cluster["selected_member_keys"]:
                key_to_label[mk] = label_id

        # 解析 member_key 组成部分
        group_cols = [c for c in ["site_id", "device_id", "branch_id", "date"] if c in feat_df.columns]

        # 给源数据加 date 列
        if "time" in source_df.columns:
            source_df["time"] = pd.to_datetime(source_df["time"], errors="coerce")
            source_df["date"] = source_df["time"].dt.date.astype(str)

        # 构建源数据 member_key
        source_df["_member_key"] = source_df.apply(
            lambda r: "|".join(str(r.get(c, "")) for c in group_cols), axis=1
        )

        # 仅保留被选中的行
        labeled_df = source_df[source_df["_member_key"].isin(key_to_label)].copy()
        labeled_df["label"] = labeled_df["_member_key"].map(key_to_label)
        labeled_df = labeled_df.drop(columns=["_member_key", "date"], errors="ignore")

        if labeled_df.empty:
            raise ValueError("选中成员在源数据中无匹配行")

        # 写不可变 CSV
        confirmed_dir = self._workspace_dir / run_id / "confirmed"
        confirmed_dir.mkdir(parents=True, exist_ok=True)
        csv_name = f"labeled-{run_id}.csv"
        csv_path = confirmed_dir / csv_name
        labeled_df.to_csv(csv_path, index=False, encoding="utf-8")
        dataset_path = _to_project_relative(csv_path)
        backend_dataset_path = _to_backend_relative(csv_path)

        from services.slot_datasets.canvas_datasets import register_trainable_dataset
        from services.slot_datasets.labeled_versions import publish_labeled_version

        labeled_version = publish_labeled_version(
            slot=slot,
            file_path=backend_dataset_path,
            status="curated",
        )
        dataset_version_id = labeled_version["dataset_version_id"]
        canvas_row = register_trainable_dataset(
            dataset_id=dataset_version_id,
            kind="labeled_version",
            slot=slot,
            ref_id=dataset_version_id,
            file_path=backend_dataset_path,
            name=f"clustering-{run_id}",
        )

        run["status"] = "confirmed"
        run["slot"] = slot
        run["confirmed_dataset_path"] = dataset_path
        run["confirmed_backend_dataset_path"] = backend_dataset_path
        run["dataset_version_id"] = dataset_version_id
        run["dataset_id"] = canvas_row["dataset_id"]
        run["confirmed_sample_count"] = int(len(labeled_df))
        run["confirmed_label_count"] = int(labeled_df["label"].nunique())
        run["confirmed_at"] = datetime.utcnow().isoformat()
        run["updated_at"] = datetime.utcnow().isoformat()

        from services.slot_datasets.review_admission import include_path_a_labeled_version

        cumulative = include_path_a_labeled_version(
            slot=slot,
            dataset_version_id=dataset_version_id,
            reviewed_at=run["confirmed_at"],
            reviewer=run.get("reviewer"),
        )
        run["cumulative_include"] = {
            "source": cumulative.get("source"),
            "reviewed_at": cumulative.get("reviewed_at"),
            "freeze_dataset_id": ((cumulative.get("freeze") or {}).get("canvas_row") or {}).get("dataset_id"),
        }
        _atomic_write_json(self._workspace_dir / run_id / "run.json", run)

        return {
            "run_id": run_id,
            "dataset_path": dataset_path,
            "dataset_version_id": dataset_version_id,
            "dataset_id": canvas_row["dataset_id"],
            "sample_count": int(len(labeled_df)),
            "label_count": int(labeled_df["label"].nunique()),
            "cumulative_include": run["cumulative_include"],
        }

    # ------------------------------------------------------------------
    # 时间切片标注
    # ------------------------------------------------------------------

    def create_confirmed_time_slice(
        self,
        source_path: str,
        time_start: str,
        time_end: str,
        label_id: int,
        reviewer: str = "operator",
        site_id: Optional[str] = None,
        device_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        time_window_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从源 CSV/Parquet 切取时间段并写入确认标签，返回 dataset_path。

        ``time_window_override`` 用于自由窗打标：让特征工程把该段聚合成独立样本，
        而不是仍按自然日窗口键合并。
        """
        # 路径校验
        normalized = Path(source_path.replace("\\", "/"))
        if normalized.is_absolute():
            raise ValueError("source_path 必须为项目根相对路径")
        full_path = _PROJECT_ROOT / normalized
        try:
            full_path.resolve().relative_to(_PROJECT_ROOT)
        except ValueError:
            raise ValueError("source_path 不可逃逸项目根目录")
        if not full_path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_path}")

        # 加载
        if full_path.suffix.lower() == ".parquet":
            df = pd.read_parquet(full_path)
        else:
            df = pd.read_csv(full_path, encoding="utf-8")

        if "time" not in df.columns:
            raise ValueError("源数据缺少 time 列")

        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        mask = (df["time"] >= pd.Timestamp(time_start)) & (df["time"] <= pd.Timestamp(time_end))
        if site_id:
            mask &= df["site_id"].astype(str) == str(site_id)
        if device_id:
            mask &= df["device_id"].astype(str) == str(device_id)
        if branch_id:
            mask &= df["branch_id"].astype(str) == str(branch_id)

        sliced = df[mask].copy()
        if sliced.empty:
            raise ValueError("时间段/筛选条件匹配到 0 行")

        # @AI_GENERATED: 按 (time, 设备三元组) 去重，避免 TSC 重叠上下文把同一时刻原始点重复计入累计集
        dedup_keys = [
            key for key in ("time", "site_id", "device_id", "branch_id") if key in sliced.columns
        ]
        if dedup_keys:
            before = len(sliced)
            sliced = sliced.drop_duplicates(subset=dedup_keys, keep="first")
            removed = before - len(sliced)
            if removed:
                logger.info(
                    "create_confirmed_time_slice: 去除 %d 行重复原始点（按 %s）",
                    removed,
                    "/".join(dedup_keys),
                )
        # @AI_GENERATED: end

        sliced["label"] = label_id
        if time_window_override:
            sliced["time_window"] = time_window_override

        # 持久化
        slice_id = f"slice-{uuid.uuid4().hex[:12]}"
        slice_dir = self._workspace_dir / "time_slices"
        slice_dir.mkdir(parents=True, exist_ok=True)
        csv_path = slice_dir / f"{slice_id}.csv"
        sliced.to_csv(csv_path, index=False, encoding="utf-8")
        dataset_path = _to_project_relative(csv_path)

        meta = {
            "slice_id": slice_id,
            "source_path": source_path,
            "time_start": time_start,
            "time_end": time_end,
            "label_id": label_id,
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "time_window": time_window_override,
            "reviewer": reviewer,
            "row_count": int(len(sliced)),
            "dataset_path": dataset_path,
            "created_at": datetime.utcnow().isoformat(),
        }
        _atomic_write_json(slice_dir / f"{slice_id}.meta.json", meta)
        return meta

    # ------------------------------------------------------------------
    # 预测批次列表/详情
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_prediction_payload(
        data: Dict[str, Any],
        *,
        batch_id: str,
        label_names: Optional[Dict[Any, str]] = None,
        sample_limit: int = 0,
    ) -> Dict[str, Any]:
        """从预测批次 JSON 提取可展示摘要：时间窗、标签分布、置信度与可选样本。"""
        predictions = data.get("predictions") or []
        if not isinstance(predictions, list):
            predictions = []

        time_windows: List[str] = []
        label_counts: Dict[str, int] = defaultdict(int)
        confidence_buckets = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        names = label_names or {}

        for item in predictions:
            if not isinstance(item, dict):
                continue
            tw = item.get("time_window")
            if tw is not None and str(tw).strip():
                time_windows.append(str(tw))
            pred_label = item.get("predicted_label")
            if pred_label is not None:
                display = names.get(pred_label) or names.get(str(pred_label)) or f"label_{pred_label}"
                label_counts[str(display)] += 1
            conf = item.get("confidence")
            if conf is None:
                confidence_buckets["unknown"] += 1
            else:
                try:
                    conf_f = float(conf)
                except (TypeError, ValueError):
                    confidence_buckets["unknown"] += 1
                else:
                    if conf_f >= 0.8:
                        confidence_buckets["high"] += 1
                    elif conf_f >= 0.5:
                        confidence_buckets["medium"] += 1
                    else:
                        confidence_buckets["low"] += 1

        summary: Dict[str, Any] = {
            "batch_id": batch_id,
            "model_ref": data.get("model_ref"),
            "model_path": data.get("model_path"),
            "dataset_version": data.get("dataset_version"),
            "prediction_count": len(predictions),
            "created_at": data.get("created_at"),
            "time_window_min": min(time_windows) if time_windows else None,
            "time_window_max": max(time_windows) if time_windows else None,
            "label_distribution": dict(label_counts),
            "confidence_distribution": confidence_buckets,
        }
        if sample_limit > 0:
            summary["sample_predictions"] = predictions[:sample_limit]
        return summary

    def _load_label_names(self, slot: str) -> Dict[Any, str]:
        try:
            from services.iterative_labeling.label_registry import LabelRegistryService
            from services.iterative_labeling.storage.file_backend import FileLabelRegistryRepository

            registry = LabelRegistryService(slot=slot, registry_repo=FileLabelRegistryRepository())
            reg_data = registry.get_current()
            return {l["label_id"]: l["label_name"] for l in reg_data.get("labels", [])}
        except Exception:
            return {}

    def _build_review_quality_metrics(
        self,
        slot: str,
        label_names: Dict[Any, str],
        *,
        batch_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """按槽位或指定预测批次汇总人工真值与模型预测的分类指标。"""
        sessions_dir = _BACKEND_SERVICE_DIR / "data" / "iterative_labeling" / "review_results" / slot
        if not sessions_dir.exists():
            return None

        correct = 0
        total_counted = 0
        per_class_tp: Dict[int, int] = defaultdict(int)
        per_class_fp: Dict[int, int] = defaultdict(int)
        per_class_fn: Dict[int, int] = defaultdict(int)
        confusion_counts: Dict[Tuple[int, int], int] = defaultdict(int)
        class_ids: Set[int] = set()

        for sess_file in sessions_dir.glob("*.json"):
            try:
                session = json.loads(sess_file.read_text(encoding="utf-8"))
                if batch_id and str(session.get("prediction_batch_id") or "") != batch_id:
                    continue
                for unit in session.get("units", []):
                    verdict = unit.get("current_verdict")
                    if not verdict or verdict.get("action_type") == "skip":
                        continue
                    true_label = verdict.get("verdict_label")
                    prediction = unit.get("classifier_prediction") or {}
                    predicted_label = prediction.get("predicted_label")
                    if true_label is None or predicted_label is None:
                        continue
                    try:
                        true_id = int(true_label)
                        predicted_id = int(predicted_label)
                    except (TypeError, ValueError):
                        continue
                    total_counted += 1
                    class_ids.update((true_id, predicted_id))
                    confusion_counts[(true_id, predicted_id)] += 1
                    if true_id == predicted_id:
                        correct += 1
                        per_class_tp[true_id] += 1
                    else:
                        per_class_fn[true_id] += 1
                        per_class_fp[predicted_id] += 1
            except Exception:
                continue

        if total_counted <= 0:
            return None

        ordered_labels = sorted(class_ids | set(per_class_tp) | set(per_class_fp) | set(per_class_fn))
        per_class_metrics = []
        for class_id in ordered_labels:
            tp = per_class_tp.get(class_id, 0)
            fp = per_class_fp.get(class_id, 0)
            fn = per_class_fn.get(class_id, 0)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
            per_class_metrics.append(
                {
                    "label": str(class_id),
                    "label_name": (
                        label_names.get(class_id)
                        or label_names.get(str(class_id))
                        or f"label_{class_id}"
                    ),
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "f1": round(f1, 4),
                    "support": tp + fn,
                }
            )

        macro_precision = sum(item["precision"] for item in per_class_metrics) / len(per_class_metrics)
        macro_recall = sum(item["recall"] for item in per_class_metrics) / len(per_class_metrics)
        macro_f1 = sum(item["f1"] for item in per_class_metrics) / len(per_class_metrics)
        return {
            "accuracy": round(correct / total_counted, 4),
            "macro_precision": round(macro_precision, 4),
            "macro_recall": round(macro_recall, 4),
            "macro_f1": round(macro_f1, 4),
            "counted_units": total_counted,
            "per_class_metrics": per_class_metrics,
            "confusion_matrix": {
                "labels": ordered_labels,
                "label_names": [item["label_name"] for item in per_class_metrics],
                "matrix": [
                    [int(confusion_counts.get((true_id, predicted_id), 0)) for predicted_id in ordered_labels]
                    for true_id in ordered_labels
                ],
            },
        }

    def list_prediction_batches(self, slot: str = "pv_fault") -> List[Dict[str, Any]]:
        batch_dir = _BACKEND_SERVICE_DIR / "data" / "iterative_labeling" / "prediction_batches" / slot
        if not batch_dir.exists():
            return []

        label_names = self._load_label_names(slot)
        batches = []
        for f in sorted(batch_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                batches.append(
                    self._summarize_prediction_payload(
                        data,
                        batch_id=f.stem,
                        label_names=label_names,
                        sample_limit=0,
                    )
                )
            except Exception:
                pass
        return batches

    def get_prediction_batch(self, batch_id: str, slot: str = "pv_fault") -> Optional[Dict[str, Any]]:
        batch_path = (
            _BACKEND_SERVICE_DIR / "data" / "iterative_labeling" / "prediction_batches" / slot / f"{batch_id}.json"
        )
        if not batch_path.exists():
            return None
        data = json.loads(batch_path.read_text(encoding="utf-8"))
        label_names = self._load_label_names(slot)
        summary = self._summarize_prediction_payload(
            data,
            batch_id=batch_id,
            label_names=label_names,
            sample_limit=50,
        )
        quality_metrics = self._build_review_quality_metrics(
            slot,
            label_names,
            batch_id=batch_id,
        )
        prediction_count = int(summary.get("prediction_count") or 0)
        counted_units = int((quality_metrics or {}).get("counted_units") or 0)
        return {
            **data,
            **summary,
            "predictions": data.get("predictions") or [],
            "quality_metrics": quality_metrics,
            "ground_truth_summary": {
                "has_ground_truth": counted_units > 0,
                "counted_units": counted_units,
                "pending_ground_truth_units": max(0, prediction_count - counted_units),
                "coverage_rate": (
                    round(counted_units / prediction_count, 4) if prediction_count > 0 else None
                ),
            },
        }

    # ------------------------------------------------------------------
    # 槽位运营总览
    # ------------------------------------------------------------------

    def build_slot_overview(self, slot: str = "pv_fault") -> Dict[str, Any]:
        """聚合 pv_fault 槽位的真实预测/审核/标签/精度状态。"""
        overview: Dict[str, Any] = {
            "domain": slot,
            "model_ref": None,
            "latest_prediction_batch": None,
            "prediction_batch_id": None,
            "prediction_summary": {"total_batches": 0, "total_predictions": 0},
            "prediction_batches": [],
            "latest_prediction_detail": None,
            "batch_label_distribution": {},
            "batch_confidence_distribution": {},
            "label_distribution": {},
            "confidence_distribution": {},
            "review_progress": {"total_sessions": 0, "reviewed_sessions": 0, "total_units": 0, "reviewed_units": 0},
            "quality_metrics": None,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # 预测批次（含时间窗与分布摘要）
        batches = self.list_prediction_batches(slot)
        overview["prediction_summary"]["total_batches"] = len(batches)
        overview["prediction_batches"] = batches[:20]
        if batches:
            latest_meta = batches[0]
            overview["latest_prediction_batch"] = latest_meta
            overview["prediction_batch_id"] = latest_meta["batch_id"]
            overview["prediction_summary"]["total_predictions"] = sum(
                int(b.get("prediction_count") or 0) for b in batches
            )
            # 最新批次明细（含样本），便于精度运营核对“预测是否成功写出”
            latest_detail = self.get_prediction_batch(str(latest_meta["batch_id"]), slot)
            if latest_detail is not None:
                overview["latest_prediction_detail"] = {
                    key: latest_detail.get(key)
                    for key in (
                        "batch_id",
                        "model_ref",
                        "model_path",
                        "dataset_version",
                        "prediction_count",
                        "created_at",
                        "time_window_min",
                        "time_window_max",
                        "label_distribution",
                        "confidence_distribution",
                        "sample_predictions",
                        "quality_metrics",
                        "ground_truth_summary",
                    )
                }
                # 预测侧分布优先展示最新批次（审核侧分布仍可从会话聚合）
                overview["batch_label_distribution"] = latest_detail.get("label_distribution") or {}
                overview["batch_confidence_distribution"] = latest_detail.get("confidence_distribution") or {}

        # 累计训练状态 → 模型 + StoryRail 所需摘要
        from services.iterative_labeling.cumulative_training import CumulativeTrainingService

        ct = CumulativeTrainingService(slot=slot)
        ct_state = ct.get_state()
        overview["model_ref"] = ct_state.get("latest_completed_model_ref")
        latest_snapshot = ct_state.get("latest_snapshot") or {}
        latest_retrain = ct_state.get("latest_retrain_request") or {}
        overview["cumulative_training"] = {
            "effective_labeled_unit_count": ct_state.get("effective_labeled_unit_count", 0),
            "labeled_import_count": ct_state.get("labeled_import_count", 0),
            "pending_change_count": ct_state.get("pending_change_count", 0),
            "retrain_label_threshold": ct_state.get("retrain_label_threshold", 20),
            "next_retrain_in": ct_state.get("next_retrain_in", 0),
            "retrain_blocker": ct_state.get("retrain_blocker"),
            "latest_snapshot_id": latest_snapshot.get("snapshot_id") or latest_snapshot.get("id"),
            "latest_retrain_status": latest_retrain.get("status"),
            "latest_retrain_request_id": latest_retrain.get("request_id"),
            "latest_completed_model_ref": ct_state.get("latest_completed_model_ref"),
        }

        # 标签注册表
        label_names = self._load_label_names(slot)

        # 审核会话
        sessions_dir = _BACKEND_SERVICE_DIR / "data" / "iterative_labeling" / "review_results" / slot
        total_sessions = 0
        reviewed_sessions = 0
        total_units = 0
        reviewed_units = 0
        all_predictions: List[Dict[str, Any]] = []
        all_verdicts: List[Dict[str, Any]] = []

        if sessions_dir.exists():
            for f in sessions_dir.glob("*.json"):
                try:
                    sess = json.loads(f.read_text(encoding="utf-8"))
                    total_sessions += 1
                    s_total = sess.get("total_count", 0)
                    s_reviewed = sess.get("reviewed_count", 0)
                    total_units += s_total
                    reviewed_units += s_reviewed
                    if sess.get("status") == "reviewed":
                        reviewed_sessions += 1
                    for unit in sess.get("units", []):
                        cp = unit.get("classifier_prediction") or {}
                        pred_label = cp.get("predicted_label")
                        confidence = cp.get("confidence")
                        if pred_label is not None:
                            all_predictions.append({"predicted_label": pred_label, "confidence": confidence})
                        verdict = unit.get("current_verdict")
                        if verdict:
                            all_verdicts.append(verdict)
                except Exception:
                    pass

        overview["review_progress"] = {
            "total_sessions": total_sessions,
            "reviewed_sessions": reviewed_sessions,
            "total_units": total_units,
            "reviewed_units": reviewed_units,
        }

        # 标签分布（预测）
        label_dist: Dict[str, int] = defaultdict(int)
        conf_buckets: Dict[str, int] = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
        for p in all_predictions:
            name = label_names.get(p["predicted_label"], f"label_{p['predicted_label']}")
            label_dist[name] += 1
            conf = p.get("confidence")
            if conf is None:
                conf_buckets["unknown"] += 1
            elif conf >= 0.8:
                conf_buckets["high"] += 1
            elif conf >= 0.5:
                conf_buckets["medium"] += 1
            else:
                conf_buckets["low"] += 1
        overview["label_distribution"] = dict(label_dist)
        overview["confidence_distribution"] = conf_buckets

        # 分类精度指标 — 仅基于已审核单元的 verdict vs classifier_prediction
        if all_verdicts:
            correct = 0
            total_counted = 0
            per_class_tp: Dict[int, int] = defaultdict(int)
            per_class_fp: Dict[int, int] = defaultdict(int)
            per_class_fn: Dict[int, int] = defaultdict(int)
            confusion_counts: Dict[Tuple[int, int], int] = defaultdict(int)
            class_ids: Set[int] = set()

            for sess_file in (sessions_dir.glob("*.json") if sessions_dir.exists() else []):
                try:
                    sess = json.loads(sess_file.read_text(encoding="utf-8"))
                    for unit in sess.get("units", []):
                        verdict = unit.get("current_verdict")
                        if not verdict or verdict.get("action_type") == "skip":
                            continue
                        true_label = verdict.get("verdict_label")
                        cp = unit.get("classifier_prediction") or {}
                        pred_label = cp.get("predicted_label")
                        if true_label is None or pred_label is None:
                            continue
                        try:
                            true_id = int(true_label)
                            pred_id = int(pred_label)
                        except (TypeError, ValueError):
                            continue
                        total_counted += 1
                        class_ids.add(true_id)
                        class_ids.add(pred_id)
                        confusion_counts[(true_id, pred_id)] += 1
                        if true_id == pred_id:
                            correct += 1
                            per_class_tp[true_id] += 1
                        else:
                            per_class_fn[true_id] += 1
                            per_class_fp[pred_id] += 1
                except Exception:
                    pass

            if total_counted > 0:
                accuracy = correct / total_counted
                all_classes = set(per_class_tp) | set(per_class_fp) | set(per_class_fn) | class_ids
                ordered_labels = sorted(all_classes)
                precisions = []
                recalls = []
                for cls in ordered_labels:
                    tp = per_class_tp.get(cls, 0)
                    fp = per_class_fp.get(cls, 0)
                    fn = per_class_fn.get(cls, 0)
                    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                    precisions.append(p)
                    recalls.append(r)
                macro_p = sum(precisions) / len(precisions) if precisions else 0.0
                macro_r = sum(recalls) / len(recalls) if recalls else 0.0
                macro_f1 = (2 * macro_p * macro_r / (macro_p + macro_r)) if (macro_p + macro_r) > 0 else 0.0

                matrix = [
                    [int(confusion_counts.get((true_id, pred_id), 0)) for pred_id in ordered_labels]
                    for true_id in ordered_labels
                ]
                overview["quality_metrics"] = {
                    "accuracy": round(accuracy, 4),
                    "macro_precision": round(macro_p, 4),
                    "macro_recall": round(macro_r, 4),
                    "macro_f1": round(macro_f1, 4),
                    "counted_units": total_counted,
                    "confusion_matrix": {
                        "labels": ordered_labels,
                        "label_names": [
                            label_names.get(lbl) or label_names.get(str(lbl)) or f"label_{lbl}"
                            for lbl in ordered_labels
                        ],
                        "matrix": matrix,
                    },
                }

        # 统一由结构化汇总器覆盖，补充各类别 Precision / Recall / F1，并保持批次详情同口径。
        overview["quality_metrics"] = self._build_review_quality_metrics(slot, label_names)
        review_coverage_rate = (
            round(reviewed_units / total_units, 4) if total_units > 0 else None
        )
        overview["review_progress"]["review_coverage_rate"] = review_coverage_rate
        counted_units = int((overview["quality_metrics"] or {}).get("counted_units") or 0)
        overview["ground_truth_summary"] = {
            "has_ground_truth": counted_units > 0,
            "counted_units": counted_units,
            "pending_review_units": max(0, total_units - reviewed_units),
            "review_coverage_rate": review_coverage_rate,
        }

        # 部署槽位
        try:
            from services.deployment.store import DeploymentSlotStore

            slot_store = DeploymentSlotStore()
            slot_obj = slot_store.get(slot)
            if slot_obj and slot_obj.production_model:
                overview["model_ref"] = overview["model_ref"] or slot_obj.production_model.workflow_id
        except Exception:
            pass

        return overview
# @AI_GENERATED: end
