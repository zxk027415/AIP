// @AI_GENERATED: algorithm-deployment-refactor 9.1/9.2/9.3 + 阶段3
/**
 * AlgorithmDeploymentPage.tsx — 算法部署统一入口页面（四 Tab）
 *
 * Tab 列表：
 *   1. 模型管理（?tab=model）  — 生产/影子/预上线三区布局，切换/回滚/配置
 *   2. 数据管线（?tab=pipeline）— 管线启停
 *   3. 定时调度（?tab=scheduler）— cron 可编辑可触发
 *   4. 预上线（?tab=prelaunch）  — 入池/观察进度/手动毕业
 */
import React, { useMemo } from 'react';
import { Card, Space, Tabs, Tag, Typography } from 'antd';
import {
  ApartmentOutlined,
  ClockCircleOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import ModelManagementTab from './deployment/ModelManagementTab';
import PipelineTab from './deployment/PipelineTab';
import SchedulerTab from './deployment/SchedulerTab';
import PrelaunchTab from './deployment/PrelaunchTab';

const { Title, Paragraph } = Typography;

type TabKey = 'model' | 'pipeline' | 'scheduler' | 'prelaunch';
const VALID_TABS: readonly TabKey[] = ['model', 'pipeline', 'scheduler', 'prelaunch'] as const;
const DEFAULT_TAB: TabKey = 'model';

const AlgorithmDeploymentPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const activeTab: TabKey = useMemo(() => {
    const raw = searchParams.get('tab');
    return raw && (VALID_TABS as readonly string[]).includes(raw) ? (raw as TabKey) : DEFAULT_TAB;
  }, [searchParams]);

  const handleTabChange = (key: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', key);
    setSearchParams(next, { replace: false });
  };

  return (
    <div style={{ padding: 24, minHeight: '100%', background: '#f3f5f8' }}>
      <div style={{ maxWidth: 1360, margin: '0 auto' }}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 10px 28px rgba(15,23,42,.06)' }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space align="center" size={12}>
                <RocketOutlined style={{ fontSize: 22, color: '#1677ff' }} />
                <Title level={3} style={{ margin: 0 }}>算法部署</Title>
                <Tag color="blue">模型全生命周期管理</Tag>
              </Space>
              <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 900 }}>
                统一管理模型上线、生产/影子/预上线切换、数据管线和定时调度。
                数据管线和定时调度入口已迁入本页；精度运营（只读健康中心）保持独立页面。
              </Paragraph>
            </Space>
          </Card>

          <Card bordered={false} style={{ borderRadius: 12, boxShadow: '0 10px 28px rgba(15,23,42,.06)' }} bodyStyle={{ padding: '8px 16px 16px' }}>
            <Tabs
              activeKey={activeTab}
              onChange={handleTabChange}
              destroyInactiveTabPane={false}
              items={[
                {
                  key: 'model',
                  label: <Space size={6}><DeploymentUnitOutlined />模型管理</Space>,
                  children: <ModelManagementTab />,
                },
                {
                  key: 'pipeline',
                  label: <Space size={6}><ApartmentOutlined />数据管线</Space>,
                  children: <PipelineTab />,
                },
                {
                  key: 'scheduler',
                  label: <Space size={6}><ClockCircleOutlined />定时调度</Space>,
                  children: <SchedulerTab />,
                },
                {
                  key: 'prelaunch',
                  label: <Space size={6}><ExperimentOutlined />预上线</Space>,
                  children: <PrelaunchTab />,
                },
              ]}
            />
          </Card>
        </Space>
      </div>
    </div>
  );
};

export default AlgorithmDeploymentPage;
// @AI_GENERATED: end
