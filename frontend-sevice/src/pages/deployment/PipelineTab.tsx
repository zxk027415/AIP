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

interface PipelineTabProps {
  /** storySlot — 当前部署页选中槽位，用于只展示对应管线 */
  storySlot?: string;
}

const PipelineTab: React.FC<PipelineTabProps> = ({ storySlot }) => {
  const isPv = storySlot === 'pv_fault';
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message={isPv ? '光伏故障诊断数据管线' : '负荷预测数据管线'}
        description={
          <Text style={{ fontSize: 13 }}>
            {isPv ? (
              <>
                本槽位仅管理 <code>pv_fault</code> 管线：模拟喂数据 → 故障预测。
                数据由 mock feeder 直写 <code>training_samples</code>，不再使用独立的数据拉取任务。
              </>
            ) : (
              <>
                本槽位仅管理 <code>load_forecast</code> 管线：数据拉取 → 滚动训练+预测 → 精度回填与监控。
                旧路径 <code>/industry-data/pipelines</code> 已重定向到本 Tab。
              </>
            )}
          </Text>
        }
      />
      <DataPipelinePanel storySlot={storySlot} />
    </Space>
  );
};

export default PipelineTab;
// @AI_GENERATED: end
