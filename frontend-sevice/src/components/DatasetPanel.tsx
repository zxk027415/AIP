/**
 * DatasetPanel — 数据集管理面板（下拉选择模式）
 * 显示当前数据集，下拉切换，预览按钮，上传入口
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Select, Button, Space, Upload, Modal, Descriptions, Table,
  message, Spin, Typography, Tooltip, Tag, Empty,
} from 'antd';
import {
  DatabaseOutlined, UploadOutlined, EyeOutlined,
} from '@ant-design/icons';
import { datasetApi } from '../services/workflowEnhancedApi';
import type { DatasetFileInfo, DatasetNodeInfo, DatasetPreview } from '../services/workflowEnhancedApi';

const { Text } = Typography;

interface DatasetPanelProps {
  workflowId?: string;
  onDatasetChanged?: () => void;
}

const DatasetPanel: React.FC<DatasetPanelProps> = ({ workflowId, onDatasetChanged }) => {
  const [loading, setLoading] = useState(false);
  const [availableDatasets, setAvailableDatasets] = useState<DatasetFileInfo[]>([]);
  const [currentNodes, setCurrentNodes] = useState<DatasetNodeInfo[]>([]);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewData, setPreviewData] = useState<DatasetPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [switchLoading, setSwitchLoading] = useState(false);

  const loadAvailableDatasets = useCallback(async () => {
    setLoading(true);
    try {
      const res = await datasetApi.listAvailable();
      if (res.success) {
        setAvailableDatasets(res.data);
      }
    } catch (e) {
      console.error('加载数据集列表失败', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCurrentDataset = useCallback(async () => {
    if (!workflowId) return;
    try {
      const res = await datasetApi.getCurrentForWorkflow(workflowId);
      if (res.success) {
        setCurrentNodes(res.data);
      }
    } catch (e) {
      console.error('加载当前数据集失败', e);
    }
  }, [workflowId]);

  useEffect(() => { loadAvailableDatasets(); }, [loadAvailableDatasets]);
  useEffect(() => { loadCurrentDataset(); }, [loadCurrentDataset]);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleSwitch = async (filePath: string) => {
    if (!workflowId) {
      message.warning('请先选择一个工作流模板');
      return;
    }
    setSwitchLoading(true);
    try {
      const res = await datasetApi.switchDataset({
        workflow_id: workflowId,
        file_path: filePath,
      });
      if (res.success) {
        message.success(`已切换数据集: ${filePath.split('/').pop()}`);
        loadCurrentDataset();
        onDatasetChanged?.();
      } else {
        message.error('切换失败');
      }
    } catch (e) {
      message.error('切换请求失败');
    } finally {
      setSwitchLoading(false);
    }
  };

  const handlePreview = async (filePath: string) => {
    setPreviewLoading(true);
    setPreviewVisible(true);
    try {
      const encodedPath = filePath.replace(/\//g, '__');
      const res = await datasetApi.preview(encodedPath, 20);
      if (res.success) {
        setPreviewData(res.data);
      } else {
        message.error('预览失败');
      }
    } catch (e) {
      message.error('预览请求失败');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleUpload = async (file: File) => {
    try {
      const res = await datasetApi.upload(file);
      message.success(`上传成功: ${res.filename}`);
      loadAvailableDatasets();
    } catch (e) {
      message.error('上传失败');
    }
    return false;
  };

  const currentFilePath = currentNodes.length > 0 ? currentNodes[0].file_path : undefined;

  if (!workflowId) {
    return null;
  }

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <DatabaseOutlined style={{ color: '#1677ff' }} />
        <Text strong style={{ fontSize: 13, whiteSpace: 'nowrap' }}>数据集</Text>
        <Select
          style={{ flex: 1, minWidth: 200 }}
          size="small"
          loading={loading || switchLoading}
          value={currentFilePath}
          placeholder="选择数据集"
          onChange={(value) => handleSwitch(value)}
          optionLabelProp="label"
          options={availableDatasets.map(ds => ({
            value: ds.file_path,
            label: ds.file_name,
            item: ds,
          }))}
          optionRender={(option) => {
            const ds = (option.data as { item: DatasetFileInfo }).item;
            return (
              <Space size={4} style={{ width: '100%', justifyContent: 'space-between' }}>
                <span>{ds.file_name}</span>
                <Space size={4}>
                  <Tag style={{ margin: 0, fontSize: 11 }}>{formatSize(ds.size_bytes)}</Tag>
                  {ds.row_count_estimate && (
                    <Tag style={{ margin: 0, fontSize: 11 }}>{ds.row_count_estimate.toLocaleString()} 行</Tag>
                  )}
                  {ds.file_path === currentFilePath && (
                    <Tag color="green" style={{ margin: 0, fontSize: 11 }}>当前</Tag>
                  )}
                </Space>
              </Space>
            );
          }}
        />
        <Tooltip title="预览当前数据集">
          <Button
            size="small"
            icon={<EyeOutlined />}
            disabled={!currentFilePath}
            onClick={() => currentFilePath && handlePreview(currentFilePath)}
          />
        </Tooltip>
        <Upload
          accept=".csv,.xlsx,.xls,.tsv"
          showUploadList={false}
          beforeUpload={(file) => { handleUpload(file); return false; }}
        >
          <Tooltip title="上传新数据集">
            <Button size="small" icon={<UploadOutlined />} />
          </Tooltip>
        </Upload>
      </div>

      {/* 预览弹窗 */}
      <Modal
        title={previewData ? `数据预览: ${previewData.file_path}` : '数据预览'}
        open={previewVisible}
        onCancel={() => { setPreviewVisible(false); setPreviewData(null); }}
        footer={null}
        width={900}
      >
        {previewLoading ? (
          <Spin tip="加载中..." style={{ display: 'block', textAlign: 'center', padding: 40 }} />
        ) : previewData ? (
          <>
            <Descriptions size="small" column={3} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="总行数">{previewData.total_rows?.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="列数">{previewData.columns?.length}</Descriptions.Item>
              {previewData.date_range && (
                <Descriptions.Item label="时间范围">
                  {previewData.date_range.start} ~ {previewData.date_range.end}
                </Descriptions.Item>
              )}
            </Descriptions>
            <Table
              dataSource={previewData.rows}
              columns={previewData.columns.map(col => ({
                title: col,
                dataIndex: col,
                key: col,
                ellipsis: true,
                width: 120,
              }))}
              rowKey={(_, idx) => String(idx)}
              size="small"
              scroll={{ x: previewData.columns.length * 120 }}
              pagination={false}
            />
          </>
        ) : (
          <Empty description="无数据" />
        )}
      </Modal>
    </>
  );
};

export default DatasetPanel;
