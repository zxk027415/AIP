# @AI_GENERATED
"""
stratified_cv_eval operator backend — 无泄漏 · 重复分层留出 分类精度评估。

用途
----
把一条「特征已提取」的分类数据集，做 N 次重复的分层留出评估，返回精度的
均值 ± 标准差、各类 recall、聚合混淆矩阵和 classification_report。

为什么是一个算子而不是「切分/SMOTE/训练/指标」四个节点
----------------------------------------------------------
无泄漏 + 重复，要求「分层切分 → mRMR(只在train fit) → SMOTE(只在train) → 训练
→ 在test预测 → 算分」这一整套在每次重复里独立跑。静态工作流 DAG 无法让这段子图
循环 N 次，因此收进单个算子内部循环。

输入 (inputs)
-------------
- 任意数量的 pd.DataFrame（三路特征算子的输出 feat_stat / feat_tsfresh / feat_compare）。
  其中至少一路必须含 `label`（真值标签）列；其余路按 id_fields 对齐合并进来。

参数 (params)
-------------
- n_repeats     (int):   重复次数，默认 10
- test_ratio    (float): 每次测试集占比，默认 0.2
- k             (int):   mRMR 选取特征数，默认 20
- n_estimators  (int):   随机森林树数，默认 80
- random_state  (int):   基准随机种子（第 i 次用 random_state + i），默认 90
- smote_limit   (int):   SMOTE 每个少数类合成后上限，默认 300
- average       (str):   precision/recall/f1 聚合方式，默认 "macro"
- id_fields     (list|str): 对齐用的 id 列，默认 ["site_id","device_id","branch_id","time_window"]
- target_col    (str):   标签列名，默认 "label"

关键保证（对应用户要求）
------------------------
1. 无泄漏：mRMR 与 SMOTE 都只在训练折上做；测试折保持原始分布、仅复用训练折选出的特征。
2. 分层 + 类别覆盖：自定义逐类分配，保证样本数 ≥2 的类在 train/test 两侧各 ≥1 条。
3. 训练/测试类别对应：任何进入 test 的类必然也在 train（每类至少给 train 留 1 条），
   因此 test 的类别集合 ⊆ train 的类别集合。

返回 (dict)
-----------
顶层放标量指标（accuracy_mean / macro_f1_mean 等）便于前端摘要直接展示，
另含 per_class_recall_mean / confusion_matrix / classification_report / warnings 等。
"""
import logging

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "stratified_cv_eval"

logger = logging.getLogger(__name__)

_DEFAULT_ID_FIELDS = ["site_id", "device_id", "branch_id", "time_window"]


def _parse_id_fields(value):
    if value is None:
        return list(_DEFAULT_ID_FIELDS)
    if isinstance(value, str):
        return [c.strip() for c in value.split(",") if c.strip()]
    if isinstance(value, (list, tuple)):
        return [str(c).strip() for c in value if str(c).strip()]
    return list(_DEFAULT_ID_FIELDS)


def _merge_feature_frames(inputs: dict, id_fields: list, target_col: str) -> pd.DataFrame:
    """合并三路特征 DataFrame。

    STAT 路是普通 RangeIndex、含 id 列与 label 列；TSF/CMP 路是 id 的 MultiIndex、无 label。
    先把带命名索引的 frame reset 成列，再以含 label 的 frame 为基准按共同 id 列 left-merge。
    """
    frames = []
    for v in inputs.values():
        if isinstance(v, pd.DataFrame) and not v.empty:
            df = v
            if df.index.names and any(n is not None for n in df.index.names):
                df = df.reset_index()
            frames.append(df)

    if not frames:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "未收到任何非空特征 DataFrame，请确认上游特征算子已连入。"
        )

    base = next((f for f in frames if target_col in f.columns), None)
    if base is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"没有任何一路特征包含标签列 '{target_col}'。"
            f"请确认统计特征算子的 id_fields 含 '{target_col}'。"
        )

    merged = base.copy()
    id_present = [c for c in id_fields if c in merged.columns]
    for f in frames:
        if f is base:
            continue
        on = [c for c in id_present if c in f.columns]
        if not on:
            logger.warning(f"[{OPERATOR_ID}] 一路特征缺少对齐 id 列，已跳过合并：cols={list(f.columns)[:6]}")
            continue
        new_cols = [c for c in f.columns if c not in merged.columns]
        if new_cols:
            merged = merged.merge(f[on + new_cols], on=on, how="left")
    return merged


