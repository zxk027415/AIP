// @AI_GENERATED
/**
 * functionApi.ts — Backend-status API client for the function/operator library.
 * Calls GET /api/functions/backend-status to discover which operator IDs have
 * real backend implementations registered on the Python side.
 */
import api from './api';

export interface BackendStatusResponse {
  /** Total number of operators registered in the Python OperatorRouter */
  total_registered: number;
  /** Sorted list of operator IDs that have a real backend implementation */
  registered_operators: string[];
}

/**
 * getBackendStatus — fetch the set of operators that have real backend implementations.
 * Returns BackendStatusResponse on success; throws on network / server error.
 */
export const getBackendStatus = (): Promise<BackendStatusResponse> =>
  api.get('/functions/backend-status');
// @AI_GENERATED: end
