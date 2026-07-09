// @AI_GENERATED: algorithm-deployment-refactor 9.2
/**
 * PipelineTab.tsx — "算法部署 → 数据管线" Tab
 *
 * 用途：
 *   把原来 `DataPipelineManagementPage`（行业数据管理下的入口）承载的核心
 *   数据管线运行面板复用到"算法部署"页面内。核心 UI 直接来自
 *   `components/data-management/DataPipelinePanel`，从而：
 *     - 保持与原有 scheduler API 相同的启动、停止和状态查看行为
 *     - 避免重复实现管线状态查询、失败记录展示、定时任务列表
 *
 * 相关 Requirements：1.1（统一入口）/ 1.2（保持原 API 行为）
 * 相关 tasks.md：9.2
 */
import React from 'react';
import { Alert, Space, Typography } from 'antd';
import DataPipelinePanel from '../../components/data-management/DataPipelinePanel';

const { Text } = Typography;

const PipelineTab: React.FC = () => (
  <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <Alert
      type="info"
      showIcon
      message="数据管线已迁入算法部署"
      description={
        <Text style={{ fontSize: 13 }}>
          本面板复用原 scheduler API：可继续在这里启动/停止 <code>load_forecast</code> 与
          <code>&nbsp;pv_fault</code> 两条管线，并查看各子任务的最近执行结果与失败记录。
          旧路径 <code>/industry-data/pipelines</code> 已重定向到本 Tab。
        </Text>
      }
    />
    <DataPipelinePanel />
  </Space>
);

export default PipelineTab;
// @AI_GENERATED: end
