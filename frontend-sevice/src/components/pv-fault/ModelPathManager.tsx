// @AI_GENERATED
/**
 * ModelPathManager — 生产/备用路径展示与切换操作。
 *
 * 展示当前 production_path 和 fallback_path。
 * 提供切换按钮（二次确认弹窗）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, Input, Modal, Space, Tag, message } from 'antd';
import { SwapOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { cumulativeTrainingApi } from '../../services/iterativeLabelingApi';

interface ModelPathManagerProps {
  slot?: string;
}

const ModelPathManager: React.FC<ModelPathManagerProps> = ({ slot = 'pv_fault' }) => {
  const [paths, setPaths] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [switchModalOpen, setSwitchModalOpen] = useState(false);
  const [switchReason, setSwitchReason] = useState('');
  const [switching, setSwitching] = useState(false);

  const loadPaths = useCallback(async () => {
    setLoading(true);
    try {
      const data = await cumulativeTrainingApi.getModelingPaths(slot);
      setPaths(data);
    } catch {
      // 可能 404（尚未配置）
      setPaths(null);
    } finally {
      setLoading(false);
    }
  }, [slot]);

  useEffect(() => { void loadPaths(); }, [loadPaths]);

  const handleSwitch = async () => {
    if (!switchReason.trim()) {
      message.warning('请输入切换原因');
      return;
    }
    setSwitching(true);
    try {
      await cumulativeTrainingApi.switchModelingFallback(switchReason.trim(), slot);
      message.success('已切换到备用路径');
      setSwitchModalOpen(false);
      setSwitchReason('');
      await loadPaths();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '切换失败');
    } finally {
      setSwitching(false);
    }
  };

  const productionPath = (paths as any)?.production_path || '未配置';
  const fallbackPath = (paths as any)?.fallback_path || '未配置';

  return (
    <Card
      size="small"
      title={<Space><SafetyCertificateOutlined /> 建模路径管理</Space>}
      loading={loading}
      style={{ marginBottom: 16 }}
    >
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="生产路径">
          <Tag color="green">{productionPath}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="备用路径">
          <Tag color="orange">{fallbackPath}</Tag>
        </Descriptions.Item>
      </Descriptions>

      <div style={{ marginTop: 12, textAlign: 'right' }}>
        <Button
          icon={<SwapOutlined />}
          onClick={() => setSwitchModalOpen(true)}
          disabled={!paths || fallbackPath === '未配置'}
        >
          切换到备用路径
        </Button>
      </div>

      <Modal
        title="切换到备用路径"
        open={switchModalOpen}
        onOk={handleSwitch}
        onCancel={() => setSwitchModalOpen(false)}
        confirmLoading={switching}
        okText="确认切换"
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`将把生产路径从「${productionPath}」切换为「${fallbackPath}」`}
          description="切换后新预测将使用备用路径的模型。请确认备用路径精度满足要求。"
        />
        <Input.TextArea
          placeholder="切换原因（必填）"
          value={switchReason}
          onChange={e => setSwitchReason(e.target.value)}
          rows={2}
        />
      </Modal>
    </Card>
  );
};

export default ModelPathManager;
// @AI_GENERATED: end
