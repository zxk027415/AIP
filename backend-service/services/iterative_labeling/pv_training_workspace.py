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
from typing import Any, Dict, List, Optional

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

        # KMeans
        from services.operator_backends.kmeans import execute as kmeans_execute

        numeric_cols = [c for c in grouped.columns if grouped[c].dtype in (np.float64, np.int64, float, int)]
        feature_df = grouped[numeric_cols].copy()
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
                    col: float(members[col].mean()) for col in numeric_cols if col in members.columns
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
            "n_clusters": n_clusters,
            "total_members": int(len(grouped)),
            "clusters": clusters,
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
    ) -> Dict[str, Any]:
        """二次确认：生成不可变 labeled CSV，返回 dataset_path（项目根相对）。

        label_id_map: {proposed_label_name: label_id}
        """
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

        run["status"] = "confirmed"
        run["confirmed_dataset_path"] = dataset_path
        run["confirmed_sample_count"] = int(len(labeled_df))
        run["confirmed_label_count"] = int(labeled_df["label"].nunique())
        run["confirmed_at"] = datetime.utcnow().isoformat()
        run["updated_at"] = datetime.utcnow().isoformat()
        _atomic_write_json(self._workspace_dir / run_id / "run.json", run)

        return {
            "run_id": run_id,
            "dataset_path": dataset_path,
            "sample_count": int(len(labeled_df)),
            "label_count": int(labeled_df["label"].nunique()),
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
    ) -> Dict[str, Any]:
        """从源 CSV/Parquet 切取时间段并写入确认标签，返回 dataset_path。"""
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

        sliced["label"] = label_id

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

    def list_prediction_batches(self, slot: str = "pv_fault") -> List[Dict[str, Any]]:
        batch_dir = _BACKEND_SERVICE_DIR / "data" / "iterative_labeling" / "prediction_batches" / slot
        if not batch_dir.exists():
            return []
        batches = []
        for f in sorted(batch_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                batches.append({
                    "batch_id": f.stem,
                    "model_ref": data.get("model_ref"),
                    "prediction_count": len(data.get("predictions", [])),
                    "created_at": data.get("created_at"),
                })
            except Exception:
                pass
        return batches

    def get_prediction_batch(self, batch_id: str, slot: str = "pv_fault") -> Optional[Dict[str, Any]]:
        batch_path = (
            _BACKEND_SERVICE_DIR / "data" / "iterative_labeling" / "prediction_batches" / slot / f"{batch_id}.json"
        )
        if not batch_path.exists():
            return None
        return json.loads(batch_path.read_text(encoding="utf-8"))

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
            "label_distribution": {},
            "confidence_distribution": {},
            "review_progress": {"total_sessions": 0, "reviewed_sessions": 0, "total_units": 0, "reviewed_units": 0},
            "quality_metrics": None,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # 预测批次
        batches = self.list_prediction_batches(slot)
        overview["prediction_summary"]["total_batches"] = len(batches)
        if batches:
            latest = batches[0]
            overview["latest_prediction_batch"] = latest
            overview["prediction_batch_id"] = latest["batch_id"]
            overview["prediction_summary"]["total_predictions"] = sum(
                b.get("prediction_count", 0) for b in batches
            )

        # 累计训练状态 → 模型
        from services.iterative_labeling.cumulative_training import CumulativeTrainingService

        ct = CumulativeTrainingService(slot=slot)
        ct_state = ct.get_state()
        overview["model_ref"] = ct_state.get("latest_completed_model_ref")

        # 标签注册表
        from services.iterative_labeling.label_registry import LabelRegistryService
        from services.iterative_labeling.storage.file_backend import FileLabelRegistryRepository

        registry = LabelRegistryService(slot=slot, registry_repo=FileLabelRegistryRepository())
        reg_data = registry.get_current()
        label_names = {l["label_id"]: l["label_name"] for l in reg_data.get("labels", [])}

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
                        total_counted += 1
                        if true_label == pred_label:
                            correct += 1
                            per_class_tp[true_label] += 1
                        else:
                            per_class_fn[true_label] += 1
                            per_class_fp[pred_label] += 1
                except Exception:
                    pass

            if total_counted > 0:
                accuracy = correct / total_counted
                all_classes = set(per_class_tp) | set(per_class_fp) | set(per_class_fn)
                precisions = []
                recalls = []
                for cls in all_classes:
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

                overview["quality_metrics"] = {
                    "accuracy": round(accuracy, 4),
                    "macro_precision": round(macro_p, 4),
                    "macro_recall": round(macro_r, 4),
                    "macro_f1": round(macro_f1, 4),
                    "counted_units": total_counted,
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
