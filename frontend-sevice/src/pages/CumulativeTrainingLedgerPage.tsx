/**
 * 天/点路径累计训练看板：同一页用选项隔离两套账本；入库只记账，训练时按时间冻结快照。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import SlotWaveformChart from '../components/slot/SlotWaveformChart';
import {
  SLOT_PRODUCT_CONFIG,
  type PvProductSlot,
} from '../config/slotProductConfig';
import {
  freezeIdOf,
  slotCumulativeApi,
  type CumulativeFreezeVersion,
  type CumulativeLedger,
  type CumulativeLedgerEvent,
  type SnapshotPreview,
} from '../services/slotCumulativeApi';

const { Title, Text, Paragraph } = Typography;

// @AI_GENERATED: Distinguish immutable bootstrap authority from ordinary path-A curation and human review.
const SOURCE_LABEL: Record<string, { color: string; text: string }> = {
  gold_bootstrap: { color: 'cyan', text: '全量金标准 bootstrap' },
  path_a: { color: 'geekblue', text: '路径 A（无标签打标确认）' },
  daily_review: { color: 'gold', text: '人工审核回流' },
  unknown: { color: 'default', text: '未标记来源' },
};
// @AI_GENERATED: end

function formatTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

function parseSlot(raw?: string | null): PvProductSlot {
  if (raw === 'pv_day') return 'pv_day';
  if (raw === 'pv_tsc') return 'pv_tsc';
  return 'pv_point';
}

const CumulativeTrainingLedgerPage: React.FC = () => {
  const navigate = useNavigate();
  const { slot: slotParam } = useParams<{ slot?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const slot: PvProductSlot = parseSlot(searchParams.get('slot') || slotParam);

  const [loading, setLoading] = useState(false);
  // @AI_GENERATED: Persistent ledger/observation error states; failures never masquerade as empty data.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [freezing, setFreezing] = useState(false);
  const [latestPreview, setLatestPreview] = useState<SnapshotPreview | null>(null);
  const [latestPreviewLoading, setLatestPreviewLoading] = useState(false);
  const [latestPreviewError, setLatestPreviewError] = useState<string | null>(null);
  // @AI_GENERATED: end
  const [ledger, setLedger] = useState<CumulativeLedger | null>(null);
  const [selectedCutoff, setSelectedCutoff] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<SnapshotPreview | null>(null);
  const [waveforms, setWaveforms] = useState<Array<{
    label_id: number;
    label_name: string;
    timestamps: string[];
    series: Record<string, Array<number | null>>;
    point_count: number;
  }>>([]);

  const load = useCallback(async () => {
    if (!slot) return;
    setLoading(true);
    // @AI_GENERATED: Switch slots atomically, then load the latest freeze observation without failing the ledger.
    setLoadError(null);
    setLedger(null);
    setSelectedCutoff(null);
    setLatestPreview(null);
    setLatestPreviewError(null);
    setLatestPreviewLoading(false);
    try {
      const body = await slotCumulativeApi.getLedger(slot);
      setLedger(body);
      const latestEvent = body.events[body.events.length - 1]?.reviewed_at || null;
      setSelectedCutoff(latestEvent);
      const latestId = freezeIdOf(slot, body.latest_freeze);
      if (latestId && !body.latest_freeze?.dataset_observation) {
        setLatestPreviewLoading(true);
        try {
          const latest = await slotCumulativeApi.previewSnapshot(slot, latestId);
          setLatestPreview(latest);
        } catch (error: any) {
          setLatestPreviewError(
            error?.response?.data?.detail?.message
              || error?.message
              || '读取最新快照观测统计失败',
          );
        } finally {
          setLatestPreviewLoading(false);
        }
      }
    } catch (error: any) {
      setLoadError(error?.response?.data?.detail?.message || error?.message || '读取累计训练账本失败');
    } finally {
      setLoading(false);
    }
    // @AI_GENERATED: end
  }, [slot]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedEvent = useMemo(
    () => (ledger?.events || []).find((item) => item.reviewed_at === selectedCutoff) || null,
    [ledger, selectedCutoff],
  );
  const latestFreezeId = freezeIdOf(slot, ledger?.latest_freeze);
  // @AI_GENERATED: Prefer immutable freeze metadata; preview remains a compatibility fallback for old snapshots.
  const latestObservation = ledger?.latest_freeze?.dataset_observation
    || latestPreview?.dataset_observation
    || null;
  const latestGrid = latestObservation?.grid || null;
  const latestSourceRows = Object.entries(latestObservation?.source_composition?.by_row || {});
  const latestGridClasses = Object.entries(latestGrid?.class_distribution || {});
  // @AI_GENERATED: end

  const openPreview = async (row: CumulativeFreezeVersion) => {
    const freezeId = freezeIdOf(slot, row);
    if (!freezeId) {
      message.warning('这个快照没有 freeze_id');
      return;
    }
    setPreviewOpen(true);
    setPreviewLoading(true);
    setWaveforms([]);
    try {
      const body = await slotCumulativeApi.previewSnapshot(slot, freezeId);
      setPreview(body);
      const artifact = body.artifact_ref || row.artifact_ref;
      if (artifact) {
        const response = await fetch(
          `/api/iterative-labeling/reference-waveforms?train_csv_path=${encodeURIComponent(artifact)}&slot=${encodeURIComponent(slot)}`,
        );
        const payload = await response.json().catch(() => ({}));
        if (response.ok && Array.isArray(payload.categories)) {
          setWaveforms(payload.categories);
        }
      }
    } catch (error: any) {
      setPreview(null);
      message.error(error?.response?.data?.detail?.message || error?.message || '读取快照内容失败');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleFreezeAndTrain = async () => {
    if (!selectedCutoff) {
      message.warning('请先选择一条审核结束时间作为冻结截止');
      return;
    }
    // @AI_GENERATED: 独立 freeze loading，避免重复点击造成重复冻结请求。
    if (freezing) return;
    setFreezing(true);
    try {
      const result = await slotCumulativeApi.freezeAt(
        slot,
        selectedCutoff,
        `看板冻结截止 ${selectedCutoff}`,
      );
      setLedger(result.ledger);
      const canvasId = (result.freeze?.canvas_row as { dataset_id?: string } | undefined)?.dataset_id
        || freezeIdOf(slot, result.ledger.latest_freeze);
      if (!canvasId) {
        message.warning('冻结成功，但未得到可训 dataset_id');
        return;
      }
      const workflowId = SLOT_PRODUCT_CONFIG[slot].trainWorkflowId;
      navigate(
        `/algorithm-dev/workflow-editor/${workflowId}?dataset_id=${encodeURIComponent(canvasId)}&slot=${encodeURIComponent(slot)}`,
      );
    } catch (error: any) {
      message.error(error?.response?.data?.detail?.message || error?.message || '冻结累计训练快照失败');
    } finally {
      setFreezing(false);
    }
    // @AI_GENERATED: end
  };

  if (slotParam === 'pv_day' || slotParam === 'pv_point' || slotParam === 'pv_tsc') {
    return <Navigate to={`/datasets/cumulative-training?slot=${slotParam}`} replace />;
  }

  const eventColumns = [
    {
      title: '人工审核结束时间',
      dataIndex: 'reviewed_at',
      key: 'reviewed_at',
      render: (value: string) => formatTime(value),
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      render: (value: string) => {
        const sourceMeta = SOURCE_LABEL[value] || SOURCE_LABEL.unknown;
        return <Tag color={sourceMeta.color}>{sourceMeta.text}</Tag>;
      },
    },
    {
      title: '确认箱 ID',
      dataIndex: 'dataset_version_id',
      key: 'dataset_version_id',
      ellipsis: true,
    },
    {
      title: '纳入累计时间',
      dataIndex: 'included_at',
      key: 'included_at',
      render: (value: string) => formatTime(value),
    },
    {
      title: '审核人',
      dataIndex: 'reviewer',
      key: 'reviewer',
      render: (value: string | null) => value || '—',
    },
  ];

  const freezeColumns = [
    {
      title: '快照时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value: string) => formatTime(value),
    },
    {
      title: '快照 ID',
      key: 'freeze_id',
      render: (_: unknown, row: CumulativeFreezeVersion) => freezeIdOf(slot, row) || '—',
    },
    {
      title: '纳入记录数',
      key: 'included_event_count',
      render: (_: unknown, row: CumulativeFreezeVersion) =>
        row.included_event_count ?? row.included_events?.length ?? row.included_labeled_version_ids?.length ?? 0,
    },
    {
      title: '文件',
      dataIndex: 'artifact_ref',
      key: 'artifact_ref',
      ellipsis: true,
      render: (value: string) => value || '—',
    },
    {
      title: '内容',
      key: 'preview',
      width: 110,
      render: (_: unknown, row: CumulativeFreezeVersion) => (
        <Button
          size="small"
          onClick={(event) => {
            event.stopPropagation();
            void openPreview(row);
          }}
        >
          查看内容
        </Button>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>累计训练数据集</Title>
        {/* @AI_GENERATED: 三槽文案，点/天/时序分类各一套独立账本。 */}
        <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: '72ch' }}>
          点、天、时序分类是三套独立账本，用下面选项切换。确认提案和审核回流只写入当前场景流水；流水不等于当前可训文件。真正训练吃最新冻结快照。
        </Paragraph>
        {/* @AI_GENERATED: end */}
      </div>

      <Space wrap>
        <Select
          value={slot}
          style={{ width: 220 }}
          options={[
            { value: 'pv_point', label: '点路径 pv_point' },
            { value: 'pv_day', label: '天路径 pv_day' },
            { value: 'pv_tsc', label: 'TSC路径 pv_tsc' },
          ]}
          onChange={(value) => setSearchParams({ slot: value })}
        />
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
        <Link to={`/iterative-labeling?tab=pv_label&slot=${slot}`}>
          <Button>去打标无标签数据</Button>
        </Link>
        <Link to={`/algorithm-deployment?slot=${slot}`}>
          <Button>查看已训练模型</Button>
        </Link>
      </Space>

      {/* @AI_GENERATED: 三槽隔离说明；pv_tsc 独立账本，冻结产出 MultiRocket 设备日可训快照。 */}
      <Alert
        type="info"
        showIcon
        message="当前只显示所选诊断路径"
        description="点路径、天路径、时序分类路径数据隔离存储。无标签打标确认、人工审核完成都会追加入库流水，但不会自动变成训练输入。点「冻结为训练快照并去训练」才生成带时间戳的可训文件；点路径冻结会排除聚类整日确认箱，保留 gold 与审核点级切片；时序分类冻结保留全量行级真值并让人工审核覆盖同一时刻，训练算子再按设备日确定性重建 288×3 网格。"
      />
      {/* @AI_GENERATED: end */}

      {/* @AI_GENERATED: 读取失败显式报错 + 重试，绝不退化为空态。 */}
      {loadError && (
        <Alert
          type="error"
          showIcon
          message="读取累计训练账本失败"
          description={loadError}
          action={<Button size="small" onClick={() => void load()}>重试</Button>}
        />
      )}
      {/* @AI_GENERATED: end */}

      {/* @AI_GENERATED: Existing status card now exposes the actual immutable source and derived 288x3 inventory. */}
      <Card size="small" title="最新状态" loading={loading}>
        {ledger ? (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="诊断路径">{ledger.slot}</Descriptions.Item>
              <Descriptions.Item label="入库 / 快照">
                {ledger.event_count} 条 / {ledger.freeze_versions.length} 版
              </Descriptions.Item>
              <Descriptions.Item label="当前默认训练真源" span={2}>
                <Text code>{latestObservation?.train_source?.dataset_id || latestFreezeId || '尚未冻结训练快照'}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="真源相对路径" span={2}>
                {latestObservation?.train_source?.file_path || ledger.latest_freeze?.artifact_ref || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="冻结时间">
                {formatTime(ledger.latest_freeze?.created_at)}
              </Descriptions.Item>
              <Descriptions.Item label="统计时间">
                {formatTime(latestObservation?.computed_at)}
              </Descriptions.Item>
              <Descriptions.Item label="总行数">
                {latestObservation?.row_count?.toLocaleString('zh-CN') ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="独立 device_id">
                {latestObservation?.device_id_count?.toLocaleString('zh-CN') ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="物理序列数">
                {latestObservation?.series_count?.toLocaleString('zh-CN') ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="原始设备日">
                {latestObservation?.device_day_count_raw?.toLocaleString('zh-CN') ?? '—'}
              </Descriptions.Item>
              {slot === 'pv_tsc' && (
                <>
                  <Descriptions.Item label="288×3 网格合格设备日">
                    {latestGrid?.available === false
                      ? '统计失败'
                      : latestGrid?.train_eligible_device_days?.toLocaleString('zh-CN') ?? '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="网格拒绝设备日">
                    {latestGrid?.rejected_device_days?.toLocaleString('zh-CN') ?? '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="训练通道" span={2}>
                    {(latestGrid?.channels || []).join(' + ') || '—'}
                  </Descriptions.Item>
                </>
              )}
              <Descriptions.Item label="最终行来源" span={2}>
                {latestSourceRows.length ? (
                  <Space wrap>
                    {latestSourceRows.map(([source, count]) => (
                      <Tag key={source} color={(SOURCE_LABEL[source] || SOURCE_LABEL.unknown).color}>
                        {(SOURCE_LABEL[source] || SOURCE_LABEL.unknown).text}：{Number(count).toLocaleString('zh-CN')}
                      </Tag>
                    ))}
                  </Space>
                ) : '—'}
              </Descriptions.Item>
              {slot === 'pv_tsc' && (
                <Descriptions.Item label="网格合格设备日类别分布" span={2}>
                  {latestGridClasses.length ? (
                    <Space wrap>
                      {latestGridClasses.map(([label, count]) => (
                        <Tag key={label}>标签 {label}：{Number(count).toLocaleString('zh-CN')}</Tag>
                      ))}
                    </Space>
                  ) : '—'}
                </Descriptions.Item>
              )}
            </Descriptions>
            {latestPreviewLoading && !latestObservation && (
              <Text type="secondary">正在计算最新快照观测统计…</Text>
            )}
            {latestPreviewError && (
              <Alert
                type="warning"
                showIcon
                message="账本已加载，但最新快照观测统计读取失败"
                description={latestPreviewError}
              />
            )}
            {latestGrid?.available === false && (
              <Alert
                type="error"
                showIcon
                message="TSC 288×3 网格统计失败"
                description={latestGrid.reason || '未返回失败原因'}
              />
            )}
          </Space>
        ) : (
          <Alert
            type="info"
            showIcon
            message={loadError ? '账本加载失败，请点上方重试' : '该场景还没有累计训练记录'}
          />
        )}
      </Card>
      {/* @AI_GENERATED: end */}

      <Card
        size="small"
        title="入库流水"
        extra={
          <Space wrap>
            <Text type="secondary">冻结截止</Text>
            <Select
              style={{ minWidth: 280 }}
              placeholder="选择审核结束时间"
              value={selectedCutoff}
              onChange={setSelectedCutoff}
              options={(ledger?.events || []).map((item: CumulativeLedgerEvent) => ({
                value: item.reviewed_at,
                label: `${formatTime(item.reviewed_at)} · ${SOURCE_LABEL[item.source || 'unknown']?.text || item.source}`,
              }))}
            />
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              disabled={!selectedCutoff || freezing}
              loading={freezing}
              onClick={() => void handleFreezeAndTrain()}
            >
              冻结为训练快照并去训练
            </Button>
          </Space>
        }
      >
        {selectedEvent && (
          <Alert
            style={{ marginBottom: 12 }}
            type="success"
            showIcon
            message={`将纳入审核时间 ≤ ${formatTime(selectedEvent.reviewed_at)} 的全部 ${slot} 入库记录`}
            description="同一截止时间重复冻结是幂等的，不会再复制一份文件。快照用时间标识，不再按 v1/v2 递增。"
          />
        )}
        <Table
          rowKey={(row) => row.event_id || `${row.dataset_version_id}-${row.reviewed_at}`}
          size="small"
          loading={loading}
          dataSource={ledger?.events || []}
          columns={eventColumns}
          pagination={{ pageSize: 10 }}
          onRow={(row) => ({
            onClick: () => setSelectedCutoff(row.reviewed_at || null),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>

      <Card size="small" title="训练快照（按时间）">
        <Table
          rowKey={(row) => freezeIdOf(slot, row) || `${row.created_at}-${row.snapshot_version}`}
          size="small"
          loading={loading}
          dataSource={ledger?.freeze_versions || []}
          columns={freezeColumns}
          pagination={{ pageSize: 8 }}
          expandable={{
            expandedRowRender: (row) => (
              <Table
                size="small"
                pagination={false}
                rowKey={(item, index) => String(item.event_id || item.dataset_version_id || index)}
                dataSource={row.included_events || []}
                columns={[
                  {
                    title: '来源',
                    dataIndex: 'source',
                    render: (value: string) => SOURCE_LABEL[value || 'unknown']?.text || value || '—',
                  },
                  { title: '确认箱', dataIndex: 'dataset_version_id', ellipsis: true },
                  {
                    title: '审核结束',
                    dataIndex: 'reviewed_at',
                    render: (value: string) => formatTime(value),
                  },
                  { title: '文件', dataIndex: 'file_path', ellipsis: true },
                ]}
              />
            ),
            rowExpandable: (row) => (row.included_events || []).length > 0,
          }}
        />
      </Card>
      <Drawer
        title={`快照内容 · ${preview?.freeze_id || ''}`}
        width={720}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
      >
        {previewLoading ? <Text>读取中…</Text> : null}
        {preview ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Descriptions size="small" bordered column={2}>
              {/* @AI_GENERATED: The drawer uses the same observation contract as the status card. */}
              <Descriptions.Item label="行数">
                {(preview.dataset_observation?.row_count ?? preview.row_count).toLocaleString('zh-CN')}
              </Descriptions.Item>
              <Descriptions.Item label="独立 device_id">
                {preview.dataset_observation?.device_id_count?.toLocaleString('zh-CN') ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="物理序列数">
                {preview.dataset_observation?.series_count?.toLocaleString('zh-CN')
                  ?? preview.device_count?.toLocaleString('zh-CN')
                  ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="原始设备日">
                {preview.dataset_observation?.device_day_count_raw?.toLocaleString('zh-CN') ?? '—'}
              </Descriptions.Item>
              {slot === 'pv_tsc' && (
                <Descriptions.Item label="288×3 网格合格设备日" span={2}>
                  {preview.dataset_observation?.grid?.train_eligible_device_days?.toLocaleString('zh-CN') ?? '—'}
                </Descriptions.Item>
              )}
              {/* @AI_GENERATED: end */}
              <Descriptions.Item label="时间范围" span={2}>
                {preview.time_start || '—'} ~ {preview.time_end || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="文件" span={2}>{preview.artifact_ref || '—'}</Descriptions.Item>
            </Descriptions>
            <Card size="small" title="类别分布">
              {Object.keys(preview.label_distribution || {}).length === 0 ? (
                <Text type="secondary">没有 label 列</Text>
              ) : (
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  {(() => {
                    const entries = Object.entries(preview.label_distribution || {});
                    const maxCount = Math.max(...entries.map(([, count]) => Number(count) || 0), 1);
                    return entries.map(([label, count]) => (
                      <div key={label}>
                        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                          <Text>{label}</Text>
                          <Text type="secondary">{count}</Text>
                        </Space>
                        <div style={{ background: '#f0f0f0', height: 8, borderRadius: 4 }}>
                          <div
                            style={{
                              width: `${Math.round((Number(count) / maxCount) * 100)}%`,
                              height: 8,
                              borderRadius: 4,
                              background: '#1677ff',
                            }}
                          />
                        </div>
                      </div>
                    ));
                  })()}
                </Space>
              )}
            </Card>
            <Card size="small" title="标签形态（reference-waveforms）">
              {waveforms.length === 0 ? (
                <Text type="secondary">这份快照没有可画的类别代表波形。</Text>
              ) : (
                waveforms.map((waveform) => (
                  <div key={waveform.label_id} style={{ marginBottom: 12 }}>
                    <Text>
                      {waveform.label_name} · {waveform.point_count} 点
                    </Text>
                    <SlotWaveformChart
                      timestamps={waveform.timestamps}
                      series={waveform.series}
                      height={200}
                    />
                  </div>
                ))
              )}
            </Card>
            <Table
              size="small"
              rowKey={(_, index) => String(index)}
              pagination={{ pageSize: 8 }}
              dataSource={preview.sample_rows}
              columns={(preview.column_names || []).slice(0, 8).map((col) => ({
                title: col,
                dataIndex: col,
                ellipsis: true,
                render: (value: unknown) => (value == null ? '—' : String(value)),
              }))}
            />
          </Space>
        ) : null}
      </Drawer>
    </Space>
  );
};

export default CumulativeTrainingLedgerPage;
