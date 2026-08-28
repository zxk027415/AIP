/**
 * SlotLabelProposalReviewPanel — 聚类提案图形化审核（天/点共用，数据按 slot 隔离）。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Drawer,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { CheckOutlined, StopOutlined } from '@ant-design/icons';
import { trainingWorkspaceApi } from '../../services/iterativeLabelingApi';
import type { PvProductSlot } from '../../config/slotProductConfig';

const { Text, Paragraph } = Typography;

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
  members_total?: number;
  waveforms?: Record<string, Array<{ time: string; value: number | null }>>;
  registry_label_names?: string[];
};

function Sparkline({ points }: { points: Array<{ time: string; value: number | null }> }) {
  const values = points.map((p) => p.value).filter((v): v is number => v != null);
  if (values.length < 2) return <Text type="secondary">无可用曲线</Text>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 420;
  const h = 120;
  const path = points
    .map((p, i) => {
      const x = (i / Math.max(points.length - 1, 1)) * w;
      const y = h - ((p.value == null ? min : p.value) - min) / span * h;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ background: '#0f172a08', borderRadius: 6 }}>
      <path d={path} fill="none" stroke="#1677ff" strokeWidth="2" />
    </svg>
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
  const registryOptions = (detail?.registry_label_names || []).map((name) => ({ value: name, label: name }));
  const selectedKeys = useMemo(() => {
    const all = current?.selected_member_keys || current?.member_keys || [];
    const drop = new Set(excluded[activeCluster] || []);
    return all.filter((k) => !drop.has(k));
  }, [current, excluded, activeCluster]);

  const waveformKey = current?.representative_member_key || selectedKeys[0] || '';
  const waveform = (detail?.waveforms || {})[waveformKey] || [];
  const unchangedClusterName = /^cluster_\d+$/.test(String(draftNames[activeCluster] || ''));

  const persistCluster = async () => {
    if (!proposalId || !activeCluster) return;
    await trainingWorkspaceApi.patchLabelProposal(proposalId, {
      slot,
      clusters: {
        [activeCluster]: {
          proposed_label_name: draftNames[activeCluster],
          selected_member_keys: selectedKeys,
        },
      },
    });
  };

  const handleConfirm = async () => {
    if (!proposalId || !detail) return;
    setActing(true);
    try {
      await persistCluster();
      const names: Record<string, string> = {};
      Object.keys(detail.clusters || {}).forEach((cid) => {
        names[cid] = draftNames[cid] || `cluster_${cid}`;
      });
      await trainingWorkspaceApi.confirmLabelProposal(proposalId, { slot, label_names: names });
      message.success('已确认并写入当前场景累计账本');
      onChanged?.();
      onClose();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: { message?: string } } }; message?: string };
      message.error(e.response?.data?.detail?.message || e.message || '确认失败');
    } finally {
      setActing(false);
    }
  };

  const handleReject = async () => {
    if (!proposalId) return;
    setActing(true);
    try {
      await trainingWorkspaceApi.rejectLabelProposal(proposalId, { slot, reason: 'ui_reject' });
      message.success('已驳回提案，不会写入累计集');
      onChanged?.();
      onClose();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: { message?: string } } }; message?: string };
      message.error(e.response?.data?.detail?.message || e.message || '驳回失败');
    } finally {
      setActing(false);
    }
  };

  return (
    <Drawer
      title={`审核提案 · ${proposalId || ''} · ${slot}`}
      width={960}
      open={open}
      onClose={onClose}
      destroyOnClose
      extra={(
        <Space>
          <Button icon={<StopOutlined />} danger disabled={detail?.status !== 'proposal'} loading={acting} onClick={() => void handleReject()}>
            驳回提案
          </Button>
          <Button type="primary" icon={<CheckOutlined />} disabled={detail?.status !== 'proposal'} loading={acting} onClick={() => void handleConfirm()}>
            确认写入累计
          </Button>
        </Space>
      )}
    >
      {loading ? <Text>读取中…</Text> : null}
      {detail && detail.status !== 'proposal' ? (
        <Alert type="warning" showIcon message={`当前状态 ${detail.status}，只能查看`} style={{ marginBottom: 12 }} />
      ) : null}
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 240px', gap: 16 }}>
        <div>
          <Text strong>簇</Text>
          <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 8 }}>
            {clusters.map(([cid, cluster]) => (
              <Button
                key={cid}
                block
                type={cid === activeCluster ? 'primary' : 'default'}
                onClick={() => setActiveCluster(cid)}
              >
                <div style={{ textAlign: 'left' }}>
                  <div>簇 {cid} · {cluster.member_count ?? 0} 条</div>
                  {(cluster.suggested_label_names || []).slice(0, 2).map((name) => (
                    <Tag key={name} style={{ marginTop: 4 }}>可能：{name}</Tag>
                  ))}
                </div>
              </Button>
            ))}
          </Space>
        </div>
        <div>
          <Text strong>代表样本曲线</Text>
          <Paragraph type="secondary" style={{ marginTop: 4 }}>
            {waveformKey || '没有选中成员'} · 点路径看 i_cal/value，天路径同样画已有数值列
          </Paragraph>
          <Sparkline points={waveform} />
          <Table
            size="small"
            style={{ marginTop: 12 }}
            rowKey={(row, index) => String(row.member_key || index)}
            pagination={{ pageSize: 6 }}
            dataSource={(detail?.members_sample || []).filter((row) => {
              if (!current) return true;
              const keys = new Set(current.member_keys || []);
              return keys.size === 0 || keys.has(String(row.member_key || ''));
            })}
            columns={[
              { title: 'member_key', dataIndex: 'member_key', ellipsis: true },
              { title: 'device_id', dataIndex: 'device_id', width: 120 },
              { title: 'time', dataIndex: 'time', ellipsis: true },
            ]}
          />
        </div>
        <div>
          <Text strong>改标签 / 剔除成员</Text>
          <Alert
            style={{ margin: '8px 0' }}
            type={unchangedClusterName ? 'warning' : 'info'}
            showIcon
            message="建议标签只是提示"
            description={unchangedClusterName
              ? '未改名会按 cluster_N 进入当前场景标签注册表。'
              : '确认名不会自动填成「可能」标签，需你自己选定。'}
          />
          <Select
            style={{ width: '100%', marginBottom: 8 }}
            allowClear
            placeholder="从注册表选择"
            options={registryOptions}
            value={registryOptions.some((o) => o.value === draftNames[activeCluster]) ? draftNames[activeCluster] : undefined}
            onChange={(value) => setDraftNames((prev) => ({ ...prev, [activeCluster]: value || prev[activeCluster] }))}
          />
          <Input
            value={draftNames[activeCluster] || ''}
            onChange={(event) => setDraftNames((prev) => ({ ...prev, [activeCluster]: event.target.value }))}
            placeholder="确认名"
          />
          <Paragraph type="secondary" style={{ marginTop: 12 }}>
            当前保留 {selectedKeys.length} / {(current?.member_keys || []).length} 个成员
          </Paragraph>
          <Select
            mode="multiple"
            style={{ width: '100%' }}
            placeholder="剔除成员"
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
