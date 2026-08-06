// @AI_GENERATED: algorithm-deployment-refactor 9.3 + 阶段3
/**
 * SchedulerTab.tsx — "算法部署 → 定时调度" Tab
 *
 * 新增（阶段3）：cron_expr 列 + 编辑弹窗（热更新）+ 立即触发按钮 + 顶部流程说明
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Button, Descriptions, Divider, Dropdown, Empty, Form, Input, InputNumber,
  Modal, Popconfirm, Select, Space, Switch, Table, Tag, Tooltip, Typography, message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { MenuProps } from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  DatabaseOutlined, EditOutlined, FundViewOutlined, MoreOutlined, PlayCircleOutlined, PlusOutlined, ProfileOutlined,
  ReloadOutlined, StopOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import {
  schedulerTaskApi,
  type DataPullEvidence, type ManualMockDataFeedResponse, type MockDataFeedPreview,
  type ScheduledTaskCreate, type ScheduledTaskDetail, type ScheduledTaskSummary,
  type PvMockFeedDataEvidence, type PvMockFeedPreview, type ManualPvMockFeedResponse,
  type PvSourceFingerprint, type PvMockFeedLastRecord, type PvMockFeedIngestBatch,
} from '../../services/deploymentApi';
// @AI_GENERATED: 后端部分时间戳是 UTC 裸字符串（fed_at / ingested_at），
// 需归一化后再转本地；调度自身字段（上次执行时间等）存的是本地时间，不能一起转。
import { formatBackendDateTime } from '../../utils/datetime';
// @AI_GENERATED: end
import { getSchedulerStatus, type FailureRecord } from '../../services/schedulerApi';

const { Text } = Typography;

const STATUS_TAG: Record<ScheduledTaskSummary['status'], { color: string; label: string }> = {
  running: { color: 'processing', label: '运行中' },
  stopped: { color: 'default', label: '已停止' },
  failed: { color: 'error', label: '失败' },
};
const LAST_EXEC_TAG: Record<NonNullable<ScheduledTaskSummary['last_execution']>, { color: string; label: string }> = {
  success: { color: 'success', label: '成功' },
  failed: { color: 'error', label: '失败' },
  skipped: { color: 'warning', label: '跳过' },
};
const SCHEDULE_TYPE_LABEL: Record<ScheduledTaskSummary['schedule_type'], string> = {
  rolling_daily: '每日滚动', cron: 'Cron 表达式', interval: '固定间隔',
};
const PIPELINE_OPTIONS = [
  { value: 'load_forecast', label: '负荷预测（load_forecast）' },
  { value: 'pv_fault', label: '光伏故障（pv_fault）' },
];
const SLOT_OPTIONS = [
  { value: 'load_forecast', label: 'load_forecast（正式负荷预测）' },
  { value: 'pv_fault', label: 'pv_fault（光伏故障诊断）' },
  { value: 'default', label: 'default（默认槽）' },
];

const DEPRECATED_TASK_IDS = new Set(['pv_data_pull']);

function resolvePipelineFilter(storySlot?: string): 'load_forecast' | 'pv_fault' | null {
  if (storySlot === 'pv_fault') return 'pv_fault';
  if (!storySlot || storySlot === 'load_forecast' || storySlot === 'default') return 'load_forecast';
  return null;
}

// @AI_GENERATED: manual mock-feed UI guard
const MOCK_DATA_FEED_TASK_ID = 'mock_data_feed';
const PV_MOCK_DATA_FEED_TASK_ID = 'pv_mock_data_feed';

function formatMockFeedPreview(preview: MockDataFeedPreview): string {
  if (preview.exhausted) return 'CSV 模拟数据已全部投喂。';
  const next = preview.next_business_date ?? '—';
  const completeness = preview.next_is_complete_day ? '完整 96 点' : `不完整 ${preview.next_source_row_count} 点`;
  if (preview.state === 'initial_feed') return `尚未投喂；首次将公开 ${next}（${completeness}）。`;
  if (preview.state === 'continue_current_business_day') return `当前模拟日还有历史遗留行待补齐；将继续公开 ${next}（${completeness}）。`;
  return `当前模拟业务日 ${preview.current_business_date ?? '—'} 已投喂；下一业务日为 ${next}（${completeness}）。`;
}

function formatPvMockFeedPreview(preview: PvMockFeedPreview): string {
  if (preview.exhausted) {
    const fp = preview.source_fingerprint;
    const range = fp?.date_min && fp?.date_max ? `${fp.date_min} ~ ${fp.date_max}` : '当前 parquet';
    const days = fp?.row_count != null ? `，约 ${fp.row_count} 行` : '';
    return `模拟源日历已全部投喂完（最近业务日 ${preview.current_business_date ?? '—'}；源范围 ${range}${days}）。这不是按钮坏了，而是源里没有更晚的自然日。可点「重置喂数进度」从首日重演，或更换更长的 parquet。`;
  }
  const next = preview.next_business_date ?? '—';
  const devices = preview.next_device_count;
  const rows = preview.next_source_row_count;
  if (preview.state === 'initial_feed') return `尚未投喂；首次将公开 ${next}（${devices} 台设备 × ${rows} 行）。`;
  return `当前业务日 ${preview.current_business_date ?? '—'} 已投喂；下一业务日为 ${next}（${devices} 台设备 × ${rows} 行）。点「推进下一天」确认后写入。`;
}
// @AI_GENERATED: end

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }); } catch { return iso; }
}

interface SchedulerTabProps {
  /** storySlot — 从精度运营故事线带回的槽位上下文，由部署页页头展示。 */
  storySlot?: string;
}

interface TaskDetailState {
  open: boolean;
  loading: boolean;
  data: ScheduledTaskDetail | null;
  dataPullEvidence: DataPullEvidence | null;
  dataPullEvidenceLoading: boolean;
  dataPullEvidenceError: string | null;
  // @AI_GENERATED: pv mock feed data evidence
  pvDataEvidence: PvMockFeedDataEvidence | null;
  pvDataEvidenceLoading: boolean;
  pvDataEvidenceError: string | null;
  /** 当前喂数源指纹 — 让详情页能看出「现在喂的是哪份数据集」 */
  pvFeedSource: PvSourceFingerprint | null;
  /** 最近一次喂数记录 — 上次喂了哪个业务日 */
  pvLastFeed: PvMockFeedLastRecord | null;
  /** 最近一次真实入库批次 — 「我最近拉到了什么」 */
  pvLastIngest: PvMockFeedIngestBatch | null;
  // @AI_GENERATED: end
}

