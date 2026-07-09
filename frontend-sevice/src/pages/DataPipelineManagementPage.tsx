import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card, Space, Typography } from 'antd';
import { ApartmentOutlined, ArrowLeftOutlined, DatabaseOutlined } from '@ant-design/icons';
import DataPipelinePanel from '../components/data-management/DataPipelinePanel';

const { Title, Paragraph, Text } = Typography;

const DataPipelineManagementPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div
      style={{
        padding: 24,
        minHeight: '100%',
        background: '#f3f5f8',
      }}
    >
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card
            bordered={false}
            style={{
              borderRadius: 12,
              boxShadow: '0 12px 32px rgba(15, 23, 42, 0.06)',
            }}
          >
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Space align="center" size={12}>
                <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/industry')}>
                  返回行业服务
                </Button>
                <Text type="secondary">行业服务 / 行业数据管理</Text>
              </Space>
              <Space align="center" size={10}>
                <DatabaseOutlined style={{ fontSize: 20, color: '#1677ff' }} />
                <Title level={3} style={{ margin: 0 }}>
                  数据管线管理
                </Title>
              </Space>
              <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 880 }}>
                这里承接原来算法运营中的“数据管线”能力，作为行业数据管理的一部分独立出来。第一阶段只迁移前端入口和展示位置，不改动现有调度器后端接口。
              </Paragraph>
            </Space>
          </Card>

          <Alert
            type="info"
            showIcon
            message="迁移说明"
            description="当前页面复用现有 scheduler API。你在这里启动、停止、查看数据管线，走的仍然是原来后端接口，只是前端入口从算法运营迁移到了行业数据管理。"
          />

          <Card
            title={
              <Space>
                <ApartmentOutlined />
                <span>数据管线运行面板</span>
              </Space>
            }
            bordered={false}
            style={{
              borderRadius: 12,
              boxShadow: '0 12px 32px rgba(15, 23, 42, 0.06)',
            }}
          >
            <DataPipelinePanel />
          </Card>
        </Space>
      </div>
    </div>
  );
};

export default DataPipelineManagementPage;
