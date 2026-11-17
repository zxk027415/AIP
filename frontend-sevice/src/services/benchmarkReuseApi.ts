/**
 * benchmarkReuseApi.ts — G6.5 / G7 benchmark graph reuse evidence report
 */
import api from './api';

export interface BenchmarkReuseReport {
  report_id: string;
  generated_at: string;
  slots: string[];
  reuse_conclusion: {
    same_visible_operator_graph: boolean;
    expected_changes: string[];
    product_governance_writes_blocked: boolean;
    subgraph_used: boolean;
  };
  workflow_comparison: {
    graph_reuse_proven: boolean;
    roles: Record<
      string,
      {
        graph_signature_match: boolean;
        workflow_ids: Record<string, string>;
        operator_ids: Record<string, string[]>;
      }
    >;
  };
  profiles: Record<
    string,
    {
      profile_id: string;
      clock_mode: string;
      preflight: { ready: boolean; row_count?: number };
      license_status?: string;
    }
  >;
  governance_evidence: {
    execution_purpose: string;
    governance_eligible: boolean;
  };
}

export const benchmarkReuseApi = {
  getReuseReport: (slots?: string[]): Promise<{ success: boolean; report: BenchmarkReuseReport }> =>
    api.get('/benchmark/reuse-report', {
      params: slots?.length ? { slots: slots.join(',') } : undefined,
    }),

  getReuseStory: (): Promise<{ success: boolean; story: G8ReuseStory }> =>
    api.get('/benchmark/reuse-story'),
};

export interface G8ReuseStory {
  story_id: string;
  generated_at: string;
  product_slots: string[];
  benchmark_slots: string[];
  reuse_conclusion: {
    same_visible_operator_graph?: boolean;
    pvdaq_unlabeled_no_fake_metrics?: boolean;
    product_governance_writes_blocked?: boolean;
    labeled_benchmarks?: string[];
    unlabeled_benchmarks?: string[];
  };
  profiles: Record<string, { profile_id: string; label_semantics?: string; preflight: { ready: boolean } }>;
}