const SchedulerTab: React.FC<SchedulerTabProps> = ({ storySlot }) => {
  const navigate = useNavigate();
  const pipelineFilter = resolvePipelineFilter(storySlot);
  const isPvSlot = pipelineFilter === 'pv_fault';
  const [messageApi, contextHolder] = message.useMessage();
  const [tasks, setTasks] = useState<ScheduledTaskSummary[]>([]);
  const [taskFailures, setTaskFailures] = useState<Record<string, FailureRecord | undefined>>({});
  const [mockFeedPreview, setMockFeedPreview] = useState<MockDataFeedPreview | null>(null);
  // @AI_GENERATED: pv mock feed preview
  const [pvMockFeedPreview, setPvMockFeedPreview] = useState<PvMockFeedPreview | null>(null);
  const [pvMockFeedPreviewError, setPvMockFeedPreviewError] = useState<string | null>(null);
  // @AI_GENERATED: end
  const [loading, setLoading] = useState(false);
  const [rowActionLoading, setRowActionLoading] = useState<Record<string, boolean>>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [form] = Form.useForm<ScheduledTaskCreate>();
  const [editOpen, setEditOpen] = useState(false);
  const [editTask, setEditTask] = useState<ScheduledTaskSummary | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editForm] = Form.useForm<{ cron_expr: string; trigger_time: string; max_window_days: number | null }>();
  const [detail, setDetail] = useState<TaskDetailState>({
    open: false,
    loading: false,
    data: null,
    dataPullEvidence: null,
    dataPullEvidenceLoading: false,
    dataPullEvidenceError: null,
    pvDataEvidence: null,
    pvDataEvidenceLoading: false,
    pvDataEvidenceError: null,
    pvFeedSource: null,
    pvLastFeed: null,
    pvLastIngest: null,
  });

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const [res, schedulerStatus] = await Promise.all([
        schedulerTaskApi.listScheduledTasks(),
        getSchedulerStatus().catch(() => null),
      ]);
      const nextTasks = res.tasks ?? [];
      setTasks(nextTasks);

      const failures: Record<string, FailureRecord> = {};
      if (schedulerStatus?.pipelines) {
        for (const pipelineStatus of Object.values(schedulerStatus.pipelines)) {
          for (const taskStatus of pipelineStatus.tasks ?? []) {
            const latest = taskStatus.recent_failures?.[0];
            if (latest) failures[taskStatus.task_id] = latest;
          }
        }
      }
      setTaskFailures(failures);
      if (nextTasks.some((task) => task.task_id === MOCK_DATA_FEED_TASK_ID)) {
        try {
          const status = await schedulerTaskApi.getMockDataFeedStatus();
          setMockFeedPreview(status.preview);
        } catch {
          setMockFeedPreview(null);
        }
      } else {
        setMockFeedPreview(null);
      }
      // @AI_GENERATED: load pv mock feed preview
      if (nextTasks.some((task) => task.task_id === PV_MOCK_DATA_FEED_TASK_ID)) {
        try {
          const pvStatus = await schedulerTaskApi.getPvMockFeedStatus();
          setPvMockFeedPreview(pvStatus.preview);
          setPvMockFeedPreviewError(null);
        } catch (err: any) {
          setPvMockFeedPreview(null);
          setPvMockFeedPreviewError(
            err?.response?.data?.detail
            || err?.message
            || '无法读取光伏喂数状态',
          );
        }
      } else {
        setPvMockFeedPreview(null);
        setPvMockFeedPreviewError(null);
      }
      // @AI_GENERATED: end
    } catch (err: any) {
      messageApi.error(`加载失败：${err?.message ?? String(err)}`);
      setTasks([]);
      setTaskFailures({});
      setMockFeedPreview(null);
      setPvMockFeedPreview(null);
      setPvMockFeedPreviewError(null);
    } finally {
      setLoading(false);
    }
  }, [messageApi]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const visibleTasks = useMemo(() => {
    return tasks.filter((task) => {
      if (DEPRECATED_TASK_IDS.has(task.task_id)) return false;
      if (!pipelineFilter) return true;
      return task.pipeline === pipelineFilter;
    });
  }, [tasks, pipelineFilter]);

  const handleStart = async (task: ScheduledTaskSummary) => {
    setRowActionLoading((s) => ({ ...s, [task.task_id]: true }));
    try { await schedulerTaskApi.startScheduledTask(task.task_id); messageApi.success(`已启动：${task.name}`); await loadTasks(); }
    catch (err: any) { messageApi.error(`启动失败：${err?.message ?? String(err)}`); }
    finally { setRowActionLoading((s) => ({ ...s, [task.task_id]: false })); }
  };

  const handleStop = async (task: ScheduledTaskSummary) => {
    setRowActionLoading((s) => ({ ...s, [task.task_id]: true }));
    try { await schedulerTaskApi.stopScheduledTask(task.task_id); messageApi.success(`已停止：${task.name}`); await loadTasks(); }
    catch (err: any) { messageApi.error(`停止失败：${err?.message ?? String(err)}`); }
    finally { setRowActionLoading((s) => ({ ...s, [task.task_id]: false })); }
  };

  const handleTriggerNow = async (task: ScheduledTaskSummary) => {
    setRowActionLoading((s) => ({ ...s, [task.task_id]: true }));
    try {
      await schedulerTaskApi.triggerTaskNow(task.task_id);
      messageApi.success(`已触发：${task.name}（后台执行中）`);
      // 触发后 3 / 6 / 12 秒自动刷新列表，让状态变化及时反映到 UI
      [3000, 3000, 6000].reduce((chain, delay) => {
        return chain.then(() => new Promise((resolve) => setTimeout(resolve, delay))).then(() => loadTasks());
      }, Promise.resolve());
    } catch (err: any) {
      messageApi.error(`触发失败：${err?.message ?? String(err)}`);
    } finally {
      setRowActionLoading((s) => ({ ...s, [task.task_id]: false }));
    }
  };

  // @AI_GENERATED: manual mock-feed confirmation interaction
  const requestMockDataFeed = async (task: ScheduledTaskSummary, advance = false) => {    setRowActionLoading((s) => ({ ...s, [task.task_id]: true }));
    try {
      const response: ManualMockDataFeedResponse = await schedulerTaskApi.manualMockDataFeed(advance);
      setMockFeedPreview(response.preview);
      if (response.status === 'confirmation_required') {
        Modal.confirm({
          title: '当前模拟业务日已投喂',
          content: `已公开 ${response.preview.current_business_date ?? '当前业务日'}。是否推进到 ${response.preview.next_business_date ?? '下一业务日'}？取消或关闭后不会写入任何新数据。`,
          okText: '推进下一业务日',
          cancelText: '停留在当前日',
          onOk: () => requestMockDataFeed(task, true),
        });
        return;
      }
      if (response.status === 'exhausted') {
        messageApi.info(response.message);
        return;
      }
      const result = response.feed_result;
      const completeness = result?.is_complete_day ? '完整 96 点' : `不完整 ${result?.source_row_count ?? 0} 点`;
      messageApi.success(`已投喂 ${result?.business_date ?? '业务日'}：新增 ${result?.inserted_row_count ?? 0} 行（${completeness}）`);
      await loadTasks();
    } catch (err: any) {
      messageApi.error(`模拟喂数据失败：${err?.message ?? String(err)}`);
    } finally {
      setRowActionLoading((s) => ({ ...s, [task.task_id]: false }));
    }
  };
  // @AI_GENERATED: end

  // @AI_GENERATED: pv mock feed interaction
  const requestPvMockDataFeed = async (task: ScheduledTaskSummary, advance = false) => {
    setRowActionLoading((s) => ({ ...s, [task.task_id]: true }));
    try {
      const response: ManualPvMockFeedResponse = await schedulerTaskApi.manualPvMockDataFeed(advance);
      setPvMockFeedPreview(response.preview);
      if (response.status === 'confirmation_required') {
        Modal.confirm({
          title: '推进到下一业务日',
          content: `当前业务日 ${response.preview.current_business_date ?? '—'} 已投喂完毕。确认后将写入下一业务日 ${response.preview.next_business_date ?? '—'}（约 ${response.preview.next_device_count} 台设备 × ${response.preview.next_source_row_count} 行）。取消则不写入。`,
          okText: '确认推进下一天',
          cancelText: '暂不推进',
          onOk: () => requestPvMockDataFeed(task, true),
        });
        return;
      }
      if (response.status === 'exhausted') {
        messageApi.info(response.message);
        return;
      }
      const result = response.feed_result;
      // @AI_GENERATED: 按真实入库数区分提示语气，不能不管插了多少行都报绿色成功。
      // status === 'fed_no_new_data' 时该业务日已全部存在于库中，本次一行没插，
      // 用 warning 而非 success，避免用户误以为喂进了新数据。
      if (response.status === 'fed_no_new_data') {
        messageApi.warning(
          `业务日 ${result?.business_date ?? '—'} 未写入任何新数据（该日观测已存在于库中，`
          + `源 ${result?.source_row_count ?? 0} 行全部跳过）。喂数进度已推进，但库内容未变化。`,
        );
      } else {
        messageApi.success(
          `光伏业务日 ${result?.business_date ?? '—'} 已写入：${result?.inserted_row_count ?? 0} 行新增（${result?.device_count ?? 0} 台设备），${result?.skipped_row_count ?? 0} 行重复跳过`,
        );
      }
      // @AI_GENERATED: end
      await loadTasks();
    } catch (err: any) {
      messageApi.error(
        err?.response?.data?.detail
        || err?.response?.data?.message
        || err?.message
        || '光伏喂数据失败',
      );
    } finally {
      setRowActionLoading((s) => ({ ...s, [task.task_id]: false }));
    }
  };

  /** 行内按钮：若已需跨日确认，先弹窗再 advance=true，避免连点无感。 */
  const handlePvMockFeedClick = (task: ScheduledTaskSummary) => {
    const preview = pvMockFeedPreview;
    if (preview?.requires_advance_confirmation && !preview.exhausted) {
      Modal.confirm({
        title: '推进到下一业务日',
        content: `当前业务日 ${preview.current_business_date ?? '—'} 已投喂完毕。确认后将写入下一业务日 ${preview.next_business_date ?? '—'}（约 ${preview.next_device_count} 台设备 × ${preview.next_source_row_count} 行）。`,
        okText: '确认推进下一天',
        cancelText: '暂不推进',
        onOk: () => requestPvMockDataFeed(task, true),
      });
      return;
    }
    void requestPvMockDataFeed(task, false);
  };
  // @AI_GENERATED: end

  const handleViewDetail = async (task: ScheduledTaskSummary) => {
    const needsDataEvidence = task.task_id === 'lf_data_pull';
    // @AI_GENERATED: pv_mock_data_feed 加载数据证据
    const needsPvEvidence = task.task_id === PV_MOCK_DATA_FEED_TASK_ID;
    // @AI_GENERATED: end
    setDetail({
      open: true,
      loading: true,
      data: null,
      dataPullEvidence: null,
      dataPullEvidenceLoading: needsDataEvidence,
      dataPullEvidenceError: null,
      pvDataEvidence: null,
      pvDataEvidenceLoading: needsPvEvidence,
      pvDataEvidenceError: null,
      pvFeedSource: null,
      pvLastFeed: null,
      pvLastIngest: null,
    });
    try {
      const data = await schedulerTaskApi.getScheduledTask(task.task_id);
      setDetail((previous) => ({ ...previous, loading: false, data }));
      if (!needsDataEvidence && !needsPvEvidence) return;
      if (needsDataEvidence) {
        try {
          const response = await schedulerTaskApi.getDataPullEvidence(task.task_id);
          setDetail((previous) => ({
            ...previous,
            dataPullEvidence: response.evidence,
            dataPullEvidenceLoading: false,
          }));
        } catch (err: any) {
          setDetail((previous) => ({
            ...previous,
            dataPullEvidenceLoading: false,
            dataPullEvidenceError: err?.message ?? String(err),
          }));
        }
      }
      // @AI_GENERATED: load pv mock feed data evidence
      if (needsPvEvidence) {
        try {
          const pvResp = await schedulerTaskApi.getPvMockFeedDataEvidence(50);
          setDetail((previous) => ({
            ...previous,
            pvDataEvidence: pvResp.evidence,
            pvFeedSource: pvResp.source ?? null,
            pvLastFeed: pvResp.last_feed ?? null,
            pvLastIngest: pvResp.last_ingest_batch ?? null,
            pvDataEvidenceLoading: false,
          }));
        } catch (err: any) {
          setDetail((previous) => ({
            ...previous,
            pvDataEvidenceLoading: false,
            pvDataEvidenceError: err?.message ?? String(err),
          }));
        }
      }
      // @AI_GENERATED: end
    } catch (err: any) {
      messageApi.error(`加载详情失败：${err?.message ?? String(err)}`);
      setDetail({
        open: true,
        loading: false,
        data: null,
        dataPullEvidence: null,
        dataPullEvidenceLoading: false,
        dataPullEvidenceError: null,
        // @AI_GENERATED: 这个错误分支原先漏了全部 pv 字段（前端 build 不做类型检查所以没暴露）
        pvDataEvidence: null,
        pvDataEvidenceLoading: false,
        pvDataEvidenceError: null,
        pvFeedSource: null,
        pvLastFeed: null,
        pvLastIngest: null,
        // @AI_GENERATED: end
      });
    }
  };
  // @AI_GENERATED: end

  const openEdit = (task: ScheduledTaskSummary) => {
    setEditTask(task);
    editForm.setFieldsValue({ cron_expr: (task as any).cron_expr ?? '', trigger_time: (task as any).trigger_time ?? '02:00', max_window_days: task.max_window_days ?? null });
    setEditOpen(true);
  };

  const submitEdit = async () => {
    try {
      const values = await editForm.validateFields();
      if (!editTask) return;
      setEditSubmitting(true);
      await schedulerTaskApi.updateScheduledTask(editTask.task_id, {
        cron_expr: values.cron_expr || undefined,
        trigger_time: values.trigger_time || undefined,
        max_window_days: values.max_window_days ?? undefined,
      });
      messageApi.success(`已更新：${editTask.name}（运行中任务 cron 立即热更新）`);
      setEditOpen(false); editForm.resetFields(); await loadTasks();
    } catch (err: any) {
      if (err?.errorFields) return;
      messageApi.error(`更新失败：${err?.message ?? String(err)}`);
    } finally { setEditSubmitting(false); }
  };

  const openCreate = () => {
    form.resetFields();
    form.setFieldsValue({
      schedule_type: 'cron',
      trigger_time: '02:00',
      max_window_days: 365,
      pipeline: pipelineFilter ?? 'load_forecast',
      slot: isPvSlot ? 'pv_fault' : 'load_forecast',
      status: 'stopped',
      retry_on_failure: true,
      max_retries: 3,
    } as Partial<ScheduledTaskCreate>);
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreateSubmitting(true);
      await schedulerTaskApi.createScheduledTask({ name: values.name, pipeline: values.pipeline, schedule_type: values.schedule_type, cron_expr: values.schedule_type === 'cron' ? values.cron_expr ?? null : null, trigger_time: values.trigger_time ?? '02:00', max_window_days: values.max_window_days ?? null, slot: values.slot ?? 'default', status: 'stopped', retry_on_failure: values.retry_on_failure ?? true, max_retries: values.max_retries ?? 3 });
      messageApi.success(`任务创建成功：${values.name}`); setCreateOpen(false); await loadTasks();
    } catch (err: any) {
      if (err && typeof err === 'object' && 'errorFields' in err) return;
      messageApi.error(`创建失败：${err?.message ?? String(err)}`);
    } finally { setCreateSubmitting(false); }
  };

  const columns: ColumnsType<ScheduledTaskSummary> = [
    { title: '任务名称', dataIndex: 'name', width: 220, ellipsis: true, render: (name: string, row) => (<Space direction="vertical" size={2}><Text strong ellipsis={{ tooltip: name }}>{name}</Text><Text code style={{ fontSize: 11 }}>{row.task_id}</Text></Space>) },
    ...(pipelineFilter ? [] : [{ title: '管线', dataIndex: 'pipeline', width: 110, render: (p: string) => <Tag>{p}</Tag> }] as ColumnsType<ScheduledTaskSummary>),
    { title: '槽位', dataIndex: 'slot', width: 120, render: (slot: string) => <Tag color={slot === 'load_forecast_e2e_demo' ? 'purple' : 'geekblue'}>{slot}</Tag> },
    { title: 'Cron', dataIndex: 'cron_expr', width: 110, render: (v: string | null) => v ? <Text code style={{ fontSize: 12 }}>{v}</Text> : <Text type="secondary" style={{ fontSize: 12 }}>滚动</Text> },
    { title: '状态', dataIndex: 'status', width: 88, render: (s: ScheduledTaskSummary['status']) => { const cfg = STATUS_TAG[s]; return <Tag color={cfg.color}>{cfg.label}</Tag>; } },
    {
      title: '上次执行',
      dataIndex: 'last_execution',
      width: 220,
      render: (r: ScheduledTaskSummary['last_execution'], row) => {
        const failure = taskFailures[row.task_id];
        if (!r) return <Tag>未执行</Tag>;
        const cfg = LAST_EXEC_TAG[r];
        return (
          <Space direction="vertical" size={2}>
            <Tag color={cfg.color}>{cfg.label}</Tag>
            {r === 'failed' && failure?.error_message ? (
              <Tooltip title={failure.error_message}>
                <Text type="danger" ellipsis style={{ fontSize: 11, maxWidth: 200 }}>
                  {failure.error_message}
                </Text>
              </Tooltip>
            ) : null}
          </Space>
        );
      },
    },
    { title: '上次执行时间', dataIndex: 'last_execution_time', width: 148, render: (t: string | null) => formatDateTime(t) },
    { title: '下次调度', dataIndex: 'next_scheduled_time', width: 148, render: (t: string | null) => formatDateTime(t) },
    {
      title: '操作', key: 'actions', width: 260,
      render: (_: unknown, row) => {
        const busy = rowActionLoading[row.task_id] ?? false;
        const moreItems: MenuProps['items'] = [
          {
            key: 'ops',
            icon: <FundViewOutlined />,
            label: '运营状态',
            onClick: () => navigate(`/accuracy-operations?slot=${encodeURIComponent(row.slot === 'default' && row.pipeline === 'pv_fault' ? 'pv_fault' : row.slot)}`),
          },
          { key: 'edit', icon: <EditOutlined />, label: '编辑', onClick: () => openEdit(row) },
          { key: 'detail', icon: <ProfileOutlined />, label: '详情', onClick: () => handleViewDetail(row) },
        ];
        return (
          <div className="scheduler-task-actions">
            <Space size={4} wrap={false}>
              {row.status !== 'running' ? (
                <Popconfirm title="确认启动？" onConfirm={() => handleStart(row)} okText="启动" cancelText="取消">
                  <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={busy}>启动</Button>
                </Popconfirm>
              ) : (
                <Popconfirm title="确认停止？" description="正在执行的批次仍会跑完。" onConfirm={() => handleStop(row)} okText="停止" cancelText="取消" okButtonProps={{ danger: true }}>
                  <Button size="small" danger icon={<StopOutlined />} loading={busy}>停止</Button>
                </Popconfirm>
              )}
              {row.task_id === MOCK_DATA_FEED_TASK_ID ? (
                <Button size="small" type="primary" icon={<DatabaseOutlined />} loading={busy} onClick={() => requestMockDataFeed(row)}>喂数据</Button>
              ) : row.task_id === PV_MOCK_DATA_FEED_TASK_ID ? (
                <Space size={4}>
                  <Button
                    size="small"
                    type="primary"
                    icon={<DatabaseOutlined />}
                    loading={busy}
                    disabled={!!pvMockFeedPreview?.exhausted}
                    onClick={() => handlePvMockFeedClick(row)}
                  >
                    {pvMockFeedPreview?.exhausted
                      ? '已喂完'
                      : pvMockFeedPreview?.state === 'initial_feed'
                        ? '喂入首日'
                        : '推进下一天'}
                  </Button>
                  {pvMockFeedPreview?.exhausted ? (
                    <Tag color="default">
                      已喂完 · 源 {pvMockFeedPreview.source_fingerprint?.date_min ?? '?'}
                      ~{pvMockFeedPreview.source_fingerprint?.date_max ?? pvMockFeedPreview.current_business_date ?? '—'}
                    </Tag>
                  ) : pvMockFeedPreview?.current_business_date ? (
                    <Tag style={{ marginInlineEnd: 0 }}>
                      已至 {pvMockFeedPreview.current_business_date}
                      {pvMockFeedPreview.source_fingerprint?.date_max
                        ? ` / 源止 ${pvMockFeedPreview.source_fingerprint.date_max}`
                        : ''}
                    </Tag>
                  ) : null}
                </Space>
              ) : (
                <Popconfirm title="立即触发一次（后台异步，不改 status）？" onConfirm={() => handleTriggerNow(row)} okText="触发" cancelText="取消">
                  <Button size="small" icon={<ThunderboltOutlined />} loading={busy}>触发</Button>
                </Popconfirm>
              )}
              <Dropdown menu={{ items: moreItems }} trigger={['click']}>
                <Button size="small" icon={<MoreOutlined />}>更多</Button>
              </Dropdown>
            </Space>
          </div>
        );
      },
    },
  ];

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          className="scheduler-flow-note"
          type="info"
          showIcon
          message={isPvSlot ? '光伏故障诊断运行约定' : '负荷预测标准运行约定'}
          description={
            <Text style={{ fontSize: 13 }}>
              {storySlot ? <>当前槽位：<Text code>{storySlot}</Text>。 </> : null}
              {isPvSlot ? (
                <>
                  模拟喂数据将 parquet 样本写入 <Text code>training_samples</Text>（label 为空），
                  随后由预测任务读取未标注样本并生成预测批次；是否形成新结果请到同槽位「运营状态」查看证据链。
                </>
              ) : (
                <>
                  数据拉取、滚动训练、T+1 预测、真值回填和精度检测构成标准顺序。列表中的“上次执行”只代表调度任务回执，
                  是否已形成指标或告警，应进入同槽位的“运营状态”查看证据链。
                </>
              )}
            </Text>
          }
        />
        {!isPvSlot && mockFeedPreview && (
          <Alert
            type={mockFeedPreview.exhausted ? 'info' : mockFeedPreview.requires_advance_confirmation ? 'warning' : 'success'}
            showIcon
            message="模拟业务日投喂闸门（负荷预测）"
            description={formatMockFeedPreview(mockFeedPreview)}
          />
        )}
        {/* @AI_GENERATED: pv mock feed status banner — 只要在光伏槽位就展示，预览失败也可见 */}
        {isPvSlot && (
          <Alert
            type={
              pvMockFeedPreviewError
                ? 'error'
                : !pvMockFeedPreview
                  ? 'info'
                  : pvMockFeedPreview.exhausted
                    ? 'info'
                    : pvMockFeedPreview.requires_advance_confirmation
                      ? 'warning'
                      : 'success'
            }
            showIcon
            message="光伏模拟数据投喂闸门（可手动推进下一天）"
            description={(
              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                <span>
                  {pvMockFeedPreviewError
                    ? `状态读取失败：${pvMockFeedPreviewError}（仍可尝试点「推进下一天」）`
                    : pvMockFeedPreview
                      ? formatPvMockFeedPreview(pvMockFeedPreview)
                      : '正在读取当前业务日…'}
                </span>
                <Space wrap>
                  <Button
                    size="small"
                    type="primary"
                    loading={!!rowActionLoading[PV_MOCK_DATA_FEED_TASK_ID]}
                    disabled={!!pvMockFeedPreview?.exhausted}
                    onClick={() => {
                      const task = tasks.find((item) => item.task_id === PV_MOCK_DATA_FEED_TASK_ID)
                        ?? visibleTasks.find((item) => item.task_id === PV_MOCK_DATA_FEED_TASK_ID);
                      if (!task) {
                        messageApi.warning('未找到光伏喂数据任务 pv_mock_data_feed');
                        return;
                      }
                      handlePvMockFeedClick(task);
                    }}
                  >
                    {pvMockFeedPreview?.exhausted
                      ? '模拟源已喂完'
                      : pvMockFeedPreview?.state === 'initial_feed'
                        ? '喂入首日'
                        : '推进到下一业务日'}
                  </Button>
                  <Button
                    size="small"
                    onClick={async () => {
                      try {
                        const resp = await schedulerTaskApi.resetPvMockFeedCursor();
                        if (resp.preview) setPvMockFeedPreview(resp.preview);
                        setPvMockFeedPreviewError(null);
                        messageApi.success(resp.message || '喂数进度已重置');
                        await loadTasks();
                      } catch (err: any) {
                        messageApi.error(err?.response?.data?.detail || err?.message || '重置喂数进度失败');
                      }
                    }}
                  >
                    重置喂数进度
                  </Button>
                  <Button
                    size="small"
                    onClick={async () => {
                      try {
                        const resp = await schedulerTaskApi.resetPvPredictionCursor();
                        messageApi.success(resp.message || '预测进度已重置');
                      } catch (err: any) {
                        messageApi.error(err?.response?.data?.detail || err?.message || '重置预测进度失败');
                      }
                    }}
                  >
                    重置预测进度
                  </Button>
                </Space>
              </Space>
            )}
          />
        )}
        {/* @AI_GENERATED: end */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary">共 {visibleTasks.length} 个任务{pipelineFilter ? `（${pipelineFilter}）` : ''}</Text>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadTasks} loading={loading}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建任务</Button>
          </Space>
        </div>
        <div className="scheduler-task-table">
          <Table<ScheduledTaskSummary>
            size="middle"
            rowKey="task_id"
            columns={columns}
            dataSource={visibleTasks}
            loading={loading}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            scroll={{ x: 'max-content' }}
            locale={{ emptyText: '暂无调度任务（后端启动后自动写入默认任务）' }}
          />
        </div>
      </Space>

      <Modal open={editOpen} title={`编辑调度：${editTask?.name ?? ''}`} onCancel={() => { if (!editSubmitting) { setEditOpen(false); editForm.resetFields(); } }} onOk={submitEdit} okText="保存（热更新）" cancelText="取消" confirmLoading={editSubmitting} width={440} destroyOnClose>
        <Alert type="info" showIcon message="cron 表达式保存后立即热更新，无需重启" style={{ marginBottom: 12 }} />
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item name="cron_expr" label="Cron 表达式（schedule_type=cron）"><Input placeholder="如 0 2 * * *（每天凌晨 2 点）" /></Form.Item>
          <Form.Item name="trigger_time" label="每日触发时间 HH:MM（schedule_type=rolling_daily）"><Input placeholder="02:00" /></Form.Item>
          <Form.Item name="max_window_days" label="滚动训练窗口最大天数"><InputNumber min={1} max={3650} style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal open={createOpen} title="新建调度任务" onCancel={() => { if (!createSubmitting) setCreateOpen(false); }} onOk={submitCreate} okText="创建" cancelText="取消" confirmLoading={createSubmitting} maskClosable={!createSubmitting} closable={!createSubmitting} width={560} destroyOnClose>
        <Form<ScheduledTaskCreate> form={form} layout="vertical" preserve={false} disabled={createSubmitting}>
          <Form.Item name="name" label="任务名称" rules={[{ required: true }]}><Input placeholder="如：负荷预测每日滚动训练" maxLength={80} /></Form.Item>
          <Form.Item name="pipeline" label="所属管线" rules={[{ required: true }]}><Select options={PIPELINE_OPTIONS} placeholder="选择管线" /></Form.Item>
          <Form.Item name="schedule_type" label="调度策略" rules={[{ required: true }]}>
            <Select options={[{ value: 'cron', label: 'Cron 表达式' }, { value: 'rolling_daily', label: '每日滚动' }, { value: 'interval', label: '固定间隔' }]} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, curr) => prev.schedule_type !== curr.schedule_type}>
            {({ getFieldValue }) => getFieldValue('schedule_type') === 'cron'
              ? <Form.Item name="cron_expr" label="Cron 表达式" rules={[{ required: true }]}><Input placeholder="如：0 2 * * *" /></Form.Item>
              : <Form.Item name="trigger_time" label="每日触发时间 HH:MM"><Input placeholder="02:00" /></Form.Item>}
          </Form.Item>
          <Form.Item name="max_window_days" label="滚动窗口最大天数"><InputNumber min={1} max={3650} style={{ width: '100%' }} placeholder="365" /></Form.Item>
          <Form.Item name="slot" label="关联槽位" rules={[{ required: true, message: '请选择部署槽位' }]}>
            <Select options={SLOT_OPTIONS} placeholder="选择实际读写的部署槽位" />
          </Form.Item>
          <Form.Item name="retry_on_failure" label="失败自动重试" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="max_retries" label="最大重试次数"><InputNumber min={0} max={10} style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <TaskDetailModal
        {...detail}
        onClose={() => setDetail({
          open: false,
          loading: false,
          data: null,
          dataPullEvidence: null,
          dataPullEvidenceLoading: false,
          dataPullEvidenceError: null,
          pvDataEvidence: null,
          pvDataEvidenceLoading: false,
          pvDataEvidenceError: null,
          pvFeedSource: null,
          pvLastFeed: null,
          pvLastIngest: null,
        })}
      />
    </>
  );
};

