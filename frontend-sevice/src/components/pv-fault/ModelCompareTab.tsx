// @AI_GENERATED
/**
 * ModelCompareTab — 模型对比 Tab 主组件。
 *
 * 功能：
 * 1. 精度对比表（Ant Design Table）：模型名、macro_F1、accuracy、训练耗时、状态
 * 2. 高亮最佳模型行
 * 3. TSC > RF + 2% 时顶部 Alert
 * 4. 「▶ 启动对比」按钮 → 配置弹窗
 * 5. 实验进行中时进度条
 * 6. 集成 ModelPathManager 和 TscExperimentDetail
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  InputNumber,
  Modal,
  Progress,
  Radio,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  ExperimentOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  TrophyOutlined,
} from '@ant-design/icons';
import { tscExperimentApi } from '../../services/iterativeLabelingApi';
import ModelPathManager from './ModelPathManager';
import TscExperimentDetail from './TscExperimentDetail';

const { Text } = Typography;

interface ModelCompareTabProps {
  slot?: string;
}

/** 聚合指标：严格口径下每个指标都是多次划分的分布，不是单个数字。 */
interface MetricAgg {
  mean: number | null;
  std: number | null;
  min?: number | null;
  max?: number | null;
  n?: number;
}

interface CompareResult {
  model_name: string;
  window_length?: number;
  stride?: number;
  status: string;
  error?: string | null;
  // legacy 口径（单次划分）字段
  macro_f1_mean?: number | null;
  macro_f1_std?: number | null;
  accuracy_mean?: number | null;
  train_time_sec?: number | null;
  // strict 口径（多次划分）字段
  macro_f1?: MetricAgg;
  balanced_accuracy?: MetricAgg;
  accuracy?: MetricAgg;
  n_splits_completed?: number;
  warning?: string;
  [key: string]: any;
}

/** 格式化成 "0.6315 ± 0.0750"。 */
const fmtAgg = (a?: MetricAgg | null, digits = 4): string => {
  if (!a || a.mean == null) return '—';
  const std = a.std == null ? 0 : a.std;
  return `${a.mean.toFixed(digits)} ± ${std.toFixed(digits)}`;
};

/** 从两种结果形态里取出 macro F1 的均值，用于排序。 */
const macroF1Mean = (r: CompareResult): number => {
  if (r.macro_f1?.mean != null) return r.macro_f1.mean;
  if (r.macro_f1_mean != null) return r.macro_f1_mean;
  return -1;
};

