// @AI_GENERATED
import React from 'react';
import { Dropdown, Button, Space, Typography } from 'antd';
import { AppstoreOutlined, ExperimentOutlined, LineChartOutlined, HistoryOutlined, SlidersOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { PipelineTemplate } from '../../types/pipeline';
import { ALL_PIPELINE_TEMPLATES } from '../../data/pipelineTemplates';

const { Text } = Typography;

interface PipelineTemplateMenuProps {
  onSelect: (template: PipelineTemplate) => void;
}

const TEMPLATE_ICONS: Record<string, React.ReactNode> = {
  training: <ExperimentOutlined />,
  prediction: <LineChartOutlined />,
  backtest: <HistoryOutlined />,
  tuning: <SlidersOutlined />,
};

const PipelineTemplateMenu: React.FC<PipelineTemplateMenuProps> = ({ onSelect }) => {
  const { t } = useTranslation();
  const items = ALL_PIPELINE_TEMPLATES.map((t_tpl) => ({
    key: t_tpl.id,
    icon: TEMPLATE_ICONS[t_tpl.type],
    label: (
      <div>
        <div>{t_tpl.name}</div>
        <Text type="secondary" style={{ fontSize: 12 }}>{t_tpl.description}</Text>
      </div>
    ),
    onClick: () => onSelect(t_tpl),
  }));

  return (
    <Dropdown menu={{ items }} trigger={['click']} placement="bottomLeft">
      <Button icon={<AppstoreOutlined />}>{t('workflow.pipelineTemplate')}</Button>
    </Dropdown>
  );
};

export default PipelineTemplateMenu;
// @AI_GENERATED: end
