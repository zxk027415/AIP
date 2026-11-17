// @AI_GENERATED
/**
 * PvFaultModelingPathOpsPanel.tsx — 两条建模路径、点级训练状态与标签来源运营面板
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Progress,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  DatabaseOutlined,
  ExperimentOutlined,
  TagOutlined,
} from '@ant-design/icons';
import { cumulativeTrainingApi, pointLabelApi } from '../../services/iterativeLabelingApi';
import type { PvFaultOpsBundle } from '../../hooks/usePvFaultAccuracyOpsBundle';
import { useNavigate } from 'react-router-dom';

const { Text, Paragraph } = Typography;

interface PvFaultModelingPathOpsPanelProps {
  slot?: string;
  opsBundle?: PvFaultOpsBundle | null;
}

const PATH_LABELS: Record<string, string> = {
  legacy_day: '天级路径 · 每天一个标签',
  seq_annotation: '点级路径 · 全天 288 点',
};

const ModelingPathCard: React.FC<{ slot: string }> = ({ slot }) => {
  const navigate = useNavigate();
  const [messageApi, contextHolder] = message.useMessage();
  const [pathsConfig, setPathsConfig] = useState<Record<string, any> | null>(null);
  const [seqTraining, setSeqTraining] = useState(false);
  // seq 训练状态轮询：记录刚触发的那条请求，持续从 getState 读取进度。
  const [seqTrainRequestId, setSeqTrainRequestId] = useState<string | null>(null);
  const [seqTrainStatus, setSeqTrainStatus] = useState<string | null>(null);
  const [seqTrainProgress, setSeqTrainProgress] = useState<Record<string, any> | null>(null);

  const loadPaths = useCallback(async () => {
    const cfg = await cumulativeTrainingApi.getModelingPaths(slot).catch(() => null);
    setPathsConfig(cfg as Record<string, any> | null);
  }, [slot]);

  useEffect(() => {
    void loadPaths();
  }, [loadPaths]);

  // seq 训练状态轮询：请求启动后持续读取 getState，直到完成/失败/取消。
  useEffect(() => {
    if (!seqTrainRequestId) return undefined;
    let disposed = false;
    const poll = async () => {
      try {
        const state = (await cumulativeTrainingApi.getState(slot)) as Record<string, any>;
        if (disposed) return;
        const latest = (state?.latest_retrain_request ?? {}) as Record<string, any>;
        if (String(latest.request_id ?? '') !== seqTrainRequestId) return;
        setSeqTrainStatus(String(latest.status ?? 'queued'));
        setSeqTrainProgress((latest.progress ?? null) as Record<string, any> | null);
        if (latest.status === 'completed') {
          messageApi.success(`序列标注训练完成：${latest.model_ref ?? '已登记实验模型'}`);
          setSeqTrainRequestId(null);
          void loadPaths();
        } else if (latest.status === 'failed') {
          const reason = latest.error ?? latest.progress?.message ?? '未知原因';
          messageApi.error(`序列标注训练失败：${reason}`);
          setSeqTrainRequestId(null);
          void loadPaths();
        }
      } catch {
        // 单次轮询失败不终止；下一轮继续读取。
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 8000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [seqTrainRequestId, slot, loadPaths, messageApi]);

  const handleStartSeqTraining = async () => {
    setSeqTraining(true);
    setSeqTrainStatus(null);
    setSeqTrainProgress(null);
    try {
      const response = await cumulativeTrainingApi.startManualRetrain(
        slot,
        'seq_annotation',
      );
      const requestId = String(response.request_id ?? '');
      setSeqTrainRequestId(requestId || null);
      if (requestId) setSeqTrainStatus('queued');
      messageApi.success(
        requestId
          ? `全天 288 点序列标注训练已启动（${requestId}）`
          : '全天 288 点序列标注训练已启动',
      );
      await loadPaths();
    } catch (err: unknown) {
      // 接口报错：明确提示失败，而不是显示成「尚未训练」。
      const reason = err instanceof Error ? err.message : '未知原因';
      messageApi.error(`启动序列标注训练失败：${reason}`);
    } finally {
      setSeqTraining(false);
    }
  };

  const handleSetProduction = async (productionPath: string) => {
    const simpleAllowed = pathsConfig?.governance?.simple_switch_allowed !== false;
    if (!simpleAllowed) {
      messageApi.warning('生产环境禁止快捷设为主线，请前往算法部署 → 双路径治理，使用严格九项准入切换');
      navigate('/algorithm-deployment?slot=pv_fault');
      return;
    }
    try {
      const fallback = productionPath === 'legacy_day' ? 'seq_annotation' : 'legacy_day';
      await cumulativeTrainingApi.setModelingPaths(productionPath, fallback, slot, {
        switch_mode: 'simple',
        confirm: true,
        operator: 'lab',
        reason: 'accuracy-ops set production path',
      });
      messageApi.success(`生产主线已设为 ${PATH_LABELS[productionPath] ?? productionPath}`);
      await loadPaths();
    } catch (err: unknown) {
      messageApi.error(err instanceof Error ? err.message : '设置生产路径失败');
    }
  };

  const pathModels = (pathsConfig?.path_models ?? {}) as Record<string, Record<string, any>>;
  const legacyModel = pathModels.legacy_day;
  const legacyMetrics = (legacyModel?.metrics ?? {}) as Record<string, any>;
  const seqModel = pathModels.seq_annotation;
  const seqMetrics = (seqModel?.metrics ?? {}) as Record<string, any>;
  const displayResults: Array<Record<string, any>> = [
    {
      path_key: 'legacy_day',
      label: PATH_LABELS.legacy_day,
      status: legacyModel?.model_ref ? 'registered' : 'not_trained',
      macro_f1_mean: legacyMetrics.macro_f1_mean,
      accuracy_mean: legacyMetrics.accuracy_mean,
      n_samples: legacyMetrics.n_samples,
    },
    {
      path_key: 'seq_annotation',
      label: PATH_LABELS.seq_annotation,
      status: seqModel?.model_ref ? 'registered' : 'not_trained',
      macro_f1_mean: seqMetrics.point_macro_f1 ?? seqMetrics.macro_f1_mean,
      accuracy_mean: seqMetrics.point_accuracy ?? seqMetrics.accuracy_mean,
      binary_f1: seqMetrics.binary_f1,
      fault_mask_iou: seqMetrics.fault_mask_iou ?? seqMetrics.segment_iou,
      n_samples: seqMetrics.n_samples,
      trained_full_day: Boolean(seqModel?.trained_full_day),
    },
  ];

  return (
    <Card
      size="small"
      title={
        <Space>
          <ExperimentOutlined />
          建模路径（天级 / 点级）
        </Space>
      }
      style={{ marginBottom: 16 }}
      extra={
        <Space>
          <Button
            size="small"
            onClick={() => navigate(`/algorithm-deployment?slot=${encodeURIComponent(slot)}&tab=governance`)}
          >
            路径切换 / 换将
          </Button>
          <Button size="small" onClick={() => void loadPaths()}>
            刷新
          </Button>
          <Button
            size="small"
            loading={seqTraining || seqTrainRequestId !== null}
            onClick={() => void handleStartSeqTraining()}
          >
            {seqTrainRequestId !== null ? '训练中…' : '训练点级路径'}
          </Button>
        </Space>
      }
    >
      {contextHolder}
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 12 }}
        message="平台只保留天级与点级两条建模路径"
        description="天级路径每天输出一个标签；点级路径保持全天 288 点连续序列。两者当前评测粒度不同，不能直接比较现有 macro-F1；历史 RF 采样策略只用于兼容旧模型，不再展示或配置。"
      />

      {seqTrainRequestId !== null && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Space direction="vertical" style={{ width: '100%' }} size={4}>
            <Text strong>序列标注训练状态</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {seqTrainStatus === 'running'
                ? String(seqTrainProgress?.message ?? '训练中')
                : seqTrainStatus === 'queued'
                  ? '排队中，等待执行…'
                  : '训练中…'}
            </Text>
            {typeof seqTrainProgress?.percent === 'number' && (
              <Progress
                percent={Math.min(100, Math.max(0, Number(seqTrainProgress.percent)))}
                size="small"
                status={seqTrainStatus === 'failed' ? 'exception' : 'active'}
              />
            )}
          </Space>
        </Card>
      )}

      {pathsConfig && (
        <Space wrap style={{ marginBottom: 12 }}>
          <Tag color="green">
            主线 {PATH_LABELS[String(pathsConfig.production_path)] ?? String(pathsConfig.production_path)}
          </Tag>
          <Tag>
            备选 {PATH_LABELS[String(pathsConfig.fallback_path)] ?? String(pathsConfig.fallback_path)}
          </Tag>
          {pathsConfig.production_model_ref && (
            <Tag color="blue">当前模型 {String(pathsConfig.production_model_ref).slice(-24)}</Tag>
          )}
        </Space>
      )}

      <Table
        size="small"
        rowKey="path_key"
        pagination={false}
        scroll={{ x: 1050 }}
        dataSource={displayResults}
        locale={{ emptyText: '尚无路径模型登记' }}
        columns={[
          {
            title: '路径',
            dataIndex: 'label',
            ellipsis: true,
            render: (label: unknown, row: Record<string, any>) => (
              <Space size={6}>
                <Text>{String(label || PATH_LABELS[row.path_key] || row.path_key)}</Text>
                {row.path_key === 'seq_annotation' && <Tag color="purple">实验</Tag>}
              </Space>
            ),
          },
          {
            title: '输出粒度',
            width: 90,
            render: (_: unknown, row: Record<string, any>) =>
              row.path_key === 'seq_annotation' ? '288 点/天' : '1 标签/样本',
          },
          {
            title: 'macro-F1',
            width: 90,
            render: (_: unknown, row: Record<string, any>) =>
              row.macro_f1_mean != null ? Number(row.macro_f1_mean).toFixed(4) : '—',
          },
          {
            title: '故障 F1',
            width: 84,
            render: (_: unknown, row: Record<string, any>) =>
              row.binary_f1 != null ? Number(row.binary_f1).toFixed(4) : '—',
          },
          {
            title: '分段 IoU',
            width: 84,
            render: (_: unknown, row: Record<string, any>) =>
              row.fault_mask_iou != null ? Number(row.fault_mask_iou).toFixed(4) : '—',
          },
          {
            title: 'Accuracy',
            width: 90,
            render: (_: unknown, row: Record<string, any>) =>
              row.accuracy_mean != null ? Number(row.accuracy_mean).toFixed(4) : '—',
          },
          { title: '样本量', dataIndex: 'n_samples', width: 80, render: (v) => v ?? '—' },
          {
            title: '跨路径比较',
            width: 110,
            render: () => <Text type="secondary">需共同基准</Text>,
          },
          {
            title: '操作',
            width: 112,
            fixed: 'right',
            render: (_: unknown, row: Record<string, any>) => {
              const pathKey = String(row.path_key);
              const entry = pathModels[pathKey];
              const isProduction = pathsConfig?.production_path === pathKey;
              const canPromote = Boolean(entry?.model_ref)
                && (pathKey !== 'seq_annotation' || Boolean(entry?.trained_full_day));
              const simpleAllowed = pathsConfig?.governance?.simple_switch_allowed !== false;
              if (isProduction) return <Tag color="green">当前主线</Tag>;
              if (row.status === 'failed') return <Text type="danger">失败</Text>;
              if (!canPromote) {
                const reason = pathKey === 'seq_annotation'
                  ? '需先完成全天 288 点训练并登记模型'
                  : '该路径尚无已登记模型';
                return (
                  <Tooltip title={reason}>
                    <Button type="link" size="small" disabled>
                      设为主线
                    </Button>
                  </Tooltip>
                );
              }
              return (
                <Tooltip title={!simpleAllowed ? '生产环境请使用双路径治理台严格切换' : undefined}>
                  <Button
                    type="link"
                    size="small"
                    disabled={!simpleAllowed}
                    onClick={() => void handleSetProduction(pathKey)}
                  >
                    设为主线
                  </Button>
                </Tooltip>
              );
            },
          },
        ]}
      />

    </Card>
  );
};

const PvFaultModelingPathOpsPanel: React.FC<PvFaultModelingPathOpsPanelProps> = ({
  slot = 'pv_fault',
  opsBundle,
}) => {
  const [messageApi, contextHolder] = message.useMessage();
  const [coverage, setCoverage] = useState<Record<string, any> | null>(null);
  const [queue, setQueue] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [coverageResp, queueResp] = await Promise.all([
        pointLabelApi.getSourceCoverage(slot).catch(() => null),
        pointLabelApi.getPendingQueue({ page: 1, pageSize: 20 }, slot).catch(() => null),
      ]);
      setCoverage(coverageResp as Record<string, any> | null);
      setQueue(queueResp as Record<string, any> | null);
    } finally {
      setLoading(false);
    }
  }, [slot]);

  const usingBundle = opsBundle !== undefined;

  useEffect(() => {
    if (!usingBundle) return;
    setCoverage((opsBundle?.sourceCoverage as Record<string, any> | null) ?? null);
    setQueue((opsBundle?.pendingQueue as Record<string, any> | null) ?? null);
  }, [usingBundle, opsBundle]);

  useEffect(() => {
    if (usingBundle) return;
    void load();
  }, [load, usingBundle]);

  const totalPoints = Number(coverage?.total_measurement_points ?? 0);
  const labeledPoints = Number(coverage?.labeled_points ?? 0);
  const unknownPoints = Number(queue?.unknown_point_count ?? Math.max(0, totalPoints - labeledPoints));
  const coverageRatio = totalPoints > 0 ? labeledPoints / totalPoints : 0;

  const sourceRows = Object.entries(coverage?.labeled_points_by_source ?? {}).map(
    ([source, count]) => ({
      source,
      point_count: count,
      share: labeledPoints > 0 ? Number(count) / labeledPoints : 0,
    }),
  );

  return (
    <>
    <Card
      size="small"
      title={
        <Space>
          <TagOutlined />
          逐点标签 · 待标注与来源覆盖
        </Space>
      }
      style={{ marginBottom: 16 }}
      extra={
        <Button size="small" loading={loading} onClick={() => void load()}>
          刷新
        </Button>
      }
    >
      {contextHolder}
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="split parity 已移除：样本切分策略写入模型 pickle，训练/预测自动对齐。"
        description="本面板展示 point_labels 覆盖与待标注队列；人工裁决与框选已写入逐点标签主链路。"
      />

      <Space wrap style={{ marginBottom: 12 }}>
        <Tag color="blue">
          已标注 {labeledPoints}/{totalPoints || '—'} 点
        </Tag>
        <Tag color={unknownPoints > 0 ? 'warning' : 'success'}>
          待标注 {unknownPoints} 点
        </Tag>
        <Tag color="processing">
          覆盖率 {(coverageRatio * 100).toFixed(1)}%
        </Tag>
      </Space>

      <Progress
        percent={Math.round(coverageRatio * 100)}
        size="small"
        style={{ marginBottom: 16 }}
      />

      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        <DatabaseOutlined /> 活跃操作按来源（label_ops）
      </Paragraph>
      <Table
        size="small"
        rowKey="source"
        pagination={false}
        loading={loading && !sourceRows.length}
        dataSource={sourceRows}
        style={{ marginBottom: 16 }}
        columns={[
          { title: '来源', dataIndex: 'source' },
          { title: '已标注点数', dataIndex: 'point_count', width: 110 },
          {
            title: '占比',
            width: 90,
            render: (_: unknown, row: { share: number }) => `${(row.share * 100).toFixed(1)}%`,
          },
        ]}
        locale={{ emptyText: '暂无逐点标签数据' }}
      />

      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        待标注队列 Top 20（未覆盖或 label_id=NULL）
      </Paragraph>
      <Table
        size="small"
        rowKey={(row) => `${row.site_id}|${row.device_id}|${row.t_start}`}
        pagination={false}
        loading={loading && !(queue?.items?.length)}
        dataSource={queue?.items ?? []}
        columns={[
          { title: '站点', dataIndex: 'site_id', width: 90, ellipsis: true },
          { title: '设备', dataIndex: 'device_id', width: 90, ellipsis: true },
          { title: '起点', dataIndex: 't_start', width: 150 },
          { title: '终点', dataIndex: 't_end', width: 150 },
          { title: '点数', dataIndex: 'point_count', width: 70 },
        ]}
        locale={{
          emptyText: unknownPoints === 0 ? '待标注队列为空（K4 生效后规模显著缩小）' : '暂无队列数据',
        }}
      />

      {(coverage?.top_unknown_devices?.length ?? 0) > 0 && (
        <>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 12, marginBottom: 8 }}>
            unknown 点数 Top 设备
          </Paragraph>
          <Space wrap>
            {(coverage?.top_unknown_devices ?? []).slice(0, 6).map((item: any) => (
              <Tag key={item.device_key}>
                {item.device_key}: {item.unknown_point_count}
              </Tag>
            ))}
          </Space>
        </>
      )}
    </Card>
    <ModelingPathCard slot={slot} />
    </>
  );
};

export default PvFaultModelingPathOpsPanel;
// @AI_GENERATED: end
