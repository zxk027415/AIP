// @AI_GENERATED
/**
 * 光伏故障项目工作台 —— 交互 Demo（纯前端 mock，不调用任何后端接口）
 *
 * 对应设计文档：.kiro/specs/pv-three-chain-product-validation/design.md
 *  - §11.1  沿用现有 MainLayout 全局壳；生命周期改为内容区顶部横向阶段带
 *  - §13    数据接入向导七步
 *  - §22.1  十个通用动作状态
 *  - §23    逐页状态合同（唯一主动作 + 状态 + 下一步）
 *  - §25    三路径 readiness 合同
 *
 * 用途：给评审看新结构长什么样。所有数据来自本文件内的常量，
 * 不发请求、不写任何真实状态，可安全打开。
 */
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Form,
  Radio,
  Segmented,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd';
import {
  ApartmentOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  LinkOutlined,
  MinusCircleOutlined,
  StopOutlined,
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;

// ─── Demo 常量：全部为假数据 ──────────────────────────────────────────────

/** 项目上下文（§11.1 项目上下文栏） */
const DEMO_CONTEXT = {
  scenarioName: '光伏制造',
  solutionName: '光伏故障诊断',
  projectName: 'PVDAQ 复验',
  slot: 'pv_tsc',
  slotLabel: 'pv_tsc（设备日时序分类）',
  datasetVersionId: 'lds-pv_tsc-20260908103200-a1b2c3',
  datasetVersionLabel: 'v3',
  runMode: 'experiment',
  runModeLabel: '实验',
  runDomain: 'sandbox',
  updatedAt: '10:32',
};

/** 六段生命周期阶段带（§11.1 ②，复用 story rail 的 tone 词汇） */
type StageTone = 'healthy' | 'pending' | 'warning' | 'critical' | 'idle';

const TONE_META: Record<StageTone, { label: string; color: string; bg: string; border: string }> = {
  healthy: { label: '已就绪', color: '#374151', bg: '#f3f4f6', border: 'rgba(55, 65, 81, 0.25)' },
  pending: { label: '进行中', color: '#b45309', bg: '#fff4eb', border: 'rgba(255, 106, 0, 0.45)' },
  warning: { label: '需关注', color: '#92400e', bg: '#fffbeb', border: 'rgba(217, 119, 6, 0.4)' },
  critical: { label: '需处理', color: '#991b1b', bg: '#fef2f2', border: 'rgba(220, 38, 38, 0.4)' },
  idle: { label: '未开始', color: '#6b7280', bg: '#fafafa', border: '#e8e8e8' },
};

const DEMO_STAGES: Array<{ key: string; label: string; detail: string; tone: StageTone }> = [
  { key: 'data', label: '数据与兼容性', detail: '已发布 v3，三路径 readiness 已出', tone: 'pending' },
  { key: 'workflow', label: '工作流与运行', detail: '已绑定 v3，预检通过', tone: 'healthy' },
  { key: 'model', label: '模型与治理', detail: '无可治理候选（validation 不可治理）', tone: 'warning' },
  { key: 'detect', label: '检测与回放', detail: 'TSC 生产观测只读，待运行', tone: 'idle' },
  { key: 'review', label: '审核与精度', detail: '3 条待审核', tone: 'pending' },
  { key: 'cumulative', label: '累计训练集', detail: '快照 v2，尚未 freeze 新版', tone: 'healthy' },
];

/** 数据预览（§13 第 3 步） */
const PREVIEW_COLUMNS = ['time', 'site_id', 'device_id', 'branch_id', 'value', 'i_cal', 'is_measured'];
const PREVIEW_ROWS = [
  { time: '2026-03-01 08:00', site_id: 'S-01', device_id: 'D-1403', branch_id: 'B-2', value: '4.812', i_cal: '5.004', is_measured: '1' },
  { time: '2026-03-01 08:05', site_id: 'S-01', device_id: 'D-1403', branch_id: 'B-2', value: '5.107', i_cal: '5.233', is_measured: '1' },
  { time: '2026-03-01 08:10', site_id: 'S-01', device_id: 'D-1403', branch_id: 'B-2', value: '5.402', i_cal: '5.488', is_measured: '1' },
  { time: '2026-03-01 08:15', site_id: 'S-01', device_id: 'D-1404', branch_id: 'B-1', value: '0.000', i_cal: '5.501', is_measured: '1' },
  { time: '2026-03-01 08:20', site_id: 'S-01', device_id: 'D-1404', branch_id: 'B-1', value: '0.000', i_cal: '5.640', is_measured: '1' },
];

/** 数据质量检查（§13 第 5 步：事实 → 影响 → 建议） */
const QUALITY_CHECKS: Array<{
  check: string;
  fact: string;
  impact: string;
  advice: string;
  tone: StageTone;
}> = [
  {
    check: '日期覆盖',
    fact: '671 天跨度内只有 35 个实际日期',
    impact: 'pv_tsc 的严格日期 × 设备双隔离可能不稳定',
    advice: '可继续做实验；要拿生产资格需补连续日期',
    tone: 'warning',
  },
  {
    check: '设备覆盖',
    fact: '设备 D-1403 从未进入测试侧（32 个异常日）',
    impact: '泛化结论不完整，不能声称已覆盖全部设备',
    advice: '记录为覆盖缺口，不阻断实验',
    tone: 'warning',
  },
  {
    check: '采样完整率',
    fact: '白天占用率 91.4%，最大空洞 4 格',
    impact: '满足 288 格点门槛（≥173 且空洞 ≤6）',
    advice: '无需处理',
    tone: 'healthy',
  },
  {
    check: '标签分布',
    fact: '13 类，其中 4 类样本数 < 20',
    impact: '少数类精度不可信，生产复验受阻',
    advice: '实验可保留；补样本后再复验',
    tone: 'warning',
  },
  {
    check: '期望电流参照 i_cal',
    fact: '存在且尺度一致，未声明校准合同',
    impact: 'i_cal 是参照量而非真值；未声明合同时不可用于治理',
    advice: '发布前显式选择 i_cal_contract',
    tone: 'critical',
  },
  {
    check: '点级真值',
    fact: '仅有设备日标签，无逐点标注',
    impact: 'pv_point 不能把整日标签当逐点真值',
    advice: 'pv_point 仅可做无标签因果回放',
    tone: 'warning',
  },
];

/** 三路径 readiness（§25） */
type ReadinessStatus = 'ready' | 'experiment_only' | 'needs_mapping' | 'needs_labels' | 'insufficient_data' | 'unsupported';

const READINESS_META: Record<ReadinessStatus, { label: string; tone: StageTone }> = {
  ready: { label: '就绪', tone: 'healthy' },
  experiment_only: { label: '仅可实验', tone: 'pending' },
  needs_mapping: { label: '缺映射', tone: 'critical' },
  needs_labels: { label: '缺标签', tone: 'warning' },
  insufficient_data: { label: '数据不足', tone: 'warning' },
  unsupported: { label: '不支持', tone: 'critical' },
};

const DEMO_READINESS: Array<{
  slot: string;
  slotLabel: string;
  status: ReadinessStatus;
  primaryBlocker: string;
  allowedRunModes: string[];
  nextAction: string;
}> = [
  {
    slot: 'pv_day',
    slotLabel: 'pv_day（设备日统计）',
    status: 'experiment_only',
    primaryBlocker: '少数类样本不足，无法取得生产资格',
    allowedRunModes: ['experiment', 'validation'],
    nextAction: '创建 day 训练工作流并按实验运行',
  },
  {
    slot: 'pv_point',
    slotLabel: 'pv_point（真实点回放）',
    status: 'needs_labels',
    primaryBlocker: '只有设备日标签，缺少点级或区间级真值',
    allowedRunModes: ['experiment'],
    nextAction: '仅可做无标签 Sandbox 因果回放',
  },
  {
    slot: 'pv_tsc',
    slotLabel: 'pv_tsc（设备日时序分类）',
    status: 'experiment_only',
    primaryBlocker: '35 个离散日期不足以稳定通过 strict 日期 × 设备双隔离',
    allowedRunModes: ['experiment', 'validation'],
    nextAction: '启动 TSC 模型辅助打标，或按实验运行训练',
  },
];

/** 十个通用动作状态（§22.1） */
const ACTION_STATES: Array<{ key: string; name: string; when: string; allow: string }> = [
  { key: 'initial_empty', name: '初始空态', when: '从未产出、队列为空、无候选', allow: '只给一个补齐前置项的主动作' },
  { key: 'loading', name: '加载态', when: '首次读取、切换 scope 后重读、轮询中', allow: '等待或取消；不得用旧数据操作' },
  { key: 'ready', name: '可开始', when: '前置齐备且无在途作业', allow: '显示唯一主动作' },
  { key: 'waiting_human', name: '等待人工', when: '等他人审核、等审批、等到数', allow: '进入审核，不重复启动计算' },
  { key: 'blocked', name: '门控阻断', when: '无权限、provenance 缺失、版本冲突', allow: '只允许修复上游或看证据' },
  { key: 'insufficient_data', name: '数据不足', when: '日期 / 设备 / 类别 / 标签覆盖不足', allow: '可实验，不伪装 production-ready' },
  { key: 'read_only', name: '只读', when: '角色只读、legacy 项目、TSC 生产观测', allow: '看证据或去授权入口' },
  { key: 'recoverable_failure', name: '可恢复失败', when: '解析失败、execution 失败、cursor 冲突', allow: '原输入重试或修改后新跑' },
  { key: 'fail_closed', name: '安全失败', when: 'scope 不匹配、证据冲突、记录缺失', allow: '修复后重读，无绕过按钮' },
  { key: 'completed', name: '已完成', when: '已产出真实产物或幂等命中', allow: '进入下一阶段' },
];

const WIZARD_STEPS = ['选择来源', '上传 / 连接', '预览', '字段映射', '数据质量', '路径兼容性', '发布版本'];

// ─── 小组件 ──────────────────────────────────────────────────────────────

function ToneTag({ tone, text }: { tone: StageTone; text?: string }) {
  const meta = TONE_META[tone];
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 8px',
        borderRadius: 10,
        fontSize: 12,
        lineHeight: '18px',
        color: meta.color,
        background: meta.bg,
        border: `1px solid ${meta.border}`,
        whiteSpace: 'nowrap',
      }}
    >
      {text || meta.label}
    </span>
  );
}

