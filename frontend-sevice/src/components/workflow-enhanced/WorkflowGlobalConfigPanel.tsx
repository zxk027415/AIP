// @AI_GENERATED
import React from 'react';
import { Modal, Form, Select, DatePicker, Space, Typography, InputNumber, Switch, Input, Button, message } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { WorkflowGlobalConfig } from '../../types/pipeline';
import dayjs from 'dayjs';
import { DEFAULT_MODEL_FAMILY, MODEL_FAMILY_REGISTRY, getDefaultModelParams } from '../../config/modelFamilyRegistry';
import TimeseriesProfilePanel from './TimeseriesProfilePanel';

interface WorkflowGlobalConfigPanelProps {
  visible: boolean;
  globalConfig: WorkflowGlobalConfig;
  onChange: (config: WorkflowGlobalConfig) => void;
  onApplyLocalParityPreset?: () => void;
  onClose: () => void;
  slot?: string;
  datasetProfileRef?: string;
  onDatasetProfileRefChange?: (profileRef: string | undefined) => void;
}

const WorkflowGlobalConfigPanel: React.FC<WorkflowGlobalConfigPanelProps> = ({
  visible, globalConfig, onChange, onApplyLocalParityPreset, onClose,
  slot, datasetProfileRef, onDatasetProfileRefChange,
}) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();

  const TIMEZONE_OPTIONS = [
    { label: t('globalConfig.timezone_options.shanghai'), value: 'Asia/Shanghai' },
    { label: t('globalConfig.timezone_options.tokyo'), value: 'Asia/Tokyo' },
    { label: t('globalConfig.timezone_options.utc'), value: 'UTC' },
    { label: t('globalConfig.timezone_options.newyork'), value: 'America/New_York' },
    { label: t('globalConfig.timezone_options.london'), value: 'Europe/London' },
  ];

  const RUN_MODE_OPTIONS = [
    { label: '训练', value: 'training' },
    { label: '预测', value: 'prediction' },
    { label: '回测', value: 'backtest' },
    { label: '调优', value: 'tuning' },
  ];

  const BACKTEST_MODE_OPTIONS = [
    { label: 'rolling_retrain（滚动重训）', value: 'rolling_retrain' },
    { label: 'inference_only（仅推理回放）', value: 'inference_only' },
  ];

  const TASK_TYPE_OPTIONS = [
    { label: t('globalConfig.taskType.DI'), value: 'DI' },
    { label: t('globalConfig.taskType.D'), value: 'D' },
    { label: t('globalConfig.taskType.WI'), value: 'WI' },
    { label: t('globalConfig.taskType.W'), value: 'W' },
    { label: t('globalConfig.taskType.MI'), value: 'MI' },
    { label: t('globalConfig.taskType.M'), value: 'M' },
  ];

  const MODEL_FAMILY_OPTIONS = Object.values(MODEL_FAMILY_REGISTRY).map((spec) => ({
    label: spec.label,
    value: spec.id,
  }));

  const buildSingleCandidateFromForm = (values: any) => {
    const modelFamily = String(values.tuning_model_family || DEFAULT_MODEL_FAMILY);
    const rawModelParams = values.tuning_model_params && typeof values.tuning_model_params === 'object'
      ? values.tuning_model_params
      : {};
    const modelParams = Object.keys(rawModelParams).length > 0 ? rawModelParams : getDefaultModelParams(modelFamily);
    return [{
      name: `${modelFamily}_base`,
      params: {
        train_days: values.backtest_train_days || 30,
        daily_horizon: values.backtest_daily_horizon || 96,
        backtest_mode: values.backtest_mode || 'rolling_retrain',
        model_ref: values.backtest_model_ref || '',
        use_reference_engine: values.use_reference_rolling_engine === true,
        strict_alignment_mode: values.strict_alignment_mode === true,
        apply_window_filter: values.backtest_apply_window_filter !== false,
        mask_target_values: values.backtest_mask_target_values !== false,
        model_family: modelFamily,
        model_params: modelParams,
      },
    }];
  };

  const handleOk = () => {
    form.validateFields().then((values) => {
      const runMode = values.run_mode || 'training';
      const operateStatus =
        runMode === 'prediction' ? 'prediction'
          : runMode === 'backtest' ? 'backtest'
            : runMode === 'tuning' ? 'tuning'
              : 'training';
      let tuningCandidates: Array<{ name?: string; params?: Record<string, any> }> | undefined;
      if (values.tuning_candidates_json && String(values.tuning_candidates_json).trim()) {
        try {
          const parsed = JSON.parse(values.tuning_candidates_json);
          if (Array.isArray(parsed)) {
            tuningCandidates = parsed;
          }
        } catch {
          // ignore invalid JSON, validation handled in form rule
        }
      }
      if (!tuningCandidates && runMode === 'tuning') {
        tuningCandidates = buildSingleCandidateFromForm(values);
      }
      onChange({
        time_zone: values.time_zone,
        run_mode: runMode,
        operate_status: operateStatus,
        nowtime: values.nowtime ? values.nowtime.format('YYYY-MM-DD HH:mm:ss') : '',
        // @AI_GENERATED
        task_type: values.task_type,
        backtest_start_date: values.backtest_range?.[0]?.format('YYYY-MM-DD') || '',
        backtest_end_date: values.backtest_range?.[1]?.format('YYYY-MM-DD') || '',
        backtest_train_days: values.backtest_train_days || 30,
        backtest_daily_horizon: values.backtest_daily_horizon || 96,
        backtest_generate_artifacts: values.backtest_generate_artifacts !== false,
        backtest_output_dir: values.backtest_output_dir || '',
        backtest_apply_window_filter: values.backtest_apply_window_filter !== false,
        backtest_mask_target_values: values.backtest_mask_target_values !== false,
        backtest_mode: values.backtest_mode || 'rolling_retrain',
        backtest_model_ref: values.backtest_model_ref || '',
        use_reference_rolling_engine: values.use_reference_rolling_engine === true,
        strict_alignment_mode: values.strict_alignment_mode === true,
        tuning_objective: values.tuning_objective || 'avg_smape',
        tuning_trials: values.tuning_trials || 20,
        tuning_candidates: tuningCandidates,
        tuning_model_family: values.tuning_model_family || DEFAULT_MODEL_FAMILY,
        tuning_model_params: values.tuning_model_params || getDefaultModelParams(values.tuning_model_family || DEFAULT_MODEL_FAMILY),
        // @AI_GENERATED: end
      });
      onClose();
    });
  };

  const handleApplyLocalParityPreset = () => {
    form.setFieldsValue({
      run_mode: 'backtest',
      backtest_train_days: 30,
      backtest_daily_horizon: 96,
      backtest_apply_window_filter: true,
      backtest_mask_target_values: true,
      backtest_generate_artifacts: true,
      backtest_mode: 'rolling_retrain',
      use_reference_rolling_engine: true,
      strict_alignment_mode: true,
    });
    if (onApplyLocalParityPreset) {
      onApplyLocalParityPreset();
    }
    message.success(t('globalConfig.localParityPresetApplied'));
  };

  return (
    <Modal
      title={<Space><SettingOutlined />{t('globalConfig.title')}</Space>}
      open={visible}
      onOk={handleOk}
      onCancel={onClose}
      okText={t('globalConfig.save')}
      cancelText={t('globalConfig.cancel')}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          time_zone: globalConfig.time_zone,
          run_mode: globalConfig.run_mode || globalConfig.operate_status || 'training',
          nowtime: globalConfig.nowtime ? dayjs(globalConfig.nowtime) : null,
          // @AI_GENERATED
          task_type: globalConfig.task_type || 'D',
          backtest_range:
            globalConfig.backtest_start_date && globalConfig.backtest_end_date
              ? [dayjs(globalConfig.backtest_start_date), dayjs(globalConfig.backtest_end_date)]
              : null,
          backtest_train_days: globalConfig.backtest_train_days || 30,
          backtest_daily_horizon: globalConfig.backtest_daily_horizon || 96,
          backtest_generate_artifacts: globalConfig.backtest_generate_artifacts !== false,
          backtest_output_dir: globalConfig.backtest_output_dir || '',
          backtest_apply_window_filter: globalConfig.backtest_apply_window_filter !== false,
          backtest_mask_target_values: globalConfig.backtest_mask_target_values !== false,
          backtest_mode: globalConfig.backtest_mode || 'rolling_retrain',
          backtest_model_ref: globalConfig.backtest_model_ref || '',
          use_reference_rolling_engine: globalConfig.use_reference_rolling_engine === true,
          strict_alignment_mode: globalConfig.strict_alignment_mode === true,
          tuning_objective: globalConfig.tuning_objective || 'avg_smape',
          tuning_trials: globalConfig.tuning_trials || 20,
          tuning_candidates_json: globalConfig.tuning_candidates ? JSON.stringify(globalConfig.tuning_candidates, null, 2) : '',
          tuning_model_family: globalConfig.tuning_model_family || DEFAULT_MODEL_FAMILY,
          tuning_model_params:
            globalConfig.tuning_model_params && Object.keys(globalConfig.tuning_model_params || {}).length > 0
              ? globalConfig.tuning_model_params
              : getDefaultModelParams(globalConfig.tuning_model_family || DEFAULT_MODEL_FAMILY),
          // @AI_GENERATED: end
        }}
      >
        {/* @AI_GENERATED */}
        <Form.Item name="task_type" label={t('globalConfig.forecastScenario')} rules={[{ required: true }]} extra={t('globalConfig.forecastScenarioHint')}>
          <Select options={TASK_TYPE_OPTIONS} />
        </Form.Item>
        {/* @AI_GENERATED: end */}
        <Form.Item name="time_zone" label={t('globalConfig.timezone')} rules={[{ required: true }]}>
          <Select options={TIMEZONE_OPTIONS} />
        </Form.Item>
        <Form.Item name="run_mode" label="运行模式" rules={[{ required: true }]}>
          <Select options={RUN_MODE_OPTIONS} />
        </Form.Item>
        <Form.Item noStyle shouldUpdate={(prev, curr) => prev.run_mode !== curr.run_mode}>
          {({ getFieldValue }) => {
            const runMode = getFieldValue('run_mode');
            const isBacktest = runMode === 'backtest';
            const isTuning = runMode === 'tuning';
            const isPredict = runMode === 'prediction';
            return (
              <>
                <Form.Item name="nowtime" label={t('globalConfig.timeBaseline')}>
                  <DatePicker
                    showTime
                    format="YYYY-MM-DD HH:mm:ss"
                    style={{ width: '100%' }}
                    disabled={isBacktest || isTuning}
                    placeholder={t('globalConfig.timeBaselinePlaceholder')}
                  />
                </Form.Item>
                {isPredict && (
                  <Form.Item name="backtest_model_ref" label="预测模型引用（model_ref）">
                    <Input placeholder="例如: xgb-abc123..." />
                  </Form.Item>
                )}
                {isBacktest && (
                  <>
                    <Form.Item label={t('globalConfig.localParityPreset')}>
                      <Button onClick={handleApplyLocalParityPreset}>
                        {t('globalConfig.localParityPresetButton')}
                      </Button>
                    </Form.Item>
                    <Form.Item name="backtest_range" label={t('globalConfig.backtestRange')}>
                      <DatePicker.RangePicker format="YYYY-MM-DD" style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="backtest_train_days" label={t('globalConfig.backtestTrainDays')}>
                      <InputNumber min={1} max={365} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="backtest_daily_horizon" label={t('globalConfig.backtestDailyHorizon')}>
                      <InputNumber min={1} max={2000} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="backtest_generate_artifacts" label={t('globalConfig.backtestGenerateArtifacts')} valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="backtest_output_dir" label={t('globalConfig.backtestOutputDir')}>
                      <Input placeholder={t('globalConfig.backtestOutputDirPlaceholder')} />
                    </Form.Item>
                    <Form.Item name="backtest_apply_window_filter" label={t('globalConfig.backtestApplyWindowFilter')} valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="backtest_mask_target_values" label={t('globalConfig.backtestMaskTargetValues')} valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="backtest_mode" label="回测模式">
                      <Select options={BACKTEST_MODE_OPTIONS} />
                    </Form.Item>
                    <Form.Item name="backtest_model_ref" label="inference_only 模型引用（model_ref）">
                      <Input placeholder="inference_only 模式下必填" />
                    </Form.Item>
                    <Form.Item name="use_reference_rolling_engine" label="使用威海参考回测引擎" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="strict_alignment_mode" label="严格对齐模式" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  </>
                )}
                {isTuning && (
                  <>
                    <Form.Item name="backtest_range" label={t('globalConfig.backtestRange')}>
                      <DatePicker.RangePicker format="YYYY-MM-DD" style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="backtest_train_days" label={t('globalConfig.backtestTrainDays')}>
                      <InputNumber min={1} max={365} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="backtest_daily_horizon" label={t('globalConfig.backtestDailyHorizon')}>
                      <InputNumber min={1} max={2000} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="backtest_apply_window_filter" label={t('globalConfig.backtestApplyWindowFilter')} valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="backtest_mask_target_values" label={t('globalConfig.backtestMaskTargetValues')} valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="backtest_mode" label="回测模式">
                      <Select options={BACKTEST_MODE_OPTIONS} />
                    </Form.Item>
                    <Form.Item name="backtest_model_ref" label="inference_only 模型引用（model_ref）">
                      <Input placeholder="inference_only 模式下必填" />
                    </Form.Item>
                    <Form.Item name="use_reference_rolling_engine" label="使用威海参考回测引擎" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="strict_alignment_mode" label="严格对齐模式" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="tuning_objective" label="调优目标">
                      <Select options={[
                        { label: 'avg_smape（推荐）', value: 'avg_smape' },
                        { label: 'avg_rmse', value: 'avg_rmse' },
                        { label: 'avg_mae', value: 'avg_mae' },
                      ]} />
                    </Form.Item>
                    <Form.Item name="tuning_model_family" label="模型家族（配置驱动）">
                      <Select
                        options={MODEL_FAMILY_OPTIONS}
                        onChange={(value: string) => {
                          const currentParams = form.getFieldValue('tuning_model_params');
                          if (!currentParams || Object.keys(currentParams || {}).length === 0) {
                            form.setFieldValue('tuning_model_params', getDefaultModelParams(value));
                          }
                        }}
                      />
                    </Form.Item>
                    <Form.Item noStyle shouldUpdate={(prev, curr) => prev.tuning_model_family !== curr.tuning_model_family}>
                      {({ getFieldValue }) => {
                        const family = getFieldValue('tuning_model_family') || DEFAULT_MODEL_FAMILY;
                        const spec = MODEL_FAMILY_REGISTRY[String(family)] || MODEL_FAMILY_REGISTRY[DEFAULT_MODEL_FAMILY];
                        return (
                          <>
                            {spec.params.map((item) => (
                              <Form.Item
                                key={`${family}-${item.key}`}
                                name={['tuning_model_params', item.key]}
                                label={item.label}
                                valuePropName={item.type === 'boolean' ? 'checked' : 'value'}
                              >
                                {item.type === 'number' ? (
                                  <InputNumber min={item.min} max={item.max} step={item.step} style={{ width: '100%' }} />
                                ) : item.type === 'boolean' ? (
                                  <Switch />
                                ) : (
                                  <Input />
                                )}
                              </Form.Item>
                            ))}
                          </>
                        );
                      }}
                    </Form.Item>
                    <Form.Item name="tuning_trials" label="候选数量（回退模式）">
                      <InputNumber min={1} max={200} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item
                      name="tuning_candidates_json"
                      label="候选参数(JSON数组)"
                      extra='示例: [{"name":"c1","params":{"train_days":30}},{"name":"c2","params":{"train_days":45}}]'
                      rules={[
                        {
                          validator: async (_, value) => {
                            if (!value || !String(value).trim()) return;
                            const parsed = JSON.parse(value);
                            if (!Array.isArray(parsed)) throw new Error('必须是数组');
                          },
                        },
                      ]}
                    >
                      <Input.TextArea rows={6} placeholder='[{"name":"candidate_1","params":{"train_days":30}}]' />
                    </Form.Item>
                    <Form.Item label="快速生成候选">
                      <Button
                        onClick={() => {
                          const values = form.getFieldsValue(true);
                          const generated = buildSingleCandidateFromForm(values);
                          form.setFieldValue('tuning_candidates_json', JSON.stringify(generated, null, 2));
                          message.success('已按当前强化配置生成候选JSON');
                        }}
                      >
                        用当前参数生成候选
                      </Button>
                    </Form.Item>
                  </>
                )}
              </>
            );
          }}
        </Form.Item>
      </Form>
      {slot && (
        <div style={{ marginTop: 16 }}>
          <TimeseriesProfilePanel
            slot={slot}
            value={datasetProfileRef}
            onChange={onDatasetProfileRefChange}
          />
        </div>
      )}
      <Typography.Text type="secondary">
        {t('globalConfig.note')}
      </Typography.Text>
    </Modal>
  );
};

export default WorkflowGlobalConfigPanel;
// @AI_GENERATED: end