def _build_Xy(merged: pd.DataFrame, id_fields: list, target_col: str):
    """从合并表拆出数值特征矩阵 X 与标签 y。丢弃 id/时间/非数值列。"""
    y = pd.to_numeric(merged[target_col], errors="coerce")
    drop_cols = set([target_col, "time", "time_window"]) | set(id_fields)
    X = merged.drop(columns=[c for c in drop_cols if c in merged.columns], errors="ignore")
    non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    if non_numeric:
        X = X.drop(columns=non_numeric)
    # 标签缺失的行剔除
    mask = y.notna()
    X = X.loc[mask].reset_index(drop=True)
    y = y.loc[mask].astype(int).reset_index(drop=True)
    X = X.fillna(0.0)
    if X.empty or X.shape[1] == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "拆分后没有可用的数值特征列。"
        )
    return X, y.to_numpy()


def _stratified_split(y: np.ndarray, test_ratio: float, rng: np.random.RandomState):
    """逐类分层切分，保证样本数 ≥2 的类在 train/test 两侧各 ≥1 条。

    返回 (train_idx, test_idx, single_sample_classes)。
    样本数 ==1 的类无法两侧覆盖，全部进 train，并在 single_sample_classes 中记录。
    """
    train_idx, test_idx = [], []
    single = []
    for cls in np.unique(y):
        idx = np.where(y == cls)[0]
        rng.shuffle(idx)
        n = len(idx)
        if n == 1:
            train_idx.extend(idx.tolist())
            single.append(int(cls))
            continue
        n_test = int(round(n * test_ratio))
        n_test = max(1, min(n_test, n - 1))  # 两侧各留 ≥1
        test_idx.extend(idx[:n_test].tolist())
        train_idx.extend(idx[n_test:].tolist())
    return np.array(train_idx), np.array(test_idx), single


def _smote_train_only(X_train: pd.DataFrame, y_train: np.ndarray, limit: int, seed: int):
    """只在训练折上做 SMOTE。少数类(train内)样本<2 无法合成则跳过该类并记录。"""
    try:
        from imblearn.over_sampling import SMOTE
    except ImportError:
        logger.warning(f"[{OPERATOR_ID}] imbalanced-learn 不可用，跳过 SMOTE")
        return X_train, y_train, ["imblearn_unavailable"]

    classes, counts = np.unique(y_train, return_counts=True)
    majority = counts.max()
    cnt_map = dict(zip(classes.tolist(), counts.tolist()))

    # 只对「少于多数类 且 train 内样本数>=2」的类合成
    synth_classes = [int(c) for c, cnt in cnt_map.items() if cnt < majority and cnt >= 2]
    skipped = [int(c) for c, cnt in cnt_map.items() if cnt < majority and cnt < 2]

    if not synth_classes:
        return X_train, y_train, skipped

    min_synth_cnt = min(cnt_map[c] for c in synth_classes)
    k_neighbors = max(1, min(5, min_synth_cnt - 1))
    strategy = {c: int(min(limit, majority)) for c in synth_classes}

    try:
        sm = SMOTE(sampling_strategy=strategy, k_neighbors=k_neighbors, random_state=seed)
        X_res, y_res = sm.fit_resample(X_train, y_train)
        return pd.DataFrame(X_res, columns=X_train.columns), np.asarray(y_res), skipped
    except Exception as exc:  # noqa: BLE001 — 合成失败不应中断评估
        logger.warning(f"[{OPERATOR_ID}] SMOTE 失败({type(exc).__name__}: {exc})，该折用原始训练数据")
        return X_train, y_train, skipped + ["smote_failed"]


def _select_features_mrmr(X_train: pd.DataFrame, y_train: np.ndarray, k: int) -> list:
    """mRMR 只在训练折上 fit，返回选中的特征名列表。"""
    from mrmr import mrmr_classif

    actual_k = min(k, X_train.shape[1])
    if actual_k <= 0:
        return list(X_train.columns)
    selected = mrmr_classif(X=X_train, y=pd.Series(y_train), K=actual_k)
    return selected or list(X_train.columns)


