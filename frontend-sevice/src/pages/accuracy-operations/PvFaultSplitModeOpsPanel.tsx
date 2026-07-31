// @AI_GENERATED
/**
 * PvFaultSplitModeOpsPanel.tsx — 逐点标签运营面板（待标注队列 + 来源覆盖 + K7 路径对比）
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  InputNumber,
  Progress,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { DatabaseOutlined, ExperimentOutlined, TagOutlined } from '@ant-design/icons';
import { cumulativeTrainingApi, pointLabelApi } from '../../services/iterativeLabelingApi';
import type { PvFaultOpsBundle } from '../../hooks/usePvFaultAccuracyOpsBundle';

const { Text, Paragraph } = Typography;

interface PvFaultSplitModeOpsPanelProps {
  slot?: string;
  opsBundle?: PvFaultOpsBundle | null;
}

const ModelingPathCompareCard: React.FC<{ slot: string }> = ({ slot }) => {
  const [messageApi, contextHolder] = message.useMessage();
  const [compare, setCompare] = useState<Record<string, any> | null>(null);
  const [pathsConfig, setPathsConfig] = useState<Record<string, any> | null>(null);
  const [nRepeats, setNRepeats] = useState(1);
  const [starting, setStarting] = useState(false);

  const loadCompare = useCallback(async () => {
    const [cmp, cfg] = await Promise.all([
      cumulativeTrainingApi.getModelingPathCompare(slot).catch(() => null),
      cumulativeTrainingApi.getModelingPaths(slot).catch(() => null),
    ]);
    setCompare(cmp as Record<string, any> | null);
    setPathsConfig(cfg as Record<string, any> | null);
  }, [slot]);

  useEffect(() => {
    void loadCompare();
  }, [loadCompare]);

  useEffect(() => {
    if (compare?.status !== 'running') return undefined;
    const timer = window.setInterval(() => void loadCompare(), 8000);
    return () => window.clearInterval(timer);
  }, [compare?.status, loadCompare]);

  const handleStart = async () => {
    setStarting(true);
    try {
      const resp = await cumulativeTrainingApi.runModelingPathCompare({ nRepeats }, slot);
      if (resp?.accepted === false) {
        messageApi.warning(String(resp.message || '对比任务已在运行'));
      } else {
        messageApi.success('路径对比已在后台启动');
      }
      await loadCompare();
    } catch (err: unknown) {
      messageApi.error(err instanceof Error ? err.message : '启动路径对比失败');
    } finally {
      setStarting(false);
    }
  };

  const handleSetProduction = async (productionPath: string) => {
    try {
      const fallback =
        productionPath === 'legacy_day' ? 'point_label_by_day_night' : 'legacy_day';
      await cumulativeTrainingApi.setModelingPaths(productionPath, fallback, slot);
      messageApi.success(`生产主线已设为 ${productionPath}`);
      await loadCompare();
    } catch (err: unknown) {
      messageApi.error(err instanceof Error ? err.message : '设置生产路径失败');
    }
  };

  const status = String(compare?.status ?? 'idle');
  const results = (compare?.results ?? compare?.partial_results ?? []) as Array<Record<string, any>>;
  const total = Number(compare?.total ?? results.length ?? 0);
  const completed = Number(compare?.completed ?? (status === 'completed' ? total : results.length));

  return (
    <Card
      size="small"
      title={
        <Space>
          <ExperimentOutlined />
          新旧建模路径 A/B 对比（K7）
        </Space>
      }
      style={{ marginBottom: 16 }}
      extra={
        <Space>
          <InputNumber
            min={1}
            max={5}
            size="small"
            value={nRepeats}
            onChange={(v) => setNRepeats(Number(v) || 1)}
            addonBefore="重复"
          />
          <Button size="small" onClick={() => void loadCompare()}>
            刷新
          </Button>
          <Button
            size="small"
            type="primary"
            loading={starting || status === 'running'}
            onClick={() => void handleStart()}
          >
            开始对比
          </Button>
        </Space>
      }
    >
      {contextHolder}
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 12 }}
        message="对比前提"
        description="新旧白天/夜间与样本粒度口径不同；须在同一批测量数据上分别完整跑老/新路径，不可直接比历史模型指标。"
      />

      {pathsConfig && (
        <Space wrap style={{ marginBottom: 12 }}>
          <Tag color="green">主线 {pathsConfig.production_path}</Tag>
          <Tag>备选 {pathsConfig.fallback_path}</Tag>
          {pathsConfig.production_model_ref && (
            <Tag color="blue">当前模型 {String(pathsConfig.production_model_ref).slice(-24)}</Tag>
          )}
        </Space>
      )}

      {status === 'running' && total > 0 && (
        <Progress
          percent={Math.round((completed / total) * 100)}
          size="small"
          status="active"
          style={{ marginBottom: 12 }}
          format={() => `${completed}/${total}`}
        />
      )}

      {compare?.message && status !== 'idle' && (
        <Paragraph type="secondary" style={{ fontSize: 12 }}>
          {compare.message}
          {compare.current_label ? ` · 当前：${compare.current_label}` : ''}
        </Paragraph>
      )}

      <Table
        size="small"
        rowKey="path_key"
        pagination={false}
        dataSource={results}
        locale={{ emptyText: '尚无对比结果，点击「开始对比」' }}
        columns={[
          { title: '路径', dataIndex: 'label', ellipsis: true },
          {
            title: 'macro-F1',
            width: 90,
            render: (_: unknown, row: Record<string, any>) =>
              row.macro_f1_mean != null ? Number(row.macro_f1_mean).toFixed(4) : '—',
          },
          {
            title: 'Accuracy',
            width: 90,
            render: (_: unknown, row: Record<string, any>) =>
              row.accuracy_mean != null ? Number(row.accuracy_mean).toFixed(4) : '—',
          },
          { title: '样本量', dataIndex: 'n_samples', width: 80 },
          {
            title: 'ΔF1 vs legacy',
            width: 100,
            render: (_: unknown, row: Record<string, any>) => {
              const delta = compare?.deltas_vs_legacy?.[row.path_key]?.macro_f1_delta;
              if (delta == null || row.path_key === 'legacy_day') return '—';
              const color = Number(delta) >= 0 ? 'success' : 'error';
              return <Tag color={color}>{Number(delta) >= 0 ? '+' : ''}{Number(delta).toFixed(4)}</Tag>;
            },
          },
          {
            title: '操作',
            width: 100,
            render: (_: unknown, row: Record<string, any>) =>
              row.status === 'ok' ? (
                <Button
                  type="link"
                  size="small"
                  onClick={() => void handleSetProduction(String(row.path_key))}
                >
                  设为主线
                </Button>
              ) : (
                <Text type="danger" style={{ fontSize: 12 }}>
                  失败
                </Text>
              ),
          },
        ]}
      />

      {compare?.best_path_key && status === 'completed' && (
        <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
          推荐路径：<Text strong>{compare.best_label ?? compare.best_path_key}</Text>
          {compare.best_macro_f1_mean != null && (
            <> · macro-F1 {Number(compare.best_macro_f1_mean).toFixed(4)}</>
          )}
        </Paragraph>
      )}
    </Card>
  );
};

const PvFaultSplitModeOpsPanel: React.FC<PvFaultSplitModeOpsPanelProps> = ({
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
    <ModelingPathCompareCard slot={slot} />
    </>
  );
};

export default PvFaultSplitModeOpsPanel;
// @AI_GENERATED: end