/** ① 项目上下文栏 —— 复用现有 .pv-page-header 样式（§11.1 ①） */
function ContextBar({ onSwitch }: { onSwitch: () => void }) {
  const item = (label: string, value: ReactNode) => (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 4 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
      <Text strong style={{ fontSize: 13 }}>{value}</Text>
    </span>
  );

  return (
    <div className="pv-page-header">
      <div style={{ minWidth: 0 }}>
        <Space size={4} wrap style={{ marginBottom: 6 }}>
          <Tag color="orange" style={{ marginInlineEnd: 4 }}>交互 Demo</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>
            纯前端 mock，不调用后端、不写任何真实状态
          </Text>
        </Space>
        <Title level={4} className="pv-page-header-title" style={{ marginBottom: 8 }}>
          {DEMO_CONTEXT.projectName}
        </Title>
        <Space size={16} wrap>
          {item('行业场景', DEMO_CONTEXT.scenarioName)}
          <Text type="secondary">›</Text>
          {item('算法方案', DEMO_CONTEXT.solutionName)}
          <Text type="secondary">›</Text>
          {item('诊断路径', DEMO_CONTEXT.slot)}
          <Divider type="vertical" />
          {item('数据版本', DEMO_CONTEXT.datasetVersionLabel)}
          {item('运行目的', <Tag color="orange" style={{ marginInlineEnd: 0 }}>{DEMO_CONTEXT.runModeLabel}</Tag>)}
          {item('运行域', <Tag style={{ marginInlineEnd: 0 }}>{DEMO_CONTEXT.runDomain}</Tag>)}
          {item('最近更新', DEMO_CONTEXT.updatedAt)}
        </Space>
      </div>
      <Space direction="vertical" align="end" size={8}>
        <Button icon={<ApartmentOutlined />} onClick={onSwitch}>切换项目 / 路径</Button>
        <Tooltip title="设计 §11.1：上下文栏吸收原先右上角的槽位下拉，不再另设一处路径选择器">
          <Text type="secondary" style={{ fontSize: 12 }}>
            <InfoCircleOutlined /> 槽位选择已并入此处
          </Text>
        </Tooltip>
      </Space>
    </div>
  );
}

