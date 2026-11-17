// @AI_GENERATED
/**
 * TrainableDatasetPicker — PV slot 工作流下 load_csv 的可训数据下拉 + file_path 联动
 */
import React from 'react';
import { Alert, Form, Input, Select, Space, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { datasetApi, type TrainableDatasetsByKind } from '../../services/workflowEnhancedApi';
import { td } from '../../utils/dataTranslation';

// @AI_GENERATED: pv_tsc 作为第三个可训产品槽，纳入可训数据集选择白名单。
const PV_TRAINABLE_SLOTS = new Set(['pv_day', 'pv_point', 'pv_tsc']);
// @AI_GENERATED: end

interface TrainableDatasetPickerProps {
  workflowSlot?: string;
  form: ReturnType<typeof Form.useForm>[0];
}

const TrainableDatasetPicker: React.FC<TrainableDatasetPickerProps> = ({ workflowSlot, form }) => {
  const normalizedSlot = React.useMemo(() => {
    const raw = String(workflowSlot || '').trim();
    return PV_TRAINABLE_SLOTS.has(raw) ? raw : '';
  }, [workflowSlot]);

  const [trainableDatasets, setTrainableDatasets] = React.useState<TrainableDatasetsByKind | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!normalizedSlot) {
      setTrainableDatasets(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    datasetApi
      .listTrainable(normalizedSlot)
      .then((resp) => {
        if (cancelled) return;
        if (resp?.success && resp.data) {
          setTrainableDatasets(resp.data);
        } else {
          setTrainableDatasets({ labeled_versions: [], cumulative_snapshots: [] });
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTrainableDatasets({ labeled_versions: [], cumulative_snapshots: [] });
        setError(err instanceof Error ? err.message : '加载可训练数据失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [normalizedSlot]);

  const handlePick = (datasetId: string) => {
    if (!trainableDatasets) return;
    const allRows = [
      ...trainableDatasets.labeled_versions,
      ...trainableDatasets.cumulative_snapshots,
    ];
    const row = allRows.find((item) => item.dataset_id === datasetId);
    if (!row) return;
    form.setFieldsValue({
      file_path: row.file_path,
      dataset_id: row.dataset_id,
    });
  };

  const labeled = trainableDatasets?.labeled_versions || [];
  const cumulative = trainableDatasets?.cumulative_snapshots || [];

  const formatLabel = (row: { dataset_id: string; name?: string; is_latest?: boolean }) => {
    const base = row.name || row.dataset_id;
    return row.is_latest ? `${base}（最新）` : base;
  };

  return (
    <>
      {!normalizedSlot ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="当前工作流未设置 pv_day / pv_point / pv_tsc slot"
          description="请使用带 slot 的 PV 训练/评估模板，或先在模板元数据中指定 slot，再从此处选择确认箱或累计训练数据。"
        />
      ) : (
        <>
          {error && (
            <Alert type="warning" showIcon message={error} style={{ marginBottom: 12 }} />
          )}
          <Form.Item name="dataset_id" label="训练数据">
            <Select
              allowClear
              showSearch
              loading={loading}
              placeholder="优先选择累计训练冻结版本"
              optionFilterProp="label"
              onChange={(value) => {
                if (value) handlePick(String(value));
              }}
              options={[
                ...(cumulative.length > 0
                  ? [{
                      label: '累计训练（优先）',
                      options: cumulative.map((row) => ({
                        label: formatLabel(row),
                        value: row.dataset_id,
                      })),
                    }]
                  : []),
                ...(labeled.length > 0
                  ? [{
                      label: '确认箱（单批，不优先）',
                      options: labeled.map((row) => ({
                        label: formatLabel(row),
                        value: row.dataset_id,
                      })),
                    }]
                  : []),
              ]}
            />
          </Form.Item>
        </>
      )}
      <Form.Item
        name="file_path"
        label={(
          <Space size={4}>
            文件路径
            <Tooltip title="从当前 slot 确认箱/累计版本选择，或手动填写相对路径">
              <InfoCircleOutlined style={{ color: '#999' }} />
            </Tooltip>
          </Space>
        )}
        rules={[{ required: true, message: '文件路径为必填项' }]}
      >
        <Input placeholder="相对 backend-service/ 或项目根路径" />
      </Form.Item>
    </>
  );
};

export default TrainableDatasetPicker;
// @AI_GENERATED: end
