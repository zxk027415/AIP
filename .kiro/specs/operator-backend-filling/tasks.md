<!-- @AI_GENERATED -->
# Implementation Plan:

## Overview

Implement 27 P0-level operator backends for the AIP platform and add a frontend badge system to visually indicate which operators have real backend implementations. The existing 46 operators will also automatically appear as "ready" in the frontend badge system.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "name": "Wave 1: Infrastructure",
      "tasks": [1, 2]
    },
    {
      "name": "Wave 2: Frontend Badge",
      "tasks": [3]
    },
    {
      "name": "Wave 3: Data Preprocessing Operators",
      "tasks": [4, 5, 6, 7, 8]
    },
    {
      "name": "Wave 4: Feature Engineering & Classification",
      "tasks": [9, 10, 11, 12]
    },
    {
      "name": "Wave 5: Regression & Clustering",
      "tasks": [13, 14, 15, 16, 17]
    },
    {
      "name": "Wave 6: Anomaly Detection & Evaluation",
      "tasks": [18, 19, 20, 21, 22]
    },
    {
      "name": "Wave 7: Visualization & Output",
      "tasks": [23, 24, 25, 26, 27]
    },
    {
      "name": "Wave 8: Time Series & Data Sources",
      "tasks": [28, 29, 30, 31]
    }
  ]
}
```

## Tasks

- [x] 1. Create shared path resolution utility `_path_utils.py`
  - [x] 1.1 Create file `backend-service/services/operator_backends/_path_utils.py` with `resolve_file_path(file_path: str) -> str` function
  - [x] 1.2 Implement search order: workspace_root → aip_dir → backend_dir → cwd (extracted from load_csv.py logic)
  - [x] 1.3 Raise FileNotFoundError with descriptive message if not found; add `# @AI_GENERATED` markers
- [x] 2. Implement Backend Status API endpoint
  - [x] 2.1 Add `GET /api/functions/backend-status` endpoint in `backend-service/api/functions.py` with Pydantic model `BackendStatusResponse`
  - [ ] 2.2 Add lazy-init `_operator_router` with `_ensure_router()` calling `auto_discover()` on first use
  - [x] 2.3 Return `{"total_registered": int, "registered_operators": sorted list}` with HTTPException(500) error handling
- [x] 3. Implement Frontend backend-ready badge and filter
  - [x] 3.1 Create `frontend-sevice/src/services/functionApi.ts` with `getBackendStatus()` calling the backend-status endpoint
  - [x] 3.2 Create `frontend-sevice/src/hooks/useBackendReadyOperators.ts` hook with sessionStorage caching returning `{readySet, total, loading, error}`
  - [x] 3.3 Modify `FunctionLibraryPage.tsx` to display green "可执行" Tag for ready operators and grey "仅定义" for others
  - [x] 3.4 Add filter button group (全部/仅可执行/仅定义) near search input and filter displayed functions accordingly
  - [x] 3.5 Handle API failure with no-badge fallback and console.warn; add i18n keys; verify `npm run build` passes
- [x] 4. Implement min_max_scale operator
  - [x] 4.1 Create `backend-service/services/operator_backends/min_max_scale.py` with OPERATOR_ID and execute function using sklearn MinMaxScaler
  - [x] 4.2 Handle ColumnNotFoundError for missing columns and return empty DataFrame for empty input
- [x] 5. Implement z_score_scale operator
  - [x] 5.1 Create `backend-service/services/operator_backends/z_score_scale.py` using sklearn StandardScaler with same interface as min_max_scale
- [x] 6. Implement column_select operator
  - [x] 6.1 Create `backend-service/services/operator_backends/column_select.py` returning selected columns DataFrame with ColumnNotFoundError handling
- [x] 7. Implement data_merge operator
  - [x] 7.1 Create `backend-service/services/operator_backends/data_merge.py` using pd.merge with join_key and how params on left/right DataFrame inputs
- [x] 8. Implement remove_duplicates operator
  - [x] 8.1 Create `backend-service/services/operator_backends/remove_duplicates.py` using df.drop_duplicates with optional subset param
- [x] 9. Implement pca operator
  - [x] 9.1 Create `backend-service/services/operator_backends/pca.py` using sklearn PCA with n_components param
  - [x] 9.2 Auto-select numeric columns, return PC_1..PC_n DataFrame and explained_variance_ratio, raise ParameterError if n_components exceeds features
- [x] 10. Implement logistic_regression operator
  - [x] 10.1 Create `backend-service/services/operator_backends/logistic_regression.py` following random_forest_classifier train/predict pattern
  - [x] 10.2 Support params mode/C/max_iter; 80/20 holdout eval, full retrain, pickle save to data/models/; raise InputError if < 2 classes
