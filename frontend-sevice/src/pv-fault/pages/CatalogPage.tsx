// @AI_GENERATED
/**
 * 平台数据集目录（数据集切片第 3 步）——「显式数据集窗口」。
 *
 * 用户原话要求：先把数据集**做质量检测然后发布**、**可以用的直接就可以选择**、
 * 在**每个数据集后面加上可适用的路径**、**新到的数据集才需要检测发布**。
 *
 * 因此本页分两区：
 * 1. 已发布条目（不可变）：展示 **来源路径** / **检测结果** / **适用路径** / **覆盖缺口**，
 *    并可直接挂载进某个项目（登记资产 + 画像 + 数据版本）；
 * 2. 未发布的候选来源：三条路径的累计快照 + 可发现的数据集单元，一键「检测并发布」。
 *
 * 「来源路径」与「适用路径」是两个不同性质的字段，刻意并列显示：
 * - 来源路径（`origin_slot`）：数据集由哪条路径产出；
 * - 适用路径（`applicable_paths`）：普通外部数据按标签粒度合同计算。
 *
 * 路径累计冻结快照（`origin=path_cumulative_snapshot`）是路径资产，强制只归自己的
 * `origin_slot`，即使底层保留 point 标签也不跨路径复用。
 */

import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Modal,
  Select,
  Skeleton,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { LinkOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { pvProjectsApi } from '../../services/pvProjectsApi';
import type {
  AvailableSourcesResult,
  CatalogEntry,
  DatasetUnitSummary,
  PathCumulativeSource,
  ProjectSummary,
} from '../../services/pvProjectsApi';

const { Title, Text } = Typography;

const SLOT_LABEL: Record<string, string> = {
  pv_day: '日路径',
  pv_point: '点路径',
  pv_tsc: 'TSC 路径',
};
const SLOT_ORDER = ['pv_day', 'pv_point', 'pv_tsc'];

/** 检测/发布与挂载用的默认字段映射（三路径累计快照的真实列名）。 */
const DEFAULT_MAPPING: Record<string, unknown> = {
  time_col: 'time',
  device_col: 'device_id',
  value_col: 'value',
  label_col: 'label',
};

function fmtNum(v?: number | null): string {
  if (v === undefined || v === null) return '—';
  return typeof v === 'number' ? v.toLocaleString('en-US') : String(v);
}

function fmtRatio(v?: number | null): string {
  if (v === undefined || v === null) return '—';
  return `${(v * 100).toFixed(2)}%`;
}

function fmtSize(bytes?: number | null): string {
  if (!bytes) return '—';
  const kb = bytes / 1024;
  return kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(1)} KB`;
}

function slotTag(slot?: string | null): JSX.Element {
  if (!slot) return <Text type="secondary">未判定</Text>;
  const color = slot === 'pv_day' ? 'blue' : slot === 'pv_point' ? 'purple' : 'geekblue';
  return <Tag color={color}>{SLOT_LABEL[slot] || slot}</Tag>;
}

export function CatalogPage(): JSX.Element {
  const [entries, setEntries] = useState<CatalogEntry[]>([]);
  const [sources, setSources] = useState<AvailableSourcesResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyRef, setBusyRef] = useState<string | null>(null);

  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [mountTarget, setMountTarget] = useState<CatalogEntry | null>(null);
  const [mountProject, setMountProject] = useState<string | undefined>();
  const [mountSlot, setMountSlot] = useState<string>('pv_day');
  const [mounting, setMounting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([pvProjectsApi.listCatalog(), pvProjectsApi.listAvailableSources(200)])
      .then(([cat, src]) => {
        setEntries(cat.entries);
        setSources(src);
      })
      .catch(() => setError('数据集目录读取失败（后端 8081 是否在运行？）'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const inspectAndPublish = async (
    datasetRef: string,
    originSlot?: string,
    displayName?: string,
    origin?: string,
  ) => {
    setBusyRef(datasetRef);
    try {
      const entry = await pvProjectsApi.publishCatalog({
        dataset_ref: datasetRef,
        mapping: DEFAULT_MAPPING,
        label_policy: { granularity: 'device_day' },
        origin_slot: originSlot,
        display_name: displayName,
        origin,
      });
      message.success(entry.idempotent_hit ? '该内容已发布过（幂等命中）' : '已检测并发布');
      load();
    } catch {
      message.error('检测 / 发布失败');
    } finally {
      setBusyRef(null);
    }
  };

  const openMount = async (entry: CatalogEntry) => {
    setMountTarget(entry);
    const allowedSlots = SLOT_ORDER.filter((slot) => entry.applicable_paths?.[slot]?.applicable);
    const preferredSlot = entry.origin_slot && allowedSlots.includes(entry.origin_slot)
      ? entry.origin_slot
      : allowedSlots[0];
    setMountSlot(preferredSlot || '');
    setMountProject(undefined);
    try {
      const res = await pvProjectsApi.listProjects(false);
      setProjects(res.projects);
    } catch {
      setProjects([]);
    }
  };

  const doMount = async () => {
    if (!mountTarget || !mountProject || !mountSlot) {
      message.warning('请选择要挂载的项目和适用路径');
      return;
    }
    setMounting(true);
    try {
      const res = await pvProjectsApi.mountCatalogEntry(mountProject, {
        slot: mountSlot,
        entry_id: mountTarget.entry_id,
      });
      message.success(res.idempotent_hit ? '该项目已挂载同一数据集（幂等命中）' : '已挂载并生成数据版本');
      setMountTarget(null);
    } catch {
      message.error('挂载失败');
    } finally {
      setMounting(false);
    }
  };

  const entryColumns: ColumnsType<CatalogEntry> = [
    {
      title: '数据集',
      dataIndex: 'display_name',
      render: (_v, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.display_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.dataset_ref}
          </Text>
        </Space>
      ),
    },
    {
      title: '来源路径',
      dataIndex: 'origin_slot',
      width: 100,
      render: (v?: string | null) => slotTag(v),
    },
    {
      title: '检测结果',
      key: 'facts',
      render: (_v, row) => {
        const f = row.facts || {};
        return (
          <Space direction="vertical" size={0} style={{ fontSize: 12 }}>
            <Text>
              {fmtNum(f.row_count)} 行 · {fmtNum(f.device_count)} 设备 · {fmtNum(f.distinct_dates)} 个离散日期
            </Text>
            <Text type="secondary">
              跨度 {fmtNum(f.date_span_days)} 天 · 日期覆盖 {fmtRatio(f.date_coverage_ratio)} · 采样完整{' '}
              {fmtRatio(f.sampling_completeness)}
            </Text>
            <Text type="secondary">标签粒度：{f.label_granularity_detected || 'unknown'}</Text>
          </Space>
        );
      },
    },
    {
      title: '适用路径',
      key: 'applicable',
      width: 240,
      render: (_v, row) => (
        <Space wrap size={4}>
          {SLOT_ORDER.map((slot) => {
            const ap = row.applicable_paths?.[slot];
            if (!ap) return null;
            return (
              <Tooltip key={slot} title={ap.reason}>
                <Tag color={ap.applicable ? 'green' : 'default'}>
                  {SLOT_LABEL[slot]}
                  {ap.applicable ? ' ✓' : ' ✕'}
                </Tag>
              </Tooltip>
            );
          })}
        </Space>
      ),
    },
    {
      title: '覆盖',
      key: 'coverage',
      width: 130,
      render: (_v, row) => {
        const c = row.coverage || ({} as CatalogEntry['coverage']);
        return (
          <Tooltip title={(c.gaps || []).join(', ') || '无缺口'}>
            <Tag color={c.sufficient ? 'green' : 'orange'}>{c.sufficient ? '可用' : '仅实验'}</Tag>
          </Tooltip>
        );
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 110,
      render: (_v, row) => (
        <Button size="small" icon={<LinkOutlined />} onClick={() => openMount(row)}>
          挂载到项目
        </Button>
      ),
    },
  ];

  const sourceColumns: ColumnsType<PathCumulativeSource> = [
    {
      title: '累计训练数据集',
      dataIndex: 'display_name',
      render: (_v, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.display_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.dataset_ref}
          </Text>
        </Space>
      ),
    },
    { title: '来源路径', dataIndex: 'origin_slot', width: 100, render: (v) => slotTag(v) },
    { title: '大小', dataIndex: 'size_bytes', width: 100, render: (v?: number) => fmtSize(v) },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_v, row) => (
        <Button
          size="small"
          type="primary"
          ghost
          icon={<ThunderboltOutlined />}
          loading={busyRef === row.dataset_ref}
          onClick={() => inspectAndPublish(
            row.dataset_ref,
            row.origin_slot,
            row.display_name,
            row.origin,
          )}
        >
          检测并发布
        </Button>
      ),
    },
  ];

  const unitColumns: ColumnsType<DatasetUnitSummary> = [
    {
      title: '数据集单元',
      dataIndex: 'dataset_ref',
      render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '形态',
      dataIndex: 'unit_kind',
      width: 110,
      render: (v: string) => <Tag>{v === 'shard_group' ? '目录分片组' : '单文件'}</Tag>,
    },
    { title: '分片数', dataIndex: 'shard_count', width: 80 },
    { title: '大小', dataIndex: 'size_bytes', width: 100, render: (v?: number) => fmtSize(v) },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_v, row) => (
        <Button
          size="small"
          icon={<ThunderboltOutlined />}
          loading={busyRef === row.dataset_ref}
          onClick={() => inspectAndPublish(row.dataset_ref)}
        >
          检测并发布
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24, minHeight: '100%' }}>
      <div style={{ maxWidth: 1440, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <Title level={3} style={{ margin: 0 }}>
              数据集目录
            </Title>
            <Text type="secondary">
              平台级数据集资产：先质量检测再发布，发布后可被任一项目选用挂载。新到的数据集才需要检测发布。
            </Text>
          </div>
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
        </div>

        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

        <Card title={`已发布条目（${entries.length}）`} style={{ marginBottom: 16 }} size="small">
          {loading ? (
            <Skeleton active paragraph={{ rows: 3 }} />
          ) : entries.length === 0 ? (
            <Empty description="还没有已发布的数据集。先在下方的候选来源里「检测并发布」。" />
          ) : (
            <Table rowKey="entry_id" columns={entryColumns} dataSource={entries} pagination={false} size="small" />
          )}
        </Card>

        <Card title="路径累计训练数据集（已冻结快照）" style={{ marginBottom: 16 }} size="small">
          {loading ? (
            <Skeleton active paragraph={{ rows: 2 }} />
          ) : !sources || sources.path_cumulative.length === 0 ? (
            <Empty description="未发现 data/slot_datasets/<slot>/snapshots/ 下的冻结快照。" />
          ) : (
            <Table
              rowKey="dataset_ref"
              columns={sourceColumns}
              dataSource={sources.path_cumulative}
              pagination={false}
              size="small"
            />
          )}
        </Card>

        <Card
          title={`其它可检测来源（${sources?.discoverable_count ?? 0}）`}
          extra={<Text type="secondary" style={{ fontSize: 12 }}>已按数据集单元收敛，排除研究产物</Text>}
          size="small"
        >
          {loading ? (
            <Skeleton active paragraph={{ rows: 2 }} />
          ) : !sources || sources.discoverable.length === 0 ? (
            <Empty description="未发现可挂载的数据文件。" />
          ) : (
            <Table
              rowKey="dataset_ref"
              columns={unitColumns}
              dataSource={sources.discoverable}
              pagination={{ pageSize: 15, hideOnSinglePage: true }}
              size="small"
            />
          )}
        </Card>
      </div>

      <Modal
        title="挂载数据集到项目"
        open={!!mountTarget}
        onOk={doMount}
        confirmLoading={mounting}
        onCancel={() => setMountTarget(null)}
        okText="挂载"
        cancelText="取消"
        destroyOnHidden
      >
        {mountTarget && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>{mountTarget.display_name}</Text>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {mountTarget.dataset_ref}
                </Text>
              </div>
            </div>
            <div>
              <Text type="secondary">挂载到项目</Text>
              <Select
                style={{ width: '100%' }}
                placeholder="选择项目"
                value={mountProject}
                onChange={setMountProject}
                options={projects.map((p) => ({
                  value: p.project_id,
                  label: p.project_name || p.project_id,
                }))}
              />
            </div>
            <div>
              <Text type="secondary">目标路径</Text>
              <Select
                style={{ width: '100%' }}
                value={mountSlot || undefined}
                placeholder="该数据集没有可挂载路径"
                onChange={setMountSlot}
                options={SLOT_ORDER
                  .filter((slot) => mountTarget?.applicable_paths?.[slot]?.applicable)
                  .map((slot) => ({ value: slot, label: SLOT_LABEL[slot] }))}
                disabled={!SLOT_ORDER.some((slot) => mountTarget?.applicable_paths?.[slot]?.applicable)}
              />
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              挂载会登记数据资产 + 画像 + 不可变数据版本；同一内容重复挂载幂等命中，不产生重复版本。
            </Text>
          </Space>
        )}
      </Modal>
    </div>
  );
}

export default CatalogPage;

// @AI_GENERATED: end
