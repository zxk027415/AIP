// @AI_GENERATED
/**
 * TscExperimentDetail — TSC 实验详情折叠面板。
 *
 * 展示：窗口配置、样本量、类分布柱状图、per_class_f1 柱状图、混淆矩阵。
 */
import React from 'react';
import { Card, Collapse, Descriptions, Tag } from 'antd';
import ReactECharts from 'echarts-for-react';
import ConfusionMatrixChart from './ConfusionMatrixChart';

interface TscExperimentDetailProps {
  result: Record<string, any>;
}

const TscExperimentDetail: React.FC<TscExperimentDetailProps> = ({ result }) => {
  if (!result || result.status !== 'ok') {
    return null;
  }

  const classDistribution: Record<string, number> = result.class_distribution || {};
  const perClassF1: Record<string, number> = result.per_class_f1 || {};
  const confusionMatrix: number[][] = result.confusion_matrix || [];

  // 类分布柱状图
  const classDistOption = {
    title: { text: '类别分布', left: 'center', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: Object.keys(classDistribution), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const },
    series: [{ type: 'bar', data: Object.values(classDistribution), itemStyle: { color: '#1890ff' } }],
    grid: { top: 40, bottom: 30, left: 50, right: 20 },
  };

  // per_class_f1 柱状图
  const perClassOption = {
    title: { text: '各类别 F1', left: 'center', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: Object.keys(perClassF1), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, max: 1 },
    series: [{ type: 'bar', data: Object.values(perClassF1), itemStyle: { color: '#52c41a' } }],
    grid: { top: 40, bottom: 30, left: 50, right: 20 },
  };

  const labels = Object.keys(classDistribution).map(k => `label_${k}`);

  return (
    <Collapse ghost defaultActiveKey={[]}>
      <Collapse.Panel header="TSC 实验详情" key="detail">
        <Descriptions bordered size="small" column={3} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="窗口长度">{result.window_length} 点</Descriptions.Item>
          <Descriptions.Item label="步长">{result.stride} 点</Descriptions.Item>
          <Descriptions.Item label="样本总数">{result.n_samples}</Descriptions.Item>
          <Descriptions.Item label="训练样本">{result.n_train_samples}</Descriptions.Item>
          <Descriptions.Item label="测试样本">{result.n_test_samples}</Descriptions.Item>
          <Descriptions.Item label="类别数">{result.n_classes}</Descriptions.Item>
          <Descriptions.Item label="训练耗时">{result.train_time_sec?.toFixed(2)}s</Descriptions.Item>
          <Descriptions.Item label="Holdout F1">{result.holdout_macro_f1?.toFixed(4)}</Descriptions.Item>
          <Descriptions.Item label="Holdout Acc">{result.holdout_accuracy?.toFixed(4)}</Descriptions.Item>
        </Descriptions>

        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {Object.keys(classDistribution).length > 0 && (
            <Card size="small" style={{ flex: '1 1 300px' }}>
              <ReactECharts option={classDistOption} style={{ height: 200 }} />
            </Card>
          )}
          {Object.keys(perClassF1).length > 0 && (
            <Card size="small" style={{ flex: '1 1 300px' }}>
              <ReactECharts option={perClassOption} style={{ height: 200 }} />
            </Card>
          )}
        </div>

        {confusionMatrix.length > 0 && (
          <Card size="small" style={{ marginTop: 16 }}>
            <ConfusionMatrixChart matrix={confusionMatrix} labels={labels} />
          </Card>
        )}
      </Collapse.Panel>
    </Collapse>
  );
};

export default TscExperimentDetail;
// @AI_GENERATED: end