def execute(params: dict, inputs: dict) -> dict:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        classification_report,
        confusion_matrix as sk_confusion_matrix,
    )

    # ── 参数 ──────────────────────────────────────────────────────────────
    def _int(name, default):
        try:
            return int(params.get(name) or default)
        except (TypeError, ValueError):
            return default

    def _float(name, default):
        try:
            return float(params.get(name) or default)
        except (TypeError, ValueError):
            return default

    n_repeats = max(1, _int("n_repeats", 10))
    test_ratio = _float("test_ratio", 0.2)
    if not (0.05 <= test_ratio <= 0.5):
        test_ratio = 0.2
    k = _int("k", 20)
    n_estimators = _int("n_estimators", 80)
    random_state = _int("random_state", 90)
    smote_limit = _int("smote_limit", 300)
    average = str(params.get("average") or "macro").strip().lower()
    if average not in ("macro", "micro", "weighted"):
        average = "macro"
    id_fields = _parse_id_fields(params.get("id_fields"))
    target_col = str(params.get("target_col") or "label").strip()

    # ── 合并特征 + 构造 X / y ────────────────────────────────────────────
    merged = _merge_feature_frames(inputs, id_fields, target_col)
    X, y = _build_Xy(merged, id_fields, target_col)

    classes_all, counts_all = np.unique(y, return_counts=True)
    class_dist = {int(c): int(n) for c, n in zip(classes_all, counts_all)}
    if len(classes_all) < 2:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"只有 1 个类别({classes_all.tolist()})，无法做分类评估。"
        )

    warnings_set = set()
    single_classes = [int(c) for c, n in class_dist.items() if n < 2]
    for c in single_classes:
        warnings_set.add(f"class_{c}_only_1_sample_train_only")

    # ── 重复分层评估 ─────────────────────────────────────────────────────
    acc_list, prec_list, rec_list, f1_list = [], [], [], []
    all_y_true, all_y_pred = [], []
    per_class_recall_runs = {int(c): [] for c in classes_all}

    for i in range(n_repeats):
        rng = np.random.RandomState(random_state + i)
        train_idx, test_idx, _single = _stratified_split(y, test_ratio, rng)
        if len(test_idx) == 0 or len(train_idx) == 0:
            warnings_set.add("empty_split_skipped")
            continue

        X_tr, y_tr = X.iloc[train_idx].reset_index(drop=True), y[train_idx]
        X_te, y_te = X.iloc[test_idx].reset_index(drop=True), y[test_idx]

        # mRMR 只在训练折 fit
        try:
            feat_list = _select_features_mrmr(X_tr, y_tr, k)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{OPERATOR_ID}] 第{i}次 mRMR 失败({exc})，使用全部特征")
            feat_list = list(X_tr.columns)
            warnings_set.add("mrmr_fallback_all_features")
        feat_list = [f for f in feat_list if f in X_tr.columns]
        X_tr_sel, X_te_sel = X_tr[feat_list], X_te[feat_list]

        # SMOTE 只在训练折
        X_tr_res, y_tr_res, skipped = _smote_train_only(X_tr_sel, y_tr, smote_limit, random_state + i)
        for s in skipped:
            warnings_set.add(f"smote_skipped_class_{s}" if isinstance(s, int) else s)

        # 训练 + 在测试折预测
        clf = RandomForestClassifier(n_estimators=n_estimators, random_state=random_state, n_jobs=-1)
        clf.fit(X_tr_res, y_tr_res)
        y_pred = clf.predict(X_te_sel).astype(int)

        acc_list.append(float(accuracy_score(y_te, y_pred)))
        prec_list.append(float(precision_score(y_te, y_pred, average=average, zero_division=0)))
        rec_list.append(float(recall_score(y_te, y_pred, average=average, zero_division=0)))
        f1_list.append(float(f1_score(y_te, y_pred, average=average, zero_division=0)))

        # 各类 recall（labels 固定为全部类，未出现的类 recall 记 NaN 不计入均值）
        labels_run = sorted(set(y_te.tolist()))
        rec_per = recall_score(y_te, y_pred, labels=labels_run, average=None, zero_division=0)
        for lbl, r in zip(labels_run, rec_per):
            per_class_recall_runs[int(lbl)].append(float(r))

        all_y_true.extend(y_te.tolist())
        all_y_pred.extend(y_pred.tolist())

    if not f1_list:
        raise OperatorExecutionError(
            OPERATOR_ID, "EvaluationError",
            "所有重复均未产生有效评估（切分为空）。请检查样本量与类别分布。"
        )

    # ── 聚合 ─────────────────────────────────────────────────────────────
    def _mean(a):
        return round(float(np.mean(a)), 4) if a else None

    def _std(a):
        return round(float(np.std(a)), 4) if a else None

    labels_sorted = [int(c) for c in classes_all]
    agg_true = np.array(all_y_true)
    agg_pred = np.array(all_y_pred)
    cm = sk_confusion_matrix(agg_true, agg_pred, labels=labels_sorted)
    report = classification_report(agg_true, agg_pred, labels=labels_sorted, zero_division=0)

    per_class_recall_mean = {
        str(lbl): (round(float(np.mean(v)), 4) if v else None)
        for lbl, v in per_class_recall_runs.items()
    }

    result = {
        "n_repeats": len(f1_list),
        "test_ratio": test_ratio,
        "k_features": k,
        "n_samples": int(len(y)),
        "n_features_total": int(X.shape[1]),
        "n_classes": int(len(classes_all)),
        "class_distribution": class_dist,
        "accuracy_mean": _mean(acc_list),
        "accuracy_std": _std(acc_list),
        f"{average}_precision_mean": _mean(prec_list),
        f"{average}_recall_mean": _mean(rec_list),
        "macro_f1_mean": _mean(f1_list),
        "macro_f1_std": _std(f1_list),
        "per_repeat_macro_f1": [round(x, 4) for x in f1_list],
        "per_class_recall_mean": per_class_recall_mean,
        "confusion_matrix": {
            "labels": [str(x) for x in labels_sorted],
            "data": cm.tolist(),
            "note": "跨所有重复的测试折累计混淆矩阵（行=真实，列=预测）",
        },
        "classification_report": report,
        "warnings": sorted(warnings_set),
    }

    logger.info(
        f"[{OPERATOR_ID}] repeats={len(f1_list)}, n={len(y)}, "
        f"acc={result['accuracy_mean']}±{result['accuracy_std']}, "
        f"macroF1={result['macro_f1_mean']}±{result['macro_f1_std']}"
    )

    # ── 评估完成后，用全量数据训练最终模型并保存 ─────────────────────────────
    save_final = str(params.get("save_final_model", "true")).lower() not in ("false", "0", "no")
    if save_final:
        import os, time as _time, uuid, pickle

        # 全量 mRMR
        try:
            final_feat_list = _select_features_mrmr(X, y, k)
        except Exception:
            final_feat_list = list(X.columns)[:k]
        X_final = X[final_feat_list]

        # 全量 SMOTE
        X_final_sm, y_final_sm, _ = _smote_train_only(X_final, y, smote_limit, random_state)

        # 全量训练
        final_clf = RandomForestClassifier(n_estimators=n_estimators, random_state=random_state, n_jobs=-1)
        final_clf.fit(X_final_sm, y_final_sm)

        # 保存到磁盘
        models_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'models')
        os.makedirs(models_dir, exist_ok=True)
        model_id = f"pv_fault_rfc_{int(_time.time())}_{uuid.uuid4().hex[:6]}"
        model_path = os.path.join(models_dir, f"{model_id}.pkl")
        with open(model_path, "wb") as f:
            pickle.dump({"model": final_clf, "feature_list": final_feat_list}, f)

        # 保存评估指标
        import json as _json
        metrics_path = os.path.join(models_dir, f"{model_id}_metrics.json")
        with open(metrics_path, "w", encoding="utf-8") as f:
            _json.dump({
                "accuracy_mean": result["accuracy_mean"],
                "macro_f1_mean": result["macro_f1_mean"],
                "n_samples": result["n_samples"],
                "n_classes": result["n_classes"],
                "class_distribution": result["class_distribution"],
            }, f, ensure_ascii=False, indent=2)

        result["model_id"] = model_id
        result["model_path"] = os.path.abspath(model_path)
        result["feature_list"] = final_feat_list

        logger.info(f"[{OPERATOR_ID}] Final model saved: {model_path} (id={model_id})")

    return result
# @AI_GENERATED: end
