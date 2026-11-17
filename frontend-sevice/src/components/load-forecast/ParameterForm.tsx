// @AI_GENERATED
/**
 * 训练参数配置表单组件
 *
 * 使用 Ant Design Form 收集训练参数，支持必填校验、正整数校验、
 * 场景推荐配置自动填充和历史记录回填。
 * parent_id / child_id / csv_path 使用默认值，收在"高级选项"折叠面板中。
 */
import React, { useEffect, useMemo } from 'react';
import {
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  TimePicker,
  Button,
  Space,
  Collapse,
} from 'antd';
import { PlayCircleOutlined, SettingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { TrainingParams } from '../../types/load-forecast';
import { TASK_TYPE_CODES } from '../../types/load-forecast';

export interface ParameterFormProps {
  initialValues?: Partial<TrainingParams>;
  onSubmit: (params: TrainingParams) => void;
  loading: boolean;
  disabled: boolean;
}

const ParameterForm: React.FC<ParameterFormProps> = ({
  initialValues,
  onSubmit,
  loading,
  disabled,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  const timeGranularityOptions = useMemo(
    () =>
      (['15min', '30min', '60min'] as const).map((value) => ({
        value,
        label: t(`loadForecast.timeGranularity.${value}`),
      })),
    [t],
  );

  const taskTypeOptions = useMemo(
    () =>
      TASK_TYPE_CODES.map((value) => ({
        value,
        label: `${t(`loadForecast.taskTypes.${value}`)} (${value})`,
      })),
    [t],
  );

  // 当 initialValues 变化时更新表单
  useEffect(() => {
    if (initialValues) {
      const values: Record<string, any> = { ...initialValues };
      if (typeof values.separate_modeling === 'string') {
        values.separate_modeling = values.separate_modeling === 'true';
      }
      if (typeof values.forecast_start_time === 'string') {
        values.forecast_start_time = dayjs(values.forecast_start_time, 'HH:mm');
      }
      form.setFieldsValue(values);
    }
  }, [initialValues, form]);

  const handleFinish = (values: any) => {
    const params: TrainingParams = {
      task_type: values.task_type,
      csv_path: values.csv_path || '',
      parent_id: values.parent_id || '',
      child_id: values.child_id || '',
      forecast_horizon: values.forecast_horizon ?? 1,
      time_granularity: values.time_granularity ?? '15min',
      separate_modeling: values.separate_modeling ? 'true' : 'false',
      forecast_start_time: values.forecast_start_time
        ? dayjs(values.forecast_start_time).format('HH:mm')
        : '00:15',
    };
    onSubmit(params);
  };

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={handleFinish}
      disabled={disabled}
      initialValues={{
        forecast_horizon: 1,
        time_granularity: '15min',
        separate_modeling: false,
        forecast_start_time: dayjs('00:15', 'HH:mm'),
      }}
    >
      {/* 必填：预测场景 */}
      <Form.Item
        name="task_type"
        label={t('loadForecast.parameterForm.taskType')}
        rules={[{ required: true, message: t('loadForecast.parameterForm.taskTypeRequired') }]}
      >
        <Select
          placeholder={t('loadForecast.parameterForm.taskTypePlaceholder')}
          options={taskTypeOptions}
          allowClear
        />
      </Form.Item>

      {/* 基本参数 */}
      <Form.Item
        name="forecast_horizon"
        label={t('loadForecast.parameterForm.forecastHorizon')}
        tooltip={t('loadForecast.parameterForm.forecastHorizonTooltip')}
        rules={[
          {
            type: 'integer',
            min: 1,
            message: t('loadForecast.parameterForm.forecastHorizonInteger'),
          },
        ]}
      >
        <InputNumber
          min={1}
          precision={0}
          style={{ width: '100%' }}
          placeholder={t('loadForecast.parameterForm.forecastHorizonPlaceholder')}
        />
      </Form.Item>

      <Form.Item
        name="time_granularity"
        label={t('loadForecast.parameterForm.timeGranularity')}
        tooltip={t('loadForecast.parameterForm.timeGranularityTooltip')}
      >
        <Select options={timeGranularityOptions} />
      </Form.Item>

      <Form.Item
        name="separate_modeling"
        label={t('loadForecast.parameterForm.separateModeling')}
        tooltip={t('loadForecast.parameterForm.separateModelingTooltip')}
        valuePropName="checked"
      >
        <Switch
          checkedChildren={t('loadForecast.parameterForm.switchOn')}
          unCheckedChildren={t('loadForecast.parameterForm.switchOff')}
        />
      </Form.Item>

      <Form.Item
        name="forecast_start_time"
        label={t('loadForecast.parameterForm.forecastStartTime')}
        tooltip={t('loadForecast.parameterForm.forecastStartTimeTooltip')}
      >
        <TimePicker format="HH:mm" style={{ width: '100%' }} />
      </Form.Item>

      {/* 高级选项（折叠） */}
      <Collapse
        ghost
        size="small"
        style={{ marginBottom: 16 }}
        items={[
          {
            key: 'advanced',
            label: (
              <span style={{ fontSize: 13, color: '#8c8c8c' }}>
                <SettingOutlined style={{ marginRight: 4 }} />
                {t('loadForecast.parameterForm.advancedCollapse')}
              </span>
            ),
            children: (
              <>
                <Form.Item
                  name="csv_path"
                  label={t('loadForecast.parameterForm.csvPath')}
                  tooltip={t('loadForecast.parameterForm.csvPathTooltip')}
                >
                  <Input placeholder={t('loadForecast.parameterForm.csvPathPlaceholder')} />
                </Form.Item>

                <Form.Item
                  name="parent_id"
                  label={t('loadForecast.parameterForm.parentId')}
                  tooltip={t('loadForecast.parameterForm.parentIdTooltip')}
                >
                  <Input placeholder={t('loadForecast.parameterForm.parentIdPlaceholder')} />
                </Form.Item>

                <Form.Item
                  name="child_id"
                  label={t('loadForecast.parameterForm.childId')}
                  tooltip={t('loadForecast.parameterForm.childIdTooltip')}
                >
                  <Input placeholder={t('loadForecast.parameterForm.childIdPlaceholder')} />
                </Form.Item>
              </>
            ),
          },
        ]}
      />

      {/* 提交按钮 */}
      <Form.Item>
        <Space>
          <Button
            type="primary"
            htmlType="submit"
            icon={<PlayCircleOutlined />}
            loading={loading}
            disabled={disabled}
          >
            {t('loadForecast.parameterForm.startTrain')}
          </Button>
          <Button onClick={() => form.resetFields()} disabled={disabled}>
            {t('loadForecast.parameterForm.reset')}
          </Button>
        </Space>
      </Form.Item>
    </Form>
  );
};

export default ParameterForm;
// @AI_GENERATED: end