/** ② 六段横向生命周期阶段带（§11.1 ②） */
function StageBand({
  activeKey,
  onPick,
}: {
  activeKey: string;
  onPick: (key: string) => void;
}) {
  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={<span className="pv-section-label" style={{ marginBottom: 0 }}>生命周期阶段</span>}
      extra={<Text type="secondary" style={{ fontSize: 12 }}>点击任意阶段进入；不再使用第二条左侧竖导航</Text>}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 10,
        }}
      >
        {DEMO_STAGES.map((stage, index) => {
          const meta = TONE_META[stage.tone];
          const isActive = stage.key === activeKey;
          return (
            <button
              key={stage.key}
              type="button"
              onClick={() => onPick(stage.key)}
              aria-current={isActive ? 'step' : undefined}
              style={{
                position: 'relative',
                textAlign: 'left',
                cursor: 'pointer',
                padding: '10px 12px 12px',
                borderRadius: 10,
                background: isActive ? '#fff' : '#fcfcfc',
                border: `1px solid ${isActive ? 'rgba(255,106,0,0.45)' : '#e8e8e8'}`,
                boxShadow: isActive ? '0 0 0 1px rgba(255,106,0,0.35)' : 'none',
                transition: 'border-color 180ms ease, box-shadow 180ms ease',
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  top: 8,
                  right: 10,
                  fontSize: 11,
                  fontWeight: 700,
                  color: '#6b7280',
                  opacity: 0.45,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {String(index + 1).padStart(2, '0')}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: meta.color,
                    flexShrink: 0,
                  }}
                />
                <Text strong style={{ fontSize: 13 }}>{stage.label}</Text>
              </div>
              <div style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.5, minHeight: 36 }}>
                {stage.detail}
              </div>
              <div style={{ marginTop: 6 }}>
                <ToneTag tone={stage.tone} />
              </div>
            </button>
          );
        })}
      </div>
    </Card>
  );
}

