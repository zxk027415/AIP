/**
 * BenchmarkReuseReportPanel — G7 最小 UI：展示 G6.5 跨数据集 graph 复用证据。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Space, Spin, Tag, Typography } from 'antd';
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { benchmarkReuseApi, type BenchmarkReuseReport, type G8ReuseStory } from '../../services/benchmarkReuseApi';
import { BENCHMARK_SLOTS } from '../../config/slotProductConfig';

const { Text, Paragraph } = Typography;

interface Props {
  refreshKey?: number;
}

const BenchmarkReuseReportPanel: React.FC<Props> = ({ refreshKey = 0 }) => {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<BenchmarkReuseReport | null>(null);
  const [story, setStory] = useState<G8ReuseStory | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [reportResp, storyResp] = await Promise.all([
        benchmarkReuseApi.getReuseReport([...BENCHMARK_SLOTS]),
        benchmarkReuseApi.getReuseStory(),
      ]);
      setReport(reportResp.report);
      setStory(storyResp.story);
    } catch (err: any) {
      setReport(null);
      setStory(null);
      setError(err?.response?.data?.detail || err?.message || '加载复用报告失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const trainRole = report?.workflow_comparison?.roles?.train_eval;
  const graphOk = report?.reuse_conclusion?.same_visible_operator_graph;

  return (
    <Card
      title={
        <Space>
          <SafetyCertificateOutlined />
          <span>G6.5 Benchmark 复用证据</span>
          {graphOk === true && <Tag color="success">graph 一致</Tag>}
          {graphOk === false && <Tag color="warning">graph 有差异</Tag>}
        </Space>
      }
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新报告
        </Button>
      }
    >
      <Spin spinning={loading}>
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
        {!report && !error && !loading && (
          <Text type="secondary">暂无报告</Text>
        )}
        {report && (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              对比 NASA 与 FHC 的可见算子/连线；仅 profile/source/clock 允许不同；产品治理写入应全部为 0。
            </Paragraph>
            <Descriptions size="small" bordered column={1}>
              <Descriptions.Item label="report_id">{report.report_id}</Descriptions.Item>
              <Descriptions.Item label="generated_at">{report.generated_at}</Descriptions.Item>
              <Descriptions.Item label="execution_purpose">
                {report.governance_evidence.execution_purpose}
              </Descriptions.Item>
              <Descriptions.Item label="governance_eligible">
                {String(report.governance_evidence.governance_eligible)}
              </Descriptions.Item>
              <Descriptions.Item label="train_eval graph 一致">
                {trainRole?.graph_signature_match ? '是' : '否'}
              </Descriptions.Item>
            </Descriptions>
            {story && (
              <Alert
                type="success"
                showIcon
                message="G8 复用故事"
                description={
                  <Space direction="vertical" size={4}>
                    <Text>story_id: {story.story_id}</Text>
                    <Text>
                      无标签 PVDAQ：
                      {story.reuse_conclusion.pvdaq_unlabeled_no_fake_metrics ? ' 通过（无伪造金标）' : ' 未通过'}
                    </Text>
                    <Text>
                      有标签 benchmark：{(story.reuse_conclusion.labeled_benchmarks ?? []).join(', ') || '—'}
                    </Text>
                    <Text>
                      无标签 benchmark：{(story.reuse_conclusion.unlabeled_benchmarks ?? []).join(', ') || '—'}
                    </Text>
                  </Space>
                }
              />
            )}
            {report.slots.map((slot) => {
              const profile = report.profiles[slot];
              const ops = trainRole?.operator_ids?.[slot]?.join(', ') || '—';
              return (
                <Alert
                  key={slot}
                  type="info"
                  showIcon
                  message={slot}
                  description={
                    <Space direction="vertical" size={4}>
                      <Text>profile: {profile?.profile_id} · clock={profile?.clock_mode}</Text>
                      <Text>preflight ready: {String(profile?.preflight?.ready)} · rows={profile?.preflight?.row_count ?? '—'}</Text>
                      <Text>operators: {ops}</Text>
                    </Space>
                  }
                />
              );
            })}
          </Space>
        )}
      </Spin>
    </Card>
  );
};

export default BenchmarkReuseReportPanel;
