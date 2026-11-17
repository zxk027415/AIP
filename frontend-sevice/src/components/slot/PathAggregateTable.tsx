// @AI_GENERATED
/**
 * 三条诊断路径并列总览：路径 + 当前模型 + 最近精度 + 数据集。
 * 未选路径时作为精度运营 / 模型部署的默认视图，点行下钻写 ?slot=。
 */

import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Select, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { slotDatasetsApi } from '../../services/slotDatasetsApi';
import type { PathOverviewAccuracyAttribution, PathOverviewRow } from '../../services/slotDatasetsApi';

const { Text } = Typography;

const PATH_AGGREGATE_TABLE_WIDTH = 1160;

function fmtAcc(value: number | null | undefined): string {
  if (value === null || value === undefined) return '暂无（缺真值不计 0）';
  return `${(value * 100).toFixed(2)}%`;
}

/**
 * 精度的产出模型与项目归属副行。
 *
 * 四种状态都要说清，不能把「非项目来源」和「解析不出」混成一句空话：
 * - 跨多个模型累计 → 不归属单一项目（累计精度是跨天按样本加权的）
 * - 有项目归属     → 给出项目名并链到项目
 * - 内置规则回放   → 明确说没有模型
 * - 有模型无项目   → 说明是非项目来源
 */
function AccuracyOrigin({ att }: { att?: PathOverviewAccuracyAttribution | null }): JSX.Element | null {
  if (!att || !att.model_id) return null;
  const small = { fontSize: 12 } as const;

  if (att.multi_model) {
    return (
      <Text type="secondary" style={small}>
        跨 {att.model_count} 个模型累计，不归属单一项目
      </Text>
    );
  }
  if (att.model_id === 'loop_demo_rule') {
    return (
      <Text type="secondary" style={small}>
        内置规则回放，无模型
      </Text>
    );
  }
  const project = att.project;
  if (!project) {
    return (
      <Text type="secondary" style={small}>
        模型 {att.model_id} · 非项目来源
      </Text>
    );
  }
  return (
    <Space size={4} wrap>
      <Tag color="green" style={{ marginInlineEnd: 0 }}>
        <Link to={`/projects/${encodeURIComponent(project.project_id)}/overview`}>
          {project.project_name || project.project_id}
        </Link>
      </Tag>
      <Text type="secondary" style={small}>
        产出模型 {att.model_id}
        {att.latest_day ? ` · ${att.latest_day}` : ''}
      </Text>
    </Space>
  );
}

function fmtModel(value: string | null | undefined): string {
  if (!value) return '未设置';
  return value.length > 36 ? `${value.slice(0, 18)}…${value.slice(-10)}` : value;
}

