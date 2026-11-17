# @AI_GENERATED
"""
ensemble_forecast operator backend — weighted ensemble for forecast outputs.
Reads multiple prediction arrays from upstream inputs and returns aggregated y_pred.
"""
import json
from typing import Dict, List

import numpy as np

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "ensemble_forecast"


def _parse_list(v, default: List[str]) -> List[str]:
    if v is None:
        return list(default)
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return list(default)


def execute(params: dict, inputs: dict) -> dict:
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    pred_keys = _parse_list(
        params.get("prediction_keys") or options.get("prediction_keys"),
        default=["y_pred_xgb", "y_pred_lgb", "y_pred_catb", "y_pred_ridge"],
    )
    # 任务 11.2：支持 weight_strategy 参数名（来自 node_param_patches），映射到内部 weight_mode
    # weight_strategy: "equal"（等权）/ "oof_rmse_inverse"（上游 OOF RMSE 逆权重）
    _ws = str(params.get("weight_strategy") or options.get("weight_strategy") or "").strip()
    if _ws == "oof_rmse_inverse":
        _ws_mapped = "upstream_oof_rmse"
    elif _ws == "equal":
        _ws_mapped = "equal"
    else:
        _ws_mapped = None  # 不覆盖，使用 weight_mode 原值
    weight_mode = _ws_mapped or str(params.get("weight_mode") or options.get("weight_mode") or "auto_rmse").lower()

    model_preds: Dict[str, np.ndarray] = {}
    for k in pred_keys:
        if k in inputs and inputs.get(k) is not None:
            arr = np.asarray(inputs.get(k), dtype=float).reshape(-1)
            if arr.size > 0:
                model_preds[k] = arr

    if not model_preds:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", f"No prediction arrays found from keys: {pred_keys}"
        )

    # align by minimum length
    mlen = min(len(v) for v in model_preds.values())
    model_preds = {k: v[:mlen] for k, v in model_preds.items()}

    # parse weights
    weights_raw = params.get("weights") or options.get("weights")
    weights_map: Dict[str, float] = {}
    if isinstance(weights_raw, dict):
        for k, v in weights_raw.items():
            try:
                weights_map[str(k)] = float(v)
            except Exception:
                pass
    elif isinstance(weights_raw, str) and weights_raw.strip():
        # format: y_pred_xgb:0.4,y_pred_lgb:0.2...
        for pair in weights_raw.split(","):
            if ":" in pair:
                kk, vv = pair.split(":", 1)
                kk = kk.strip()
                try:
                    weights_map[kk] = float(vv.strip())
                except Exception:
                    continue

    # auto_rmse: use y_true and inverse RMSE weighting, fallback to manual/equal
    auto_weights = None
    auto_weight_source = None
    y_true = None
    for key in ("y_true", "test_target", "train_target"):
        if key in inputs and inputs[key] is not None:
            y_true = np.asarray(inputs[key], dtype=float).reshape(-1)[:mlen]
            break

    # upstream_oof_rmse mode: use OOF RMSE from upstream model operators (aligned with local code)
    if weight_mode == "upstream_oof_rmse":
        oof_rmses: Dict[str, float] = {}
        for k in model_preds.keys():
            # Try oof_rmse_{suffix} first (e.g. oof_rmse_xgb), then generic oof_rmse
            suffix = k.replace("y_pred_", "")
            oof_key = f"oof_rmse_{suffix}"
            if oof_key in inputs and inputs[oof_key] is not None:
                try:
                    oof_rmses[k] = float(inputs[oof_key])
                except (TypeError, ValueError):
                    pass
        if len(oof_rmses) == len(model_preds):
            # Inverse RMSE weighting (same as local _compute_adaptive_weights)
            inv = {k: 1.0 / v for k, v in oof_rmses.items() if v > 1e-9}
            if inv:
                s = sum(inv.values())
                auto_weights = {k: v / s for k, v in inv.items()}
                auto_weight_source = "upstream_oof_rmse"

        # Fallback: if not all models have oof_rmse, fall back to auto_rmse on test set
        if auto_weights is None:
            weight_mode = "auto_rmse"  # fall through to auto_rmse logic below

    if weight_mode == "auto_rmse" and y_true is not None and y_true.size > 0:
        rmses: Dict[str, float] = {}
        yt = np.asarray(y_true, dtype=float).reshape(-1)[:mlen]
        finite_yt = np.isfinite(yt)
        for k, pred in model_preds.items():
            yp = np.asarray(pred, dtype=float).reshape(-1)[:mlen]
            mask = finite_yt & np.isfinite(yp)
            if not mask.any():
                continue
            rmse = float(np.sqrt(np.mean(np.square(yp[mask] - yt[mask]))))
            if rmse > 1e-9:
                rmses[k] = rmse
        if rmses:
            inv = {k: 1.0 / v for k, v in rmses.items()}
            s = sum(inv.values())
            auto_weights = {k: v / s for k, v in inv.items()}
            auto_weight_source = "auto_rmse"

    if auto_weights is not None:
        weights_map = auto_weights
    elif not weights_map:
        if weight_mode == "equal":
            n = len(model_preds)
            weights_map = {k: 1.0 / n for k in model_preds.keys()}
        else:
            n = len(model_preds)
            weights_map = {k: 1.0 / n for k in model_preds.keys()}
    else:
        # keep only available keys, normalize positive weights
        weights_map = {k: float(v) for k, v in weights_map.items() if k in model_preds and float(v) > 0}
        if not weights_map:
            n = len(model_preds)
            weights_map = {k: 1.0 / n for k in model_preds.keys()}
        else:
            s = sum(weights_map.values())
            weights_map = {k: v / s for k, v in weights_map.items()}

    y_pred = np.zeros(mlen, dtype=float)
    for k, w in weights_map.items():
        y_pred += w * model_preds[k]
    y_pred = np.maximum(y_pred, 0.0)

    out = {
        "y_pred": y_pred,
        "predictions": y_pred,
        "forecast_values": y_pred.tolist(),
        "model_weights": weights_map,
        "weight_mode_used": auto_weight_source if auto_weights is not None else ("manual" if weights_raw else "equal"),
    }
    if y_true is not None and y_true.size > 0:
        out["y_true"] = y_true
    return out
# @AI_GENERATED: end
