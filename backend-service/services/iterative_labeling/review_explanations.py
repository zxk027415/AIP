"""审核解释辅助：从预测批次加载模型与特征向量，供 SHAP / 相似案例使用。"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[2]


def _norm_id(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x).strip()


def unit_key_from_parts(site_id: Any, device_id: Any, branch_id: Any, time_window: Any) -> str:
    return f"{_norm_id(site_id)}|{_norm_id(device_id)}|{_norm_id(branch_id)}|{time_window}"


def load_prediction_batch(slot: str, batch_id: str) -> Optional[Dict[str, Any]]:
    if not batch_id:
        return None
    path = (
        _BACKEND
        / "data"
        / "iterative_labeling"
        / "prediction_batches"
        / slot
        / f"{batch_id}.json"
    )
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("读取预测批次失败 %s: %s", path, exc)
        return None


def resolve_batch_for_session(session: Dict[str, Any], slot: str) -> Optional[Dict[str, Any]]:
    batch_id = str(session.get("prediction_batch_id") or "").strip()
    batch = load_prediction_batch(slot, batch_id)
    if batch:
        return batch
    # 编辑器会话可能没有 pred- 批次文件
    return None


def load_sklearn_model(model_ref: Optional[str], model_path: Optional[str] = None):
    """返回 (model, feature_list)。失败返回 (None, [])。"""
    candidates: List[Path] = []
    if model_path:
        p = Path(str(model_path))
        if not p.is_absolute():
            # 相对项目根或 backend-service
            for base in (_BACKEND.parent, _BACKEND):
                cand = (base / p).resolve()
                if cand.exists():
                    candidates.append(cand)
                    break
        elif p.exists():
            candidates.append(p)
    if model_ref:
        candidates.append((_BACKEND / "data" / "models" / f"{model_ref}.pkl").resolve())

    for path in candidates:
        try:
            with open(path, "rb") as handle:
                payload = pickle.load(handle)
            if isinstance(payload, dict) and "model" in payload:
                return payload["model"], list(payload.get("feature_list") or [])
            return payload, []
        except Exception as exc:
            logger.warning("加载模型失败 %s: %s", path, exc)
    return None, []


def get_unit_feature_vector(
    batch: Dict[str, Any],
    unit_key: str,
    feature_list: Optional[List[str]] = None,
) -> Tuple[Optional[np.ndarray], List[str], str]:
    """从批次 unit_features 取向量。返回 (vector, names, reason)。"""
    unit_features = batch.get("unit_features") or {}
    feat_map = unit_features.get(unit_key)
    if not isinstance(feat_map, dict) or not feat_map:
        return None, [], "unit_features_missing"

    names = list(feature_list) if feature_list else list(feat_map.keys())
    if not names:
        names = list(feat_map.keys())
    values = []
    for name in names:
        if name not in feat_map:
            return None, names, f"feature_missing:{name}"
        val = feat_map[name]
        try:
            values.append(float(val) if val is not None else 0.0)
        except (TypeError, ValueError):
            values.append(0.0)
    return np.asarray(values, dtype=float), names, "ok"


def build_feature_matrix_from_batch(
    batch: Dict[str, Any],
    feature_list: Optional[List[str]] = None,
) -> Tuple[np.ndarray, List[str], List[Dict[str, Any]]]:
    """构建整批特征矩阵 + 元数据（用于相似案例索引）。"""
    unit_features = batch.get("unit_features") or {}
    predictions = batch.get("predictions") or []
    meta: List[Dict[str, Any]] = []
    rows: List[List[float]] = []
    names: List[str] = list(feature_list) if feature_list else []

    if not names:
        for feat_map in unit_features.values():
            if isinstance(feat_map, dict) and feat_map:
                names = list(feat_map.keys())
                break

    for row in predictions:
        uk = unit_key_from_parts(
            row.get("site_id"), row.get("device_id"), row.get("branch_id"), row.get("time_window")
        )
        feat_map = unit_features.get(uk)
        if not isinstance(feat_map, dict) or not feat_map or not names:
            continue
        values = []
        ok = True
        for name in names:
            if name not in feat_map:
                ok = False
                break
            try:
                values.append(float(feat_map[name]) if feat_map[name] is not None else 0.0)
            except (TypeError, ValueError):
                values.append(0.0)
        if not ok:
            continue
        rows.append(values)
        meta.append(
            {
                "unit_key": uk,
                "label": row.get("predicted_label"),
                "label_name": None,
                "confidence": row.get("confidence"),
                "time_window": row.get("time_window"),
            }
        )

    if not rows:
        return np.zeros((0, 0)), names, []
    return np.asarray(rows, dtype=float), names, meta