export function PathAggregateTable({
  onSelectSlot,
  selectLabel = '查看该路径',
}: {
  onSelectSlot: (slot: string) => void;
  selectLabel?: string;
}): JSX.Element {
  const [rows, setRows] = useState<PathOverviewRow[]>([]);
  const [candidates, setCandidates] = useState<Array<{ dataset_ref: string }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingSlot, setSavingSlot] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    Promise.all([
      slotDatasetsApi.getPathOverview(),
      slotDatasetsApi.getFeedSources(200).catch(() => ({ candidates: [], current: {} })),
    ])
      .then(([data, feeds]) => {
        setRows(data.paths || []);
        setCandidates(feeds.candidates || []);
        setError(null);
      })
      .catch(() => {
        setError('三条路径总览读取失败');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const onSwitchFeed = async (slot: string, datasetRef: string | null) => {
    setSavingSlot(slot);
    try {
      await slotDatasetsApi.selectFeedSource(slot, datasetRef);
      message.success(datasetRef ? '已切换喂数数据集' : '已回落内置生成');
      reload();
    } catch {
      message.error('切换喂数数据集失败');
    } finally {
      setSavingSlot(null);
    }
  };

  const columns: ColumnsType<PathOverviewRow> = [
    {
      title: '路径',
      dataIndex: 'slot',
      width: 144,
      render: (_: string, row) => (
        <Space direction="vertical" size={0} style={{ width: '100%' }}>
          <Text strong>{row.label}</Text>
          <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
            {row.slot} · {row.granularity === 'point' ? '按点到达' : '等整日到达'}
          </Text>
        </Space>
      ),
    },
    {
      title: '当前模型 / champion',
      width: 192,
      render: (_: unknown, row) => (
        <Space direction="vertical" size={0} style={{ width: '100%' }}>
          <Text style={{ overflowWrap: 'anywhere' }}>{fmtModel(row.current_model)}</Text>
          <Text type="secondary" style={{ fontSize: 12, overflowWrap: 'anywhere' }}>
            champion {row.champion ? fmtModel(row.champion) : '空'}
          </Text>
        </Space>
      ),
    },
    {
      title: '最近精度 / 来源',
      width: 216,
      render: (_: unknown, row) => (
        <Space direction="vertical" size={2} style={{ width: '100%', minWidth: 0 }}>
          <Text>{fmtAcc(row.classifier_accuracy)}</Text>
          <AccuracyOrigin att={row.accuracy_attribution} />
        </Space>
      ),
    },
    {
      title: '当前数据集',
      width: 256,
      render: (_: unknown, row) => (
        <Space direction="vertical" size={4} style={{ width: '100%', minWidth: 0 }}>
          <Select
            showSearch
            allowClear
            size="small"
            style={{ width: '100%' }}
            placeholder="内置生成"
            value={row.dataset?.selected && row.dataset.dataset_ref ? row.dataset.dataset_ref : undefined}
            options={candidates.map((item) => ({ value: item.dataset_ref, label: item.dataset_ref }))}
            loading={savingSlot === row.slot}
            onChange={(value) => void onSwitchFeed(row.slot, value ?? null)}
            filterOption={(input, option) =>
              String(option?.label || '').toLowerCase().includes(input.toLowerCase())
            }
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.dataset?.selected && row.dataset.dataset_ref
              ? `${row.dataset.has_gold ? '自带真值' : '无真值'}${row.dataset.row_count != null ? ` · ${row.dataset.row_count} 行` : ''}`
              : '未选择（回落内置生成）'}
          </Text>
        </Space>
      ),
    },
    {
      title: '该路径可用数据集',
      width: 208,
      render: (_: unknown, row) => {
        const items = row.available_datasets || [];
        if (items.length === 0) return <Text type="secondary">暂无已发布条目</Text>;
        return (
          <Space direction="vertical" size={2} style={{ width: '100%' }}>
            {items.slice(0, 3).map((item) => (
              <Space key={item.dataset_ref} size={4} wrap style={{ width: '100%' }}>
                <Text style={{ fontSize: 12, overflowWrap: 'anywhere' }}>{item.display_name}</Text>
                {item.mountable ? (
                  <Tag color="green" style={{ marginInlineEnd: 0 }}>可挂载</Tag>
                ) : (
                  <Tag style={{ marginInlineEnd: 0 }}>待发布</Tag>
                )}
              </Space>
            ))}
            {items.length > 3 ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                另有 {items.length - 3} 个
              </Text>
            ) : null}
          </Space>
        );
      },
    },
    {
      title: '',
      width: 144,
      render: (_: unknown, row) => (
        <Button type="link" style={{ whiteSpace: 'nowrap' }} onClick={() => onSelectSlot(row.slot)}>
          {selectLabel}
        </Button>
      ),
    },
  ];

  return (
    <div>
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      <Table
        rowKey="slot"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
        size="middle"
        tableLayout="fixed"
        scroll={{ x: PATH_AGGREGATE_TABLE_WIDTH }}
      />
    </div>
  );
}

export default PathAggregateTable;
// @AI_GENERATED: end