const TaskDetailModal: React.FC<{
  open: boolean;
  loading: boolean;
  data: ScheduledTaskDetail | null;
  dataPullEvidence: DataPullEvidence | null;
  dataPullEvidenceLoading: boolean;
  dataPullEvidenceError: string | null;
  pvDataEvidence: PvMockFeedDataEvidence | null;
  pvDataEvidenceLoading: boolean;
  pvDataEvidenceError: string | null;
  pvFeedSource: PvSourceFingerprint | null;
  pvLastFeed: PvMockFeedLastRecord | null;
  pvLastIngest: PvMockFeedIngestBatch | null;
  onClose: () => void;
}> = ({
  open, loading, data, dataPullEvidence, dataPullEvidenceLoading, dataPullEvidenceError,
  pvDataEvidence, pvDataEvidenceLoading, pvDataEvidenceError, pvFeedSource, pvLastFeed,
  pvLastIngest, onClose,
}) => (
  <Modal open={open} title="调度任务详情" onCancel={onClose} footer={<Button onClick={onClose}>关闭</Button>} width={880} destroyOnClose>
    {loading || !data ? (
      <Text type="secondary">{loading ? '加载中…' : '未获取到任务详情'}</Text>
    ) : (
      <>
        <Descriptions column={2} size="small" labelStyle={{ width: 130, color: '#64748b' }} bordered>
          <Descriptions.Item label="task_id" span={2}><Text code copyable={{ text: data.task_id }}>{data.task_id}</Text></Descriptions.Item>
          <Descriptions.Item label="任务名称" span={2}>{data.name}</Descriptions.Item>
          <Descriptions.Item label="管线">{data.pipeline}</Descriptions.Item>
          <Descriptions.Item label="调度类型">{SCHEDULE_TYPE_LABEL[data.schedule_type] ?? data.schedule_type}</Descriptions.Item>
          <Descriptions.Item label="Cron 表达式">{data.cron_expr ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="每日触发时间">{data.trigger_time}</Descriptions.Item>
          <Descriptions.Item label="滚动窗口最大天数">{data.max_window_days ?? '不限'}</Descriptions.Item>
          <Descriptions.Item label="部署槽位">{data.slot}</Descriptions.Item>
          <Descriptions.Item label="状态"><Tag color={STATUS_TAG[data.status].color}>{STATUS_TAG[data.status].label}</Tag></Descriptions.Item>
          <Descriptions.Item label="上次执行结果">{data.last_result ? <Tag color={LAST_EXEC_TAG[data.last_result].color}>{LAST_EXEC_TAG[data.last_result].label}</Tag> : <Tag>未执行</Tag>}</Descriptions.Item>
          <Descriptions.Item label="上次执行时间">{formatDateTime(data.last_execution_time)}</Descriptions.Item>
          <Descriptions.Item label="下次调度时间">{formatDateTime(data.next_scheduled_time)}</Descriptions.Item>
          <Descriptions.Item label="失败自动重试">{data.retry_on_failure ? '开启' : '关闭'}</Descriptions.Item>
          <Descriptions.Item label="最大重试次数">{data.max_retries}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDateTime(data.created_at)}</Descriptions.Item>
          <Descriptions.Item label="最后更新">{formatDateTime(data.updated_at)}</Descriptions.Item>
        </Descriptions>
        {data.task_id === 'lf_data_pull' && (
          <DataPullEvidenceSection evidence={dataPullEvidence} loading={dataPullEvidenceLoading} error={dataPullEvidenceError} />
        )}
        {/* @AI_GENERATED: pv mock feed data evidence section */}
        {data.task_id === PV_MOCK_DATA_FEED_TASK_ID && (
          <PvDataEvidenceSection
            evidence={pvDataEvidence}
            loading={pvDataEvidenceLoading}
            error={pvDataEvidenceError}
            source={pvFeedSource}
            lastFeed={pvLastFeed}
            lastIngest={pvLastIngest}
          />
        )}
        {/* @AI_GENERATED: end */}
      </>
    )}
  </Modal>
);