- [x] 11. Implement svm_classifier operator
  - [x] 11.1 Create `backend-service/services/operator_backends/svm_classifier.py` using SVC(probability=True) with kernel/C params and same train/predict pattern
- [x] 12. Implement decision_tree_classifier operator
  - [x] 12.1 Create `backend-service/services/operator_backends/decision_tree_classifier.py` using DecisionTreeClassifier with max_depth/min_samples_split params
- [x] 13. Implement linear_regression operator
  - [x] 13.1 Create `backend-service/services/operator_backends/linear_regression.py` with train/predict pattern returning coefficients and intercept
- [x] 14. Implement lasso_regression operator
  - [x] 14.1 Create `backend-service/services/operator_backends/lasso_regression.py` using sklearn Lasso with alpha param
- [x] 15. Implement elastic_net operator
  - [x] 15.1 Create `backend-service/services/operator_backends/elastic_net.py` using sklearn ElasticNet with alpha and l1_ratio params
- [x] 16. Implement kmeans operator
  - [x] 16.1 Create `backend-service/services/operator_backends/kmeans.py` returning labels, cluster_centers, and inertia with InputError for < 2 samples
- [x] 17. Implement dbscan operator
  - [x] 17.1 Create `backend-service/services/operator_backends/dbscan.py` with eps/min_samples params returning labels and n_clusters_found
- [x] 18. Implement isolation_forest operator
  - [x] 18.1 Create `backend-service/services/operator_backends/isolation_forest.py` with fit_predict/predict dual mode returning labels and scores
- [x] 19. Implement one_class_svm operator
  - [x] 19.1 Create `backend-service/services/operator_backends/one_class_svm.py` with kernel/nu params and same dual-mode pattern as isolation_forest
- [x] 20. Implement r2_score operator
  - [x] 20.1 Create `backend-service/services/operator_backends/r2_score.py` using sklearn r2_score returning score float with InputError for length mismatch
- [x] 21. Implement mape_score operator
  - [x] 21.1 Create `backend-service/services/operator_backends/mape_score.py` computing MAPE manually, excluding zero entries, returning score and excluded_zero_count
- [x] 22. Implement roc_auc operator
  - [x] 22.1 Create `backend-service/services/operator_backends/roc_auc.py` using sklearn roc_auc_score with ovr/macro for multiclass
- [x] 23. Implement line_chart operator
  - [x] 23.1 Create `backend-service/services/operator_backends/line_chart.py` generating ECharts line option from x_column/y_column params
- [x] 24. Implement scatter_chart operator
  - [x] 24.1 Create `backend-service/services/operator_backends/scatter_chart.py` generating ECharts scatter option with same interface as line_chart
- [x] 25. Implement histogram operator
  - [x] 25.1 Create `backend-service/services/operator_backends/histogram.py` using numpy histogram with target_column/bins params generating ECharts bar option
- [x] 26. Implement export_csv operator
  - [x] 26.1 Create `backend-service/services/operator_backends/export_csv.py` writing DataFrame to CSV with auto-generated relative path under data/exports/
- [x] 27. Implement export_excel operator
  - [x] 27.1 Create `backend-service/services/operator_backends/export_excel.py` writing DataFrame to xlsx with openpyxl and same path pattern as export_csv
- [x] 28. Implement arima operator
  - [x] 28.1 Create `backend-service/services/operator_backends/arima.py` using statsmodels ARIMA with p/d/q/forecast_horizon params
  - [x] 28.2 Return forecast and forecast_dates arrays; raise InputError if < 10 data points
- [x] 29. Implement prophet operator
  - [x] 29.1 Create `backend-service/services/operator_backends/prophet.py` with DependencyError if prophet not installed
  - [x] 29.2 Return forecast/forecast_dates/forecast_lower/forecast_upper; raise InputError if < 10 points
- [x] 30. Implement load_parquet operator
  - [x] 30.1 Create `backend-service/services/operator_backends/load_parquet.py` using _path_utils and pd.read_parquet with optional columns projection
- [x] 31. Implement load_json operator
  - [x] 31.1 Create `backend-service/services/operator_backends/load_json.py` using _path_utils and pd.read_json supporting .jsonl with lines=True

## Notes

- All new operator files must include `# @AI_GENERATED` / `# @AI_GENERATED: end` markers.
- All operators follow the pattern: `OPERATOR_ID` constant + `execute(params, inputs) -> dict` function.
- Operators in Waves 3-8 can run in parallel within each wave since they are independent.
- The existing 46 operators already in `operator_backends/` will automatically appear in the backend-status API response and be marked as "ready" in the frontend.
- Model persistence uses relative paths under `backend-service/data/models/`; data exports under `backend-service/data/exports/`.
<!-- @AI_GENERATED: end -->