/** ③ 通栏下一步条（§11.1 ③：不做右侧竖栏） */
function NextStepBar({
  reason,
  impact,
  primary,
  secondary,
}: {
  reason: string;
  impact: string;
  primary: string;
  secondary: string;
}) {
  return (
    <Card
      size="small"
      style={{ marginBottom: 16, borderColor: 'rgba(255,106,0,0.35)', background: '#fffaf5' }}
      bodyStyle={{ padding: '12px 16px' }}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
        <div style={{ flex: '1 1 420px', minWidth: 0 }}>
          <Space size={6} style={{ marginBottom: 2 }}>
            <Text strong style={{ fontSize: 13 }}>下一步</Text>
            <ToneTag tone="pending" text="唯一主动作" />
          </Space>
          <div style={{ fontSize: 13, color: '#111' }}>{reason}</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>影响范围：{impact}</div>
        </div>
        <Space>
          <Button>{secondary}</Button>
          <Button type="primary">{primary}</Button>
        </Space>
      </div>
    </Card>
  );
}

// ─── 数据接入向导（§13） ─────────────────────────────────────────────────

function DataOnboardingWizard() {
  const [step, setStep] = useState(0);
  const [source, setSource] = useState<'upload' | 'asset' | 'connector' | 'reuse'>('upload');
  const [published, setPublished] = useState(false);

  const canNext = step < WIZARD_STEPS.length - 1;

  const sourceOptions = [
    { value: 'upload', label: '上传 CSV / Parquet', desc: '浏览器直接选文件，不填服务器路径' },
    { value: 'asset', label: '选择平台数据资产', desc: '复用已注册的数据资产' },
    { value: 'connector', label: '注册数据库 / 对象存储连接器', desc: '只保存连接器 ID，不保存凭据' },
    { value: 'reuse', label: '复用本项目历史版本', desc: '从已发布的不可变版本再建一版' },
  ];

  return (
    <Card
      title={<span className="pv-section-label" style={{ marginBottom: 0 }}>数据接入向导（设计 §13）</span>}
      extra={
        <Text type="secondary" style={{ fontSize: 12 }}>
          目标态：选数据资产 → 确认映射 → 看质量事实 → 看三路径 readiness → 发布不可变版本
        </Text>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="与当前实现的差别"
        description={
          <span style={{ fontSize: 13 }}>
            当前平台没有这条路：数据集管理页的上传按钮不发请求，实际做法是先手工把文件放到后端目录，
            再打开工作流编辑器点中 <Text code>load_csv</Text> 节点手填相对路径；非 pv 槽位甚至没有下拉可选。
            本向导要把这一段替换为浏览器内可完成、且产出**不可变数据版本**的流程。
          </span>
        }
      />

      <Steps
        size="small"
        current={step}
        onChange={setStep}
        style={{ marginBottom: 20 }}
        items={WIZARD_STEPS.map((title) => ({ title }))}
      />

      {/* 第 1 步 选择来源 */}
      {step === 0 && (
        <Radio.Group
          value={source}
          onChange={(e) => setSource(e.target.value)}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12, width: '100%' }}
        >
          {sourceOptions.map((opt) => (
            <Radio.Button
              key={opt.value}
              value={opt.value}
              style={{ height: 'auto', padding: '12px 14px', textAlign: 'left', whiteSpace: 'normal', lineHeight: 1.5 }}
            >
              <div style={{ fontWeight: 600, fontSize: 13 }}>{opt.label}</div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>{opt.desc}</div>
            </Radio.Button>
          ))}
        </Radio.Group>
      )}

      {/* 第 2 步 上传 / 连接 */}
      {step === 1 && (
        <>
          {source === 'upload' ? (
            <Upload.Dragger
              disabled
              accept=".csv,.parquet"
              style={{ background: '#fafafa' }}
              beforeUpload={() => false}
            >
              <p style={{ fontSize: 30, color: '#ff6a00', marginBottom: 8 }}><InboxOutlined /></p>
              <p style={{ fontSize: 13, margin: 0 }}>Demo 中已禁用真实上传</p>
              <p style={{ fontSize: 12, color: '#6b7280', margin: '4px 0 0' }}>
                目标态调用 <Text code>POST /api/upload/file</Text>，只持久化相对工件引用
              </p>
            </Upload.Dragger>
          ) : (
            <Alert
              type="warning"
              showIcon
              message={`已选来源：${sourceOptions.find((o) => o.value === source)?.label}`}
              description="连接器只保存 connector_id 与逻辑对象描述；凭据不进入 API、日志或证据。预览限制行数与时间范围，完整物化异步执行并可恢复。"
            />
          )}
          <Descriptions size="small" column={2} bordered style={{ marginTop: 16 }}>
            <Descriptions.Item label="文件名">pvdaq_expansion_6m.parquet</Descriptions.Item>
            <Descriptions.Item label="大小">184.2 MB</Descriptions.Item>
            <Descriptions.Item label="持久化形式">相对 artifact_ref（不写机器绝对路径）</Descriptions.Item>
            <Descriptions.Item label="长任务">物化任务可离开页面后恢复</Descriptions.Item>
          </Descriptions>
        </>
      )}

      {/* 第 3 步 预览 */}
      {step === 2 && (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>展示样例行与列类型，帮助判断映射；不是最终数据。</Text>
          <Table
            size="small"
            style={{ marginTop: 12 }}
            pagination={false}
            scroll={{ x: 720 }}
            rowKey="time"
            dataSource={PREVIEW_ROWS}
            columns={PREVIEW_COLUMNS.map((c) => ({ title: c, dataIndex: c, key: c, width: 130 }))}
          />
        </>
      )}

      {/* 第 4 步 字段映射 */}
      {step === 3 && (
        <>
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="映射必须由用户确认，不能只依赖系统猜测"
            description="这是当前实现最缺的一环：现在列名不匹配只能在算子面板手写 rename_columns 的 JSON，且错误要等执行时才暴露。"
          />
          <Form layout="vertical" size="small">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0 16px' }}>
              <Form.Item label="时间列" required tooltip="决定日边界、point event-time 顺序与 TSC 288 格点">
                <Select defaultValue="time" options={PREVIEW_COLUMNS.map((c) => ({ label: c, value: c }))} />
              </Form.Item>
              <Form.Item label="时区" required>
                <Select defaultValue="Asia/Shanghai" options={[{ label: 'Asia/Shanghai', value: 'Asia/Shanghai' }, { label: 'UTC', value: 'UTC' }]} />
              </Form.Item>
              <Form.Item label="采样频率" required>
                <Select defaultValue="5min" options={[{ label: '5 分钟', value: '5min' }, { label: '15 分钟', value: '15min' }]} />
              </Form.Item>
              <Form.Item label="重复点策略" required>
                <Select defaultValue="keep_last" options={[{ label: '保留最后一条', value: 'keep_last' }, { label: '报错', value: 'raise' }]} />
              </Form.Item>
              <Form.Item label="设备 device_id" required>
                <Select defaultValue="device_id" options={PREVIEW_COLUMNS.map((c) => ({ label: c, value: c }))} />
              </Form.Item>
              <Form.Item label="支路 branch_id">
                <Select defaultValue="branch_id" allowClear options={PREVIEW_COLUMNS.map((c) => ({ label: c, value: c }))} />
              </Form.Item>
              <Form.Item label="实测值 value" required>
                <Select defaultValue="value" options={PREVIEW_COLUMNS.map((c) => ({ label: c, value: c }))} />
              </Form.Item>
              <Form.Item
                label="期望电流参照 i_cal"
                tooltip="i_cal 是参照量，不是 ground truth；使用时必须显式声明校准合同"
              >
                <Select defaultValue="i_cal" allowClear options={PREVIEW_COLUMNS.map((c) => ({ label: c, value: c }))} />
              </Form.Item>
              <Form.Item label="校准合同 i_cal_contract" required tooltip="不提供默认值，缺失即 fail-closed">
                <Select
                  placeholder="必须显式选择"
                  options={[
                    { label: 'value_only（i_cal 固定为 0）', value: 'value_only' },
                    { label: 'global_train_devices_only', value: 'global_train_devices_only' },
                    { label: 'history_past_only', value: 'history_past_only' },
                    { label: 'leaky_device_ical（泄漏上界，仅诊断）', value: 'leaky_device_ical' },
                  ]}
                />
              </Form.Item>
              <Form.Item label="标签粒度" required tooltip="禁止把设备日标签冒充 pv_point 点级真值">
                <Select
                  defaultValue="device_day"
                  options={[
                    { label: '设备日级', value: 'device_day' },
                    { label: '区间级', value: 'interval' },
                    { label: '点级', value: 'point' },
                  ]}
                />
              </Form.Item>
            </div>
          </Form>
        </>
      )}

      {/* 第 5 步 数据质量 */}
      {step === 4 && (
        <Table
          size="small"
          pagination={false}
          rowKey="check"
          dataSource={QUALITY_CHECKS}
          columns={[
            { title: '检查', dataIndex: 'check', width: 130 },
            { title: '事实', dataIndex: 'fact', width: 260 },
            { title: '产品影响', dataIndex: 'impact', width: 280 },
            { title: '建议', dataIndex: 'advice', width: 220 },
            {
              title: '级别',
              dataIndex: 'tone',
              width: 90,
              render: (tone: StageTone) => <ToneTag tone={tone} />,
            },
          ]}
          scroll={{ x: 980 }}
        />
      )}

      {/* 第 6 步 路径兼容性 */}
      {step === 5 && (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>
            三条路径**分别**给结论，不给项目一个模糊总分。注意：“就绪”只表示输入与预检合同可用，不表示可以上生产。
          </Text>
          <Table
            size="small"
            style={{ marginTop: 12 }}
            pagination={false}
            rowKey="slot"
            dataSource={DEMO_READINESS}
            columns={[
              { title: '诊断路径', dataIndex: 'slotLabel', width: 200 },
              {
                title: 'readiness',
                dataIndex: 'status',
                width: 110,
                render: (s: ReadinessStatus) => <ToneTag tone={READINESS_META[s].tone} text={READINESS_META[s].label} />,
              },
              { title: '首要阻断 primary_blocker', dataIndex: 'primaryBlocker', width: 320 },
              {
                title: '允许运行目的',
                dataIndex: 'allowedRunModes',
                width: 180,
                render: (modes: string[]) => (
                  <Space size={4} wrap>
                    {modes.map((m) => <Tag key={m} style={{ marginInlineEnd: 0 }}>{m}</Tag>)}
                    <Tooltip title="production 未列出，因为数据不足以取得生产资格">
                      <Tag color="default" style={{ marginInlineEnd: 0, opacity: 0.6 }}>
                        <StopOutlined /> production
                      </Tag>
                    </Tooltip>
                  </Space>
                ),
              },
              { title: '最短下一步', dataIndex: 'nextAction', width: 260 },
            ]}
            scroll={{ x: 1080 }}
          />
        </>
      )}

      {/* 第 7 步 发布版本 */}
      {step === 6 && (
        <>
          {published ? (
            <Alert
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
              message="已发布不可变数据版本（Demo 未写入任何真实状态）"
              description="下一步：为可用路径创建工作流。工作流的加载节点从此选择“已发布数据版本”，不再输入路径。"
              style={{ marginBottom: 16 }}
            />
          ) : (
            <Alert
              type="info"
              showIcon
              message="发布后版本内容不可更改"
              description="修改映射会创建新的 dataset_profile_id 与新版本，而不是静默改写原版本。"
              style={{ marginBottom: 16 }}
            />
          )}
          <Descriptions size="small" bordered column={1}>
            <Descriptions.Item label="dataset_id">ds-pvdaq-expansion-6m</Descriptions.Item>
            <Descriptions.Item label="dataset_version_id">{DEMO_CONTEXT.datasetVersionId}</Descriptions.Item>
            <Descriptions.Item label="dataset_profile_id">dp-20260908103200-7f31aa</Descriptions.Item>
            <Descriptions.Item label="内容摘要 sha256">e3b0c442…（不可变）</Descriptions.Item>
            <Descriptions.Item label="工件引用 artifact_ref">
              <Text code>data/uploads/upload-20260908103200-7f31aa.parquet</Text>
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>相对路径，不含机器绝对路径</Text>
            </Descriptions.Item>
            <Descriptions.Item label="三路径 readiness">
              <Space size={8} wrap>
                {DEMO_READINESS.map((r) => (
                  <span key={r.slot}>
                    <Text style={{ fontSize: 12 }}>{r.slot}</Text>{' '}
                    <ToneTag tone={READINESS_META[r.status].tone} text={READINESS_META[r.status].label} />
                  </span>
                ))}
              </Space>
            </Descriptions.Item>
          </Descriptions>
          {!published && (
            <Button type="primary" style={{ marginTop: 16 }} onClick={() => setPublished(true)}>
              发布数据版本（Demo）
            </Button>
          )}
        </>
      )}

      <Divider style={{ margin: '20px 0 12px' }} />
      <Space>
        <Button disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>上一步</Button>
        <Button type="primary" disabled={!canNext} onClick={() => setStep((s) => Math.min(WIZARD_STEPS.length - 1, s + 1))}>
          下一步
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          第 {step + 1} / {WIZARD_STEPS.length} 步 · {WIZARD_STEPS[step]}
        </Text>
      </Space>
    </Card>
  );
}