const DataPullEvidenceSection: React.FC<{
  evidence: DataPullEvidence | null;
  loading: boolean;
  error: string | null;
}> = ({ evidence, loading, error }) => (
  <>
    <Divider orientation="left" plain>平台实际拉取数据（只读）</Divider>
    {loading ? (
      <Text type="secondary">正在查询平台 StationData 落库记录…</Text>
    ) : error ? (
      <Alert type="warning" showIcon message="数据证据加载失败" description={error} />
    ) : !evidence || evidence.total_rows === 0 ? (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该槽位尚未查询到平台已落库数据" />
    ) : (
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Descriptions column={2} size="small" bordered>
          <Descriptions.Item label="实际落库行数">{evidence.total_rows.toLocaleString('zh-CN')}</Descriptions.Item>
          <Descriptions.Item label="站点数">{evidence.station_count}</Descriptions.Item>
          <Descriptions.Item label="数据起点">{formatDateTime(evidence.time_start)}</Descriptions.Item>
          <Descriptions.Item label="数据终点">{formatDateTime(evidence.time_end)}</Descriptions.Item>
          <Descriptions.Item label="特征" span={2}>{evidence.feature_names.join('、') || '—'}</Descriptions.Item>
          <Descriptions.Item label="最新业务时间">{formatDateTime(evidence.latest?.timestamp_utc)}</Descriptions.Item>
          <Descriptions.Item label="最新值">{evidence.latest?.value ?? '—'}</Descriptions.Item>
        </Descriptions>
        <Table
          size="small"
          rowKey={(row) => `${row.station_id}-${row.feature_name}-${row.timestamp_utc}`}
          pagination={false}
          scroll={{ y: 260 }}
          dataSource={evidence.samples}
          locale={{ emptyText: '没有可展示的数据样本' }}
          columns={[
            { title: '业务时间', dataIndex: 'timestamp_utc', width: 180, render: (value: string) => formatDateTime(value) },
            { title: '站点', dataIndex: 'station_id', width: 120 },
            { title: '特征', dataIndex: 'feature_name', width: 100 },
            { title: '实际值', dataIndex: 'value', align: 'right', render: (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) },
            { title: '入库时间', dataIndex: 'ingested_at', width: 180, render: (value: string) => formatDateTime(value) },
          ]}
        />
      </Space>
    )}
  </>
);

