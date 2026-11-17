/**
 * 人工审核预测准确率页面 - 光伏故障人机协同迭代标注闭环
 * 
 * 功能：
 * 1. 双来源并列展示：分类器预测 + LLM 建议
 * 2. 不一致高亮提示
 * 3. 四类审核动作：确认正确/纠正为已有标签/打成新标签/标记存疑跳过
 * 4. 三方精度面板：分类器/LLM/人工核对精度
 * 5. 进度与断点恢复
 * 6. 复用数据集预览接口
 * 
 * 映射需求: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 6.1, 3.5
 */

import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Card,
  Row,
  Col,
  Table,
  Button,
  Tag,
  Space,
  Typography,
  Progress,
  Statistic,
  Alert,
  Modal,
  Select,
  Input,
  message,
  Descriptions,
  Divider,
  Badge,
  Tooltip,
  Radio,
  Form,
  List,
} from 'antd';
import {
  CheckCircleOutlined,
  EditOutlined,
  PlusCircleOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
  LineChartOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { reviewSessionApi } from '../services/iterativeLabelingApi';
import { isPvProductSlot } from '../config/slotProductConfig';
import PvFaultWorkspaceShell from '../components/pv-fault/PvFaultWorkspaceShell';
import { PV_FAULT_PRIMARY, PV_FAULT_OK } from '../theme/pvFaultTheme';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

/**
 * 诊断单元 — site_id × device_id × (可选 branch_id) × time_window
 */
interface DiagnosisUnit {
  unit_key: string;                    // 诊断单元标识
  site_id: string;                     // 站点ID
  device_id: string;                   // 设备ID
  branch_id?: string;                  // 支路ID（可选）
  time_window: string;                 // 诊断窗口
  
  // 分类器预测（Classifier_Prediction）
  classifier_prediction: {
    predicted_label: number | null;    // 预测标签 label_id；纯手工标注时为空
    predicted_label_name?: string;     // 预测标签名称（用于展示）
    confidence: number;                // 置信度 0~1
  };
  
  // LLM 建议（LLM_Suggestion）
  llm_suggestion?: {
    suggested_label?: number;          // 建议标签 label_id
    suggested_label_name?: string;     // 建议标签名称
    reason?: string;                   // 建议理由
    out_of_registry: boolean;          // 是否越界标签
    available: boolean;                // 是否可用（调用失败时为 false）
  };
  
  disagreement: boolean;               // 是否双来源分歧
  current_verdict?: {                  // 已提交裁决（断点恢复用）
    verdict_label?: number;
    action_type: string;
    reviewer: string;
  };

  // @AI_GENERATED: pv_tsc 设备日结论 + MultiRocket 重叠窗口证据（day/point 场景为空）
  tsc_evidence?: {
    target_day?: string;               // 目标业务日
    n_windows: number;                 // 参与聚合的窗口数
    aggregation?: string;              // 聚合方式（majority / avg_proba）
    model_name?: string;               // 模型名称（MultiRocket）
    model_ref?: string;                // 模型工件引用
    model_role?: string;               // 模型角色（challenger / champion / ...）
    model_candidate_id?: string;       // 模型候选 ID
    model_window_config?: Record<string, unknown>; // 训练窗口/步长契约
    per_window_details: Array<{
      window_start?: string;
      window_end?: string;
      predicted_label?: number;
      confidence?: number;
    }>;
  };
  // @AI_GENERATED: end
}

/**
 * 审核会话状态
 */
interface FreeformLabelRecord {
  unit_key: string;
  t_start: string;
  t_end: string;
  time_window: string;
  verdict_label: number;
  action_type: string;
  site_id?: string;
  device_id?: string;
  branch_id?: string;
  source_unit_key?: string;
  row_count?: number;
}

interface ReviewSession {
  review_id: string;                   // 审核会话标识
  loop_id: string;                     // 所属迭代闭环
  status: 'reviewing' | 'reviewed';    // 会话状态
  reviewed_count: number;              // 已审核数
  total_count: number;                 // 总数
  units: DiagnosisUnit[];              // 待审核单元数组
  sampling_strategy?: string;
  freeform_labels?: FreeformLabelRecord[];
  prediction_context?: {
    manual_labeling?: boolean;
    source_csv_path?: string;
    modeling_path?: string;
    prediction_granularity?: 'day' | 'point';
    source?: string;
    fed_day?: string;
    // @AI_GENERATED: pv_tsc 审核会话携带的模型角色与调度快照（不新增 'tsc' 粒度）
    review_kind?: string;
    detection_date?: string;
    model_ref?: string;
    model_source?: string;
    model_role?: string;
    model_candidate_id?: string;
    model_window_config?: Record<string, unknown>;
    // @AI_GENERATED: end
  };
}

function normalizeReviewUnit(raw: Record<string, unknown>): DiagnosisUnit {
  const nested = raw.classifier_prediction && typeof raw.classifier_prediction === 'object'
    ? raw.classifier_prediction as Record<string, unknown>
    : null;
  const parts = String(raw.unit_key || '').split('|');
  const predictedLabel = typeof nested?.predicted_label === 'number'
    ? nested.predicted_label
    : (typeof raw.predicted_label === 'number' ? raw.predicted_label : null);
  const confidence = typeof nested?.confidence === 'number'
    ? nested.confidence
    : (typeof raw.confidence === 'number' ? raw.confidence : 0);
  const finalLabel = typeof raw.final_label === 'number' ? raw.final_label : undefined;
  const storedVerdict = raw.current_verdict && typeof raw.current_verdict === 'object'
    ? raw.current_verdict as DiagnosisUnit['current_verdict']
    : undefined;
  // @AI_GENERATED: 归一化时保留 MultiRocket 设备日重叠窗口证据与模型角色，避免丢失 TSC 语义。
  const rawWindows = Array.isArray(raw.per_window_details)
    ? raw.per_window_details as Array<Record<string, unknown>>
    : [];
  const perWindowDetails = rawWindows.map((w) => ({
    window_start: typeof w.window_start === 'string' ? w.window_start : undefined,
    window_end: typeof w.window_end === 'string' ? w.window_end : undefined,
    predicted_label: typeof w.predicted_label === 'number' ? w.predicted_label : undefined,
    confidence: typeof w.confidence === 'number' ? w.confidence : undefined,
  }));
  const nWindows = typeof raw.n_windows === 'number' ? raw.n_windows : perWindowDetails.length;
  const tscEvidence = (nWindows > 0 || perWindowDetails.length > 0 || raw.model_role || raw.model_source)
    ? {
        target_day: typeof raw.target_day === 'string' ? raw.target_day : undefined,
        n_windows: nWindows,
        aggregation: typeof raw.aggregation === 'string' ? raw.aggregation : undefined,
        model_name: typeof raw.model_name === 'string' ? raw.model_name : undefined,
        model_ref: typeof raw.model_ref === 'string' ? raw.model_ref : undefined,
        model_role: typeof raw.model_role === 'string'
          ? raw.model_role
          : (typeof raw.model_source === 'string' ? raw.model_source : undefined),
        model_candidate_id: typeof raw.model_candidate_id === 'string' ? raw.model_candidate_id : undefined,
        model_window_config: (raw.model_window_config && typeof raw.model_window_config === 'object'
          ? raw.model_window_config
          : undefined) as Record<string, unknown> | undefined,
        per_window_details: perWindowDetails,
      }
    : undefined;
  // @AI_GENERATED: end
  return {
    unit_key: String(raw.unit_key || ''),
    site_id: String(raw.site_id || parts[0] || ''),
    device_id: String(raw.device_id || parts[1] || ''),
    branch_id: raw.branch_id != null ? String(raw.branch_id) : (parts[2] || undefined),
    time_window: String(raw.time_window || raw.time || raw.date || (parts.length >= 4 ? parts.slice(3).join('|') : '')),
    classifier_prediction: {
      predicted_label: predictedLabel,
      predicted_label_name: typeof nested?.predicted_label_name === 'string' ? nested.predicted_label_name : undefined,
      confidence,
    },
    llm_suggestion: (raw.llm_suggestion && typeof raw.llm_suggestion === 'object'
      ? raw.llm_suggestion
      : undefined) as DiagnosisUnit['llm_suggestion'],
    disagreement: Boolean(raw.disagreement),
    current_verdict: storedVerdict || (finalLabel != null
      ? {
          verdict_label: finalLabel,
          action_type: predictedLabel === finalLabel ? 'confirm' : 'correct',
          reviewer: 'mock_gold',
        }
      : undefined),
    // @AI_GENERATED: 透传 TSC 设备日证据到审核单元。
    tsc_evidence: tscEvidence,
    // @AI_GENERATED: end
  };
}

function normalizeReviewSession(data: Record<string, unknown>): ReviewSession {
  const units = Array.isArray(data.units)
    ? (data.units as Array<Record<string, unknown>>).map(normalizeReviewUnit)
    : [];
  return {
    review_id: String(data.review_id || ''),
    loop_id: String(data.loop_id || ''),
    status: data.status === 'reviewed' ? 'reviewed' : 'reviewing',
    reviewed_count: Number(data.reviewed_count || 0),
    total_count: Number(data.total_count ?? units.length),
    units,
    sampling_strategy: typeof data.sampling_strategy === 'string' ? data.sampling_strategy : undefined,
    freeform_labels: Array.isArray(data.freeform_labels) ? data.freeform_labels as FreeformLabelRecord[] : [],
    prediction_context: (data.prediction_context && typeof data.prediction_context === 'object'
      ? data.prediction_context
      : undefined) as ReviewSession['prediction_context'],
  };
}

function calendarDay(value?: string): string {
  return String(value || '').slice(0, 10);
}

function freeformCoversUnit(label: FreeformLabelRecord, unit: DiagnosisUnit): boolean {
  const unitKey = String(unit.unit_key || '');
  if (unitKey && (String(label.source_unit_key || '') === unitKey || String(label.unit_key || '') === unitKey)) {
    return true;
  }
  const sameEntity =
    String(label.site_id ?? '') === String(unit.site_id ?? '')
    && String(label.device_id ?? '') === String(unit.device_id ?? '')
    && String(label.branch_id ?? '') === String(unit.branch_id ?? '');
  if (!sameEntity) return false;
  const unitDay = calendarDay(unit.time_window);
  const labelDay = calendarDay(label.t_start || label.time_window);
  return !unitDay || !labelDay || unitDay === labelDay;
}

/**
 * 三方精度对比
 */
interface AccuracySnapshot {
  classifier_accuracy: number;          // 分类器原始预测精度
  llm_accuracy: number;                 // LLM 建议精度
  human_verified_accuracy: number;      // 人工核对后精度基线（100%）
  llm_coverage: number;                 // LLM 覆盖率
  counted_units: number;                // 纳入统计的单元数
  macro?: {                              // Macro 口径精度
    precision?: number;
    recall?: number;
    f1?: number;
  };
}

/**
 * 标签注册表
 */
interface LabelRegistry {
  label_space_version: string;          // 标签空间版本号
  labels: Array<{                       // 标签数组
    label_id: number;                   // 标签编码（主键）
    label_name: string;                 // 标签业务名称
    created_at: string;
  }>;
  label_map: Record<string, number>;    // 标签映射（业务名 → 数值类别）
}

const IterativeLabelingReviewPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const reviewId = searchParams.get('review_id');
  // @AI_GENERATED: 审核页面默认进入正式 pv_fault 场景，并将 URL 场景透传给全部读取与写入请求，防止跨业务线串数据。
  const slot = searchParams.get('slot') || 'pv_point';
  const slotQuery = `slot=${encodeURIComponent(slot)}`;
  const isProductSlot = isPvProductSlot(slot);
  
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [session, setSession] = useState<ReviewSession | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracySnapshot | null>(null);
  const [labelRegistry, setLabelRegistry] = useState<LabelRegistry | null>(null);
  const [currentUnitIndex, setCurrentUnitIndex] = useState(0);
  
  // 审核动作相关状态
  const [actionModalVisible, setActionModalVisible] = useState(false);
  const [currentAction, setCurrentAction] = useState<string>('');
  const [selectedLabel, setSelectedLabel] = useState<number | undefined>();
  const [newLabelName, setNewLabelName] = useState('');
  const [form] = Form.useForm();

  // 回流生成数据集相关状态
  const [backfillModalOpen, setBackfillModalOpen] = useState(false);
  const [backfillLoading, setBackfillLoading] = useState(false);
  const [mergeBase, setMergeBase] = useState(false);
  const [baseCsvPath, setBaseCsvPath] = useState('');
  const [backfillResult, setBackfillResult] = useState<{
    dataset_version: string;
    csv_path: string;
    labeled_rows: number;
    labeled_units: number;
    total_source_rows: number;
  } | null>(null);
  const [admitLoading, setAdmitLoading] = useState(false);

  // 当前单元时序波形
  const [unitTimeseries, setUnitTimeseries] = useState<{
    timestamps: string[];
    series: Record<string, Array<number | null>>;
    point_count: number;
    prediction_overlay?: {
      granularity: 'point';
      timestamps: string[];
      point_predictions: number[];
      point_confidences: number[];
      segment_predictions: Array<{
        t_start: string;
        t_end: string;
        label: number;
        n_points: number;
      }>;
      model_name?: string;
      seq_len_used?: number;
      trained_full_day?: boolean;
    } | null;
  } | null>(null);
  const [timeseriesLoading, setTimeseriesLoading] = useState(false);

  // 各类故障参考波形
  const [refWaveforms, setRefWaveforms] = useState<Array<{
    label_id: number;
    label_name: string;
    timestamps: string[];
    series: Record<string, Array<number | null>>;
    point_count: number;
  }>>([]);
  const [refWaveformsLoading, setRefWaveformsLoading] = useState(false);

  // 自由时间窗框选打标
  const chartRef = useRef<ReactECharts | null>(null);
  const [freeformModalOpen, setFreeformModalOpen] = useState(false);
  const [freeformSaving, setFreeformSaving] = useState(false);
  const [freeformRange, setFreeformRange] = useState<{ tStart: string; tEnd: string } | null>(null);
  const [freeformAction, setFreeformAction] = useState<'correct' | 'new_label'>('correct');
  const [freeformLabelId, setFreeformLabelId] = useState<number | undefined>();
  const [freeformNewName, setFreeformNewName] = useState('');

  // SHAP / 相似案例
  const [explainLoading, setExplainLoading] = useState(false);
  const [shapResult, setShapResult] = useState<{
    available?: boolean;
    reason?: string;
    note?: string;
    source?: string;
    top_features?: Array<{ name: string; value: number; shap_value: number }>;
  } | null>(null);
  const [similarResult, setSimilarResult] = useState<{
    source?: string;
    note?: string;
    cases?: Array<{
      unit_key?: string;
      label?: number;
      label_name?: string | null;
      similarity_score?: number;
    }>;
  } | null>(null);

  /**
   * 加载审核会话
   */
  const loadReviewSession = async () => {
    if (!reviewId) {
      message.error('缺少审核会话 ID');
      return;
    }
    
    setLoading(true);
    setLoadError(null);
    try {
      // 需求 3.4：支持会话中断后恢复
      const response = await fetch(`/api/iterative-labeling/review-sessions/${reviewId}?${slotQuery}`);
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(typeof err.detail === 'string' ? err.detail : `加载审核会话失败（${response.status}）`);
      }
      
      const data = await response.json();
      const normalized = normalizeReviewSession(data);
      setSession(normalized);
      
      // 断点恢复：找到第一个未审核的单元
      const firstUnreviewedIndex = normalized.units.findIndex(
        (u: DiagnosisUnit) => !u.current_verdict
      );
      if (firstUnreviewedIndex !== -1) {
        setCurrentUnitIndex(firstUnreviewedIndex);
      }
      message.success('加载审核会话成功');
    } catch (error) {
      setSession(null);
      setLoadError(error instanceof Error ? error.message : String(error));
      message.error(`加载失败: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  /**
   * 加载标签注册表
   */
  const loadLabelRegistry = async () => {
    try {
      const response = await fetch(`/api/iterative-labeling/label-registry?${slotQuery}`);
      if (!response.ok) throw new Error('加载标签注册表失败');
      
      const data = await response.json();
      setLabelRegistry(data);
    } catch (error) {
      message.error(`加载标签注册表失败: ${error}`);
    }
  };

  /**
   * 加载三方精度
   */
  const loadAccuracy = async () => {
    if (!reviewId) return;
    
    try {
      const response = await fetch(`/api/iterative-labeling/review-sessions/${reviewId}/accuracy?${slotQuery}`);
      if (!response.ok) throw new Error('加载精度失败');
      
      const data = await response.json();
      setAccuracy(data);
    } catch (error) {
      console.error('加载精度失败:', error);
    }
  };

  /**
   * 回流：把人工确认的标签回贴到原始时序，生成可再训练的新数据集 CSV
   */
  const handleBackfill = async () => {
    if (!reviewId) return;
    setBackfillLoading(true);
    try {
      const response = await fetch(
        `/api/iterative-labeling/review-sessions/${reviewId}/backfill-to-dataset?${slotQuery}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            merge_base: mergeBase,
            base_csv_path: mergeBase && baseCsvPath.trim() ? baseCsvPath.trim() : null,
          }),
        }
      );
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || '回流失败');
      }
      const data = await response.json();
      setBackfillResult(data);
      message.success(`已生成新数据集：${data.labeled_rows} 行 / ${data.labeled_units} 单元`);
    } catch (error: any) {
      message.error(`生成数据集失败: ${error.message || error}`);
    } finally {
      setBackfillLoading(false);
    }
  };

  /**
   * 加载各类故障参考波形（依赖已加载的 session，避免重复拉会话）
   */
  const loadReferenceWaveforms = async (sessData?: ReviewSession | null) => {
    const sessionData = sessData ?? session;
    if (!sessionData) return;
    setRefWaveformsLoading(true);
    try {
      const ctx = sessionData.prediction_context || {};
      // 训练数据路径：使用相对于项目根目录的路径（后端 _resolve_data_path 会解析）
      // 训练数据已含 label 列，单文件模式即可
      const trainPath = ctx.reference_train_path || 'fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet';
      const resp = await fetch(
        `/api/iterative-labeling/reference-waveforms?train_csv_path=${encodeURIComponent(trainPath)}&${slotQuery}`
      );
      if (!resp.ok) return;
      const data = await resp.json();
      setRefWaveforms(data.categories || []);
    } catch (e) {
      console.error('加载参考波形失败:', e);
    } finally {
      setRefWaveformsLoading(false);
    }
  };

  /**
   * 加载当前单元的原始时序波形
   */
  const loadUnitTimeseries = async (unitKey: string) => {
    if (!reviewId || !unitKey) return;
    setTimeseriesLoading(true);
    setUnitTimeseries(null);
    try {
      const resp = await fetch(
        `/api/iterative-labeling/review-sessions/${reviewId}/unit-timeseries?unit_key=${encodeURIComponent(unitKey)}&${slotQuery}`
      );
      if (!resp.ok) throw new Error('加载波形失败');
      const data = await resp.json();
      setUnitTimeseries(data);
    } catch (e) {
      console.error('加载单元波形失败:', e);
      setUnitTimeseries(null);
    } finally {
      setTimeseriesLoading(false);
    }
  };

  // 故障码 → 名称（与预测工作流口径一致），用于波形标注
  const FAULT_NAMES: Record<string, string> = {
    '0': '正常', '1': '组串遮挡', '4': '直流侧异常', '7': '汇流箱告警',
    '8': '汇流箱故障', '11': '组串开路', '12': '组串短路', '16': '其他故障',
  };
  const getLabelName = (labelId?: number | null): string => {
    if (labelId === undefined || labelId === null) return '未知';
    const fromReg = labelRegistry?.labels.find((l) => l.label_id === labelId)?.label_name;
    return fromReg || FAULT_NAMES[String(labelId)] || `故障${labelId}`;
  };

  /**
   * 提交人工裁决
   */
  const submitVerdict = async (actionType: string, verdictLabel?: number) => {
    if (!reviewId || !session) return;
    
    const currentUnit = session.units[currentUnitIndex];
    if (!currentUnit) return;
    
    setLoading(true);
    try {
      const response = await fetch(
        `/api/iterative-labeling/review-sessions/${reviewId}/verdicts?${slotQuery}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            unit_key: currentUnit.unit_key,
            action_type: actionType,
            verdict_label: verdictLabel,
            reviewer: 'current_user', // 实际应从用户上下文获取
          }),
        }
      );
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '提交裁决失败');
      }
      
      const result = await response.json();
      
      // 更新精度快照
      if (result.accuracy_snapshot) {
        setAccuracy(result.accuracy_snapshot);
      }
      
      message.success('裁决已提交');
      
      // 移动到下一个单元
      if (currentUnitIndex < session.units.length - 1) {
        setCurrentUnitIndex(currentUnitIndex + 1);
      } else {
        message.info('已完成全部单元审核');
      }
      
      // 重新加载会话以更新进度
      await loadReviewSession();
      
    } catch (error) {
      message.error(`提交失败: ${error}`);
    } finally {
      setLoading(false);
      setActionModalVisible(false);
      form.resetFields();
    }
  };

  /**
   * 处理确认正确动作
   */
  const handleConfirm = () => {
    const currentUnit = session?.units[currentUnitIndex];
    if (!currentUnit) return;
    if (currentUnit.classifier_prediction?.predicted_label == null) {
      message.warning('纯手工标注没有可直接确认的模型标签，请选择已有标签或创建新标签');
      return;
    }
    
    // 需求 5.1：确认正确，以分类器 predicted_label 作为裁决
    Modal.confirm({
      title: '确认正确',
      content: `确认分类器预测标签「${currentUnit.classifier_prediction.predicted_label_name || currentUnit.classifier_prediction.predicted_label}」正确？`,
      onOk: () => submitVerdict('confirm', currentUnit.classifier_prediction.predicted_label),
    });
  };

  /**
   * 处理纠正为已有标签动作
   */
  const handleCorrect = () => {
    setCurrentAction('correct');
    setActionModalVisible(true);
  };

  /**
   * 处理打成新标签动作
   */
  const handleNewLabel = () => {
    setCurrentAction('new_label');
    setActionModalVisible(true);
  };

  /**
   * 处理标记存疑跳过动作
   */
  const handleSkip = () => {
    // 需求 5.4：标记存疑跳过，不写入真值标签
    Modal.confirm({
      title: '标记存疑跳过',
      content: '此单元将被标记为存疑（pending），不计入精度统计，也不进入回流训练集。确认跳过？',
      onOk: () => submitVerdict('skip'),
    });
  };

  /**
   * 处理动作模态框确认
   */
  const handleActionModalOk = async () => {
    if (currentAction === 'correct') {
      if (selectedLabel === undefined) {
        message.warning('请选择纠正标签');
        return;
      }
      await submitVerdict('correct', selectedLabel);
    } else if (currentAction === 'new_label') {
      if (!newLabelName.trim()) {
        message.warning('请输入新标签名称');
        return;
      }
      
      try {
        // 需求 8.1：新增标签类别
        const response = await fetch(`/api/iterative-labeling/label-registry/labels?${slotQuery}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label_name: newLabelName.trim() }),
        });
        
        if (!response.ok) throw new Error('新增标签失败');
        
        const result = await response.json();
        message.success(`新标签已创建: ${result.label_id}`);
        
        // 重新加载标签注册表
        await loadLabelRegistry();
        
        // 提交裁决
        await submitVerdict('new_label', result.label_id);
        
        setNewLabelName('');
      } catch (error) {
        message.error(`新增标签失败: ${error}`);
      }
    }
  };

  // 初始化加载
  useEffect(() => {
    void (async () => {
      await Promise.all([loadReviewSession(), loadLabelRegistry()]);
    })();
    void loadAccuracy();

    const interval = setInterval(loadAccuracy, 5000);
    return () => clearInterval(interval);
  }, [reviewId, slot]);

  useEffect(() => {
    if (!session) return;
    void loadReferenceWaveforms(session);
  }, [session?.review_id]);

  // 当前单元变化时加载其原始时序波形
  useEffect(() => {
    const unit = session?.units?.[currentUnitIndex];
    if (unit?.unit_key) {
      loadUnitTimeseries(unit.unit_key);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewId, slot, currentUnitIndex, session?.units?.[currentUnitIndex]?.unit_key]);

  // 当前单元变化时加载 SHAP + 相似案例
  useEffect(() => {
    const unit = session?.units?.[currentUnitIndex];
    if (!reviewId || !unit?.unit_key || session?.prediction_context?.manual_labeling) {
      setShapResult(null);
      setSimilarResult(null);
      return;
    }
    let cancelled = false;
    const loadExplain = async () => {
      setExplainLoading(true);
      try {
        const uk = encodeURIComponent(unit.unit_key);
        const [shapResp, simResp] = await Promise.all([
          fetch(`/api/iterative-labeling/review-sessions/${reviewId}/shap/${uk}?${slotQuery}&top_k=5`),
          fetch(`/api/iterative-labeling/review-sessions/${reviewId}/similar/${uk}?${slotQuery}&k=3`),
        ]);
        const shapJson = shapResp.ok ? await shapResp.json() : { available: false, reason: 'http_error' };
        const simJson = simResp.ok ? await simResp.json() : { cases: [], note: 'http_error' };
        if (!cancelled) {
          setShapResult(shapJson);
          setSimilarResult(simJson);
        }
      } catch {
        if (!cancelled) {
          setShapResult({ available: false, reason: 'load_failed' });
          setSimilarResult({ cases: [], note: 'load_failed' });
        }
      } finally {
        if (!cancelled) setExplainLoading(false);
      }
    };
    void loadExplain();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewId, slot, currentUnitIndex, session?.units?.[currentUnitIndex]?.unit_key]);

  const freeformLabelsForCurrentDevice = useMemo(() => {
    const unit = session?.units?.[currentUnitIndex];
    if (!unit || !session?.freeform_labels?.length) return [] as FreeformLabelRecord[];
    return session.freeform_labels.filter((item) => freeformCoversUnit(item, unit));
  }, [session?.freeform_labels, session?.units, currentUnitIndex]);

  const boxedUnitCount = useMemo(() => {
    const units = session?.units || [];
    const labels = session?.freeform_labels || [];
    return units.filter((unit) => labels.some((label) => freeformCoversUnit(label, unit))).length;
  }, [session?.units, session?.freeform_labels]);

  const handleBrushEnd = (params: any) => {
    const area = params?.areas?.[0];
    if (!area || !unitTimeseries?.timestamps?.length) return;
    const range = area.coordRange || area.range;
    if (!Array.isArray(range) || range.length < 2) return;

    const timestamps = unitTimeseries.timestamps;
    let startIdx: number;
    let endIdx: number;
    if (typeof range[0] === 'number' && range[0] <= timestamps.length) {
      startIdx = Math.max(0, Math.floor(Math.min(range[0], range[1])));
      endIdx = Math.min(timestamps.length - 1, Math.ceil(Math.max(range[0], range[1])));
    } else {
      // category value fallback: match short display labels poorly — prefer raw indices from brush
      startIdx = 0;
      endIdx = timestamps.length - 1;
      const startLabel = String(range[0]);
      const endLabel = String(range[1]);
      const display = timestamps.map((t) =>
        t.includes(' ') ? t.split(' ')[1]?.slice(0, 5) || t : t.slice(11, 16)
      );
      const si = display.indexOf(startLabel);
      const ei = display.lastIndexOf(endLabel);
      if (si >= 0) startIdx = si;
      if (ei >= 0) endIdx = ei;
    }
    if (endIdx <= startIdx) {
      message.warning('请框选至少一个时间区间');
      return;
    }
    setFreeformRange({
      tStart: timestamps[startIdx],
      tEnd: timestamps[endIdx],
    });
    setFreeformAction('correct');
    setFreeformLabelId(undefined);
    setFreeformNewName('');
    setFreeformModalOpen(true);
  };

  const submitFreeformLabel = async () => {
    if (!reviewId || !freeformRange || !session) return;
    const unit = session.units[currentUnitIndex];
    if (!unit) return;
    if (freeformAction === 'correct' && freeformLabelId === undefined) {
      message.warning('请选择标签');
      return;
    }
    if (freeformAction === 'new_label' && !freeformNewName.trim()) {
      message.warning('请输入新标签名称');
      return;
    }
    setFreeformSaving(true);
    try {
      const payload = await reviewSessionApi.createFreeformLabel(
        reviewId,
        {
          t_start: freeformRange.tStart,
          t_end: freeformRange.tEnd,
          action_type: freeformAction,
          reviewer: 'operator',
          verdict_label: freeformAction === 'correct' ? freeformLabelId : undefined,
          new_label_name: freeformAction === 'new_label' ? freeformNewName.trim() : undefined,
          source_unit_key: unit.unit_key,
        },
        slot
      );
      const saved = ((payload as any).record || payload) as FreeformLabelRecord;
      const nextLabels = [...(session.freeform_labels || []), saved];
      setSession({ ...session, freeform_labels: nextLabels });
      if (freeformAction === 'new_label') {
        await loadLabelRegistry();
      }
      const ct = (payload as any).cumulative_training || {};
      const retrainReq = ct.retrain_request;
      if (retrainReq?.request_id) {
        message.success(
          `已写入累计训练集并触发重训请求 ${retrainReq.request_id}（请到算法部署页执行）`,
        );
      } else if (ct.imported === false) {
        message.success('该自由窗切片此前已登记，未重复计入阈值');
      } else {
        const nextIn = ct.next_retrain_in;
        message.success(
          typeof nextIn === 'number'
            ? `已写入累计训练集（${saved.row_count ?? '?'} 行），距下次重训还差 ${nextIn} 次变更`
            : `已框选打标并写入累计训练集（${saved.row_count ?? '?'} 行）`,
        );
      }
      setFreeformModalOpen(false);
      setFreeformRange(null);
      try {
        chartRef.current?.getEchartsInstance()?.dispatchAction({ type: 'brush', areas: [] });
      } catch {
        // ignore brush clear failures
      }
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || error;
      message.error(`框选打标失败: ${detail}`);
    } finally {
      setFreeformSaving(false);
    }
  };

  const revokeFreeformLabel = async (unitKey: string) => {
    if (!reviewId || !session) return;
    try {
      await reviewSessionApi.revokeFreeformLabel(reviewId, unitKey, slot);
      setSession({
        ...session,
        freeform_labels: (session.freeform_labels || []).filter((item) => item.unit_key !== unitKey),
      });
      message.success('已撤销自由窗标注（会话指针）');
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || error;
      message.error(`撤销失败: ${detail}`);
    }
  };

  const handleCompleteAndAdmit = async () => {
    if (!reviewId || !isProductSlot) return;
    setAdmitLoading(true);
    try {
      const result = await reviewSessionApi.completeReviewSessionAndAdmit(
        reviewId,
        slot as 'pv_day' | 'pv_point' | 'pv_tsc',
        { reviewer: 'ui-operator' },
      );
      if (result?.skipped) {
        message.success('审核已完成。本组只有 holdout 单元，未写入累计训练流水。');
      } else {
        message.success(`已纳入累计训练账本（${String(result.dataset_version_id || '')}）。训练快照请到累计页按时间冻结。`);
      }
      const refreshed = await fetch(`/api/iterative-labeling/review-sessions/${encodeURIComponent(reviewId)}?${slotQuery}`);
      if (refreshed.ok) {
        setSession(await refreshed.json());
      }
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      const msg = typeof detail === 'object' && detail?.message
        ? detail.message
        : typeof detail === 'string'
          ? detail
          : error?.message || '纳入累计失败';
      message.error(msg);
    } finally {
      setAdmitLoading(false);
    }
  };

  if (!reviewId) {
    return (
      <Card>
        <Alert
          message="缺少审核会话 ID"
          description="请从迭代闭环页面发起审核会话"
          type="warning"
          showIcon
        />
      </Card>
    );
  }

  if (!session) {
    if (loadError) {
      return (
        <Card>
          <Alert
            type="error"
            showIcon
            message="审核会话加载失败"
            description={loadError}
          />
        </Card>
      );
    }
    return <Card loading={loading}>加载中...</Card>;
  }

  const units = session.units || [];
  const currentUnit = units[currentUnitIndex];
  const classifier = currentUnit?.classifier_prediction;
  const demoSession = session.prediction_context?.source === 'loop_demo';
  const manualLabeling = Boolean(session.prediction_context?.manual_labeling);
  const progressPercent = session.total_count > 0
    ? Math.round((session.reviewed_count / session.total_count) * 100)
    : 0;

  return (
    <PvFaultWorkspaceShell className="pv-page-shell">
      <Title level={2}>
        <FileTextOutlined /> {manualLabeling ? '人工打标' : '人工审核预测准确率'}
      </Title>
      {demoSession ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`演示自动审核${session.prediction_context?.fed_day ? ` · ${session.prediction_context.fed_day}` : ''}`}
          description="真值已按 gold 自动 confirm/correct，只给对照看，没有写入累计训练集。点路径一天 576 个点，可逐条翻看。"
        />
      ) : null}
      
      {/* 需求 3.3：显示审核进度 */}
      <Card
        title="审核进度"
        style={{ marginBottom: 16 }}
        extra={
          <Space>
            {isProductSlot && (
              <Tooltip
                title={
                  demoSession
                    ? '演示自动审核只做对照，不会写入累计训练集'
                    : (session.units?.length || 0) > 0 && boxedUnitCount < session.units.length
                    ? `还需框选 ${session.units.length - boxedUnitCount} 个检测单元后才能完成`
                    : '全部检测单元都要框选（含 holdout）；holdout 不进入累计训练集'
                }
              >
                <span>
                  <Button
                    type="primary"
                    loading={admitLoading}
                    disabled={
                      demoSession
                      || ((session.units?.length || 0) > 0
                        ? boxedUnitCount < session.units.length
                        : (session.freeform_labels?.length || 0) === 0)
                    }
                    onClick={() => void handleCompleteAndAdmit()}
                  >
                    完成并纳入累计训练集
                  </Button>
                </span>
              </Tooltip>
            )}
            {!isProductSlot && (
              <Button
                type="primary"
                icon={<FileTextOutlined />}
                disabled={session.reviewed_count === 0}
                onClick={() => { setBackfillResult(null); setBackfillModalOpen(true); }}
              >
                完成 → 生成新真值数据集
              </Button>
            )}
          </Space>
        }
      >
        <Row gutter={16}>
          <Col span={18}>
            <Progress
              percent={progressPercent}
              status={session.status === 'reviewed' ? 'success' : 'active'}
              format={() => `${session.reviewed_count} / ${session.total_count}`}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="当前进度"
              value={session.reviewed_count}
              suffix={`/ ${session.total_count}`}
            />
          </Col>
        </Row>
      </Card>

      {/* 三方精度对比：仅在全部审核完成后展示 */}
      {accuracy && session.status === 'reviewed' && (
        <Card
          title={
            <Space>
              <LineChartOutlined />
              三方精度实时对比
              <Tooltip title="以已审核单元为基准，实时计算三方精度">
                <InfoCircleOutlined />
              </Tooltip>
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <Row gutter={16}>
            <Col span={6}>
              <Statistic
                title="分类器预测精度"
                value={(accuracy.classifier_accuracy * 100).toFixed(2)}
                suffix="%"
                valueStyle={{ color: PV_FAULT_OK, fontWeight: 600 }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                辅助建议
              </Text>
            </Col>
            <Col span={6}>
              <Statistic
                title="LLM 建议精度"
                value={(accuracy.llm_accuracy * 100).toFixed(2)}
                suffix="%"
                valueStyle={{ color: '#6B7280', fontWeight: 600 }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                辅助建议 | 覆盖率 {(accuracy.llm_coverage * 100).toFixed(1)}%
              </Text>
            </Col>
            <Col span={6}>
              <Statistic
                title="人工核对精度基线"
                value={100}
                suffix="%"
                valueStyle={{ color: PV_FAULT_PRIMARY, fontWeight: 600 }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                已审核单元
              </Text>
            </Col>
            <Col span={6}>
              <Statistic
                title="已审核单元数"
                value={accuracy.counted_units}
                suffix="条"
              />
            </Col>
          </Row>
          
          <Divider />
          
          {/* 需求 6.3：Macro precision/recall/f1 */}
          <Row gutter={16}>
            <Col span={8}>
              <Statistic
                title="Macro Precision"
                value={accuracy.macro?.precision == null ? '—' : (accuracy.macro.precision * 100).toFixed(2)}
                suffix="%"
                precision={2}
              />
            </Col>
            <Col span={8}>
              <Statistic
                title="Macro Recall"
                value={accuracy.macro?.recall == null ? '—' : (accuracy.macro.recall * 100).toFixed(2)}
                suffix="%"
                precision={2}
              />
            </Col>
            <Col span={8}>
              <Statistic
                title="Macro F1"
                value={accuracy.macro?.f1 == null ? '—' : (accuracy.macro.f1 * 100).toFixed(2)}
                suffix="%"
                precision={2}
              />
            </Col>
          </Row>
        </Card>
      )}

      {/* 当前审核单元 */}
      {currentUnit && (
        <Card
          title={
            <Space>
              当前单元 ({currentUnitIndex + 1} / {units.length})
              {currentUnit.disagreement && (
                <Tag color="orange" icon={<WarningOutlined />}>
                  双来源分歧
                </Tag>
              )}
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <Descriptions bordered column={2}>
            <Descriptions.Item label="诊断单元标识">
              {currentUnit.unit_key}
            </Descriptions.Item>
            <Descriptions.Item label="站点 ID">
              {currentUnit.site_id}
            </Descriptions.Item>
            <Descriptions.Item label="设备 ID">
              {currentUnit.device_id}
            </Descriptions.Item>
            <Descriptions.Item label="诊断窗口">
              {currentUnit.time_window}
            </Descriptions.Item>
          </Descriptions>

          {/* @AI_GENERATED: pv_tsc 设备日结论 + MultiRocket 重叠窗口证据；不依赖 manual_labeling，纯手工会话无该证据不渲染。 */}
          {currentUnit.tsc_evidence && (
            <>
              <Divider>时序分类诊断（MultiRocket 设备日）</Divider>
              <Descriptions bordered column={2} size="small">
                <Descriptions.Item label="设备日最终标签">
                  <Space>
                    <Tag color={
                      classifier?.predicted_label != null && classifier.predicted_label !== 0 && classifier.predicted_label !== 7
                        ? 'error'
                        : 'success'
                    }>
                      {getLabelName(classifier?.predicted_label)}
                    </Tag>
                    {classifier?.confidence != null && (
                      <Text type="secondary">置信度 {(classifier.confidence * 100).toFixed(1)}%</Text>
                    )}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="目标业务日">
                  {currentUnit.tsc_evidence.target_day || currentUnit.time_window || '—'}
                </Descriptions.Item>
                <Descriptions.Item label="模型 / 角色">
                  <Space wrap size={4}>
                    <Tag color="blue">{currentUnit.tsc_evidence.model_name || 'MultiRocket'}</Tag>
                    <Tag color={currentUnit.tsc_evidence.model_role === 'champion' ? 'gold' : 'purple'}>
                      {currentUnit.tsc_evidence.model_role || session.prediction_context?.model_role || 'challenger'}
                    </Tag>
                    {currentUnit.tsc_evidence.model_candidate_id && (
                      <Text code style={{ fontSize: 11 }}>{currentUnit.tsc_evidence.model_candidate_id}</Text>
                    )}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="窗口 / 步长">
                  {(() => {
                    const cfg = currentUnit.tsc_evidence.model_window_config
                      || session.prediction_context?.model_window_config
                      || {};
                    const win = (cfg.window_length ?? cfg.window ?? '—') as React.ReactNode;
                    const stride = (cfg.inference_stride ?? cfg.stride ?? '—') as React.ReactNode;
                    return <Text>window={win} · stride={stride}</Text>;
                  })()}
                </Descriptions.Item>
                <Descriptions.Item label="聚合方式">
                  {currentUnit.tsc_evidence.aggregation || 'majority'}
                </Descriptions.Item>
                <Descriptions.Item label="窗口数">
                  <Tag color="blue">{currentUnit.tsc_evidence.n_windows}</Tag>
                </Descriptions.Item>
              </Descriptions>
              {currentUnit.tsc_evidence.per_window_details.length > 0 ? (
                <Table
                  size="small"
                  style={{ marginTop: 12 }}
                  rowKey={(_, index) => String(index)}
                  pagination={{ pageSize: 6, showSizeChanger: false }}
                  dataSource={currentUnit.tsc_evidence.per_window_details.map((w, index) => ({ ...w, index }))}
                  columns={[
                    {
                      title: '窗口起',
                      dataIndex: 'window_start',
                      key: 'window_start',
                      render: (v?: string) => (v ? String(v).replace('T', ' ').slice(0, 16) : '—'),
                    },
                    {
                      title: '窗口止',
                      dataIndex: 'window_end',
                      key: 'window_end',
                      render: (v?: string) => (v ? String(v).replace('T', ' ').slice(0, 16) : '—'),
                    },
                    {
                      title: '窗口标签',
                      dataIndex: 'predicted_label',
                      key: 'predicted_label',
                      width: 140,
                      render: (v?: number) => (
                        <Tag color={v != null && v !== 0 && v !== 7 ? 'error' : 'success'}>
                          {getLabelName(v)}
                        </Tag>
                      ),
                    },
                    {
                      title: '窗口置信度',
                      dataIndex: 'confidence',
                      key: 'confidence',
                      width: 120,
                      render: (v?: number) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`),
                    },
                  ]}
                />
              ) : (
                <Alert
                  style={{ marginTop: 12 }}
                  type="info"
                  showIcon
                  message="本设备日没有逐窗明细"
                  description="设备日最终标签仍可用于审核；逐窗证据缺失通常是历史批次未记录 per_window_details。"
                />
              )}
            </>
          )}
          {/* @AI_GENERATED: end */}

          {/* 各类故障参考波形对照 — 缩小放在设备波形上方方便对照 */}
          {refWaveforms.length > 0 && (
            <>
              <Divider>各类故障典型波形参考（对照用）</Divider>
              <Row gutter={[8, 8]}>
                {refWaveforms.map((ref) => (
                  <Col key={ref.label_id} span={8}>
                    <div style={{ border: '1px solid #f0f0f0', borderRadius: 4, padding: '4px 8px' }}>
                      <Space size={4} style={{ marginBottom: 2 }}>
                        <Tag color={ref.label_id === 0 || ref.label_id === 7 ? 'orange' : 'red'} style={{ fontSize: 11 }}>
                          label_{ref.label_id}
                        </Tag>
                        <span style={{ fontSize: 11 }}>{ref.label_name}（{ref.point_count}点）</span>
                      </Space>
                      {ref.timestamps.length > 0 ? (
                        <ReactECharts
                          style={{ height: 120 }}
                          option={{
                            tooltip: { trigger: 'axis' },
                            legend: { show: false },
                            grid: { left: 36, right: 8, top: 6, bottom: 20 },
                            xAxis: { type: 'category', data: ref.timestamps.map(t => t.includes(' ') ? t.split(' ')[1]?.slice(0, 5) || t : t), axisLabel: { fontSize: 8, rotate: 30 }, show: true },
                            yAxis: [{ type: 'value', axisLabel: { fontSize: 8 } }],
                            series: Object.entries(ref.series).map(([k, data], idx) => ({
                              name: k === 'value' ? '实测电流' : k === 'i_cal' ? '理论电流' : k,
                              type: 'line',
                              data,
                              smooth: true,
                              showSymbol: false,
                              lineStyle: { width: 1 },
                              itemStyle: { color: idx === 0 ? '#1890ff' : '#fa8c16' },
                            })),
                          }}
                        />
                      ) : <Text type="secondary" style={{ fontSize: 11 }}>无可用波形</Text>}
                    </div>
                  </Col>
                ))}
              </Row>
            </>
          )}
          {refWaveformsLoading && <div style={{ textAlign: 'center', padding: 8, color: '#999', fontSize: 12 }}>参考波形加载中...</div>}

          {/* 原始时序波形（辅助人工判断） */}
          <Divider>设备波形（电压 / 电流）— 可框选时段打标</Divider>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 8 }}
            message="框选自由时间窗"
            description="在波形工具栏点「横向选择」后拖选区间，确认标签后会写入专属窗口样本并进入累计训练集（不影响整日单元裁决）。"
          />
          {unitTimeseries?.prediction_overlay && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 8 }}
              message={`序列标注逐点预测 · ${unitTimeseries.prediction_overlay.seq_len_used ?? 288} 点/天`}
              description="图中底色色带和下方分段列表来自模型逐点输出。上方“确认正确”只确认天级摘要，不会把整天写成同一标签；请框选真实故障区间，形成 human_range 逐点真值。"
            />
          )}
          {timeseriesLoading ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>波形加载中...</div>
          ) : unitTimeseries && unitTimeseries.timestamps.length > 0 ? (
            (() => {
              const predId = currentUnit.classifier_prediction?.predicted_label;
              const predName = getLabelName(predId);
              const predConf = currentUnit.classifier_prediction?.confidence ?? 0;
              const isFault = predId !== undefined && predId !== null && predId !== 0 && predId !== 7; // 0正常/7汇流箱告警视为非严重
              const seriesEntries = Object.entries(unitTimeseries.series);
              const SERIES_NAMES: Record<string, string> = { value: '实测电流', i_cal: '理论电流' };
              const axisLabels = unitTimeseries.timestamps.map((t) =>
                t.includes(' ') ? t.split(' ')[1]?.slice(0, 5) || t : t.slice(11, 16)
              );
              const freeformMarkAreas = freeformLabelsForCurrentDevice.map((item) => {
                const name =
                  labelRegistry?.labels.find((l) => l.label_id === item.verdict_label)?.label_name ||
                  `label_${item.verdict_label}`;
                // markArea uses category axis labels; fall back to nearest displayed tick.
                const startDisp = item.t_start.includes(' ')
                  ? item.t_start.split(' ')[1]?.slice(0, 5) || item.t_start
                  : item.t_start.slice(11, 16);
                const endDisp = item.t_end.includes(' ')
                  ? item.t_end.split(' ')[1]?.slice(0, 5) || item.t_end
                  : item.t_end.slice(11, 16);
                const startIdx = unitTimeseries.timestamps.findIndex((t) => t >= item.t_start);
                const endIdx = [...unitTimeseries.timestamps]
                  .map((t, i) => ({ t, i }))
                  .reverse()
                  .find((row) => row.t <= item.t_end)?.i;
                const x0 = startIdx >= 0 ? axisLabels[startIdx] : startDisp;
                const x1 = endIdx !== undefined ? axisLabels[endIdx] : endDisp;
                return [
                  {
                    name,
                    itemStyle: { color: 'rgba(114, 46, 209, 0.18)' },
                    xAxis: x0,
                  },
                  { xAxis: x1 },
                ];
              });
              const seqPredictionMarkAreas = (
                unitTimeseries.prediction_overlay?.segment_predictions ?? []
              ).map((segment) => {
                const labelName = getLabelName(segment.label);
                const startMs = new Date(segment.t_start).getTime();
                const endMs = new Date(segment.t_end).getTime();
                const startIdx = unitTimeseries.timestamps.findIndex(
                  (timestamp) => new Date(timestamp).getTime() >= startMs,
                );
                const endIdx = [...unitTimeseries.timestamps]
                  .map((timestamp, index) => ({ timestamp, index }))
                  .reverse()
                  .find(({ timestamp }) => new Date(timestamp).getTime() <= endMs)?.index;
                const isNormalSegment = segment.label === 0;
                return [
                  {
                    name: `逐点预测：${labelName}`,
                    itemStyle: {
                      color: isNormalSegment
                        ? 'rgba(82, 196, 26, 0.07)'
                        : 'rgba(255, 77, 79, 0.14)',
                    },
                    xAxis: axisLabels[Math.max(0, startIdx)],
                  },
                  {
                    xAxis: axisLabels[endIdx ?? Math.max(0, startIdx)],
                  },
                ];
              });
              const predictedSegments = unitTimeseries.prediction_overlay?.segment_predictions ?? [];
              const faultSegments = predictedSegments.filter((segment) => segment.label !== 0);
              const displayedSegments = (faultSegments.length > 0 ? faultSegments : predictedSegments).slice(0, 12);
              return (
                <>
                  <ReactECharts
                  ref={chartRef}
                  style={{ height: 360 }}
                  onEvents={{ brushEnd: handleBrushEnd }}
                  option={{
                    title: {
                      text: manualLabeling ? '待人工标注' : `分类器预测：${predName}（label_${predId}）`,
                      subtext: manualLabeling ? '请结合波形选择正确标签' : predConf > 0 ? `置信度 ${(predConf * 100).toFixed(1)}%` : '置信度不可用（模型未输出概率）',
                      left: 'center',
                      textStyle: { fontSize: 13, color: isFault ? '#cf1322' : '#389e0d' },
                      subtextStyle: { fontSize: 11 },
                    },
                    tooltip: { trigger: 'axis' },
                    legend: {
                      data: seriesEntries.map(([k]) => SERIES_NAMES[k] || k),
                      bottom: 0,
                    },
                    toolbox: {
                      right: 12,
                      feature: {
                        brush: { type: ['lineX', 'clear'] },
                      },
                    },
                    brush: {
                      xAxisIndex: 0,
                      brushLink: 'all',
                      throttleType: 'debounce',
                      throttleDelay: 200,
                      outOfBrush: { colorAlpha: 0.1 },
                    },
                    grid: { left: 60, right: 30, top: 50, bottom: 60 },
                    xAxis: {
                      type: 'category',
                      data: axisLabels,
                      axisLabel: { rotate: 45, fontSize: 10 },
                    },
                    yAxis: [{ type: 'value' }],
                    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 34 }],
                    series: seriesEntries.map(([k, data], idx) => ({
                      name: SERIES_NAMES[k] || k,
                      type: 'line',
                      data,
                      smooth: true,
                      showSymbol: false,
                      lineStyle: { width: 1.5 },
                      itemStyle: { color: idx === 0 ? '#1890ff' : '#fa8c16' },
                      ...(idx === 0
                        ? {
                            markArea: {
                              silent: true,
                              data: [
                                [
                                  {
                                    itemStyle: {
                                      color: isFault
                                        ? 'rgba(255,77,79,0.06)'
                                        : 'rgba(82,196,26,0.06)',
                                    },
                                    xAxis: 'min',
                                  },
                                  { xAxis: 'max' },
                                ],
                                ...seqPredictionMarkAreas,
                                ...freeformMarkAreas,
                              ],
                            },
                          }
                        : {}),
                    })),
                  }}
                />
                  {unitTimeseries.prediction_overlay && (
                    <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 10, marginTop: 4 }}>
                      <Space wrap size={[6, 6]}>
                        <Text strong style={{ fontSize: 12 }}>模型分段</Text>
                        {displayedSegments.map((segment, index) => (
                          <Tag
                            key={`${segment.t_start}-${segment.label}-${index}`}
                            color={segment.label === 0 ? 'success' : 'error'}
                          >
                            {getLabelName(segment.label)} · {segment.t_start.slice(11, 16)}–{segment.t_end.slice(11, 16)} · {segment.n_points}点
                          </Tag>
                        ))}
                        {predictedSegments.length > displayedSegments.length && (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            另有 {predictedSegments.length - displayedSegments.length} 段
                          </Text>
                        )}
                      </Space>
                    </div>
                  )}
                </>
              );
            })()
          ) : (
            <Alert
              type="warning"
              showIcon
              message="未能加载该单元的原始波形"
              description="可能是原始 CSV 路径不可用，或该 设备×窗口 在原始数据中无匹配行。不影响打标，可结合预测标签与置信度判断。"
            />
          )}
          {unitTimeseries && unitTimeseries.point_count > 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              该窗口共 {unitTimeseries.point_count} 个采样点
              {session.sampling_strategy === 'uncertainty' ? ' · 队列已按低置信度优先排序' : ''}
            </Text>
          )}
          {freeformLabelsForCurrentDevice.length > 0 && (
            <Card size="small" title="本设备自由窗标注" style={{ marginTop: 12 }}>
              <List
                size="small"
                dataSource={freeformLabelsForCurrentDevice}
                renderItem={(item) => {
                  const name =
                    labelRegistry?.labels.find((l) => l.label_id === item.verdict_label)?.label_name ||
                    `label_${item.verdict_label}`;
                  return (
                    <List.Item
                      actions={[
                        <Button
                          key="revoke"
                          type="link"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => void revokeFreeformLabel(item.unit_key)}
                        >
                          撤销
                        </Button>,
                      ]}
                    >
                      <Space wrap>
                        <Tag color="purple">{name}</Tag>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {item.t_start} → {item.t_end}
                        </Text>
                        {item.row_count != null && (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {item.row_count} 行
                          </Text>
                        )}
                      </Space>
                    </List.Item>
                  );
                }}
              />
            </Card>
          )}

          {!session?.prediction_context?.manual_labeling && (
            <Card
              size="small"
              title="审核辅助：为什么判成这个 / 相似案例"
              style={{ marginTop: 12 }}
              loading={explainLoading}
            >
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Typography.Text strong>特征贡献（SHAP）</Typography.Text>
                  {shapResult?.available && (shapResult.top_features?.length ?? 0) > 0 ? (
                    <List
                      size="small"
                      style={{ marginTop: 8 }}
                      dataSource={shapResult.top_features || []}
                      renderItem={(item) => (
                        <List.Item>
                          <Space direction="vertical" size={0} style={{ width: '100%' }}>
                            <Text>{item.name}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              贡献 {Number(item.shap_value).toFixed(4)}
                              {' · '}
                              特征值 {Number(item.value).toFixed(4)}
                            </Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Alert
                      style={{ marginTop: 8 }}
                      type="info"
                      showIcon
                      message={shapResult?.available === false ? '暂无法计算 SHAP' : '暂无解释'}
                      description={
                        shapResult?.note
                        || shapResult?.reason
                        || '需要带特征向量的新预测批次（重新跑预测后建审核会话）'
                      }
                    />
                  )}
                  {shapResult?.source && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      来源：{shapResult.source}
                    </Text>
                  )}
                </Col>
                <Col xs={24} md={12}>
                  <Typography.Text strong>相似案例</Typography.Text>
                  {(similarResult?.cases?.length ?? 0) > 0 ? (
                    <List
                      size="small"
                      style={{ marginTop: 8 }}
                      dataSource={similarResult?.cases || []}
                      renderItem={(item) => {
                        const idx = session?.units?.findIndex((u) => u.unit_key === item.unit_key) ?? -1;
                        const labelText =
                          item.label_name
                          || (item.label != null
                            ? labelRegistry?.labels.find((l) => l.label_id === item.label)?.label_name
                              || `label_${item.label}`
                            : '—');
                        return (
                          <List.Item
                            actions={
                              idx >= 0
                                ? [
                                    <Button
                                      key="jump"
                                      type="link"
                                      size="small"
                                      onClick={() => setCurrentUnitIndex(idx)}
                                    >
                                      跳转
                                    </Button>,
                                  ]
                                : undefined
                            }
                          >
                            <Space direction="vertical" size={0}>
                              <Text>{labelText}</Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                相似度 {(Number(item.similarity_score || 0) * 100).toFixed(1)}%
                                {item.unit_key ? ` · ${item.unit_key}` : ''}
                              </Text>
                            </Space>
                          </List.Item>
                        );
                      }}
                    />
                  ) : (
                    <Alert
                      style={{ marginTop: 8 }}
                      type="info"
                      showIcon
                      message="暂无相似案例"
                      description={similarResult?.note || '同批次可比较样本不足'}
                    />
                  )}
                  {similarResult?.source && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      来源：{similarResult.source === 'feature_vectors' ? '真实特征向量' : '弱代理（建议重新预测）'}
                    </Text>
                  )}
                </Col>
              </Row>
            </Card>
          )}

          {/* 需求 4：双来源并列展示 */}
          <Divider>{manualLabeling ? '标注依据' : '双来源预测对比'}</Divider>
          {manualLabeling && (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="这是从累计训练集扩充流程创建的纯手工标注会话"
              description="该数据集没有模型预测真值，请根据设备波形选择“纠正为已有标签”或“打成新标签”。完成后的标签会回流到累计训练集。"
            />
          )}
          
          {!manualLabeling && <Row gutter={16}>
            {/* 需求 4.1：分类器预测 */}
            <Col span={12}>
              <Card
                title={
                  <Space>
                    <Badge status="processing" />
                    分类器预测
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      （辅助建议）
                    </Text>
                  </Space>
                }
                bordered={false}
                style={{
                  backgroundColor: currentUnit.disagreement ? '#fff7e6' : '#f0f5ff',
                }}
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Statistic
                    title="预测标签"
                    value={
                      classifier?.predicted_label_name
                      || (classifier?.predicted_label != null ? `label_${classifier.predicted_label}` : '—')
                    }
                    valueStyle={{ fontSize: 24 }}
                  />
                  <Statistic
                    title="置信度"
                    value={classifier?.confidence == null ? '—' : (classifier.confidence * 100).toFixed(1)}
                    suffix="%"
                    precision={1}
                  />
                </Space>
              </Card>
            </Col>

            {/* 需求 4.1：LLM 建议 */}
            <Col span={12}>
              <Card
                title={
                  <Space>
                    <Badge status="success" />
                    LLM 建议
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      （辅助建议）
                    </Text>
                  </Space>
                }
                bordered={false}
                style={{
                  backgroundColor: currentUnit.disagreement ? '#fff7e6' : '#f6ffed',
                }}
              >
                {/* 需求 4.4：LLM 缺失时标注不可用，不阻断审核 */}
                {currentUnit.llm_suggestion?.available === false ? (
                  <Alert
                    message="LLM 建议不可用"
                    description="LLM 调用失败或超时，请仅参考分类器预测"
                    type="info"
                    showIcon
                  />
                ) : currentUnit.llm_suggestion ? (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Statistic
                      title="建议标签"
                      value={
                        currentUnit.llm_suggestion.suggested_label_name ||
                        `label_${currentUnit.llm_suggestion.suggested_label}`
                      }
                      valueStyle={{ fontSize: 24 }}
                    />
                    {currentUnit.llm_suggestion.out_of_registry && (
                      <Alert
                        message="疑似新类别（越界标签）"
                        type="warning"
                        showIcon
                        banner
                      />
                    )}
                    <div>
                      <Text strong>建议理由：</Text>
                      <Paragraph style={{ marginTop: 8 }}>
                        {currentUnit.llm_suggestion.reason || '无'}
                      </Paragraph>
                    </div>
                  </Space>
                ) : (
                  <Alert
                    message="LLM 建议不可用"
                    description="未启用 LLM 辅助打标"
                    type="info"
                    showIcon
                  />
                )}
              </Card>
            </Col>
          </Row>}

          {/* 需求 4.2：不一致高亮提示 */}
          {currentUnit.disagreement && (
            <Alert
              message="双来源分歧"
              description="分类器预测与 LLM 建议不一致，请仔细判断并做出最终裁决"
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              style={{ marginTop: 16 }}
            />
          )}

          {/* 需求 5：四类审核动作 */}
          <Divider>审核动作</Divider>
          
          <Space size="large" style={{ width: '100%', justifyContent: 'center' }}>
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              size="large"
              onClick={handleConfirm}
              disabled={loading || classifier?.predicted_label == null}
            >
              确认正确
            </Button>
            <Button
              icon={<EditOutlined />}
              size="large"
              onClick={handleCorrect}
              disabled={loading}
            >
              纠正为已有标签
            </Button>
            <Button
              icon={<PlusCircleOutlined />}
              size="large"
              onClick={handleNewLabel}
              disabled={loading}
            >
              打成新标签
            </Button>
            <Button
              icon={<QuestionCircleOutlined />}
              size="large"
              danger
              onClick={handleSkip}
              disabled={loading}
            >
              标记存疑跳过
            </Button>
          </Space>
        </Card>
      )}

      {/* 动作模态框 */}
      <Modal
        title={currentAction === 'correct' ? '纠正为已有标签' : '打成新标签'}
        open={actionModalVisible}
        onOk={handleActionModalOk}
        onCancel={() => {
          setActionModalVisible(false);
          form.resetFields();
        }}
        confirmLoading={loading}
      >
        <Form form={form} layout="vertical">
          {currentAction === 'correct' ? (
            // 需求 5.2：从注册表现有类别中选择
            <Form.Item
              label="选择纠正标签"
              required
              help="从已有标签类别中选择正确标签"
            >
              <Select
                placeholder="请选择标签"
                value={selectedLabel}
                onChange={setSelectedLabel}
                showSearch
                filterOption={(input, option) =>
                  (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                }
                options={labelRegistry?.labels.map(l => ({
                  label: `${l.label_name} (ID: ${l.label_id})`,
                  value: l.label_id,
                }))}
              />
            </Form.Item>
          ) : (
            // 需求 5.3：打成新标签，走标签扩充
            <Form.Item
              label="新标签名称"
              required
              help="输入新的故障类别名称，将自动分配唯一标签 ID"
            >
              <Input
                placeholder="例如：组串失配-新子类型A"
                value={newLabelName}
                onChange={(e) => setNewLabelName(e.target.value)}
                maxLength={50}
                showCount
              />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title="框选时段打标"
        open={freeformModalOpen}
        onOk={() => void submitFreeformLabel()}
        onCancel={() => {
          setFreeformModalOpen(false);
          setFreeformRange(null);
        }}
        confirmLoading={freeformSaving}
        okText="写入累计训练集"
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Alert
            type="info"
            showIcon
            message="将创建专属自由窗样本"
            description={
              freeformRange
                ? `${freeformRange.tStart} → ${freeformRange.tEnd}`
                : '未选择区间'
            }
          />
          <Radio.Group
            value={freeformAction}
            onChange={(e) => setFreeformAction(e.target.value)}
          >
            <Radio.Button value="correct">已有标签</Radio.Button>
            <Radio.Button value="new_label">新标签</Radio.Button>
          </Radio.Group>
          {freeformAction === 'correct' ? (
            <Select
              style={{ width: '100%' }}
              placeholder="选择标签"
              value={freeformLabelId}
              onChange={setFreeformLabelId}
              options={labelRegistry?.labels.map((l) => ({
                label: `${l.label_name} (ID: ${l.label_id})`,
                value: l.label_id,
              }))}
            />
          ) : (
            <Input
              placeholder="例如：夜间漏电流"
              value={freeformNewName}
              onChange={(e) => setFreeformNewName(e.target.value)}
              maxLength={50}
              showCount
            />
          )}
        </Space>
      </Modal>

      {/* 回流：生成新真值数据集 */}
      <Modal
        title="完成审核 → 生成新真值数据集"
        open={backfillModalOpen}
        onCancel={() => setBackfillModalOpen(false)}
        footer={backfillResult ? [
          <Button key="close" onClick={() => setBackfillModalOpen(false)}>关闭</Button>
        ] : [
          <Button key="cancel" onClick={() => setBackfillModalOpen(false)}>取消</Button>,
          <Button key="ok" type="primary" loading={backfillLoading} onClick={handleBackfill}>
            生成数据集
          </Button>
        ]}
      >
        {!backfillResult ? (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="将把已确认/纠正/新标签的单元回贴到原始时序，生成可直接再训练的 CSV"
              description="标记“存疑跳过”的单元不会写入。未审核的单元也不会包含在内。"
            />
            <Form layout="vertical">
              <Form.Item label="累积合并基线训练数据">
                <Radio.Group value={mergeBase} onChange={(e) => setMergeBase(e.target.value)}>
                  <Radio value={false}>仅本轮标注（不合并）</Radio>
                  <Radio value={true}>与基线训练 CSV 累积合并</Radio>
                </Radio.Group>
              </Form.Item>
              {/* @AI_GENERATED: 回流合并仅接受相对项目根目录路径，避免前端提示用户写入机器相关的绝对路径。 */}
              {mergeBase && (
                <Form.Item
                  label="基线训练 CSV 路径"
                  help="填入上一轮训练使用的相对项目根目录 CSV 路径；将拼接到新标注数据前，留空则仅使用本轮标注。"
                >
                  <Input
                    placeholder="backend-service/data/uploads/baseline.csv"
                    value={baseCsvPath}
                    onChange={(e) => setBaseCsvPath(e.target.value)}
                  />
                </Form.Item>
              )}
              {/* @AI_GENERATED: end */}
            </Form>
          </>
        ) : (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="新数据集已生成"
              description={`标注行数 ${backfillResult.labeled_rows} / 单元数 ${backfillResult.labeled_units}（原始 ${backfillResult.total_source_rows} 行）`}
            />
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="数据集版本">
                {backfillResult.dataset_version}
              </Descriptions.Item>
              <Descriptions.Item label="CSV 路径（复制到训练工作流 load_csv 的 file_path）">
                <Typography.Text copyable style={{ wordBreak: 'break-all' }}>
                  {backfillResult.csv_path}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>
            <Alert
              type="info"
              showIcon
              style={{ marginTop: 16 }}
              message="下一轮：把上面的 CSV 路径粘贴到训练工作流的 load_csv 节点 file_path，即可用扩充后的真值数据重新训练。"
            />
          </>
        )}
      </Modal>

      {/* @AI_GENERATED: 数据预览显式复用当前审核页面的 slot，避免 pv_fault 会话读取到其他场景的数据。 */}
      <Card
        title="数据预览（原始预测数据集）"
        size="small"
        style={{ marginTop: 16 }}
      >
        <DataPreviewTable
          sourceCsvPath={session.prediction_context?.source_csv_path as string | undefined}
          slotQuery={slotQuery}
        />
      </Card>
      {/* @AI_GENERATED: end */}
    </PvFaultWorkspaceShell>
  );
};

/**
 * 数据预览子组件：从会话的 source_csv_path 加载前 20 行展示
 */
// @AI_GENERATED: 将 URL 中的已编码场景参数传入独立组件，确保数据预览与审核会话保持同一分区。
const DataPreviewTable: React.FC<{ sourceCsvPath?: string; slotQuery: string }> = ({ sourceCsvPath, slotQuery }) => {
  const [previewData, setPreviewData] = useState<{ columns: string[]; rows: Array<Record<string, unknown>> } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    if (!sourceCsvPath) {
      setPreviewData(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setPreviewLoading(true);
      try {
        const resp = await fetch(`/api/iterative-labeling/data-preview?file_path=${encodeURIComponent(sourceCsvPath)}&rows=20&${slotQuery}`);
        if (!resp.ok || cancelled) return;
        const data = await resp.json();
        if (!cancelled) setPreviewData(data);
      } catch {
        if (!cancelled) setPreviewData(null);
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [sourceCsvPath, slotQuery]);
// @AI_GENERATED: end

  if (previewLoading) return <div style={{ textAlign: 'center', padding: 32 }}>加载数据预览...</div>;
  if (!previewData || !previewData.columns.length) return <Alert type="info" showIcon message="无法预览数据（会话缺少原始 CSV 路径）" />;

  const columns = previewData.columns.map((col) => ({
    title: col,
    dataIndex: col,
    key: col,
    ellipsis: true,
    width: 120,
    render: (v: unknown) => v === null || v === undefined || v === '' ? <Typography.Text type="secondary">-</Typography.Text> : String(v),
  }));

  return (
    <Table
      dataSource={previewData.rows.map((r, i) => ({ ...r, __key: i }))}
      columns={columns}
      rowKey="__key"
      size="small"
      pagination={false}
      scroll={{ x: 'max-content', y: 300 }}
    />
  );
};

export default IterativeLabelingReviewPage;