// ─── 其他阶段的占位内容 ──────────────────────────────────────────────────

function StagePlaceholder({ stageKey }: { stageKey: string }) {
  const stage = DEMO_STAGES.find((s) => s.key === stageKey);
  const map: Record<string, { section: string; primary: string; states: string[] }> = {
    workflow: {
      section: '§15 工作流与运行：创建 + 执行前预检 + 运行中心',
      primary: '预检通过后运行',
      states: ['预检加载 / 失败 / 阻断 / 警告', '运行中重复提交', '取消确认', '刷新恢复', '后端记录不存在'],
    },
    model: {
      section: '§16 模型与治理：四层结构（当前检测模型 / 待处理候选 / 实验结果 / 治理历史）',
      primary: '当前阶段唯一治理动作',
      states: ['registry 不存在或结构错误', '候选空态', 'provenance 缺失', '复验轮询失败', '版本冲突', 'validation 不可治理'],
    },
    detect: {
      section: '§17 检测与回放：Sandbox 回放 / Validation 观察 / Production 观测',
      primary: '创建或继续运行会话',
      states: ['无 Sandbox', '等待到数', '连接中断', '生产只读', '重置无权限'],
    },
    review: {
      section: '§18 审核与精度',
      primary: '提交当前 verdict 或完成并准入',
      states: ['队列空 / 加载 / 失败', '并发改判冲突', '部分完成', '准入禁用原因', '无有效真值显示“未产出”'],
    },
    cumulative: {
      section: '§19 累计训练集与再训练（已准入事件 / 已冻结快照 / 训练结果 三层）',
      primary: 'freeze 或从快照训练',
      states: ['无入账事件', 'freeze queued / running / failed / cancelled', '幂等命中', '无权限'],
    },
  };
  const info = map[stageKey];

  return (
    <Card title={<span className="pv-section-label" style={{ marginBottom: 0 }}>{stage?.label}</span>}>
      {info ? (
        <>
          <Paragraph style={{ marginBottom: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>对应设计章节</Text>
            <br />
            <Text strong>{info.section}</Text>
          </Paragraph>
          <Descriptions size="small" bordered column={1}>
            <Descriptions.Item label="唯一主动作">{info.primary}</Descriptions.Item>
            <Descriptions.Item label="必须覆盖的状态">
              <Space size={6} wrap>
                {info.states.map((s) => <Tag key={s} style={{ marginInlineEnd: 0 }}>{s}</Tag>)}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="当前状态">
              <ToneTag tone={stage?.tone || 'idle'} /> <Text type="secondary" style={{ fontSize: 12 }}>{stage?.detail}</Text>
            </Descriptions.Item>
          </Descriptions>
          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message="Demo 只呈现数据接入这一阶段的完整交互"
            description="其余阶段在此仅展示“唯一主动作 + 必须覆盖的状态”的合同形态，用于说明每页结构一致。"
          />
        </>
      ) : (
        <Text type="secondary">该阶段暂无 Demo 内容。</Text>
      )}
    </Card>
  );
}

/** 十个动作状态词汇表（§22.1）—— 说明为什么要统一 */
function ActionStateVocabulary() {
  return (
    <Card
      size="small"
      style={{ marginTop: 16 }}
      title={<span className="pv-section-label" style={{ marginBottom: 0 }}>统一动作状态词汇（设计 §22.1）</span>}
      extra={
        <Text type="secondary" style={{ fontSize: 12 }}>
          每页的每种情形都必须归到这十个之一，不允许各页自造状态名
        </Text>
      }
    >
      <Table
        size="small"
        pagination={false}
        rowKey="key"
        dataSource={ACTION_STATES}
        columns={[
          {
            title: '状态',
            dataIndex: 'name',
            width: 130,
            render: (name: string, row) => (
              <span>
                <Text strong style={{ fontSize: 13 }}>{name}</Text>
                <br />
                <Text code style={{ fontSize: 11 }}>{row.key}</Text>
              </span>
            ),
          },
          { title: '什么时候用', dataIndex: 'when', width: 300 },
          { title: '允许的动作与恢复', dataIndex: 'allow', width: 320 },
        ]}
        scroll={{ x: 780 }}
      />
      <Space size={16} wrap style={{ marginTop: 12 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          <MinusCircleOutlined /> 横切标记可叠加：已取消 CANCELLED
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          <ExclamationCircleOutlined /> 结论已过期 STALE
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          <StopOutlined /> 后端记录缺失 BACKEND_RECORD_MISSING
        </Text>
      </Space>
    </Card>
  );
}

/** 前后端入口对照（§40）—— 让评审直接看到差距 */
function EntryPointPanel() {
  const rows = [
    { stage: '上传数据集', fe: 'DatasetPage.tsx 上传弹窗', be: '未接（beforeUpload 直接 return false）', real: '假' },
    { stage: '真实文件上传', fe: 'DatasetPanel / SlotStoryLoopPanel / FunctionExecutor', be: 'POST /api/upload/file', real: '真' },
    { stage: '数据源管理', fe: 'DataSourcePage.tsx', be: '无', real: '假' },
    { stage: 'pv 数据登记', fe: 'DatasetPage.tsx 内 PvTrainingDatasetCard', be: '/api/iterative-labeling/data-preview 等', real: '真（起点是手填路径）' },
    { stage: '工作流选数据', fe: 'PropertyPanelV2.tsx renderTrainableFilePathField', be: 'GET /datasets/trainable?slot=', real: '真（仅 pv 三槽有下拉）' },
    { stage: '算子读文件', fe: '—', be: 'operator_backends/load_csv.py', real: '真（四级相对路径搜索）' },
    { stage: '数据版本实体', fe: '—', be: 'slot_datasets/labeled_versions.py', real: '真（仅 pv 三槽）' },
  ];
  return (
    <Card
      size="small"
      style={{ marginTop: 16 }}
      title={<span className="pv-section-label" style={{ marginBottom: 0 }}>数据接入的前后端入口现状（设计 §40.1）</span>}
    >
      <Table
        size="small"
        pagination={false}
        rowKey="stage"
        dataSource={rows}
        columns={[
          { title: '环节', dataIndex: 'stage', width: 130 },
          { title: '前端入口', dataIndex: 'fe', width: 320, render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text> },
          { title: '后端接口', dataIndex: 'be', width: 280, render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text> },
          {
            title: '真实性',
            dataIndex: 'real',
            width: 160,
            render: (v: string) => <ToneTag tone={v.startsWith('真') ? 'healthy' : 'critical'} text={v} />,
          },
        ]}
        scroll={{ x: 880 }}
      />
    </Card>
  );
}

// ─── 页面 ────────────────────────────────────────────────────────────────

const PvFaultWorkbenchDemoPage: React.FC = () => {
  const [activeStage, setActiveStage] = useState('data');
  const [view, setView] = useState<'workbench' | 'vocabulary'>('workbench');

  const nextStep = useMemo(() => {
    if (activeStage === 'data') {
      return {
        reason: '数据版本 v3 已发布；pv_tsc 仅可实验（35 个离散日期不足以稳定通过 strict 双隔离）',
        impact: '创建工作流不写生产状态，只产生实验 execution',
        primary: '为 pv_tsc 创建工作流',
        secondary: '查看质量事实',
      };
    }
    const stage = DEMO_STAGES.find((s) => s.key === activeStage);
    return {
      reason: stage?.detail || '',
      impact: 'Demo 不写任何真实状态',
      primary: '查看该阶段证据',
      secondary: '返回数据阶段',
    };
  }, [activeStage]);

  return (
    <div className="pv-fault-workspace pv-page-shell">
      <ContextBar onSwitch={() => undefined} />

      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="这是设计评审用的交互 Demo"
        description={
          <span style={{ fontSize: 13 }}>
            页面沿用现有 MainLayout 全局壳（左侧菜单不变），内容区按设计 §11.1 分为
            「项目上下文栏 → 横向生命周期阶段带 → 通栏下一步条 → 内容区」四层。
            所有数据为本文件内常量，<Text strong>不调用任何后端接口，不写任何真实状态</Text>。
          </span>
        }
      />

      <Segmented
        style={{ marginBottom: 16 }}
        value={view}
        onChange={(v) => setView(v as 'workbench' | 'vocabulary')}
        options={[
          { label: <span><DatabaseOutlined /> 工作台结构与数据接入</span>, value: 'workbench' },
          { label: <span><FileTextOutlined /> 状态词汇与入口对照</span>, value: 'vocabulary' },
        ]}
      />

      {view === 'workbench' ? (
        <>
          <StageBand activeKey={activeStage} onPick={setActiveStage} />
          <NextStepBar {...nextStep} />
          {activeStage === 'data' ? <DataOnboardingWizard /> : <StagePlaceholder stageKey={activeStage} />}
        </>
      ) : (
        <>
          <ActionStateVocabulary />
          <EntryPointPanel />
          <Card size="small" style={{ marginTop: 16 }}>
            <Space direction="vertical" size={4}>
              <Text strong style={{ fontSize: 13 }}>
                <LinkOutlined /> 相关设计章节
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>§11.1 工作台在现有壳内的落位 · §11.4 现有组件包装优先归属</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>§13 数据接入向导 · §25 数据 readiness 合同</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>§22 生命周期与横切状态 · §23 逐页状态合同</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>§40 前后端入口对照（现状与目标）</Text>
            </Space>
          </Card>
        </>
      )}

      <div style={{ marginTop: 20, textAlign: 'center' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          <CloudUploadOutlined /> Demo 页面路径：<Text code>frontend-sevice/src/pages/pv-fault-demo/PvFaultWorkbenchDemoPage.tsx</Text>
        </Text>
      </div>
    </div>
  );
};

export default PvFaultWorkbenchDemoPage;
// @AI_GENERATED: end
