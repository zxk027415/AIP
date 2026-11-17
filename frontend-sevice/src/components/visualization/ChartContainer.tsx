import React, { useState } from 'react';
import { Card, Select, Button, Space, Tooltip } from 'antd';
import { DownloadOutlined, SettingOutlined } from '@ant-design/icons';
import './ChartContainer.css';

const { Option } = Select;

export type ChartType = 'line' | 'scatter' | 'bar';

export interface ChartConfig {
  title?: string;
  xAxisLabel?: string;
  yAxisLabel?: string;
  color?: string;
  pointSize?: number;
  showLegend?: boolean;
  showGrid?: boolean;
}

interface ChartContainerProps {
  initialType?: ChartType;
  config?: ChartConfig;
  onConfigChange?: (config: ChartConfig) => void;
  children: React.ReactNode;
}

const ChartContainer: React.FC<ChartContainerProps> = ({
  initialType = 'line',
  config = {},
  children,
}) => {
  const [chartType, setChartType] = useState<ChartType>(initialType);
  const [showConfig, setShowConfig] = useState(false);

  const handleTypeChange = (value: ChartType) => {
    setChartType(value);
  };

  const handleExport = () => {
    // 触发ECharts的导出功能
    // 这将由子图表组件处理
    const event = new CustomEvent('chart-export', { detail: { chartType } });
    window.dispatchEvent(event);
  };

  const toggleConfig = () => {
    setShowConfig(!showConfig);
  };

  return (
    <Card
      className="chart-container"
      title={
        <Space>
          <span>数据可视化</span>
          <Select
            value={chartType}
            onChange={handleTypeChange}
            style={{ width: 120 }}
            size="small"
          >
            <Option value="line">折线图</Option>
            <Option value="scatter">散点图</Option>
            <Option value="bar">柱状图</Option>
          </Select>
        </Space>
      }
      extra={
        <Space>
          <Tooltip title="配置">
            <Button
              type="text"
              icon={<SettingOutlined />}
              onClick={toggleConfig}
            />
          </Tooltip>
          <Tooltip title="导出为PNG">
            <Button
              type="text"
              icon={<DownloadOutlined />}
              onClick={handleExport}
            />
          </Tooltip>
        </Space>
      }
    >
      {showConfig && (
        <div className="chart-config-panel">
          {/* 配置面板内容 - 可以根据需要扩展 */}
          <p>图表配置选项</p>
        </div>
      )}
      <div className="chart-content">
        {React.Children.map(children, (child) => {
          if (React.isValidElement(child)) {
            return React.cloneElement(child as React.ReactElement<any>, {
              chartType,
              config,
            });
          }
          return child;
        })}
      </div>
    </Card>
  );
};

export default ChartContainer;