const ModelCompareTab: React.FC<ModelCompareTabProps> = ({ slot = 'pv_fault' }) => {
  const [results, setResults] = useState<CompareResult[]>([]);
  const [bestModel, setBestModel] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [selectedDetail, setSelectedDetail] = useState<CompareResult | null>(null);
  const [meta, setMeta] = useState<{
    evaluation?: string; splitMode?: string; nRepeats?: number;
    dataSummary?: Record<string, any>; pairwise?: Record<string, any>;
  }>({});
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // 配置表单
  const [tierFilter, setTierFilter] = useState<number | undefined>(1);
  const [nRepeats, setNRepeats] = useState(10);
  const [windowLength, setWindowLength] = useState(288);
  const [evaluation, setEvaluation] = useState<'strict' | 'legacy'>('strict');

  // 加载结果。兼容两种形态：
  //   strict 口径 -> results 是 {模型名: 结果} 字典
  //   legacy 口径 -> results 是数组
  const loadResult = useCallback(async () => {
    try {
      const data: any = await tscExperimentApi.getTscCompareResult(slot);
      const raw = data.results;
      const list: CompareResult[] = Array.isArray(raw)
        ? raw
        : Object.entries(raw || {}).map(([name, v]) => ({
            ...(v as object), model_name: name,
          })) as CompareResult[];
      setResults(list);
      setBestModel(data.best_model || null);
      setMeta({
        evaluation: data.evaluation,
        splitMode: data.split_mode ?? data.config?.split_mode,
        nRepeats: data.n_repeats ?? data.config?.n_repeats,
        dataSummary: data.data_summary,
        pairwise: data.pairwise_vs_baseline,
      });
    } catch {
      // 404 表示无结果
      setResults([]);
      setMeta({});
    }
  }, [slot]);

  // 加载状态
  const loadStatus = useCallback(async () => {
    try {
      const data: any = await tscExperimentApi.getTscCompareStatus(slot);
      setStatus(data);
      return data.status;
    } catch {
      setStatus(null);
      return 'idle';
    }
  }, [slot]);

  // 初始化
  useEffect(() => {
    void loadResult();
    void loadStatus();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadResult, loadStatus]);

  // 轮询
  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const s = await loadStatus();
      if (s === 'completed' || s === 'failed') {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        await loadResult();
        if (s === 'completed') message.success('TSC 对比实验完成');
        else message.error('TSC 对比实验失败');
      }
    }, 3000);
  }, [loadStatus, loadResult]);

  // 启动对比
  const handleStart = async () => {
    setStarting(true);
    try {
      const resp = await tscExperimentApi.startTscCompare({
        tierFilter,
        nRepeats,
        evaluation,
        windowConfigs: [{ window_length: windowLength, stride: Math.floor(windowLength / 4) }],
      }, slot);
      message.success('TSC 对比实验已启动');
      if (resp?.warning) message.warning(resp.warning, 6);
      setConfigModalOpen(false);
      startPolling();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '启动失败');
    } finally {
      setStarting(false);
    }
  };

  // 表格列
  const columns = [
    {
      title: '模型',
      dataIndex: 'model_name',
      key: 'model_name',
      render: (name: string, record: CompareResult) => (
        <Space>
          {bestModel && bestModel.includes(name) && <TrophyOutlined style={{ color: '#faad14' }} />}
          <Text strong={bestModel?.includes(name)}>{name}</Text>
          {record.status === 'failed' && <Tag color="error">失败</Tag>}
        </Space>
      ),
    },
    {
      title: <Tooltip title="完整标签空间上的 macro F1，多次划分的 mean ± std">macro F1</Tooltip>,
      key: 'f1',
      width: 150,
      render: (_: unknown, r: CompareResult) =>
        r.macro_f1
          ? fmtAgg(r.macro_f1)
          : (r.macro_f1_mean != null
              ? `${r.macro_f1_mean.toFixed(4)} ± ${(r.macro_f1_std || 0).toFixed(4)}`
              : '—'),
      sorter: (a: CompareResult, b: CompareResult) => macroF1Mean(a) - macroF1Mean(b),
      defaultSortOrder: 'descend' as const,
    },
    {
      title: <Tooltip title="类别均衡的准确率。本任务多数类占比高，普通 accuracy 会高估">balanced acc</Tooltip>,
      key: 'balacc',
      width: 150,
      render: (_: unknown, r: CompareResult) => fmtAgg(r.balanced_accuracy),
    },
    {
      title: <Tooltip title="普通准确率，仅供参考：多数类基线已可达 0.47">accuracy</Tooltip>,
      key: 'acc',
      width: 150,
      render: (_: unknown, r: CompareResult) =>
        r.accuracy
          ? fmtAgg(r.accuracy)
          : (r.accuracy_mean != null ? r.accuracy_mean.toFixed(4) : '—'),
    },
    {
      title: <Tooltip title="成功完成的划分次数。<10 时标准差不可靠">划分数</Tooltip>,
      key: 'splits',
      width: 80,
      render: (_: unknown, r: CompareResult) =>
        r.n_splits_completed != null
          ? (
            <Tag color={r.n_splits_completed >= 10 ? 'green' : 'orange'}>
              {r.n_splits_completed}
            </Tag>
          )
          : '—',
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: CompareResult) => (
        record.status === 'ok' ? (
          <Button size="small" onClick={() => setSelectedDetail(record)}>详情</Button>
        ) : null
      ),
    },
  ];

  const isRunning = status?.status === 'running';
  const progressPct = isRunning && status?.total
    ? Math.round(((status.completed || 0) / status.total) * 100)
    : 0;

  return (
    <div>
      {/* 路径管理 */}
      <ModelPathManager slot={slot} />

      {/* 实验控制 */}
      <Card
        size="small"
        title={<Space><ExperimentOutlined /> TSC 多模型对比</Space>}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadResult} loading={loading}>刷新</Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => setConfigModalOpen(true)}
              disabled={isRunning}
            >
              启动对比
            </Button>
          </Space>
        }
      >
        {/* 进度条 */}
        {isRunning && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={
              <Space>
                实验进行中：{status?.current_model || '...'}
                <Progress percent={progressPct} size="small" style={{ width: 120 }} />
                ({status?.completed || 0}/{status?.total || '?'})
              </Space>
            }
          />
        )}

        {/* 评估口径说明 —— 避免有人把 legacy 单次划分的数字拿去汇报 */}
        {results.length > 0 && (
          meta.evaluation === 'strict_multi_split' ? (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 12 }}
              message={
                `严格口径：${meta.splitMode === 'strict' ? '时间 + 设备双隔离' : meta.splitMode}`
                + `，${meta.nRepeats ?? '?'} 次划分，数字为 mean ± std`
              }
              description={
                meta.dataSummary
                  ? `窗口 ${meta.dataSummary.n_windows?.toLocaleString?.() ?? '?'} 个，`
                    + `${meta.dataSummary.n_devices ?? '?'} 设备，`
                    + `${meta.dataSummary.n_classes ?? '?'} 类。`
                    + ' macro 指标在完整标签空间上计算。'
                  : undefined
              }
            />
          ) : (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="这是 legacy 口径（单次按设备划分），不可用于对外汇报"
              description="单次划分实测标准差可达 0.075、极差 0.20，且按设备划分是「同期跨设备」口径会高估。请用严格口径重跑。"
            />
          )
        )}

        {/* 精度对比表 */}
        <Table
          dataSource={results}
          columns={columns}
          rowKey={(r) => `${r.model_name}-${r.window_length ?? 'na'}`}
          size="small"
          pagination={false}
          rowClassName={(r) => bestModel === r.model_name || bestModel?.includes(r.model_name)
            ? 'ant-table-row-selected' : ''}
        />

        {/* 逐划分配对差 —— 比各自的 mean±std 更有说服力 */}
        {meta.pairwise && Object.keys(meta.pairwise).length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Text strong style={{ fontSize: 13 }}>相对基线的逐划分配对差</Text>
            <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
              （同一划分上比较，消除划分难度影响，比各自的 mean ± std 更可靠）
            </Text>
            <Table
              size="small"
              pagination={false}
              style={{ marginTop: 8 }}
              dataSource={Object.entries(meta.pairwise).map(([name, v]: [string, any]) => ({
                key: name, model: name, ...v,
              }))}
              columns={[
                { title: '模型', dataIndex: 'model', key: 'model' },
                { title: '对照基线', dataIndex: 'vs', key: 'vs', width: 110 },
                {
                  title: 'macro F1 差',
                  key: 'diff',
                  width: 150,
                  render: (_: unknown, r: any) =>
                    r.macro_f1_diff_mean != null ? (
                      <Text type={r.macro_f1_diff_mean > 0 ? 'success' : 'danger'}>
                        {r.macro_f1_diff_mean > 0 ? '+' : ''}
                        {r.macro_f1_diff_mean.toFixed(4)} ± {(r.macro_f1_diff_std ?? 0).toFixed(4)}
                      </Text>
                    ) : '—',
                },
                {
                  title: '胜出划分',
                  key: 'wins',
                  width: 100,
                  render: (_: unknown, r: any) => `${r.wins ?? '?'} / ${r.n_paired ?? '?'}`,
                },
              ]}
            />
          </div>
        )}
      </Card>

      {/* 详情折叠 */}
      {selectedDetail && (
        <Card size="small" style={{ marginTop: 12 }} title={`${selectedDetail.model_name} 详情`}
              extra={<Button size="small" onClick={() => setSelectedDetail(null)}>关闭</Button>}>
          <TscExperimentDetail result={selectedDetail} />
        </Card>
      )}

      {/* 配置弹窗 */}
      <Modal
        title="TSC 对比实验配置"
        open={configModalOpen}
        onOk={handleStart}
        onCancel={() => setConfigModalOpen(false)}
        confirmLoading={starting}
        okText="启动"
      >
        <Space direction="vertical" style={{ width: '100%' }} size={14}>
          <div>
            <Text strong>评估口径：</Text>
            <Radio.Group
              value={evaluation}
              onChange={e => setEvaluation(e.target.value)}
              style={{ marginLeft: 8 }}
            >
              <Radio.Button value="strict">严格（推荐）</Radio.Button>
              <Radio.Button value="legacy">legacy</Radio.Button>
            </Radio.Group>
            <div style={{ marginTop: 6 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {evaluation === 'strict'
                  ? '时间 + 设备双隔离，多次划分输出 mean ± std。可用于对外汇报。'
                  : '单次按设备划分，同期跨设备口径会高估，仅供快速探索，不可对外引用。'}
              </Text>
            </div>
          </div>
          <div>
            <Text>模型 Tier：</Text>
            <Checkbox.Group
              options={[
                { label: 'Tier 1 (ROCKET系列)', value: 1 },
                { label: 'Tier 2 (InceptionTime/ResNet)', value: 2 },
                { label: 'Tier 3 (CNN-LSTM, 需GPU)', value: 3 },
              ]}
              value={tierFilter !== undefined ? [tierFilter] : [1, 2, 3]}
              onChange={(vals) => setTierFilter(vals.length === 1 ? vals[0] as number : undefined)}
            />
          </div>
          <div>
            <Text>窗口长度：</Text>
            <InputNumber value={windowLength} onChange={v => setWindowLength(v || 288)} min={36} max={1152} />
            <Text type="secondary" style={{ marginLeft: 8 }}>
              ({windowLength} 点 = {(windowLength * 5 / 60).toFixed(1)}h)
            </Text>
            {windowLength !== 288 && (
              <div style={{ marginTop: 4 }}>
                <Text type="warning" style={{ fontSize: 12 }}>
                  实测缩短窗口会降低精度（-0.08~-0.16）：标签是天级粒度，288 点（1 天）恰好匹配。
                </Text>
              </div>
            )}
          </div>
          <div>
            <Text>{evaluation === 'strict' ? '划分次数：' : 'CV 重复次数：'}</Text>
            <InputNumber value={nRepeats} onChange={v => setNRepeats(v || 10)} min={1} max={30} />
            {evaluation === 'strict' && nRepeats < 10 && (
              <Text type="warning" style={{ marginLeft: 8, fontSize: 12 }}>
                &lt; 10 次时标准差估计不可靠
              </Text>
            )}
          </div>
        </Space>
      </Modal>
    </div>
  );
};

export default ModelCompareTab;
// @AI_GENERATED: end
