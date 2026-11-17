/**
 * SlotLabelProposalReviewPanel — 聚类提案图形化审核（天/点共用，数据按 slot 隔离）。
 * 打标模板把无标签样本聚成几簇；这里给人看形状、改业务名、决定进不进累计训练集。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Drawer,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { CheckOutlined, StopOutlined } from '@ant-design/icons';
import { trainingWorkspaceApi } from '../../services/iterativeLabelingApi';
import { getSlotWorkflowConfig, type PvProductSlot } from '../../config/slotProductConfig';
import SlotWaveformChart from './SlotWaveformChart';

const { Text, Paragraph, Title } = Typography;

type ClusterView = {
  cluster_id?: number;
  proposed_label_name?: string;
  member_count?: number;
  member_keys?: string[];
  selected_member_keys?: string[];
  suggested_label_names?: string[];
  representative_member_key?: string;
};

type ProposalDetail = {
  proposal_id: string;
  slot?: string;
  status?: string;
  clusters?: Record<string, ClusterView>;
  members_sample?: Array<Record<string, unknown>>;
  members_by_cluster?: Record<string, Array<Record<string, unknown>>>;
  members_total?: number;
  waveforms?: Record<string, Array<{ time: string; value?: number | null; i_cal?: number | null }>>;
  registry_label_names?: string[];
};

function Sparkline({ points }: { points: Array<{ time: string; value?: number | null; i_cal?: number | null }> }) {
  return (
    <SlotWaveformChart
      points={points}
      height={240}
      emptyText="这簇没有可画的电流/功率序列"
    />
  );
}

function DayFeatureBars({ points }: { points: Array<{ time: string; value: number | null }> }) {
  const values = points.map((p) => p.value).filter((v): v is number => v != null);
  if (!values.length) return <Text type="secondary">这簇没有可画的日特征数值</Text>;
  const max = Math.max(...values.map((v) => Math.abs(v)), 1);
  return (
    <Table
      size="small"
      pagination={false}
      rowKey={(_, index) => String(index)}
      dataSource={points.slice(0, 24).map((p, index) => ({ ...p, index }))}
      columns={[
        { title: '特征 / 时间', dataIndex: 'time', ellipsis: true },
        {
          title: '数值',
          dataIndex: 'value',
          width: 180,
          render: (value: number | null) => {
            if (value == null) return '—';
            const width = Math.max(4, Math.round((Math.abs(value) / max) * 120));
            return (
              <Space>
                <span style={{ display: 'inline-block', width, height: 8, background: '#1677ff', borderRadius: 2 }} />
                <Text>{value.toFixed(3)}</Text>
              </Space>
            );
          },
        },
      ]}
    />
  );
}

interface Props {
  slot: PvProductSlot;
  proposalId: string | null;
  open: boolean;
  onClose: () => void;
  onChanged?: () => void;
}

const SlotLabelProposalReviewPanel: React.FC<Props> = ({ slot, proposalId, open, onClose, onChanged }) => {
  const scene = getSlotWorkflowConfig(slot)?.shortLabel || '当前场景';
  // @AI_GENERATED: 三态区分 day/point/tsc；pv_tsc 是设备日聚合，证据是重叠模型窗口，不能复用 day 特征条或 point 逐点色带。
  const isDay = slot === 'pv_day';
  const isTsc = slot === 'pv_tsc';
  const useDayFeatureBars = isDay;
  const memberDayColumn = isDay || isTsc;
  // @AI_GENERATED: end
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [detail, setDetail] = useState<ProposalDetail | null>(null);
  const [activeCluster, setActiveCluster] = useState<string>('');
  const [draftNames, setDraftNames] = useState<Record<string, string>>({});
  const [excluded, setExcluded] = useState<Record<string, string[]>>({});

  const load = async () => {
    if (!proposalId) return;
    setLoading(true);
    try {
      const body = await trainingWorkspaceApi.getLabelProposal(proposalId, slot) as ProposalDetail;
      if (body.slot && body.slot !== slot) {
        message.error('提案不属于当前场景，已阻止跨仓读取');
        onClose();
        return;
      }
      setDetail(body);
      const first = Object.keys(body.clusters || {})[0] || '';
      setActiveCluster(first);
      const names: Record<string, string> = {};
      Object.entries(body.clusters || {}).forEach(([cid, cluster]) => {
        names[cid] = cluster.proposed_label_name || `cluster_${cid}`;
      });
      setDraftNames(names);
      setExcluded({});
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: { message?: string } } }; message?: string };
      message.error(e.response?.data?.detail?.message || e.message || '读取提案失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && proposalId) void load();
    if (!open) setDetail(null);
  }, [open, proposalId, slot]);

  const clusters = useMemo(() => Object.entries(detail?.clusters || {}), [detail]);
  const current = (detail?.clusters || {})[activeCluster];
  const registryOptions = useMemo(() => {
    const names = [
      ...(detail?.registry_label_names || []),
      ...((current?.suggested_label_names) || []),
    ];
    return [...new Set(names.filter(Boolean))].map((name) => ({ value: name, label: name }));
  }, [detail?.registry_label_names, current?.suggested_label_names]);
  const selectedKeys = useMemo(() => {
    const all = current?.selected_member_keys || current?.member_keys || [];
    const drop = new Set(excluded[activeCluster] || []);
    return all.filter((k) => !drop.has(k));
  }, [current, excluded, activeCluster]);

  const waveformKey = activeCluster || current?.representative_member_key || selectedKeys[0] || '';
  const waveform = (detail?.waveforms || {})[waveformKey]
    || (detail?.waveforms || {})[current?.representative_member_key || '']
    || [];
  const clusterMembers = (detail?.members_by_cluster || {})[activeCluster]
    || (detail?.members_sample || []).filter((row) => {
      if (!current) return true;
      const keys = new Set(current.member_keys || []);
      return keys.size === 0 || keys.has(String(row.member_key || ''));
    });
  const unchangedNames = clusters.filter(([cid]) => /^cluster_\d+$/.test(String(draftNames[cid] || '')));
  const currentUnnamed = /^cluster_\d+$/.test(String(draftNames[activeCluster] || ''));

  const handleConfirm = async () => {
    if (!proposalId || !detail) return;
    const unnamed = unchangedNames.map(([cid]) => `簇 ${cid} → ${draftNames[cid] || `cluster_${cid}`}`);
    Modal.confirm({
      title: `把这些簇写入${scene}累计训练集？`,
      content: (
        <Space direction="vertical" size={8}>
          <Text>确认后，留下的成员会进当前场景账本，训练时再冻结。不会立刻改生产模型。</Text>
          {clusters.map(([cid]) => (
            <Text key={cid}>簇 {cid}：{draftNames[cid] || `cluster_${cid}`} · 保留成员见右侧</Text>
          ))}
          {unnamed.length ? (
            <Alert type="warning" showIcon message="有簇还叫 cluster_N，会按这个名字进标签注册表。" />
          ) : null}
        </Space>
      ),
      okText: '确认写入',
      cancelText: '再改改',
      onOk: async () => {
        setActing(true);
        try {
          await trainingWorkspaceApi.patchLabelProposal(proposalId, {
            slot,
            clusters: Object.fromEntries(clusters.map(([cid, cluster]) => {
              const all = cluster.selected_member_keys || cluster.member_keys || [];
              const drop = new Set(excluded[cid] || []);
              return [cid, {
                proposed_label_name: draftNames[cid] || `cluster_${cid}`,
                selected_member_keys: all.filter((key) => !drop.has(key)),
              }];
            })),
          });
          const names: Record<string, string> = {};
          Object.keys(detail.clusters || {}).forEach((cid) => {
            names[cid] = draftNames[cid] || `cluster_${cid}`;
          });
          await trainingWorkspaceApi.confirmLabelProposal(proposalId, { slot, label_names: names });
          message.success(`已写入${scene}累计账本`);
          onChanged?.();
          onClose();
        } catch (err: unknown) {
          const e = err as { response?: { data?: { detail?: { message?: string } } }; message?: string };
          message.error(e.response?.data?.detail?.message || e.message || '确认失败');
        } finally {
          setActing(false);
        }
      },
    });
  };

  const handleReject = async () => {
    if (!proposalId) return;
    Modal.confirm({
      title: '驳回整份提案？',
      content: '所有簇都不会进累计训练集。已经聚好的结果会留在列表里，但不能再确认。',
      okText: '驳回',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setActing(true);
        try {
          await trainingWorkspaceApi.rejectLabelProposal(proposalId, { slot, reason: 'ui_reject' });
          message.success('已驳回，未写入累计集');
          onChanged?.();
          onClose();
        } catch (err: unknown) {
          const e = err as { response?: { data?: { detail?: { message?: string } } }; message?: string };
          message.error(e.response?.data?.detail?.message || e.message || '驳回失败');
        } finally {
          setActing(false);
        }
      },
    });
  };

  return (
    <Drawer
      title={`审核聚类提案 · ${scene}`}
      width={1040}
      open={open}
      onClose={onClose}
      destroyOnClose
      extra={(
        <Space>
          <Button icon={<StopOutlined />} danger disabled={detail?.status !== 'proposal'} loading={acting} onClick={() => void handleReject()}>
            整份不要
          </Button>
          <Button type="primary" icon={<CheckOutlined />} disabled={detail?.status !== 'proposal'} loading={acting} onClick={() => void handleConfirm()}>
            这些簇可以进训练集
          </Button>
        </Space>
      )}
    >
      {loading ? <Text>读取中…</Text> : null}
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="这是在审「长得像一类」的样本堆，不是逐条预测审核"
        description={(
          <span>
            打标模板把无标签数据聚成几堆（簇）。你要做的事：左边换一簇 → 中间看它长什么样、里面有哪些设备 → 右边给这簇起业务名（如「组串失配」），不像的样本剔掉。
            全部簇看完，再点右上角写入{scene}累计账本。灰色「可能：…」只是猜测，不会自动当标签。
          </span>
        )}
      />
      {detail && detail.status !== 'proposal' ? (
        <Alert type="warning" showIcon message={`这份提案已经是「${detail.status}」，只能查看，不能再确认或驳回`} style={{ marginBottom: 12 }} />
      ) : null}
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 260px', gap: 16 }}>
        <div>
          <Title level={5} style={{ marginTop: 0 }}>1. 选一簇</Title>
          <Paragraph type="secondary" style={{ marginBottom: 8 }}>每一簇打算变成一个故障类别。</Paragraph>
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            {clusters.map(([cid, cluster]) => (
              <Button
                key={cid}
                block
                type={cid === activeCluster ? 'primary' : 'default'}
                onClick={() => setActiveCluster(cid)}
              >
                <div style={{ textAlign: 'left' }}>
                  <div>簇 {cid} · {draftNames[cid] || cluster.proposed_label_name || `cluster_${cid}`}</div>
                  <Text type={cid === activeCluster ? undefined : 'secondary'} style={{ fontSize: 12 }}>
                    {cluster.member_count ?? 0} 条样本
                  </Text>
                  {(cluster.suggested_label_names || []).slice(0, 2).map((name) => (
                    <Tag key={name} style={{ marginTop: 4 }}>可能：{name}</Tag>
                  ))}
                </div>
              </Button>
            ))}
          </Space>
        </div>
        <div>
          <Title level={5} style={{ marginTop: 0 }}>2. 看这一簇长什么样</Title>
          {/* @AI_GENERATED: 三态说明，pv_tsc 以设备日时序 + 重叠窗口证据展示。 */}
          <Paragraph type="secondary" style={{ marginBottom: 8 }}>
            {isDay
              ? '天路径按日特征看形态，不是 5 分钟电流曲线。下面是代表样本的数值，再下面是这簇里有哪些设备/日。'
              : isTsc
                ? '时序分类按设备日聚合，一级单元是设备日最终标签，证据是 MultiRocket 重叠窗口。下面画这簇设备日的实测/理论电流时序，再下面是有哪些设备日。'
                : '点路径画这一簇全部成员的实测/理论电流，按时间排开。'}
          </Paragraph>
          {waveformKey ? (
            <Text style={{ display: 'block', marginBottom: 8 }}>
              簇 {activeCluster} · {waveform.length} 个点（整簇按时间排列，不是只截代表样本一两笔）
            </Text>
          ) : <Text type="secondary">没有选中成员</Text>}
          {useDayFeatureBars ? <DayFeatureBars points={waveform} /> : <Sparkline points={waveform} />}
          {/* @AI_GENERATED: end */}
          <Table
            size="small"
            style={{ marginTop: 12 }}
            rowKey={(row, index) => String(row.member_key || index)}
            pagination={{ pageSize: 6 }}
            locale={{ emptyText: '这簇没有成员行' }}
            dataSource={clusterMembers}
            columns={[
              { title: '样本', dataIndex: 'member_key', ellipsis: true },
              { title: '设备', dataIndex: 'device_id', width: 88 },
              { title: memberDayColumn ? '业务日' : '时间', dataIndex: memberDayColumn ? 'date' : 'time', ellipsis: true, render: (_: unknown, row: Record<string, unknown>) => String(row.date || row.time || '—') },
            ]}
          />
        </div>
        <div>
          <Title level={5} style={{ marginTop: 0 }}>3. 给这簇起名</Title>
          <Alert
            style={{ margin: '0 0 8px' }}
            type={currentUnnamed ? 'warning' : 'info'}
            showIcon
            message={currentUnnamed ? '还没起业务名' : '确认名已改'}
            description={currentUnnamed
              ? '不改的话，会以 cluster_N 进当前场景标签注册表。建议从下面选已有故障名，或自己输入。'
              : '「可能」标签不会自动填进来，这个名字才是写入累计时用的。'}
          />
          <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>已有故障类别</Text>
          <Select
            style={{ width: '100%', marginBottom: 8 }}
            allowClear
            placeholder="从注册表选择，例如 组串失配"
            options={registryOptions}
            value={registryOptions.some((o) => o.value === draftNames[activeCluster]) ? draftNames[activeCluster] : undefined}
            onChange={(value) => setDraftNames((prev) => ({ ...prev, [activeCluster]: value || prev[activeCluster] }))}
          />
          <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>或手写确认名</Text>
          <Input
            value={draftNames[activeCluster] || ''}
            onChange={(event) => setDraftNames((prev) => ({ ...prev, [activeCluster]: event.target.value }))}
            placeholder="例如：组串失配"
          />
          <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 4 }}>
            当前这簇保留 {selectedKeys.length} / {(current?.member_keys || []).length} 条。不像的剔掉，不要整份驳回。
          </Paragraph>
          <Select
            mode="multiple"
            style={{ width: '100%' }}
            placeholder="选择要剔除的样本"
            value={excluded[activeCluster] || []}
            options={(current?.member_keys || []).map((key) => ({ value: key, label: key }))}
            onChange={(value) => setExcluded((prev) => ({ ...prev, [activeCluster]: value }))}
          />
        </div>
      </div>
    </Drawer>
  );
};

export default SlotLabelProposalReviewPanel;
