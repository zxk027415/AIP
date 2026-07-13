// @AI_GENERATED
/**
 * RCAReportViewer.tsx — 根因分析报告展示组件
 *
 * 展示完整的 RCA 诊断输出，包含：
 *   1. 报告头部：根因、置信度、触发类型、状态
 *   2. 推理过程（可展开）
 *   3. 支撑证据列表
 *   4. 误差画像（mape_by_hour / mape_by_weekday / worst_windows / error_bias）
 *   5. 数据质量诊断（缺失率、异常值率、特征漂移、数据时效）
 *   6. 可执行建议（按 priority 排序，含折叠证据）
 *
 * Props: { rcaReport: RCAReport | null; loading?: boolean }
 * 相关 spec：accuracy-operations / Task 13.6
 */

import React from 'react';
import {
  Card,
  Progress,
  Tag,
  Badge,
  Typography,
  List,
  Table,
  Descriptions,
  Statistic,
  Collapse,
  Spin,
  Empty,
  Row,
  Col,
  Space,
} from 'antd';
import {
  ExperimentOutlined,
  BulbOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import type {
  RCAReport,
  ActionableInsight,
  InsightType,
  InsightPriority,
  ErrorBias,
  WorstWindow,
  FeatureDriftDetail,
  RCAStatus,
  RCATriggerType,
} from '../../types/accuracy-operations';

const { Text, Paragraph, Title } = Typography;
const { Panel } = Collapse;

// ===========================================================================
// Props
// ===========================================================================

interface RCAReportViewerProps {
  /** rcaReport — 当前展示的 RCA 报告，null 时展示空态提示 */
  rcaReport: RCAReport | null;
  /** loading — 是否正在加载报告 */
  loading?: boolean;
}

// ===========================================================================
// 颜色映射辅助
// ===========================================================================

/** insightTypeColor — 建议类型颜色映射 */
const insightTypeColor: Record<InsightType, string> = {
  feature_engineering: 'purple',
  data_sourcing: 'cyan',
  model_retraining_signal: 'red',
  observation: 'default',
  hyperparameter_hint: 'blue',
};

/** insightTypeLabel — 建议类型中文标签 */
const insightTypeLabel: Record<InsightType, string> = {
  feature_engineering: '特征工程',
  data_sourcing: '数据来源',
  model_retraining_signal: '重训信号',
  observation: '观察',
  hyperparameter_hint: '超参提示',
};

/** priorityBadge — 优先级状态映射 */
const priorityBadge: Record<InsightPriority, { status: 'error' | 'warning' | 'success'; label: string }> = {
  high: { status: 'error', label: '高' },
  medium: { status: 'warning', label: '中' },
  low: { status: 'success', label: '低' },
};

/** errorBiasColor — 误差偏差方向颜色 */
const errorBiasColor: Record<ErrorBias, string> = {
  over_forecast: 'orange',
  under_forecast: 'blue',
  balanced: 'green',
};

/** errorBiasLabel — 误差偏差方向中文 */
const errorBiasLabel: Record<ErrorBias, string> = {
  over_forecast: '高估',
  under_forecast: '低估',
  balanced: '均衡',
};

/** rcaStatusColor — 报告执行状态颜色 */
const rcaStatusColor: Record<RCAStatus, string> = {
  running: 'processing',
  succeeded: 'success',
  failed: 'error',
  timeout: 'warning',
};

/** rcaStatusLabel — 报告执行状态中文 */
const rcaStatusLabel: Record<RCAStatus, string> = {
  running: '运行中',
  succeeded: '成功',
  failed: '失败',
  timeout: '超时',
};

/** triggerTypeLabel — 触发方式中文 */
const triggerTypeLabel: Record<RCATriggerType, string> = {
  scheduled: '定时',
  alert: '告警驱动',
  manual: '手动',
};

/** weekdayLabel — 星期数字 → 中文 */
const weekdayLabel: Record<string, string> = {
  '0': '周一',
  '1': '周二',
  '2': '周三',
  '3': '周四',
  '4': '周五',
  '5': '周六',
  '6': '周日',
};

// ===========================================================================
// 子组件：误差画像 — 24h MAPE 表格
// ===========================================================================

interface MapeHourTableProps {
  /** mapeByHour — 24小时分组 MAPE，key="0"~"23" */
  mapeByHour: Record<string, number>;
}

const MapeHourTable: React.FC<MapeHourTableProps> = ({ mapeByHour }) => {
  // 分两行展示：0-11 和 12-23
  const hours = Array.from({ length: 24 }, (_, i) => String(i));
  const makeColumns = (start: number, end: number) =>
    hours.slice(start, end).map((h) => ({
      title: <Text style={{ fontSize: 11 }}>{`${h}时`}</Text>,
      dataIndex: h,
      key: h,
      width: 52,
      render: (v: number | undefined) => (
        <Text style={{ fontSize: 12 }}>
          {v !== undefined ? (v * 100).toFixed(2) : '—'}
        </Text>
      ),
    }));

  const row1 = hours.slice(0, 12).reduce<Record<string, number>>((acc, h) => {
    acc[h] = mapeByHour[h];
    return acc;
  }, {});
  const row2 = hours.slice(12, 24).reduce<Record<string, number>>((acc, h) => {
    acc[h] = mapeByHour[h];
    return acc;
  }, {});

  return (
    <div style={{ overflowX: 'auto' }}>
      <Text type="secondary" style={{ fontSize: 11 }}>单位：%（已乘100）</Text>
      <Table
        dataSource={[{ key: '0-11', ...row1 }]}
        columns={makeColumns(0, 12)}
        pagination={false}
        size="small"
        style={{ marginTop: 4 }}
        scroll={{ x: true }}
      />
      <Table
        dataSource={[{ key: '12-23', ...row2 }]}
        columns={makeColumns(12, 24)}
        pagination={false}
        size="small"
        style={{ marginTop: 4 }}
        scroll={{ x: true }}
      />
    </div>
  );
};

// ===========================================================================
// 子组件：误差画像 — 7天 MAPE 表格
// ===========================================================================

interface MapeWeekdayTableProps {
  /** mapeByWeekday — 7天分组 MAPE，key="0"(Mon)~"6"(Sun) */
  mapeByWeekday: Record<string, number>;
}

const MapeWeekdayTable: React.FC<MapeWeekdayTableProps> = ({ mapeByWeekday }) => {
  const days = ['0', '1', '2', '3', '4', '5', '6'];
  const columns = days.map((d) => ({
    title: weekdayLabel[d] ?? `Day${d}`,
    dataIndex: d,
    key: d,
    width: 68,
    render: (v: number | undefined) => (
      <Text style={{ fontSize: 12 }}>
        {v !== undefined ? (v * 100).toFixed(2) : '—'}
      </Text>
    ),
  }));

  const row = days.reduce<Record<string, number>>((acc, d) => {
    acc[d] = mapeByWeekday[d];
    return acc;
  }, {});

  return (
    <Table
      dataSource={[{ key: 'weekday', ...row }]}
      columns={columns}
      pagination={false}
      size="small"
      style={{ marginTop: 4 }}
    />
  );
};

// ===========================================================================
// 子组件：误差画像 — 最差时间窗口
// ===========================================================================

const worstWindowColumns = [
  {
    title: '起始时间',
    dataIndex: 'start_time',
    key: 'start_time',
    render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
  },
  {
    title: '结束时间',
    dataIndex: 'end_time',
    key: 'end_time',
    render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
  },
  {
    title: 'MAPE',
    dataIndex: 'mape',
    key: 'mape',
    render: (v: number) => (
      <Text style={{ color: '#f5222d', fontWeight: 600, fontSize: 12 }}>
        {(v * 100).toFixed(2)}%
      </Text>
    ),
  },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    render: (v: string) => <Text style={{ fontSize: 12 }}>{v || '—'}</Text>,
  },
];

