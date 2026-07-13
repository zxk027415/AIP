// @AI_GENERATED
/**
 * AccuracyOperationsPage.tsx — 精度运营主页面
 *
 * 组合 ModelLifecycleCard、MonitoringPanel、AlertPanel 三个子面板，
 * 顶部提供 slot 选择器（默认 "default"）。切换 slot 时同步拉取所有子面板数据。
 *
 * 相关 spec：.kiro/specs/accuracy-operations/
 *   - Requirements 10.1（主页面入口）
 *   - Requirements 10.7（slot 切换）
 *   - Requirements 10.8（各面板独立错误处理）
 *   - Task 13.1
 */

import React, { useEffect } from 'react';
import { Card, Select, Typography, Row, Col } from 'antd';
import { useAccuracyOperationsStore } from '../stores/accuracyOperationsStore';
import ModelLifecycleCard from './accuracy-operations/ModelLifecycleCard';
import MonitoringPanel from './accuracy-operations/MonitoringPanel';
import AlertPanel from './accuracy-operations/AlertPanel';
import type { AccuracyAlert } from '../types/accuracy-operations';

const { Title } = Typography;

// ===========================================================================
// 可选 Slot 列表（可按需扩展）
// ===========================================================================

const SLOT_OPTIONS = [
  { label: 'default（默认槽）', value: 'default' },
  { label: 'load_forecast（负荷预测）', value: 'load_forecast' },
];

// ===========================================================================
// 组件
// ===========================================================================

/**
 * AccuracyOperationsPage — 精度运营主页面
 *
 * 布局说明：
 *   - 顶部：Slot 选择器
 *   - Row 1（全宽）：ModelLifecycleCard
 *   - Row 2（左右各半）：MonitoringPanel | AlertPanel
 *   - Row 3（全宽）：RCA 报告占位卡片（Task 13.6 实现后替换）
 */
const AccuracyOperationsPage: React.FC = () => {
  const { currentSlot, setCurrentSlot, fetchOverview, fetchAlerts, fetchMonitoringSnapshot, fetchLifecycle } =
    useAccuracyOperationsStore();

  // 挂载时拉取所有数据
  useEffect(() => {
    fetchOverview(currentSlot);
    fetchAlerts(currentSlot);
    fetchMonitoringSnapshot(currentSlot);
    fetchLifecycle(currentSlot);
  }, [currentSlot, fetchOverview, fetchAlerts, fetchMonitoringSnapshot, fetchLifecycle]);

  /** handleSlotChange — slot 变更时更新 store 并触发重新拉取 */
  const handleSlotChange = (value: string) => {
    setCurrentSlot(value);
    // useEffect 依赖 currentSlot，会在下一渲染周期自动触发 fetch
  };

  /** handleSelectAlert — AlertPanel 行点击回调（预留给 RCAReportViewer） */
  const handleSelectAlert = (_alert: AccuracyAlert) => {
    // Task 13.6 RCAReportViewer 实现后，在此更新 selectedAlert
    useAccuracyOperationsStore.getState().setSelectedAlert(_alert);
  };

  return (
    <div
      style={{ padding: '24px', maxWidth: '1600px', margin: '0 auto' }}
      aria-label="精度运营页面"
    >
      {/* ---- 页面标题 + Slot 选择器 ---- */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '20px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          精度运营
        </Title>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '13px', color: '#666' }}>槽位：</span>
          <Select<string>
            value={currentSlot}
            onChange={handleSlotChange}
            options={SLOT_OPTIONS}
            style={{ width: 220 }}
            showSearch
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
            aria-label="选择操作槽位"
          />
        </div>
      </div>

      {/* ---- Row 1：模型生命周期（全宽） ---- */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col span={24}>
          <ModelLifecycleCard slot={currentSlot} />
        </Col>
      </Row>

      {/* ---- Row 2：精度监控 | 精度告警（左右各半） ---- */}
      <Row gutter={[16, 16]} style={{ marginBottom: '16px' }}>
        <Col xs={24} lg={12}>
          <MonitoringPanel slot={currentSlot} />
        </Col>
        <Col xs={24} lg={12}>
          <AlertPanel slot={currentSlot} onSelectAlert={handleSelectAlert} />
        </Col>
      </Row>

      {/* ---- Row 3：RCA 报告占位（Task 13.6 实现后替换） ---- */}
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card
            aria-label="RCA 报告查看区域"
            style={{ minHeight: '120px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          >
            <span style={{ color: '#bbb', fontSize: '14px' }}>
              选中告警后查看 RCA 报告
            </span>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default AccuracyOperationsPage;
// @AI_GENERATED: end
