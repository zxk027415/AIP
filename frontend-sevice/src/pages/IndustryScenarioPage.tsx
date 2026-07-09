// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert, Card, Typography, Spin, Tag, Space, Breadcrumb, Tabs, Row, Col,
  Button, Grid,
} from 'antd';
import {
  AppstoreOutlined,
  ApartmentOutlined,
  ExperimentOutlined,
  NodeIndexOutlined,
  RocketOutlined,
  BranchesOutlined,
} from '@ant-design/icons';
import { industryApi } from '../services/industryApi';
import { useTranslation } from 'react-i18next';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import type { IndustryScenario } from '../types/industry';
import type { IndustryTemplate } from '../services/industryApi';

const { Title, Paragraph, Text } = Typography;
const { useBreakpoint } = Grid;

// @AI_GENERATED: Kiro v1.0
/** 基础模块层级数据（Tab 2）- 13个行业场景 */
const LAYER_DATA: Record<string, { layer: string; color: string; modules: string[] }[]> = {
  'renewable-energy': [
    { layer: '数据管理层', color: '#1890ff', modules: ['MQTT实时数据订阅', 'OPC UA数据读取', 'COMTRADE故障录波', 'IEC 61850数据读取'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['时序重采样', '缺失值处理', '异常值检测', '小波去噪', 'Z-Score标准化'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['LSTM时序预测', 'Transformer预测', 'XGBoost回归', '孤立森林异常检测'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['自动调参', '时序交叉验证', 'RMSE评估', 'R²决定系数', '预测结果可视化'] },
  ],
  'thermal-power': [
    { layer: '数据管理层', color: '#1890ff', modules: ['DCS数据接入', 'OPC UA数据读取', '历史数据库接入', 'SIS系统对接'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['时序重采样', '缺失值处理', '异常值检测', '特征工程', '数据对齐'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['LSTM时序预测', 'XGBoost回归', '遗传算法优化', '振动信号分析', '图像缺陷检测'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['RMSE评估', 'MAPE评估', '优化报告生成', '预警仪表盘'] },
  ],
  'energy-storage': [
    { layer: '数据管理层', color: '#1890ff', modules: ['CAN总线数据读取', 'Modbus设备数据', 'BMS数据接入'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['卡尔曼滤波', 'Z-Score标准化', '缺失值处理', '数据聚合'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['扩展卡尔曼滤波(SOC)', 'LSTM寿命预测', '孤立森林异常检测'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['F1指标', '准确率指标', '异常检测可视化', '仪表盘渲染'] },
  ],
  'power-grid': [
    { layer: '数据管理层', color: '#1890ff', modules: ['SCADA数据接入', 'PMU数据读取', 'IEC 61850数据读取'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['时序重采样', '缺失值处理', '傅里叶变换', '小波分析'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['LSTM负荷预测', '潮流计算', '状态估计', '孤立森林异常检测'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['MAPE评估', 'RMSE评估', '电网可视化', '调度报告'] },
  ],
  'steel-manufacturing': [
    { layer: '数据管理层', color: '#1890ff', modules: ['OPC UA数据读取', 'Modbus设备数据', 'MES系统对接'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['带通滤波', '快速傅里叶变换', 'PCA降维', '特征选择'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['SPC统计过程控制', '遗传算法优化', 'YOLO缺陷检测', '振动诊断'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['mAP指标', '频谱图可视化', '热力图渲染', '质量报告'] },
  ],
  'pv-manufacturing': [
    { layer: '数据管理层', color: '#1890ff', modules: ['MES系统对接', '图像采集系统', 'EL检测设备接入'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['图像预处理', '特征提取', '数据增强', '归一化'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['CNN缺陷检测', 'YOLO目标检测', 'XGBoost良率预测'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['mAP指标', 'F1指标', '缺陷可视化', '良率报告'] },
  ],
  'battery-manufacturing': [
    { layer: '数据管理层', color: '#1890ff', modules: ['MES系统对接', '化成设备数据', '分选设备数据'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['时序对齐', '缺失值处理', '特征工程', '归一化'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['一致性分析', 'LSTM寿命预测', '孤立森林异常检测'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['RMSE评估', 'F1指标', '一致性可视化', '质量报告'] },
  ],
  'semiconductor': [
    { layer: '数据管理层', color: '#1890ff', modules: ['设备数据采集', 'FDC系统对接', '量测数据接入'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['特征工程', 'PCA降维', '数据对齐', '归一化'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['虚拟量测', 'CNN缺陷检测', 'XGBoost良率预测', 'R2R控制'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['RMSE评估', 'mAP指标', '良率可视化', 'SPC报告'] },
  ],
  'chemical-process': [
    { layer: '数据管理层', color: '#1890ff', modules: ['DCS数据接入', 'LIMS系统对接', '在线分析仪数据'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['时序重采样', '缺失值处理', '异常值检测', '特征工程'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['MPC模型预测控制', '遗传算法优化', '孤立森林异常检测'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['RMSE评估', '优化报告', '安全预警仪表盘'] },
  ],
  'port-logistics': [
    { layer: '数据管理层', color: '#1890ff', modules: ['TOS系统对接', 'AGV调度系统', 'AIS船舶数据'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['时序处理', '空间数据处理', '特征工程'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['路径规划算法', '调度优化', 'LSTM吞吐预测'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['MAPE评估', '调度可视化', '运营报告'] },
  ],
  'building-campus': [
    { layer: '数据管理层', color: '#1890ff', modules: ['BACnet数据接入', 'Modbus设备数据', '能源计量数据'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['时序重采样', '缺失值处理', '特征工程'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['LSTM负荷预测', 'MPC暖通控制', '遗传算法优化'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['MAPE评估', '能耗可视化', '审计报告'] },
  ],
  'carbon-management': [
    { layer: '数据管理层', color: '#1890ff', modules: ['能源数据接入', '生产数据接入', '排放因子库'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['数据清洗', '单位换算', '边界划分'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['碳核算模型', 'LSTM排放预测', '优化算法'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['碳排放可视化', '碳足迹追踪', '合规报告'] },
  ],
  'water-environment': [
    { layer: '数据管理层', color: '#1890ff', modules: ['SCADA数据接入', '在线水质仪表', 'GIS管网数据'] },
    { layer: '数据处理层', color: '#52c41a', modules: ['时序重采样', '缺失值处理', '异常值检测'] },
    { layer: '算法模型层', color: '#722ed1', modules: ['LSTM水质预测', '管网水力模型', '加药优化算法'] },
    { layer: 'MLOps层', color: '#eb2f96', modules: ['RMSE评估', '水质可视化', '运营报告'] },
  ],
};
// @AI_GENERATED: end

const DEFAULT_LAYERS = [
  { layer: '数据管理层', color: '#1890ff', modules: ['CSV/Excel加载', '数据库连接', 'REST API接入', 'MQTT订阅', '图像/视频加载'] },
  { layer: '数据处理层', color: '#52c41a', modules: ['缺失值处理', '异常值检测', 'Z-Score标准化', 'Min-Max归一化', '特征选择', 'PCA降维'] },
  { layer: '算法模型层', color: '#722ed1', modules: ['时序预测', '异常检测', '分类识别', '目标检测', '聚类分析', '优化求解'] },
  { layer: 'MLOps层', color: '#eb2f96', modules: ['模型训练', '自动调参', '评估指标', '可视化报告', '模型部署'] },
];

/** 按 display_category 分组模板 */
function groupByCategory(templates: IndustryTemplate[]): { category: string; templates: IndustryTemplate[] }[] {
  const map = new Map<string, IndustryTemplate[]>();
  for (const t of templates) {
    const cat = t.display_category || '其他';
    if (!map.has(cat)) map.set(cat, []);
    map.get(cat)!.push(t);
  }
  // @AI_GENERATED
  // 排序：能源预测排在最前面
  const CATEGORY_ORDER: Record<string, number> = { '能源预测': 0 };
  const groups = Array.from(map.entries()).map(([category, tpls]) => ({ category, templates: tpls }));
  groups.sort((a, b) => (CATEGORY_ORDER[a.category] ?? 99) - (CATEGORY_ORDER[b.category] ?? 99));
  return groups;
  // @AI_GENERATED: end
}

const IndustryScenarioPage: React.FC = () => {
  const { scenarioId } = useParams<{ scenarioId: string }>();
  const navigate = useNavigate();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  const { t } = useTranslation();

  const [scenario, setScenario] = useState<IndustryScenario | null>(null);
  const [templates, setTemplates] = useState<IndustryTemplate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!scenarioId) return;
    setLoading(true);
    Promise.all([
      industryApi.getScenario(scenarioId),
      industryApi.getTemplates(scenarioId),
    ])
      .then(([sc, tpls]) => {
        setScenario(sc);
        setTemplates(tpls);
      })
      .catch(() => navigate('/industry'))
      .finally(() => setLoading(false));
  }, [scenarioId, navigate]);

  const grouped = useMemo(() => groupByCategory(templates), [templates]);

  if (loading || !scenario) {
    return <div style={{ textAlign: 'center', padding: '80px 0' }}><Spin size="large" /></div>;
  }

  const layers = LAYER_DATA[scenario.id] || DEFAULT_LAYERS;

  return (
    <div
      style={{
        padding: isMobile ? 12 : 24,
        minHeight: '100%',
        background: '#f3f5f8',
      }}
    >
      <Breadcrumb
        items={[
          { title: <a onClick={() => navigate('/industry')}>{t('industry.industryScenarios')}</a> },
          { title: td(scenario.name) },
        ]}
        style={{ marginBottom: 16 }}
      />

      <Card
        style={{
          marginBottom: 24,
          borderRadius: 12,
          boxShadow: '0 12px 32px rgba(15, 23, 42, 0.06)',
        }}
        bordered={false}
      >
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="blue">行业服务 / 场景详情</Tag>
            <Tag color="purple">第七代入口收敛版</Tag>
          </Space>
          <Space>
            <span style={{ fontSize: 32 }}>{scenario.icon}</span>
            <Title level={3} style={{ margin: 0 }}>{td(scenario.name)}</Title>
          </Space>
          <Paragraph type="secondary">{td(scenario.description)}</Paragraph>
          <Space wrap>
            {scenario.capabilities?.map((cap: string) => (
              <Tag key={cap} color="blue">{td(cap)}</Tag>
            ))}
          </Space>
          <Alert
            type="info"
            showIcon
            message="第一阶段说明"
            description="当前页面已向第七代结构收敛：场景模板仍从现有行业接口读取，但主要动作入口会优先导向新的算法开发路由。"
          />
        </Space>
      </Card>

      <Tabs
        defaultActiveKey="templates"
        items={[
          // @AI_GENERATED: Kiro v1.0
          {
            key: 'templates',
            label: <span><AppstoreOutlined /> {t('industry.scenarioAlgorithms')}</span>,
            children: (
              <div>
                {grouped.length === 0 ? (
                  <Card><Text type="secondary">{t('industry.noTemplateData')}</Text></Card>
                ) : (
                  <>
                    {grouped.map(({ category, templates: tpls }) => (
                      <Card
                        key={category}
                        title={<span><ExperimentOutlined /> {td(category)}</span>}
                        size="small"
                        style={{ marginBottom: 16, borderRadius: 12 }}
                      >
                        <Row gutter={[12, 12]}>
                          {tpls.map((tpl) => (
                            <Col key={tpl.id} xs={24} sm={12} md={8} lg={6}>
                              <Card
                                size="small"
                                hoverable
                                bordered={false}
                                style={{
                                  cursor: 'pointer',
                                  borderRadius: 10,
                                  background: '#fafcff',
                                  boxShadow: '0 8px 20px rgba(15, 23, 42, 0.05)',
                                }}
                                title={
                                  <span
                                    style={{ cursor: 'pointer' }}
                                    onClick={() => navigate(`/algorithm-solutions?template=${encodeURIComponent(tpl.id)}`)}
                                  >
                                    {td(tpl.name)}
                                  </span>
                                }
                                extra={
                                  tpl.default_workflows?.length ? (
                                    <Tag color="green">
                                      <BranchesOutlined /> {tpl.default_workflows.length} 工作流模板
                                    </Tag>
                                  ) : null
                                }
                                onClick={() => navigate(`/algorithm-solutions?template=${encodeURIComponent(tpl.id)}`)}
                              >
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  {td(tpl.description) || t('industry.noDescription')}
                                </Text>
                                {tpl.default_workflows && tpl.default_workflows.length > 0 && (
                                  <div style={{ marginTop: 8 }}>
                                    {tpl.default_workflows.map((wf: { profile: string; name: string }) => (
                                      <Tag
                                        key={wf.profile}
                                        color={
                                          wf.profile === 'high-accuracy' ? 'green'
                                            : wf.profile === 'balanced' ? 'blue'
                                            : 'orange'
                                        }
                                        style={{ marginBottom: 4 }}
                                      >
                                        {td(wf.name)}
                                      </Tag>
                                    ))}
                                  </div>
                                )}
                                <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                  <Button
                                    size="small"
                                    type="primary"
                                    icon={<RocketOutlined />}
                                    onClick={() =>
                                      navigate(
                                        `/algorithm-dev/workflow-editor?template=${encodeURIComponent(tpl.id)}&scenario=${encodeURIComponent(
                                          scenario.id,
                                        )}`,
                                      )
                                    }
                                  >
                                    进入工作流编排
                                  </Button>
                                  <Button
                                    size="small"
                                    icon={<ApartmentOutlined />}
                                    onClick={() =>
                                      navigate(
                                        `/algorithm-dev/management?scenario=${encodeURIComponent(scenario.id)}&template=${encodeURIComponent(
                                          tpl.id,
                                        )}`,
                                      )
                                    }
                                  >
                                    查看算法管理
                                  </Button>
                                  {/* @AI_GENERATED */}
                                  {(tpl.id === 'load_forecast' || tpl.name.includes('负荷预测')) && (
                                    <Button
                                      size="small"
                                      type="primary"
                                      ghost
                                      icon={<ExperimentOutlined />}
                                      onClick={() =>
                                        navigate(
                                          `/algorithm-dev/autoresearch?challenger=${encodeURIComponent(
                                            'workflow-load-forecast-training-v2',
                                          )}`,
                                        )
                                      }
                                    >
                                      自动化回测
                                    </Button>
                                  )}
                                  {/* @AI_GENERATED: end */}
                                </div>
                              </Card>
                            </Col>
                          ))}
                        </Row>
                      </Card>
                    ))}
                    <div style={{ textAlign: 'center', marginTop: 16 }}>
                      <Button
                        type="link"
                        onClick={() => navigate(`/templates?scenario=${encodeURIComponent(scenarioId || '')}`)}
                      >
                        {t('industry.viewMoreTemplates')}
                      </Button>
                    </div>
                  </>
                )}
              </div>
            ),
          },
          // @AI_GENERATED: end
          // @AI_GENERATED: Kiro v1.0
          {
            key: 'basic-modules',
            label: <span><NodeIndexOutlined /> {t('industry.relatedModules')}</span>,
            children: (
              <Row gutter={[16, 16]}>
                {layers.map((l) => (
                  <Col key={l.layer} xs={24} sm={12} md={6}>
                    <Card
                      title={<Tag color={l.color}>{td(l.layer)}</Tag>}
                      size="small"
                      bordered={false}
                      style={{ borderRadius: 12 }}
                      extra={
                        <Button
                          type="link"
                          size="small"
                          onClick={() => navigate(`/algorithm-dev/operators?layer=${encodeURIComponent(l.layer)}`)}
                        >
                          {t('industry.viewMore')}
                        </Button>
                      }
                    >
                      {l.modules.map((m) => (
                        <Tag
                          key={m}
                          style={{ marginBottom: 4, cursor: 'pointer' }}
                          onClick={() => navigate(`/algorithm-dev/operators?q=${encodeURIComponent(m)}`)}
                        >
                          {td(m)}
                        </Tag>
                      ))}
                    </Card>
                  </Col>
                ))}
              </Row>
            ),
          },
          // @AI_GENERATED: end
        ]}
      />
    </div>
  );
};

export default IndustryScenarioPage;
// @AI_GENERATED: end