// ===========================================================================
// 子组件：数据质量 — 特征漂移详情表格
// ===========================================================================

const driftDetailColumns = [
  {
    title: '特征名',
    dataIndex: 'feature_name',
    key: 'feature_name',
    render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
  },
  {
    title: '漂移幅度',
    dataIndex: 'drift_magnitude',
    key: 'drift_magnitude',
    render: (v: number) => (
      <Text style={{ color: '#fa8c16', fontWeight: 600, fontSize: 12 }}>
        {v.toFixed(4)}
      </Text>
    ),
  },
  {
    title: '漂移方向',
    dataIndex: 'drift_direction',
    key: 'drift_direction',
    render: (v: string) => <Text style={{ fontSize: 12 }}>{v || '—'}</Text>,
  },
];

// ===========================================================================
// 主组件
// ===========================================================================

const RCAReportViewer: React.FC<RCAReportViewerProps> = ({ rcaReport, loading = false }) => {
  // ---------- 加载中 ----------
  if (loading) {
    return (
      <Card title={<><ExperimentOutlined /> 根因分析报告</>}>
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip="加载 RCA 报告…" />
        </div>
      </Card>
    );
  }

  // ---------- 空态 ----------
  if (!rcaReport) {
    return (
      <Card title={<><ExperimentOutlined /> 根因分析报告</>}>
        <Empty description="选中告警并触发RCA后查看分析报告" />
      </Card>
    );
  }

  const {
    root_cause,
    confidence,
    undetermined,
    trigger_type,
    status,
    reasoning,
    supporting_evidence,
    error_profile,
    data_quality_diagnosis,
    actionable_insights,
  } = rcaReport;

  // 可执行建议按优先级排序：high → medium → low
  const priorityOrder: Record<InsightPriority, number> = { high: 0, medium: 1, low: 2 };
  const sortedInsights = [...actionable_insights].sort(
    (a, b) => priorityOrder[a.priority] - priorityOrder[b.priority],
  );

  return (
    <Card
      title={<><ExperimentOutlined /> 根因分析报告</>}
      style={{ marginBottom: 16 }}
    >
      {/* ===== 1. 报告头部 ===== */}
      <div style={{ marginBottom: 20 }}>
        <Space align="start" wrap>
          <Title level={4} style={{ margin: 0 }}>{root_cause}</Title>
          {undetermined && (
            <Badge status="warning" text={<Text type="warning">无法定论</Text>} />
          )}
          <Tag color={rcaStatusColor[status]}>{rcaStatusLabel[status]}</Tag>
          <Tag color="geekblue">{triggerTypeLabel[trigger_type]}</Tag>
        </Space>

        <div style={{ marginTop: 12 }}>
          <Text type="secondary">置信度</Text>
          <Progress
            percent={Math.round(confidence * 100)}
            status={confidence >= 0.6 ? 'normal' : 'exception'}
            style={{ maxWidth: 400, marginTop: 4 }}
            strokeColor={
              confidence >= 0.8
                ? '#52c41a'
                : confidence >= 0.6
                ? '#1677ff'
                : '#ff4d4f'
            }
          />
        </div>
      </div>

      <Collapse ghost defaultActiveKey={['reasoning', 'evidence', 'error_profile', 'data_quality', 'insights']}>
        {/* ===== 2. 推理过程 ===== */}
        {reasoning && (
          <Panel
            header={<Text strong><InfoCircleOutlined /> 推理过程</Text>}
            key="reasoning"
          >
            <Paragraph
              ellipsis={{ rows: 4, expandable: true, symbol: '展开' }}
              style={{ marginBottom: 0 }}
            >
              {reasoning}
            </Paragraph>
          </Panel>
        )}

        {/* ===== 3. 支撑证据 ===== */}
        {supporting_evidence && supporting_evidence.length > 0 && (
          <Panel
            header={<Text strong><DatabaseOutlined /> 支撑证据</Text>}
            key="evidence"
          >
            <List
              size="small"
              dataSource={supporting_evidence}
              renderItem={(item: string) => (
                <List.Item>
                  <Text style={{ fontSize: 13 }}>{item}</Text>
                </List.Item>
              )}
            />
          </Panel>
        )}

        {/* ===== 4. 误差画像 ===== */}
        {error_profile && (
          <Panel
            header={<Text strong><BarChartOutlined /> 误差画像</Text>}
            key="error_profile"
          >
            <Row gutter={16} style={{ marginBottom: 16 }}>
              {/* 误差偏差方向 */}
              <Col span={8}>
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="偏差方向">
                    <Tag color={errorBiasColor[error_profile.error_bias]}>
                      {errorBiasLabel[error_profile.error_bias]}
                    </Tag>
                  </Descriptions.Item>
                </Descriptions>
              </Col>
              {/* 峰谷误差比 */}
              {error_profile.peak_valley_error_ratio !== null && (
                <Col span={8}>
                  <Statistic
                    title="峰谷误差比"
                    value={error_profile.peak_valley_error_ratio.toFixed(3)}
                    suffix="x"
                  />
                </Col>
              )}
            </Row>

            {/* 24h MAPE */}
            {Object.keys(error_profile.mape_by_hour).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ fontSize: 13 }}>24小时 MAPE 分布</Text>
                <MapeHourTable mapeByHour={error_profile.mape_by_hour} />
              </div>
            )}

            {/* 7天 MAPE */}
            {Object.keys(error_profile.mape_by_weekday).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ fontSize: 13 }}>星期 MAPE 分布</Text>
                <MapeWeekdayTable mapeByWeekday={error_profile.mape_by_weekday} />
              </div>
            )}

            {/* 最差时间窗口 */}
            {error_profile.worst_windows && error_profile.worst_windows.length > 0 && (
              <div>
                <Text strong style={{ fontSize: 13 }}>最差时间窗口 (Top {error_profile.worst_windows.length})</Text>
                <Table<WorstWindow>
                  dataSource={error_profile.worst_windows.map((w, i) => ({ ...w, key: i }))}
                  columns={worstWindowColumns}
                  pagination={false}
                  size="small"
                  style={{ marginTop: 4 }}
                />
              </div>
            )}
          </Panel>
        )}

        {/* ===== 5. 数据质量诊断 ===== */}
        {data_quality_diagnosis && (
          <Panel
            header={<Text strong><DatabaseOutlined /> 数据质量诊断</Text>}
            key="data_quality"
          >
            <Row gutter={24} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>缺失率</Text>
                <Progress
                  percent={Math.round(data_quality_diagnosis.missing_rate * 100)}
                  strokeColor={data_quality_diagnosis.missing_rate > 0.1 ? '#f5222d' : '#52c41a'}
                  size="small"
                />
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12 }}>异常值率</Text>
                <Progress
                  percent={Math.round(data_quality_diagnosis.outlier_rate * 100)}
                  strokeColor={data_quality_diagnosis.outlier_rate > 0.05 ? '#fa8c16' : '#52c41a'}
                  size="small"
                />
              </Col>
            </Row>

            <Row gutter={24} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="特征漂移">
                    {data_quality_diagnosis.feature_drift_detected ? (
                      <Badge status="error" text={<Text type="danger">已检测到</Text>} />
                    ) : (
                      <Badge status="success" text={<Text style={{ color: '#52c41a' }}>正常</Text>} />
                    )}
                  </Descriptions.Item>
                </Descriptions>
              </Col>
              <Col span={8}>
                <Statistic
                  title="数据时效滞后"
                  value={data_quality_diagnosis.data_freshness_lag_hours}
                  suffix="小时"
                />
              </Col>
            </Row>

            {/* 特征漂移详情 */}
            {data_quality_diagnosis.feature_drift_detected &&
              data_quality_diagnosis.feature_drift_details.length > 0 && (
              <div>
                <Text strong style={{ fontSize: 13 }}>漂移特征详情</Text>
                <Table<FeatureDriftDetail>
                  dataSource={data_quality_diagnosis.feature_drift_details.map((d, i) => ({
                    ...d,
                    key: i,
                  }))}
                  columns={driftDetailColumns}
                  pagination={false}
                  size="small"
                  style={{ marginTop: 4 }}
                />
              </div>
            )}
          </Panel>
        )}

        {/* ===== 6. 可执行建议 ===== */}
        {sortedInsights.length > 0 && (
          <Panel
            header={
              <Text strong>
                <BulbOutlined /> 可执行建议 ({sortedInsights.length})
              </Text>
            }
            key="insights"
          >
            <List<ActionableInsight>
              dataSource={sortedInsights}
              renderItem={(insight: ActionableInsight) => {
                const { status: badgeStatus, label: badgeLabel } =
                  priorityBadge[insight.priority];
                return (
                  <List.Item style={{ display: 'block', padding: '8px 0' }}>
                    <Card
                      size="small"
                      style={{
                        borderLeft: `3px solid ${
                          insight.priority === 'high'
                            ? '#ff4d4f'
                            : insight.priority === 'medium'
                            ? '#fa8c16'
                            : '#52c41a'
                        }`,
                      }}
                    >
                      <Space style={{ marginBottom: 6 }} wrap>
                        <Tag color={insightTypeColor[insight.insight_type]}>
                          {insightTypeLabel[insight.insight_type]}
                        </Tag>
                        <Badge
                          status={badgeStatus}
                          text={<Text style={{ fontSize: 12 }}>优先级：{badgeLabel}</Text>}
                        />
                      </Space>
                      <Paragraph style={{ marginBottom: insight.supporting_evidence.length > 0 ? 8 : 0 }}>
                        {insight.description}
                      </Paragraph>
                      {insight.supporting_evidence.length > 0 && (
                        <Collapse ghost size="small">
                          <Panel
                            header={
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                查看支撑依据 ({insight.supporting_evidence.length} 条)
                              </Text>
                            }
                            key="evidence"
                          >
                            <List
                              size="small"
                              dataSource={insight.supporting_evidence}
                              renderItem={(ev: string) => (
                                <List.Item>
                                  <Text style={{ fontSize: 12 }}>{ev}</Text>
                                </List.Item>
                              )}
                            />
                          </Panel>
                        </Collapse>
                      )}
                    </Card>
                  </List.Item>
                );
              }}
            />
          </Panel>
        )}
      </Collapse>
    </Card>
  );
};

export default RCAReportViewer;
// @AI_GENERATED: end
