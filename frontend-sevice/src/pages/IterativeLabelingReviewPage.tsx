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

import React, { useState, useEffect } from 'react';
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
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';

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
    predicted_label: number;           // 预测标签 label_id
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
}

/**
 * 审核会话状态
 */
interface ReviewSession {
  review_id: string;                   // 审核会话标识
  loop_id: string;                     // 所属迭代闭环
  status: 'reviewing' | 'reviewed';    // 会话状态
  reviewed_count: number;              // 已审核数
  total_count: number;                 // 总数
  units: DiagnosisUnit[];              // 待审核单元数组
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
  macro: {                              // Macro 口径精度
    precision: number;
    recall: number;
    f1: number;
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
  
  const [loading, setLoading] = useState(false);
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

  // 当前单元时序波形
  const [unitTimeseries, setUnitTimeseries] = useState<{
    timestamps: string[];
    series: Record<string, Array<number | null>>;
    point_count: number;
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

  /**
   * 加载审核会话
   */
  const loadReviewSession = async () => {
    if (!reviewId) {
      message.error('缺少审核会话 ID');
      return;
    }
    
    setLoading(true);
    try {
      // 需求 3.4：支持会话中断后恢复
      const response = await fetch(`/api/iterative-labeling/review-sessions/${reviewId}`);
      if (!response.ok) throw new Error('加载审核会话失败');
      
      const data = await response.json();
      setSession(data);
      
      // 断点恢复：找到第一个未审核的单元
      const firstUnreviewedIndex = data.units.findIndex(
        (u: DiagnosisUnit) => !u.current_verdict
      );
      if (firstUnreviewedIndex !== -1) {
        setCurrentUnitIndex(firstUnreviewedIndex);
      }
      
      message.success('加载审核会话成功');
    } catch (error) {
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
      const response = await fetch('/api/iterative-labeling/label-registry');
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
      const response = await fetch(`/api/iterative-labeling/review-sessions/${reviewId}/accuracy`);
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
        `/api/iterative-labeling/review-sessions/${reviewId}/backfill-to-dataset`,
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
   * 加载各类故障参考波形（仅在首次渲染时加载一次）
   */
  const loadReferenceWaveforms = async () => {
    if (!reviewId) return;
    setRefWaveformsLoading(true);
    try {
      // 从会话的 prediction_context 获取训练数据路径
      const sessResp = await fetch(`/api/iterative-labeling/review-sessions/${reviewId}`);
      if (!sessResp.ok) return;
      const sessData = await sessResp.json();
      const ctx = sessData.prediction_context || {};
      // 训练数据路径：使用相对于项目根目录的路径（后端 _resolve_data_path 会解析）
      // 训练数据已含 label 列，单文件模式即可
      const trainPath = ctx.reference_train_path || 'fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet';
      const resp = await fetch(
        `/api/iterative-labeling/reference-waveforms?train_csv_path=${encodeURIComponent(trainPath)}`
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
        `/api/iterative-labeling/review-sessions/${reviewId}/unit-timeseries?unit_key=${encodeURIComponent(unitKey)}`
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
  const getLabelName = (labelId?: number): string => {
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
        `/api/iterative-labeling/review-sessions/${reviewId}/verdicts`,
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
      if (!selectedLabel) {
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
        const response = await fetch('/api/iterative-labeling/label-registry/labels', {
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
    loadReviewSession();
    loadLabelRegistry();
    loadAccuracy();
    loadReferenceWaveforms();
    
    // 定期刷新精度（需求 6.4：增量更新）
    const interval = setInterval(loadAccuracy, 5000);
    return () => clearInterval(interval);
  }, [reviewId]);

  // 当前单元变化时加载其原始时序波形
  useEffect(() => {
    const unit = session?.units?.[currentUnitIndex];
    if (unit?.unit_key) {
      loadUnitTimeseries(unit.unit_key);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewId, currentUnitIndex, session?.units?.[currentUnitIndex]?.unit_key]);

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
    return <Card loading={loading}>加载中...</Card>;
  }

  const currentUnit = session.units[currentUnitIndex];
  const progressPercent = session.total_count > 0
    ? Math.round((session.reviewed_count / session.total_count) * 100)
    : 0;

  return (
    <div style={{ padding: '24px' }}>
      <Title level={2}>
        <FileTextOutlined /> 人工审核预测准确率
      </Title>
      
      {/* 需求 3.3：显示审核进度 */}
      <Card
        title="审核进度"
        style={{ marginBottom: 16 }}
        extra={
          <Button
            type="primary"
            icon={<FileTextOutlined />}
            disabled={session.reviewed_count === 0}
            onClick={() => { setBackfillResult(null); setBackfillModalOpen(true); }}
          >
            完成 → 生成新真值数据集
          </Button>
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
                valueStyle={{ color: '#1890ff' }}
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
                valueStyle={{ color: '#52c41a' }}
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
                valueStyle={{ color: '#faad14' }}
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
                value={(accuracy.macro.precision * 100).toFixed(2)}
                suffix="%"
                precision={2}
              />
            </Col>
            <Col span={8}>
              <Statistic
                title="Macro Recall"
                value={(accuracy.macro.recall * 100).toFixed(2)}
                suffix="%"
                precision={2}
              />
            </Col>
            <Col span={8}>
              <Statistic
                title="Macro F1"
                value={(accuracy.macro.f1 * 100).toFixed(2)}
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
              当前单元 ({currentUnitIndex + 1} / {session.units.length})
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

          {/* 各类故障参考波形对照 — 缩小放在设备波形上方方便对照 */}
          {refWaveforms.length > 0 && (
            <>
              <Divider>各类故障典型波形参考（对照用）</Divider>
              <Row gutter={[8, 8]}>
                {refWaveforms.map((ref) => (
                  <Col key={ref.label_id} span={8}>
                    <div style={{ border: '1px solid #f0f0f0', borderRadius: 4, padding: '4px 8px' }}>
                      <Space size={4} style={{ marginBottom: 2 }}>
                        <Tag color={ref.label_id === 0 || ref.label_id === 7 ? 'green' : 'red'} style={{ fontSize: 11 }}>
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
          <Divider>设备波形（电压 / 电流）</Divider>
          {timeseriesLoading ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>波形加载中...</div>
          ) : unitTimeseries && unitTimeseries.timestamps.length > 0 ? (
            (() => {
              const predId = currentUnit.classifier_prediction?.predicted_label;
              const predName = getLabelName(predId);
              const predConf = currentUnit.classifier_prediction?.confidence ?? 0;
              const isFault = predId !== undefined && predId !== 0 && predId !== 7; // 0正常/7汇流箱告警视为非严重
              const seriesEntries = Object.entries(unitTimeseries.series);
              const SERIES_NAMES: Record<string, string> = { value: '实测电流', i_cal: '理论电流' };
              return (
                <ReactECharts
                  style={{ height: 320 }}
                  option={{
                    title: {
                      text: `分类器预测：${predName}（label_${predId}）`,
                      subtext: predConf > 0 ? `置信度 ${(predConf * 100).toFixed(1)}%` : '置信度不可用（模型未输出概率）',
                      left: 'center',
                      textStyle: { fontSize: 13, color: isFault ? '#cf1322' : '#389e0d' },
                      subtextStyle: { fontSize: 11 },
                    },
                    tooltip: { trigger: 'axis' },
                    legend: {
                      data: seriesEntries.map(([k]) => SERIES_NAMES[k] || k),
                      bottom: 0,
                    },
                    grid: { left: 60, right: 30, top: 50, bottom: 50 },
                    xAxis: {
                      type: 'category',
                      data: unitTimeseries.timestamps.map((t) =>
                        t.includes(' ') ? t.split(' ')[1]?.slice(0, 5) || t : t.slice(11, 16)
                      ),
                      axisLabel: { rotate: 45, fontSize: 10 },
                    },
                    yAxis: [{ type: 'value' }],
                    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 28 }],
                    series: seriesEntries.map(([k, data], idx) => ({
                      name: SERIES_NAMES[k] || k,
                      type: 'line',
                      data,
                      smooth: true,
                      showSymbol: false,
                      lineStyle: { width: 1.5 },
                      itemStyle: { color: idx === 0 ? '#1890ff' : '#fa8c16' },
                      // 在第一条序列上叠加整窗预测标注（整天一个预测）
                      ...(idx === 0 ? {
                        markArea: {
                          silent: true,
                          itemStyle: { color: isFault ? 'rgba(255,77,79,0.08)' : 'rgba(82,196,26,0.08)' },
                          data: [[{ xAxis: 'min' }, { xAxis: 'max' }]],
                        },
                      } : {}),
                    })),
                  }}
                />
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
            </Text>
          )}

          {/* 需求 4：双来源并列展示 */}
          <Divider>双来源预测对比</Divider>
          
          <Row gutter={16}>
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
                      currentUnit.classifier_prediction.predicted_label_name ||
                      `label_${currentUnit.classifier_prediction.predicted_label}`
                    }
                    valueStyle={{ fontSize: 24 }}
                  />
                  <Statistic
                    title="置信度"
                    value={(currentUnit.classifier_prediction.confidence * 100).toFixed(1)}
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
          </Row>

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
              disabled={loading}
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
              {mergeBase && (
                <Form.Item
                  label="基线训练 CSV 路径"
                  help="填上一轮训练用的 CSV 绝对路径，将拼接到新标注数据前；留空则仅用本轮标注"
                >
                  <Input
                    placeholder="/Users/.../train_ori/xxx.csv"
                    value={baseCsvPath}
                    onChange={(e) => setBaseCsvPath(e.target.value)}
                  />
                </Form.Item>
              )}
            </Form>
          </>
        ) : (
          <>
            <Alert
              type="success"
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

      {/* 数据预览：展示原始预测数据集前 20 行 */}
      <Card
        title="数据预览（原始预测数据集）"
        size="small"
        style={{ marginTop: 16 }}
      >
        <DataPreviewTable reviewId={reviewId} />
      </Card>
    </div>
  );
};

/**
 * 数据预览子组件：从会话的 source_csv_path 加载前 20 行展示
 */
const DataPreviewTable: React.FC<{ reviewId: string | null }> = ({ reviewId }) => {
  const [previewData, setPreviewData] = useState<{ columns: string[]; rows: Array<Record<string, unknown>> } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    if (!reviewId) return;
    let cancelled = false;
    const load = async () => {
      setPreviewLoading(true);
      try {
        // 先拿会话获取 source_csv_path
        const sessResp = await fetch(`/api/iterative-labeling/review-sessions/${reviewId}`);
        if (!sessResp.ok || cancelled) return;
        const sess = await sessResp.json();
        const csvPath = sess?.prediction_context?.source_csv_path;
        if (!csvPath) { setPreviewData(null); return; }
        // 调用预览接口
        const resp = await fetch(`/api/iterative-labeling/data-preview?file_path=${encodeURIComponent(csvPath)}&rows=20`);
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
  }, [reviewId]);

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
