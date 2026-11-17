// @AI_GENERATED: Kiro v1.0
/**
 * 迁移差异对比视图 — 左右对比源/目标模板，高亮变更节点
 */
import { useMemo } from 'react';
import {
  Card, Row, Col, Tag, Typography, Progress, Alert, Space, List, Empty,
} from 'antd';
import {
  SwapOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import type { MigrationReport, MigrationAlgorithmReport, CompatibilityCategory } from '../../types/workflow-agent';

const { Text, Title } = Typography;

interface MigrationDiffViewProps {
  report: MigrationReport | null;
}

const CATEGORY_CONFIG: Record<CompatibilityCategory, {
  color: string;
  tagColor: string;
  icon: React.ReactNode;
  label: string;
}> = {
  compatible: {
    color: '#52c41a',
    tagColor: 'success',
    icon: <CheckCircleOutlined />,
    label: '兼容',
  },
  adaptable: {
    color: '#faad14',
    tagColor: 'warning',
    icon: <WarningOutlined />,
    label: '需调整',
  },
  incompatible: {
    color: '#ff4d4f',
    tagColor: 'error',
    icon: <CloseCircleOutlined />,
    label: '不兼容',
  },
};

function AlgorithmItem({ item }: { item: MigrationAlgorithmReport }) {
  const cfg = CATEGORY_CONFIG[item.category];
  return (
    <List.Item>
      <List.Item.Meta
        avatar={<span style={{ color: cfg.color, fontSize: 18 }}>{cfg.icon}</span>}
        title={
          <Space>
            <Text>{item.algorithm_name}</Text>
            <Tag color={cfg.tagColor}>{cfg.label}</Tag>
          </Space>
        }
        description={
          <Space direction="vertical" size={2}>
            <Text type="secondary">{item.reason}</Text>
            {item.replacement_id && (
              <Text>替换为: <Tag color="blue">{item.replacement_id}</Tag></Text>
            )}
          </Space>
        }
      />
    </List.Item>
  );
}

function extractNodeNames(workflow: Record<string, unknown> | undefined): string[] {
  if (!workflow) return [];
  const nodes = (workflow.nodes as { data?: { label?: string; name?: string } }[]) || [];
  return nodes.map((n) => n.data?.label || n.data?.name || '未命名节点');
}

const MigrationDiffView: React.FC<MigrationDiffViewProps> = ({ report }) => {
  if (!report) {
    return <Card size="small"><Empty description="暂无迁移报告" /></Card>;
  }

  const grouped = useMemo(() => {
    const g: Record<CompatibilityCategory, MigrationAlgorithmReport[]> = {
      compatible: [],
      adaptable: [],
      incompatible: [],
    };
    for (const r of report.algorithm_reports) {
      g[r.category].push(r);
    }
    return g;
  }, [report.algorithm_reports]);

  const sourceNodes = extractNodeNames(report.migrated_workflow ?? undefined);
  const confidenceColor =
    report.confidence_score >= 70 ? '#52c41a'
    : report.confidence_score >= 50 ? '#faad14'
    : '#ff4d4f';

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Space>
              <SwapOutlined style={{ fontSize: 20 }} />
              <Title level={5} style={{ margin: 0 }}>
                跨场景迁移: {report.source_scenario_id} → {report.target_scenario_id}
              </Title>
            </Space>
          </Col>
          <Col>
            <Space direction="vertical" align="center" size={0}>
              <Text type="secondary">迁移置信度</Text>
              <Progress
                type="circle"
                percent={report.confidence_score}
                size={64}
                strokeColor={confidenceColor}
                format={(p) => `${p}%`}
              />
            </Space>
          </Col>
        </Row>
      </Card>

      {report.warnings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="迁移警告"
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {report.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          }
        />
      )}

      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Card
            size="small"
            title={<Text>源模板节点 ({sourceNodes.length})</Text>}
          >
            {sourceNodes.length === 0 ? (
              <Empty description="无节点" />
            ) : (
              <Space wrap>
                {sourceNodes.map((name, i) => {
                  const isChanged = report.changes_highlighted.length > 0;
                  return <Tag key={i} color={isChanged ? 'default' : 'blue'}>{name}</Tag>;
                })}
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" title={<Text>算法兼容性分析</Text>}>
            <Space style={{ marginBottom: 8 }}>
              <Tag color="success">{grouped.compatible.length} 兼容</Tag>
              <Tag color="warning">{grouped.adaptable.length} 需调整</Tag>
              <Tag color="error">{grouped.incompatible.length} 不兼容</Tag>
            </Space>
            <List
              size="small"
              dataSource={report.algorithm_reports}
              renderItem={(item) => <AlgorithmItem item={item} />}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default MigrationDiffView;
// @AI_GENERATED: end