// @AI_GENERATED: pv mock feed data evidence display component
const PvDataEvidenceSection: React.FC<{
  evidence: PvMockFeedDataEvidence | null;
  loading: boolean;
  error: string | null;
  source: PvSourceFingerprint | null;
  lastFeed: PvMockFeedLastRecord | null;
  lastIngest: PvMockFeedIngestBatch | null;
}> = ({ evidence, loading, error, source, lastFeed, lastIngest }) => (
  <>
    {/* 当前喂数源单独一段：换数据集后必须能立刻看出来喂的是哪份数据 */}
    <Divider orientation="left" plain>当前喂数源</Divider>
    {source && !source.error ? (
      <Descriptions column={2} size="small" bordered>
        <Descriptions.Item label="数据文件" span={2}>
          <Text code style={{ fontSize: 11 }}>{source.source_path ?? '—'}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="源覆盖日期">
          {source.date_min ?? '—'} ~ {source.date_max ?? '—'}
        </Descriptions.Item>
        <Descriptions.Item label="源行数">
          {source.row_count != null ? source.row_count.toLocaleString('zh-CN') : '—'}
        </Descriptions.Item>
        <Descriptions.Item label="上次喂入业务日">
          {lastFeed?.business_date ?? '尚未喂过'}
          {lastFeed?.row_count != null ? `（源 ${lastFeed.row_count.toLocaleString('zh-CN')} 行）` : ''}
        </Descriptions.Item>
        {/* fed_at 是 UTC 裸字符串，必须归一化后再转本地，否则比真实时间早 8 小时 */}
        <Descriptions.Item label="上次喂入时刻">{formatBackendDateTime(lastFeed?.fed_at)}</Descriptions.Item>
        <Descriptions.Item label="上次实际入库" span={2}>
          {lastFeed?.inserted_row_count == null ? (
            <Text type="secondary">—</Text>
          ) : lastFeed.inserted_row_count > 0 ? (
            <Text type="success">{lastFeed.inserted_row_count.toLocaleString('zh-CN')} 行</Text>
          ) : (
            <Text type="danger">0 行（源数据已在库中，本次全部跳过）</Text>
          )}
        </Descriptions.Item>
      </Descriptions>
    ) : (
      <Alert
        type="warning"
        showIcon
        message="数据源指纹不可用"
        description={source?.error ?? '后端未返回喂数源信息'}
      />
    )}

    {/* 「喂过这一天」≠「插进去了数据」：游标只记业务日与源行数，
        源数据若已在库，INSERT IGNORE 会全部跳过而游标照样前进。这里显式提示。 */}
    {lastFeed?.inserted_row_count === 0 && (
      <Alert
        style={{ marginTop: 8 }}
        type="warning"
        showIcon
        message={`上次喂入的业务日 ${lastFeed.business_date} 没有新增任何数据`}
        description="该业务日的观测已存在于 training_samples，INSERT IGNORE 全部跳过。喂数游标仍会前进，因此「上次喂入业务日」会变、但库里内容不变。若要喂入真正的新数据，请确认当前喂数源是否为期望的数据集。"
      />
    )}

    {/* 最近一次真实入库批次 —— 直接回答「我最近拉到了什么」 */}
    <Divider orientation="left" plain>最近拉到的数据</Divider>
    {lastIngest ? (
      <Descriptions column={3} size="small" bordered>
        <Descriptions.Item label="入库时刻">{formatBackendDateTime(lastIngest.ingested_at)}</Descriptions.Item>
        <Descriptions.Item label="本批行数">{lastIngest.row_count.toLocaleString('zh-CN')}</Descriptions.Item>
        <Descriptions.Item label="覆盖自然日">{lastIngest.day_count} 天</Descriptions.Item>
        <Descriptions.Item label="观测时间范围" span={2}>
          {/* 观测时间是业务时间，不做时区转换 */}
          {formatDateTime(lastIngest.observed_time_min)} ~ {formatDateTime(lastIngest.observed_time_max)}
        </Descriptions.Item>
        <Descriptions.Item label="设备 / 支路">
          {lastIngest.device_count} / {lastIngest.branch_count}
        </Descriptions.Item>
        <Descriptions.Item label="入库时刻区间" span={3}>
          {formatBackendDateTime(lastIngest.ingested_at_min)} ~ {formatBackendDateTime(lastIngest.ingested_at_max)}
          <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
            按 120 秒窗口聚合；若连续快速喂了多天，这里会合并显示
          </Text>
        </Descriptions.Item>
      </Descriptions>
    ) : (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无入库批次" />
    )}

    <Divider orientation="left" plain>已写入 training_samples 的光伏观测数据</Divider>
    {loading ? (
      <Text type="secondary">正在查询 training_samples 落库记录…</Text>
    ) : error ? (
      <Alert type="warning" showIcon message="数据证据加载失败" description={error} />
    ) : !evidence || evidence.total_rows === 0 ? (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={'尚未喂入任何数据（先点"喂数据"按钮）'} />
    ) : (
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Descriptions column={3} size="small" bordered>
          <Descriptions.Item label="总行数">{evidence.total_rows.toLocaleString('zh-CN')}</Descriptions.Item>
          <Descriptions.Item label="设备数">{evidence.device_count}</Descriptions.Item>
          {/* 已覆盖自然日 = DISTINCT DATE(time)，与首末跨度分开展示，避免把跨度误读成覆盖量 */}
          <Descriptions.Item label="已覆盖自然日">
            {evidence.date_count} 天
            {evidence.date_span_days != null && evidence.date_span_days !== evidence.date_count
              ? <Text type="secondary" style={{ fontSize: 11 }}>（首末跨度 {evidence.date_span_days} 天）</Text>
              : null}
          </Descriptions.Item>
          <Descriptions.Item label="最早观测时间">{formatDateTime(evidence.earliest_time)}</Descriptions.Item>
          <Descriptions.Item label="最新观测时间">{formatDateTime(evidence.latest_time)}</Descriptions.Item>
          {/* latest_ingested_at 是 UTC 裸字符串，与业务时间口径不同 */}
          <Descriptions.Item label="最近入库时间">{formatBackendDateTime(evidence.latest_ingested_at)}</Descriptions.Item>
        </Descriptions>
        <Table
          size="small"
          rowKey={(row) => `${row.id}`}
          pagination={false}
          scroll={{ y: 280, x: 940 }}
          dataSource={evidence.samples}
          locale={{ emptyText: '无样本' }}
          columns={[
            { title: '入库时间', dataIndex: 'ingested_at', width: 170, render: (v: string | null) => formatBackendDateTime(v) },
            { title: '观测时间', dataIndex: 'time', width: 170, render: (v: string) => formatDateTime(v) },
            { title: '站点', dataIndex: 'site_id', width: 90, ellipsis: true },
            { title: '设备', dataIndex: 'device_id', width: 160, ellipsis: true },
            { title: '支路', dataIndex: 'branch_id', width: 60 },
            { title: '实测电流', dataIndex: 'value', width: 90, align: 'right', render: (v: number | null) => v != null ? v.toFixed(4) : '—' },
            { title: '理论电流', dataIndex: 'i_cal', width: 90, align: 'right', render: (v: number | null) => v != null ? v.toFixed(4) : '—' },
            {
              title: '标签', dataIndex: 'label', width: 70, align: 'center',
              render: (v: number | null) => v != null ? <Tag color="blue">{v}</Tag> : <Tag>NULL</Tag>,
            },
          ]}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          展示最近入库的 50 行（按入库时间倒序），因此这里始终反映最近一次喂数的结果；
          若按观测时间倒序，看到的会恒是全库业务时间最大的那批历史数据。
          标签为 NULL 表示尚未标注（正常），预测任务将消费这些行。
        </Text>
      </Space>
    )}
  </>
);
// @AI_GENERATED: end

export default SchedulerTab;
// @AI_GENERATED: end
