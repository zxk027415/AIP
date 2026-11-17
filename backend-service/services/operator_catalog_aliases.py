"""Catalog function ID → backend OPERATOR_ID aliases (G13.1)."""

from __future__ import annotations

# Keep in sync with frontend-sevice/src/hooks/useBackendReadyOperators.ts
FRONTEND_TO_BACKEND_ALIASES: dict[str, str] = {
    "arima_forecast": "arima",
    "prophet_forecast": "prophet",
    "elastic_net_forecast": "elastic_net",
    "pca_reduce": "pca",
    "pca_reduction": "pca",
    "kmeans_cluster": "kmeans",
    "dbscan_cluster": "dbscan",
    "agglomerative_cluster": "agglomerative_clustering",
    "ocsvm_anomaly": "one_class_svm",
    "dbscan_anomaly": "dbscan",
    "elliptic_envelope_anomaly": "elliptic_envelope",
    "isolation_forest_anomaly": "isolation_forest",
    "lof_anomaly": "lof_detector",
    "elastic_net_regression": "elastic_net",
    "roc_auc_score": "roc_auc",
    "confusion_matrix_eval": "confusion_matrix",
    "f1_metric": "f1_score",
    "accuracy_metric": "accuracy_score",
    "r2_metric": "r2_score",
    "histogram_chart": "histogram",
    "train_test_split": "train_test_split_ts",
    "save_model": "save_model_artifact",
    "load_model": "load_model_artifact",
}


def resolve_backend_operator_id(catalog_id: str) -> str:
    """Return backend operator id for a catalog function id."""
    return FRONTEND_TO_BACKEND_ALIASES.get(catalog_id, catalog_id)


def catalog_has_backend(catalog_id: str, registered: set[str]) -> bool:
    """True when catalog id or its alias is registered in operator_backends."""
    if catalog_id in registered:
        return True
    alias = FRONTEND_TO_BACKEND_ALIASES.get(catalog_id)
    return bool(alias and alias in registered)
