// @AI_GENERATED
/**
 * useBackendReadyOperators — React hook that fetches the set of operators that
 * have real backend implementations.
 *
 * Caching strategy:
 *   - On mount, immediately reads sessionStorage key `aip:backend-ready-operators`
 *     and returns cached data synchronously (loading=false, readySet populated).
 *   - Then always fires an async fetch to refresh the cache.
 *   - On API failure: if cached data exists it is kept; otherwise readySet stays empty
 *     and error is set. A console.warn is always emitted on failure.
 *
 * Frontend↔Backend ID Alias Handling:
 *   The frontend static catalog (basicModuleFunctions.ts) uses semantic suffixes
 *   like `_forecast`, `_cluster`, `_anomaly`, `_chart`, `_score` because it lists
 *   many variants side-by-side. Backend operators use canonical names without
 *   these suffixes. The `readySet` returned by this hook is the UNION of:
 *     - raw backend IDs (canonical names)
 *     - frontend catalog IDs that alias to a backend ID via FRONTEND_TO_BACKEND_ALIASES
 *   So consumers can just check `readySet.has(fn.id)` regardless of naming scheme.
 *
 * Return shape:
 *   readySet  — Set<string> of operator IDs with real backends (canonical + alias)
 *   total     — total_registered count from the API
 *   loading   — true while the first fetch is in-flight AND no cache exists yet
 *   error     — non-null when the fetch failed AND no cached data was available
 */
import { useState, useEffect } from 'react';
import { getBackendStatus } from '../services/functionApi';

const CACHE_KEY = 'aip:backend-ready-operators';

/**
 * 前端目录 ID → 后端算子 ID 的别名映射。
 *
 * 前端 basicModuleFunctions.ts 用语义后缀区分同一算子的不同用法（预测/回归/聚类/异常），
 * 后端 operator_backends 用规范名。这个映射让徽标能正确显示。
 *
 * 举例：
 *   前端 `arima_forecast`（时序预测子分类下的 ARIMA） → 后端 `arima`
 *   前端 `kmeans_cluster`（聚类子分类下的 K-Means） → 后端 `kmeans`
 *   前端 `histogram_chart`（可视化子分类下的直方图） → 后端 `histogram`
 */
const FRONTEND_TO_BACKEND_ALIASES: Record<string, string> = {
  // ── 时序预测子分类 ──
  arima_forecast: 'arima',
  prophet_forecast: 'prophet',
  elastic_net_forecast: 'elastic_net',
  // ── 降维子分类 ──
  pca_reduce: 'pca',
  pca_reduction: 'pca',
  // ── 聚类子分类 ──
  kmeans_cluster: 'kmeans',
  dbscan_cluster: 'dbscan',
  agglomerative_cluster: 'agglomerative_clustering',
  // ── 异常检测子分类 ──
  ocsvm_anomaly: 'one_class_svm',
  dbscan_anomaly: 'dbscan',
  elliptic_envelope_anomaly: 'elliptic_envelope',
  isolation_forest_anomaly: 'isolation_forest',
  lof_anomaly: 'lof_detector',
  // ── 回归子分类 ──
  elastic_net_regression: 'elastic_net',
  // ── 评估指标（含"工业模板评估指标"子分类的 *_metric 命名）──
  roc_auc_score: 'roc_auc',
  confusion_matrix_eval: 'confusion_matrix',
  f1_metric: 'f1_score',
  accuracy_metric: 'accuracy_score',
  r2_metric: 'r2_score',
  // ── 可视化 ──
  histogram_chart: 'histogram',
  // ── 模型管理（train_model 子分类）──
  train_test_split: 'train_test_split_ts',
  save_model: 'save_model_artifact',
  load_model: 'load_model_artifact',
};

interface CacheShape {
  total_registered: number;
  registered_operators: string[];
}

export interface BackendReadyState {
  readySet: Set<string>;
  total: number;
  loading: boolean;
  error: unknown;
}

const parseCached = (): CacheShape | null => {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as CacheShape;
  } catch {
    return null;
  }
};

/**
 * 把后端 ID 集合 + 别名映射 合并成一个包含所有"可执行"标识的集合。
 * 例如后端返回 ["arima", "kmeans", ...]，前端目录里 "arima_forecast" 也算命中。
 */
const buildReadySet = (backendIds: string[]): Set<string> => {
  const set = new Set(backendIds);
  const backendSet = new Set(backendIds);
  for (const [frontendId, backendId] of Object.entries(FRONTEND_TO_BACKEND_ALIASES)) {
    if (backendSet.has(backendId)) {
      set.add(frontendId);
    }
  }
  return set;
};

const useBackendReadyOperators = (): BackendReadyState => {
  // Initialise synchronously from cache so the first render is instant
  const cached = parseCached();
  const [readySet, setReadySet] = useState<Set<string>>(
    () => buildReadySet(cached?.registered_operators ?? []),
  );
  const [total, setTotal] = useState<number>(cached?.total_registered ?? 0);
  // loading=true only when there is no cache yet
  const [loading, setLoading] = useState<boolean>(cached === null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchStatus = async () => {
      try {
        const data = await getBackendStatus();
        if (cancelled) return;
        // Persist to sessionStorage for next mount within this browser session
        try {
          sessionStorage.setItem(
            CACHE_KEY,
            JSON.stringify({
              total_registered: data.total_registered,
              registered_operators: data.registered_operators,
            }),
          );
        } catch {
          // sessionStorage quota exceeded — ignore, in-memory state is still valid
        }
        setReadySet(buildReadySet(data.registered_operators));
        setTotal(data.total_registered);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        console.warn(
          '[useBackendReadyOperators] Failed to fetch backend status — badges will be hidden.',
          err,
        );
        // Only surface the error to callers when there was no cached fallback
        if (parseCached() === null) {
          setError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  return { readySet, total, loading, error };
};

export default useBackendReadyOperators;
// @AI_GENERATED: end
