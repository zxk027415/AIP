# @AI_GENERATED
"""
feature_select operator backend — Feature selection for classification tasks.

Supports four methods:
  - mutual_info  : SelectKBest with mutual_info_classif (sklearn)
  - f_test       : SelectKBest with f_classif (sklearn)
  - importance   : Tree-based feature importance (sklearn RandomForestClassifier)
  - mrmr         : Maximum Relevance Minimum Redundancy (mrmr-selection library)

For mrmr method, two modes are supported:
  - fit       : Compute mRMR ranking and return selected features + feature_list + target
  - transform : Filter columns by an existing feature_list without recomputing

Return format (all methods):
  {
    "selected_features": pd.DataFrame,   # filtered feature matrix
    "feature_list":      list,           # selected feature names
    "target":            np.ndarray      # y labels (passed through)
  }
"""
import os
import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "feature_select"

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _backend_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _existing_model_path(raw: str) -> str | None:
    path = str(raw or "").strip().replace("\\", "/")
    if not path:
        return None
    if path.startswith("backend-service/"):
        path = path[len("backend-service/") :]
    if os.path.exists(path):
        return path
    alt = os.path.join(_backend_dir(), path)
    return alt if os.path.exists(alt) else None


def _resolve_transform_pkl(params: dict) -> tuple[str | None, str]:
    """Locate the RFC pickle that owns feature_list. Never silently pick xgbr_*.pkl first."""
    gc = params.get("_global_config") if isinstance(params.get("_global_config"), dict) else {}
    model_id = str(params.get("model_id") or gc.get("model_id") or "").strip()
    candidates = [
        (params.get("model_path"), "params.model_path"),
        (gc.get("model_ref"), "global_config.model_ref"),
        (gc.get("backtest_model_ref"), "global_config.backtest_model_ref"),
    ]
    if model_id:
        candidates.append((f"data/models/{model_id}.pkl", "model_id"))
    for raw, source in candidates:
        found = _existing_model_path(str(raw or ""))
        if found:
            return found, source
    models_dir = os.path.join(_backend_dir(), "data", "models")
    if not os.path.isdir(models_dir):
        return None, "missing_models_dir"
    names = [name for name in os.listdir(models_dir) if name.endswith(".pkl")]
    slot = str(params.get("slot") or gc.get("slot") or "")
    preferred = names
    if slot in {"pv_day", "pv_fault"}:
        preferred = [name for name in names if name.startswith("pv_fault_rfc_")] or names
    if not preferred:
        return None, "none"
    chosen = sorted(preferred, reverse=True)[0]
    return os.path.join(models_dir, chosen), "latest_glob"


def _parse_feature_list(value) -> list | None:
    """Parse feature_list from string/list/None."""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(f) for f in value]
    if isinstance(value, str):
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(f) for f in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
        # comma-separated fallback
        return [f.strip() for f in value.split(",") if f.strip()]
    return None


def _extract_X_y(data: pd.DataFrame, target_col: str) -> tuple[pd.DataFrame, np.ndarray]:
    """Split a DataFrame into numeric feature matrix X and label array y.

    Non-numeric columns (e.g. site_id, device_id, time_window) are automatically
    dropped from X so that downstream selectors receive a clean float matrix.
    """
    if target_col not in data.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"target column '{target_col}' not found. Available: {list(data.columns)}",
        )
    y = data[target_col].to_numpy()
    X = data.drop(columns=[target_col])
    # Drop non-numeric columns (id fields like site_id, device_id, time_window)
    non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    if non_numeric:
        logger.info(
            f"[{OPERATOR_ID}] Dropping {len(non_numeric)} non-numeric columns "
            f"before feature selection: {non_numeric[:5]}{'...' if len(non_numeric) > 5 else ''}"
        )
        X = X.drop(columns=non_numeric)
    if X.empty:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "No numeric feature columns remain after dropping non-numeric columns.",
        )
    return X, y


# ──────────────────────────────────────────────
# Method: mutual_info
# ──────────────────────────────────────────────

def _select_mutual_info(X: pd.DataFrame, y: np.ndarray, k: int) -> list[str]:
    from sklearn.feature_selection import SelectKBest, mutual_info_classif

    k = min(k, X.shape[1])
    selector = SelectKBest(score_func=mutual_info_classif, k=k)
    selector.fit(X.fillna(0), y)
    mask = selector.get_support()
    return list(X.columns[mask])


# ──────────────────────────────────────────────
# Method: f_test
# ──────────────────────────────────────────────

def _select_f_test(X: pd.DataFrame, y: np.ndarray, k: int) -> list[str]:
    from sklearn.feature_selection import SelectKBest, f_classif

    k = min(k, X.shape[1])
    selector = SelectKBest(score_func=f_classif, k=k)
    selector.fit(X.fillna(0), y)
    mask = selector.get_support()
    return list(X.columns[mask])


