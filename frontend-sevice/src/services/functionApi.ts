// @AI_GENERATED
/**
 * functionApi.ts — Backend-status API client for the function/operator library.
 * Calls GET /api/functions/backend-status to discover which operator IDs have
 * real backend implementations and which passed 5-layer + real-data e2e tests.
 */
import api from './api';

export interface BackendStatusResponse {
  /** Total number of operators registered in the Python OperatorRouter */
  total_registered: number;
  /** Sorted list of operator IDs that have a real backend implementation */
  registered_operators: string[];
  /** Operators that passed 5-layer tests AND real-data e2e (subset of registered) */
  verified_operators?: string[];
  /** Count of verified_operators */
  total_verified?: number;
}

/**
 * getBackendStatus — fetch registered / verified operator IDs.
 * Returns BackendStatusResponse on success; throws on network / server error.
 */
export const getBackendStatus = (): Promise<BackendStatusResponse> =>
  api.get('/functions/backend-status');
// @AI_GENERATED: end
