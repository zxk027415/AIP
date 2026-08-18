// @AI_GENERATED
/**
 * PvDualPathConsole — 光伏故障双路径面板。
 * 不再作为独立侧栏页：治理卡挂算法部署 pv_fault，运营卡挂精度运营 pv_fault。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { pvDualPathApi } from '../services/pvDualPathApi';
import type {
  GateResult,
  LedgerPage,
  ModelingPathsState,
  PathSwitchEvent,
  PromotionEvent,
  ShadowReport,
} from '../types/pvDualPath';
import {
  PV_DUAL_PATH_REFRESH_MS,
  formatAgreementRate,
  isCrossPath,
  isStrictTrue,
  ledgerStatusLabel,
  requiresBackfillDays,
} from './pv-dual-path/pvDualPathConsoleLogic';

const { Text, Title, Paragraph } = Typography;

const SLOT = 'pv_fault';

export type PvDualPathPanelVariant = 'governance' | 'operations' | 'all';

const PvDualPathConsole: React.FC<{ variant?: PvDualPathPanelVariant }> = ({ variant = 'all' }) => {
  const [paths, setPaths] = useState<ModelingPathsState | null>(null);
  const [ledger, setLedger] = useState<LedgerPage | null>(null);
  const [epochs, setEpochs] = useState<Record<string, unknown> | null>(null);
  const [promotions, setPromotions] = useState<PromotionEvent[]>([]);
  const [switches, setSwitches] = useState<PathSwitchEvent[]>([]);
  const [shadow, setShadow] = useState<ShadowReport | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState<Record<string, boolean>>({});

  const loadAll = useCallback(async () => {
    const mark = async (key: string, fn: () => Promise<void>) => {
      setLoading((prev) => ({ ...prev, [key]: true }));
      try {
        await fn();
        setErrors((prev) => ({ ...prev, [key]: '' }));
      } catch (exc) {
        setErrors((prev) => ({ ...prev, [key]: exc instanceof Error ? exc.message : String(exc) }));
      } finally {
        setLoading((prev) => ({ ...prev, [key]: false }));
      }
    };
    await Promise.all([
      mark('paths', async () => {
        setPaths(await pvDualPathApi.getModelingPaths(SLOT));
      }),
      mark('ledger', async () => {
        setLedger(await pvDualPathApi.getLedger({ slot: SLOT, page: 1, page_size: 20 }));
      }),
      mark('epochs', async () => {
        setEpochs(await pvDualPathApi.getEpochs({ slot: SLOT, page: 1, page_size: 10 }));
      }),
      mark('events', async () => {
        const [promo, sw] = await Promise.all([
          pvDualPathApi.getPromotionEvents({ slot: SLOT, page: 1, page_size: 20 }),
          pvDualPathApi.getPathSwitchEvents({ slot: SLOT, page: 1, page_size: 20 }),
        ]);
        setPromotions(promo.items || []);
        setSwitches(sw.items || []);
      }),
    ]);
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const showGovernance = variant === 'all' || variant === 'governance';
  const showOperations = variant === 'all' || variant === 'operations';

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: variant === 'all' ? 16 : 0 }}>
      {variant === 'all' ? (
        <>
          <Title level={3}>光伏故障双路径</Title>
          <Paragraph type="secondary">
            路径内换将只改 Champion；跨路径换班组必须九项准入并人工确认。Seq 游标只是连续完成前沿摘要。
          </Paragraph>
        </>
      ) : (
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          槽位固定为 pv_fault。路径内换将只改 Champion；跨路径换班组必须九项准入并人工确认。
        </Paragraph>
      )}
      {showGovernance ? (
        <>
          <PathSwitchCard paths={paths} loading={loading.paths} error={errors.paths} onChanged={loadAll} />
          <ModelGovernanceCard paths={paths} loading={loading.paths} error={errors.paths} onChanged={loadAll} />
          <ActivationEpochCard epochs={epochs} loading={loading.epochs} error={errors.epochs} />
          <AuditEventsCard promotions={promotions} switches={switches} loading={loading.events} error={errors.events} />
        </>
      ) : null}
      {showOperations ? (
        <>
          <SeqDeviceDayLedgerCard ledger={ledger} loading={loading.ledger} error={errors.ledger} />
          <PathDetectionStatusCard />
          <IngestionCompletenessCard />
          <ShadowCompareCard shadow={shadow} setShadow={setShadow} />
        </>
      ) : null}
    </Space>
  );
};

export const PvDualPathGovernancePanel: React.FC = () => <PvDualPathConsole variant="governance" />;
export const PvDualPathOperationsPanel: React.FC = () => <PvDualPathConsole variant="operations" />;

const CardState: React.FC<{ loading?: boolean; error?: string; empty?: boolean; children: React.ReactNode }> = ({
  loading,
  error,
  empty,
  children,
}) => {
  if (loading) return <Spin />;
  if (error) return <Alert type="error" showIcon message={error} />;
  if (empty) return <Empty description="暂无数据" />;
  return <>{children}</>;
};

const PathSwitchCard: React.FC<{
  paths: ModelingPathsState | null;
  loading?: boolean;
  error?: string;
  onChanged: () => Promise<void>;
}> = ({ paths, loading, error, onChanged }) => {
  const [form] = Form.useForm();
  const [gate, setGate] = useState<GateResult | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [strictMode, setStrictMode] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const current = String(paths?.production_path || 'legacy_day');
  const target = Form.useWatch('modeling_path', form) || current;
  const mode = Form.useWatch('activation_mode', form) || 'cutover_only';
  const cross = isCrossPath(current, target);
  const targetChampion = target === 'seq_annotation'
    ? paths?.path_models?.seq_annotation?.champion?.model_ref
    : paths?.path_models?.legacy_day?.champion?.model_ref;

  const submit = async () => {
    const values = await form.validateFields();
    if (cross && !isStrictTrue(confirm)) {
      message.error('切换日滚主线必须勾选确认');
      return;
    }
    if (cross && strictMode && requiresBackfillDays(mode) && !values.backfill_days) {
      message.error('recent_window 必须填写 backfill_days');
      return;
    }
    setSubmitting(true);
    const previous = paths;
    try {
      const body = {
        modeling_path: values.modeling_path,
        slot: SLOT,
        note: values.note,
        ...(cross
          ? (strictMode
            ? {
                comparison_id: values.comparison_id,
                activation_mode: values.activation_mode,
                confirm: true,
                operator: values.operator,
                reason: values.reason,
                backfill_days: values.backfill_days,
                device_scope: values.device_scope_text
                  ? JSON.parse(values.device_scope_text)
                  : [],
              }
            : {
                switch_mode: 'simple',
                confirm: true,
                activation_mode: 'cutover_only',
                operator: 'lab',
                reason: values.note || 'lab simple switch',
              })
          : {}),
      };
      const result = await pvDualPathApi.setModelingPaths(body);
      if ((result as { status?: string }).status === 'rejected') {
        setGate((result as { gate?: GateResult }).gate || null);
        message.error(strictMode ? '九项准入未全部通过，当前路径保持不变' : '简化切换被拒绝，当前路径保持不变');
        return;
      }
      message.success(cross ? '日滚主线已切换，下一轮预测走新路径' : '同路径登记已更新');
      window.setTimeout(() => {
        void onChanged();
      }, PV_DUAL_PATH_REFRESH_MS);
    } catch (exc) {
      message.error(exc instanceof Error ? exc.message : '切换失败，界面保持旧值');
      setPathsSafe(previous);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card title="路径切换">
      <CardState loading={loading} error={error}>
        <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
          <Descriptions.Item label="当前日滚主线">{current}</Descriptions.Item>
          <Descriptions.Item label="Fallback">{paths?.fallback_path || '—'}</Descriptions.Item>
          <Descriptions.Item label="Legacy Champion">
            {paths?.path_models?.legacy_day?.champion?.model_ref || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Seq Champion">
            {paths?.path_models?.seq_annotation?.champion?.model_ref || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="Active Epoch">
            {paths?.active_activation_epoch?.activation_epoch_id
              || paths?.active_activation_epoch_id
              || '—'}
          </Descriptions.Item>
        </Descriptions>
        <Form form={form} layout="vertical" initialValues={{ modeling_path: current, activation_mode: 'cutover_only' }}>
          <Form.Item name="modeling_path" label="目标路径" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'legacy_day', label: '天级 · legacy_day' },
                { value: 'seq_annotation', label: '点级 · seq_annotation' },
              ]}
            />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input maxLength={500} />
          </Form.Item>
          {cross && (
            <>
              <Alert
                type="info"
                showIcon
                message="默认是实验室简化切换：目标路径已有 Champion 并勾选确认即可改日滚主线。"
                description="不跑 Shadow、不填设备 JSON、不建生产 Epoch。点级还没训出 Champion 时不能切。生产换班组请展开下方严格准入。"
                style={{ marginBottom: 12 }}
              />
              {!targetChampion && (
                <Alert
                  type="warning"
                  showIcon
                  message={`目标路径还没有 Champion，请先在模型状态页重训「${target === 'seq_annotation' ? '点级' : '天级'}」。`}
                  style={{ marginBottom: 12 }}
                />
              )}
              <Checkbox checked={confirm} onChange={(event) => setConfirm(event.target.checked)}>
                确认把日滚主线切到所选路径
              </Checkbox>
              <Collapse
                style={{ marginTop: 12 }}
                onChange={(keys) => setStrictMode((Array.isArray(keys) ? keys : [keys]).includes('strict'))}
                items={[
                  {
                    key: 'strict',
                    label: '生产严格切换（九项准入 / Shadow / Epoch）',
                    children: (
                      <>
                        <Alert
                          type="warning"
                          showIcon
                          message="严格模式仍要求 Shadow 报告、设备边界和九项全真。"
                          style={{ marginBottom: 12 }}
                        />
                        <Form.Item name="activation_mode" label="启用模式">
                          <Select
                            options={[
                              { value: 'cutover_only', label: 'cutover_only' },
                              { value: 'recent_window', label: 'recent_window' },
                              { value: 'full_backfill', label: 'full_backfill（独立限流）' },
                            ]}
                          />
                        </Form.Item>
                        {requiresBackfillDays(mode) && (
                          <Form.Item name="backfill_days" label="backfill_days">
                            <InputNumber min={1} style={{ width: '100%' }} />
                          </Form.Item>
                        )}
                        <Form.Item name="comparison_id" label="Shadow comparison_id">
                          <Input />
                        </Form.Item>
                        <Form.Item name="operator" label="操作人">
                          <Input />
                        </Form.Item>
                        <Form.Item name="reason" label="原因">
                          <Input />
                        </Form.Item>
                        <Form.Item name="device_scope_text" label="device_scope JSON">
                          <Input.TextArea rows={3} placeholder='[{"site_id":"s","device_id":"d","branch_id":"b"}]' />
                        </Form.Item>
                      </>
                    ),
                  },
                ]}
              />
            </>
          )}
        </Form>
        {gate && (
          <Table
            size="small"
            rowKey="number"
            pagination={false}
            style={{ marginTop: 12 }}
            dataSource={gate.conditions}
            columns={[
              { title: '#', dataIndex: 'number', width: 48 },
              { title: '条件', dataIndex: 'name' },
              {
                title: '结果',
                dataIndex: 'passed',
                render: (passed: boolean) => (
                  <Tag color={passed ? 'green' : 'red'}>{passed ? '通过' : '失败'}</Tag>
                ),
              },
              { title: '原因', dataIndex: 'reason' },
            ]}
          />
        )}
        <Button type="primary" style={{ marginTop: 12 }} loading={submitting} onClick={() => void submit()}>
          {cross ? (strictMode ? '确认严格切换' : '切换日滚主线') : '更新同路径登记'}
        </Button>
      </CardState>
    </Card>
  );
};

function setPathsSafe(_previous: ModelingPathsState | null) {
  return _previous;
}

const ModelGovernanceCard: React.FC<{
  paths: ModelingPathsState | null;
  loading?: boolean;
  error?: string;
  onChanged: () => Promise<void>;
}> = ({ paths, loading, error, onChanged }) => {
  const [candidateId, setCandidateId] = useState('');
  const [path, setPath] = useState('legacy_day');
  return (
    <Card title="模型治理（路径内换将）">
      <CardState loading={loading} error={error} empty={!paths}>
        {(['legacy_day', 'seq_annotation'] as const).map((item) => {
          const life = paths?.path_models?.[item];
          return (
            <Card key={item} size="small" style={{ marginBottom: 8 }} title={item}>
              <Text>Champion：{life?.champion?.model_ref || '无'}</Text>
              <div>Challengers：{(life?.challengers || []).map((c) => c.candidate_id || c.evaluation_id).join(', ') || '无'}</div>
              <div>Retired：{(life?.retired || []).map((c) => c.model_ref).join(', ') || '无'}</div>
            </Card>
          );
        })}
        <Space>
          <Select
            value={path}
            onChange={setPath}
            options={[
              { value: 'legacy_day', label: 'legacy_day' },
              { value: 'seq_annotation', label: 'seq_annotation' },
            ]}
          />
          <Input
            placeholder="candidate_id"
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
            style={{ width: 240 }}
          />
          <Button
            onClick={async () => {
              await pvDualPathApi.promoteWithinPath(path, {
                candidate_id: candidateId,
                set_as_production: true,
                production_slot: SLOT,
              });
              message.success('路径内换将已提交，不会改变生产路径');
              await onChanged();
            }}
          >
            路径内换将
          </Button>
          <Text type="secondary">跨路径换班组请使用上方 PathSwitchCard</Text>
        </Space>
      </CardState>
    </Card>
  );
};

const SeqDeviceDayLedgerCard: React.FC<{ ledger: LedgerPage | null; loading?: boolean; error?: string }> = ({
  ledger,
  loading,
  error,
}) => (
  <Card title="Seq 设备日记账">
    <Alert
      type="info"
      showIcon
      style={{ marginBottom: 12 }}
      message="较早 waiting_data / failed 不阻塞较晚 ready。游标只是连续完成前沿摘要，不是处理权威。"
    />
    <CardState loading={loading} error={error} empty={!ledger || ledger.items.length === 0}>
      <Table
        size="small"
        rowKey={(row) => `${row.site_id}-${row.device_id}-${row.business_date}`}
        dataSource={ledger?.items || []}
        pagination={{ total: ledger?.total, pageSize: ledger?.page_size }}
        columns={[
          { title: '日期', dataIndex: 'business_date' },
          { title: '设备', dataIndex: 'device_id' },
          {
            title: '状态',
            dataIndex: 'status',
            render: (status: string) => <Tag>{ledgerStatusLabel(status)}</Tag>,
          },
          { title: '指纹', dataIndex: 'input_fingerprint', ellipsis: true },
          { title: 'batch', dataIndex: 'batch_id' },
          { title: 'supersedes', dataIndex: 'supersedes_batch_id' },
          { title: '尝试', dataIndex: 'attempt_count' },
          { title: '错误', dataIndex: 'last_error', ellipsis: true },
        ]}
      />
    </CardState>
  </Card>
);

const PathDetectionStatusCard: React.FC = () => (
  <Card title="检测状态">
    <Paragraph>
      CycleResult、分区游标与最近审核批次挂在本页。Seq cursor 标注为「连续完成前沿摘要，不是处理权威真相」。
    </Paragraph>
  </Card>
);

const IngestionCompletenessCard: React.FC = () => (
  <Card title="到达完整性">
    <Paragraph>
      按设备日展示 point_count / expected_point_count。点级按占用 ≥173/288 放行（光伏白天完整日通常过不了 90%/288），天级宽松放行已到达点。
    </Paragraph>
  </Card>
);

const ShadowCompareCard: React.FC<{
  shadow: ShadowReport | null;
  setShadow: (report: ShadowReport | null) => void;
}> = ({ shadow, setShadow }) => {
  const [comparisonId, setComparisonId] = useState('');
  return (
    <Card title="Shadow 三层证据">
      <Space style={{ marginBottom: 12 }}>
        <Input
          placeholder="comparison_id"
          value={comparisonId}
          onChange={(event) => setComparisonId(event.target.value)}
        />
        <Button
          onClick={async () => {
            const report = await pvDualPathApi.getShadowCompare(comparisonId);
            setShadow(report);
          }}
        >
          加载报告
        </Button>
      </Space>
      {!shadow ? (
        <Empty description="尚未加载 Shadow 报告" />
      ) : (
        <Descriptions size="small" column={2}>
          <Descriptions.Item label="有效期/生成">{shadow.generated_at || '—'}</Descriptions.Item>
          <Descriptions.Item label="Legacy Champion">{shadow.legacy_model_ref}</Descriptions.Item>
          <Descriptions.Item label="Seq Champion">{shadow.seq_model_ref}</Descriptions.Item>
          <Descriptions.Item label="一致率">{formatAgreementRate(shadow.agreement_rate)}</Descriptions.Item>
          <Descriptions.Item label="覆盖率">{formatAgreementRate(shadow.coverage_rate)}</Descriptions.Item>
          <Descriptions.Item label="可比设备日">{shadow.comparable_total}</Descriptions.Item>
          <Descriptions.Item label="共同天级">{JSON.stringify(shadow.common_metrics || {})}</Descriptions.Item>
          <Descriptions.Item label="Seq 原生">
            {JSON.stringify({
              ...(shadow.seq_native_metrics || {}),
              legacy_counterpart: shadow.seq_native_metrics?.legacy_counterpart ?? '无 Legacy 对应值',
            })}
          </Descriptions.Item>
          <Descriptions.Item label="运行指标">{JSON.stringify(shadow.runtime_metrics || {})}</Descriptions.Item>
          <Descriptions.Item label="不可比">
            {(shadow.uncomparable_items || [])
              .map((item) => `${item.severity || 'deferred'}:${item.reason || ''}`)
              .join('; ') || '无'}
          </Descriptions.Item>
        </Descriptions>
      )}
    </Card>
  );
};

const ActivationEpochCard: React.FC<{
  epochs: Record<string, unknown> | null;
  loading?: boolean;
  error?: string;
}> = ({ epochs, loading, error }) => {
  const [taskId, setTaskId] = useState('');
  const items = ((epochs?.items as Array<Record<string, unknown>>) || []);
  return (
    <Card title="启用周期与历史回放">
      <CardState loading={loading} error={error} empty={items.length === 0}>
        <Table
          size="small"
          rowKey="activation_epoch_id"
          dataSource={items}
          columns={[
            { title: 'Epoch', dataIndex: 'activation_epoch_id' },
            { title: '路径', dataIndex: 'modeling_path' },
            { title: '模式', dataIndex: 'activation_mode' },
            { title: '起始日', dataIndex: 'effective_from_date' },
          ]}
        />
      </CardState>
      <Space style={{ marginTop: 12 }}>
        <Input placeholder="backfill_task_id" value={taskId} onChange={(event) => setTaskId(event.target.value)} />
        <Button onClick={() => void pvDualPathApi.getBackfill(taskId).then(() => message.success('已查询'))}>
          查询 Backfill
        </Button>
        <Button onClick={() => void pvDualPathApi.retryBackfill(taskId)}>重试</Button>
        <Button
          danger
          onClick={() =>
            void pvDualPathApi.cancelReleaseBackfill(taskId, {
              confirm: true,
              operator: 'console',
              reason: 'explicit-release',
            })
          }
        >
          取消并释放
        </Button>
      </Space>
    </Card>
  );
};

const AuditEventsCard: React.FC<{
  promotions: PromotionEvent[];
  switches: PathSwitchEvent[];
  loading?: boolean;
  error?: string;
}> = ({ promotions, switches, loading, error }) => (
  <Card title="双栏审计：路径内晋升 / 跨路径切换">
    <CardState loading={loading} error={error}>
      <Row gutter={16}>
        <Col span={12}>
          <Title level={5}>PromotionEvent · 路径内换将</Title>
          <Table
            size="small"
            rowKey="promotion_event_id"
            dataSource={promotions}
            pagination={false}
            columns={[
              { title: '路径', dataIndex: 'modeling_path' },
              { title: '新 Champion', dataIndex: 'challenger_model_ref', ellipsis: true },
              { title: '时间', dataIndex: 'promoted_at' },
            ]}
          />
        </Col>
        <Col span={12}>
          <Title level={5}>PathSwitchEvent · 生产路径切换</Title>
          <Table
            size="small"
            rowKey="path_switch_event_id"
            dataSource={switches}
            pagination={false}
            columns={[
              { title: '从', dataIndex: 'from_path' },
              { title: '到', dataIndex: 'to_path' },
              { title: '时间', dataIndex: 'switched_at' },
            ]}
          />
        </Col>
      </Row>
    </CardState>
  </Card>
);

export default PvDualPathConsole;
// @AI_GENERATED: end
