import React from 'react';
import { Button, Dropdown, message } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';

interface ChartExporterProps {
  chartRef: React.RefObject<any>;
  filename?: string;
}

const ChartExporter: React.FC<ChartExporterProps> = ({
  chartRef,
  filename = 'chart',
}) => {
  const exportToPNG = () => {
    if (!chartRef.current) {
      message.error('图表未加载');
      return;
    }

    try {
      const echartInstance = chartRef.current.getEchartsInstance();
      const url = echartInstance.getDataURL({
        type: 'png',
        pixelRatio: 2,
        backgroundColor: '#fff',
      });

      const link = document.createElement('a');
      link.href = url;
      link.download = `${filename}.png`;
      link.click();

      message.success('导出成功');
    } catch (error) {
      message.error('导出失败');
      console.error('Export error:', error);
    }
  };

  const exportToSVG = () => {
    if (!chartRef.current) {
      message.error('图表未加载');
      return;
    }

    try {
      const echartInstance = chartRef.current.getEchartsInstance();
      const url = echartInstance.getDataURL({
        type: 'svg',
        backgroundColor: '#fff',
      });

      const link = document.createElement('a');
      link.href = url;
      link.download = `${filename}.svg`;
      link.click();

      message.success('导出成功');
    } catch (error) {
      message.error('导出失败');
      console.error('Export error:', error);
    }
  };

  const exportToCSV = () => {
    if (!chartRef.current) {
      message.error('图表未加载');
      return;
    }

    try {
      const echartInstance = chartRef.current.getEchartsInstance();
      const option = echartInstance.getOption();
      
      // 提取数据
      const series = option.series[0];
      const data = series.data;

      if (!data || data.length === 0) {
        message.error('没有可导出的数据');
        return;
      }

      // 转换为CSV格式
      let csv = '';
      
      if (Array.isArray(data[0])) {
        // 二维数据
        csv = 'X,Y\n';
        data.forEach((point: any) => {
          csv += `${point[0]},${point[1]}\n`;
        });
      } else if (typeof data[0] === 'object') {
        // 对象数据
        const keys = Object.keys(data[0]);
        csv = keys.join(',') + '\n';
        data.forEach((item: any) => {
          csv += keys.map(key => item[key]).join(',') + '\n';
        });
      } else {
        // 一维数据
        csv = 'Index,Value\n';
        data.forEach((value: any, index: number) => {
          csv += `${index},${value}\n`;
        });
      }

      // 下载CSV
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${filename}.csv`;
      link.click();
      URL.revokeObjectURL(url);

      message.success('导出成功');
    } catch (error) {
      message.error('导出失败');
      console.error('Export error:', error);
    }
  };

  const items: MenuProps['items'] = [
    {
      key: 'png',
      label: '导出为 PNG',
      onClick: exportToPNG,
    },
    {
      key: 'svg',
      label: '导出为 SVG',
      onClick: exportToSVG,
    },
    {
      key: 'csv',
      label: '导出数据为 CSV',
      onClick: exportToCSV,
    },
  ];

  return (
    <Dropdown menu={{ items }} placement="bottomRight">
      <Button icon={<DownloadOutlined />}>
        导出
      </Button>
    </Dropdown>
  );
};

export default ChartExporter;