# ──────────────────────────────────────────────
# Method: importance
# ──────────────────────────────────────────────

def _select_importance(X: pd.DataFrame, y: np.ndarray, k: int) -> list[str]:
    from sklearn.ensemble import RandomForestClassifier

    k = min(k, X.shape[1])
    clf = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)
    clf.fit(X.fillna(0), y)
    importances = pd.Series(clf.feature_importances_, index=X.columns)
    top_features = importances.nlargest(k).index.tolist()
    return top_features


# ──────────────────────────────────────────────
# Method: mrmr (fit + transform modes)
# ──────────────────────────────────────────────

def _select_mrmr_fit(X: pd.DataFrame, y: np.ndarray, k: int) -> list[str]:
    """
    Compute mRMR feature ranking via mrmr-selection library.
    K is clamped to min(k, available_features) to avoid out-of-range errors.
    """
    from mrmr import mrmr_classif

    actual_k = min(k, len(X.columns))
    if actual_k <= 0:
        raise ValueError(
            f"[{OPERATOR_ID}] mRMR: no feature columns available for selection "
            f"(X has {len(X.columns)} columns)"
        )

    y_series = pd.Series(y) if not isinstance(y, pd.Series) else y
    selected = mrmr_classif(X=X, y=y_series, K=actual_k)

    if not selected:
        raise ValueError(
            f"[{OPERATOR_ID}] mRMR feature selection returned an empty list. "
            "Check that X contains numeric data and y has at least two classes."
        )

    return selected


def _select_mrmr_transform(X: pd.DataFrame, feature_list: list[str]) -> list[str]:
    """
    Filter X columns to the pre-computed feature_list (transform mode).
    Warns about missing columns but does not raise to allow partial matches.
    """
    missing = [f for f in feature_list if f not in X.columns]
    if missing:
        logger.warning(
            f"[{OPERATOR_ID}] mRMR transform: {len(missing)} feature(s) not found in X "
            f"and will be skipped: {missing[:10]}{'...' if len(missing) > 10 else ''}"
        )
    available = [f for f in feature_list if f in X.columns]
    if not available:
        raise ValueError(
            f"[{OPERATOR_ID}] mRMR transform: none of the provided feature_list "
            "columns exist in the input DataFrame."
        )
    return available


# ──────────────────────────────────────────────
# Main execute()
# ──────────────────────────────────────────────

