import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Alert, Button, Card, Descriptions, Space, Tag, Typography } from 'antd';
import {
  ArrowLeftOutlined,
  DeploymentUnitOutlined,
  RocketOutlined,
} from '@ant-design/icons';

const { Title, Paragraph, Text } = Typography;

const AlgorithmDeploymentPlaceholderPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const workflowId = searchParams.get('workflowId');
  const workflowName = searchParams.get('workflowName');
  const scenarioName = searchParams.get('scenarioName');
  const version = searchParams.get('version');

  return (
    <div
      style={{
        padding: 24,
        minHeight: '100%',
        background: '#f5f7fa',
      }}
    >
      <div style={{ maxWidth: 1040, margin: '0 auto' }}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card
            bordered={false}
            style={{
              borderRadius: 12,
              boxShadow: '0 10px 28px rgba(15, 23, 42, 0.06)',
            }}
          >
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Space align="center" size={12}>
                <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/algorithm-dev/management')}>
                  返回算法管理
                </Button>
                <Tag color="blue" icon={<DeploymentUnitOutlined />}>
                  第七代算法部署入口
                </Tag>
              </Space>
              <Title level={3} style={{ margin: 0 }}>
                算法部署
              </Title>
              <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 760 }}>
                第一阶段只提供部署入口和资产上下文，不改动现有后端部署逻辑。后续这里会逐步补齐预上线、灰度、回滚和生产登记链路。
              </Paragraph>
            </Space>
          </Card>

          <Card
            title="当前待部署资产"
            bordered={false}
            style={{
              borderRadius: 12,
              boxShadow: '0 10px 28px rgba(15, 23, 42, 0.06)',
            }}
          >
            <Descriptions
              column={1}
              size="middle"
              labelStyle={{ width: 120, color: '#64748b' }}
              contentStyle={{ color: '#0f172a', fontWeight: 500 }}
            >
              <Descriptions.Item label="工作流名称">
                {workflowName || '未指定'}
              </Descriptions.Item>
              <Descriptions.Item label="工作流 ID">
                {workflowId || '未指定'}
              </Descriptions.Item>
              <Descriptions.Item label="所属场景">
                {scenarioName || '未指定'}
              </Descriptions.Item>
              <Descriptions.Item label="当前版本">
                {version || '开发版本'}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Alert
            type="info"
            showIcon
            message="当前阶段行为说明"
            description={
              <Space direction="vertical" size={6}>
                <Text>1. 这里先不触发现有部署后端接口。</Text>
                <Text>2. 第一阶段的目标是把第七代算法资产入口和部署上下文串起来。</Text>
                <Text>3. 等 demo 定稿后，再决定哪些状态和动作正式接入现有部署链路。</Text>
              </Space>
            }
          />

          <Card
            bordered={false}
            style={{
              borderRadius: 12,
              boxShadow: '0 10px 28px rgba(15, 23, 42, 0.06)',
            }}
          >
            <Space direction="vertical" size={12}>
              <Title level={5} style={{ margin: 0 }}>
                后续能力规划
              </Title>
              <Space wrap size={[8, 8]}>
                <Tag color="purple">预上线验证</Tag>
                <Tag color="gold">灰度发布</Tag>
                <Tag color="green">生产登记</Tag>
                <Tag color="cyan">版本回滚</Tag>
                <Tag color="processing">运行态监控</Tag>
              </Space>
              <Button
                type="primary"
                icon={<RocketOutlined />}
                onClick={() => navigate('/algorithm-dev/management')}
              >
                返回继续管理算法版本
              </Button>
            </Space>
          </Card>
        </Space>
      </div>
    </div>
  );
};

export default AlgorithmDeploymentPlaceholderPage;
