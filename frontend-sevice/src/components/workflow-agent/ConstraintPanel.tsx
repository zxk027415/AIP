// @AI_GENERATED: Kiro v1.0
/**
 * 约束可视化面板 — 展示当前模板的业务约束及合规状态
 */
import { useState, useEffect } from 'react';
import {
  Card, Table, Tag, Space, Typography, Spin, Empty, Tooltip,
} from 'antd';
import {
  CheckCircleOutlined,
  WarningOutlined,
  QuestionCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { workflowAgentApi } from '../../services/workflowAgentApi';
import type { DomainConstraintResponse } from '../../types/workflow-agent';

const { Text, Title } = Typography;

interface ConstraintPanelProps {
  scenarioId?: string;
  workflowParams?: Record<string, unknown>;
}

type ComplianceStatus = 'compliant' | 'violation' | 'unchecked';

interface ConstraintRow {
  key: string;
  paramName: string;
  constraintType: string;
  constraintValue: string;
  currentValue: string;
  status: ComplianceStatus;
}

const STATUS_CONFIG: Record<ComplianceStatus, { color: string; icon: React.ReactNode; label: string }> = {
  compliant: { color: 'success', icon: <CheckCircleOutlined />, label: '合规' },
  violation: { color: 'error', icon: <WarningOutlined />, label: '违规' },
  unchecked: { color: 'default', icon: <QuestionCircleOutlined />, label: '未检查' },
};

function checkCompliance(
  paramName: string,
  constraint: Record<string, unknown>,
  workflowParams?: Record<string, unknown>,
): { status: ComplianceStatus; currentValue: string } {
  if (!workflowParams || !(paramName in workflowParams)) {
    return { status: 'unchecked', currentValue: '-' };
  }
  const val = workflowParams[paramName];
  const currentValue = String(val);
  const min = constraint.min as number | undefined;
  const max = constraint.max as number | undefined;

  if (typeof val === 'number' && min !== undefined && max !== undefined) {
    return {
      status: val >= min && val <= max ? 'compliant' : 'violation',
      currentValue,
    };
  }
  return { status: 'unchecked', currentValue };
}

function buildRows(
  data: DomainConstraintResponse | null,
  workflowParams?: Record<string, unknown>,
): ConstraintRow[] {
  if (!data) return [];
  const rows: ConstraintRow[] = [];
  const pc = data.parameter_constraints as Record<string, Record<string, unknown>> | undefined;
  if (!pc) return rows;

  for (const [paramName, constraint] of Object.entries(pc)) {
    const { status, currentValue } = checkCompliance(paramName, constraint, workflowParams);
    rows.push({
      key: paramName,
      paramName,
      constraintType: String(constraint.type ?? 'range'),
      constraintValue: constraint.min !== undefined && constraint.max !== undefined
        ? `[${constraint.min}, ${constraint.max}]`
        : JSON.stringify(constraint),
      currentValue,
      status,
    });
  }
  return rows;
}

const columns = [
  {
    title: '参数',
    dataIndex: 'paramName',
    key: 'paramName',
    render: (v: string) => <Text strong>{v}</Text>,
  },
  {
    title: '约束类型',
    dataIndex: 'constraintType',
    key: 'constraintType',
    render: (v: string) => <Tag>{v}</Tag>,
  },
  {
    title: '约束范围',
    dataIndex: 'constraintValue',
    key: 'constraintValue',
  },
  {
    title: '当前值',
    dataIndex: 'currentValue',
    key: 'currentValue',
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    render: (s: ComplianceStatus) => {
      const cfg = STATUS_CONFIG[s];
      return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>;
    },
  },
];

const ConstraintPanel: React.FC<ConstraintPanelProps> = ({ scenarioId, workflowParams }) => {
  const [data, setData] = useState<DomainConstraintResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scenarioId) return;
    setLoading(true);
    setError(null);
    workflowAgentApi
      .queryConstraints(scenarioId)
      .then((res) => setData(res))
      .catch((e) => setError(e?.message || '加载约束失败'))
      .finally(() => setLoading(false));
  }, [scenarioId]);

  if (!scenarioId) {
    return <Card size="small"><Empty description="请先选择场景" /></Card>;
  }

  if (loading) {
    return <Card size="small"><Spin tip="加载约束..." /></Card>;
  }

  if (error) {
    return <Card size="small"><Text type="danger">{error}</Text></Card>;
  }

  const rows = buildRows(data, workflowParams);

  return (
    <Card
      size="small"
      title={
        <Space>
          <SafetyCertificateOutlined />
          <span>业务约束 — {data?.scenario_name || scenarioId}</span>
        </Space>
      }
      extra={
        data?.evaluation_metrics?.length ? (
          <Tooltip title="评估指标">
            <Space size={4}>
              {data.evaluation_metrics.map((m) => (
                <Tag key={m} color="blue">{m}</Tag>
              ))}
            </Space>
          </Tooltip>
        ) : null
      }
    >
      {rows.length === 0 ? (
        <Empty description="暂无约束数据" />
      ) : (
        <Table
          columns={columns}
          dataSource={rows}
          pagination={false}
          size="small"
          rowClassName={(r) => r.status === 'violation' ? 'ant-table-row-danger' : ''}
        />
      )}
      {data?.business_rules && data.business_rules.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Title level={5}>业务规则</Title>
          {data.business_rules.map((rule, i) => (
            <Tag
              key={i}
              color={rule.severity === 'error' ? 'red' : rule.severity === 'warning' ? 'orange' : 'blue'}
              style={{ marginBottom: 4 }}
            >
              {rule.rule || rule.description || JSON.stringify(rule)}
            </Tag>
          ))}
        </div>
      )}
    </Card>
  );
};

export default ConstraintPanel;
// @AI_GENERATED: end