def execute(params: dict, inputs: dict) -> dict:
    """
    Select features for classification tasks.

    Args:
        params:
            - method (str): "mutual_info" | "f_test" | "importance" | "mrmr". Default "mutual_info".
            - k (int): Number of features to select. Default 50.
            - target_col (str): Name of the label column in the input DataFrame. Default "label".
            - mode (str, mrmr only): "fit" | "transform". Default "fit".
            - feature_list (list|str, mrmr transform mode): Pre-computed feature names.
        inputs:
            - data (pd.DataFrame): Feature matrix with a label column OR
            - features (pd.DataFrame): Feature matrix (alternative key)
            - target (np.ndarray, optional): Label array (used when label not in data)

    Returns:
        {
            "selected_features": pd.DataFrame,
            "feature_list": list[str],
            "target": np.ndarray,
        }
    """
    # ── Resolve input data ──────────────────────────────────────────────────
    # Support multi-input merge: when three feature extractor branches all feed
    # into feature_select, _collect_upstream_inputs only passes the first "data"
    # key. Check all input keys and merge any DataFrames found.
    data = inputs.get("data")
    if data is None:
        data = inputs.get("features")

    # Collect any additional DataFrame inputs (from parallel feature branches)
    extra_dfs = []
    for k, v in inputs.items():
        if k in ("data", "features", "target"):
            continue
        if isinstance(v, pd.DataFrame) and not v.empty:
            extra_dfs.append(v)

    if extra_dfs and isinstance(data, pd.DataFrame):
        # Merge extra feature matrices on shared index (id_fields columns or default RangeIndex)
        # First: reset named MultiIndex on any extra frame so id_fields become columns
        for i, extra in enumerate(extra_dfs):
            if extra.index.names and any(n is not None for n in extra.index.names):
                extra_dfs[i] = extra.reset_index()

        # Also reset on data if it has a named index
        if data.index.names and any(n is not None for n in data.index.names):
            data = data.reset_index()

        for extra in extra_dfs:
            try:
                if data.index.equals(extra.index):
                    # Same index — direct column concat
                    new_cols = [c for c in extra.columns if c not in data.columns]
                    if new_cols:
                        data = pd.concat([data, extra[new_cols]], axis=1)
                else:
                    # Try merge on common non-numeric columns (id fields)
                    common_cols = [c for c in extra.columns if c in data.columns and not pd.api.types.is_numeric_dtype(data[c])]
                    if common_cols:
                        new_cols = [c for c in extra.columns if c not in data.columns]
                        if new_cols:
                            data = data.merge(extra[common_cols + new_cols], on=common_cols, how='left')
                    else:
                        # Fallback: positional concat
                        min_rows = min(len(data), len(extra))
                        new_cols = [c for c in extra.columns if c not in data.columns]
                        if new_cols:
                            data = pd.concat([data.iloc[:min_rows].reset_index(drop=True),
                                              extra.iloc[:min_rows][new_cols].reset_index(drop=True)], axis=1)
            except Exception as e:
                logger.warning(f"[{OPERATOR_ID}] Could not merge extra feature DataFrame: {e}")

    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "Input 'data' (or 'features') must be a pandas DataFrame",
        )

    # ── Parse params ────────────────────────────────────────────────────────
    import json

    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    method = str(params.get("method") or options.get("method") or "mutual_info").strip().lower()
    k = int(params.get("k") or options.get("k") or 50)
    target_col = str(params.get("target_col") or options.get("target_col") or "label").strip()
    mode = str(params.get("mode") or options.get("mode") or "fit").strip().lower()
    feature_list_raw = params.get("feature_list") or options.get("feature_list")
    feature_list = _parse_feature_list(feature_list_raw)

    valid_methods = {"mutual_info", "f_test", "importance", "mrmr"}
    if method not in valid_methods:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Invalid method '{method}'. Must be one of {sorted(valid_methods)}",
        )

    # ── Extract X and y ─────────────────────────────────────────────────────
    external_target = inputs.get("target")

    # transform 模式不需要标签，提前进入快捷路径（避免在预测数据里找 target_col）
    if method == "mrmr" and mode == "transform":
        if external_target is not None:
            X = data
            y = np.asarray(external_target)
        else:
            # 预测流水线没有标签列，直接用全量特征
            X = data
            y = np.array([])

        # ── 从指定模型 / 调度 model_ref 读取 feature_list，避免 glob 到 xgbr_*.pkl ──
        if not feature_list or (isinstance(feature_list, list) and len(feature_list) == 1
                                and str(feature_list[0]).strip().lower() == "latest"):
            import pickle as _pickle
            pkl_path, source = _resolve_transform_pkl(params)
            if not pkl_path:
                raise OperatorExecutionError(
                    OPERATOR_ID, "ParameterError",
                    "feature_list='latest' but no saved models found. Run training first.",
                )
            with open(pkl_path, "rb") as _f:
                _payload = _pickle.load(_f)
            if not isinstance(_payload, dict):
                raise OperatorExecutionError(
                    OPERATOR_ID, "ParameterError",
                    f"model pickle is not a dict (source={source}, path={pkl_path})",
                )
            feature_list = _payload.get("feature_list") or []
            logger.info(
                f"[{OPERATOR_ID}] feature_list loaded from {source}: "
                f"{len(feature_list)} features path={pkl_path}"
            )
        if not feature_list:
            raise OperatorExecutionError(
                OPERATOR_ID, "ParameterError",
                "mrmr transform mode requires 'feature_list' to be provided (or 'latest')",
            )

        # 只保留数值列（去掉 id 字段等字符串列）
        non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
        if non_numeric:
            X = X.drop(columns=non_numeric)

        try:
            selected = _select_mrmr_transform(X, feature_list)
        except ValueError as exc:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "ValueError",
                f"{exc} feature_list[:5]={list(feature_list)[:5]} X.columns[:10]={list(X.columns)[:10]}",
            ) from exc
        logger.info(f"[{OPERATOR_ID}] mRMR transform: retained {len(selected)} / "
                    f"{len(feature_list)} features")
        return {
            "selected_features": X[selected].copy(),
            "feature_list": selected,
            "target": y,
        }

    # ── fit / other modes: need y ─────────────────────────────────────────
    if external_target is not None:
        X = data
        y = np.asarray(external_target)
    else:
        X, y = _extract_X_y(data, target_col)

    # ── fit modes ────────────────────────────────────────────────────────────
    try:
        if method == "mutual_info":
            selected = _select_mutual_info(X, y, k)
        elif method == "f_test":
            selected = _select_f_test(X, y, k)
        elif method == "importance":
            selected = _select_importance(X, y, k)
        elif method == "mrmr":
            # mode == "fit" (default) or anything else falls here
            selected = _select_mrmr_fit(X, y, k)
        else:
            # unreachable — already validated above
            raise OperatorExecutionError(
                OPERATOR_ID, "ParameterError", f"Unexpected method '{method}'"
            )
    except ValueError as exc:
        raise OperatorExecutionError(OPERATOR_ID, "SelectionError", str(exc)) from exc

    if not selected:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "SelectionError",
            f"Feature selection (method={method}) returned an empty list",
        )

    logger.info(
        f"[{OPERATOR_ID}] Selected {len(selected)} features "
        f"(method={method}, k={k}, mode={mode})"
    )

    return {
        "selected_features": X[selected].copy(),
        "feature_list": selected,
        "target": y,
    }
# @AI_GENERATED: end
