// @AI_GENERATED: Kiro v1.0
/**
 * Skill 详情页面
 * 展示单个 Skill 的完整信息，包括文件结构、代码内容、训练历史等
 */
import { useState, useEffect } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Space, Typography, Tag, Row, Col, Descriptions, Tabs, List, Alert,
  Button, Spin, Empty, message, Breadcrumb,
} from 'antd';
import {
  ThunderboltOutlined, ArrowLeftOutlined, CheckCircleOutlined, SyncOutlined,
  ClockCircleOutlined, CodeOutlined, ApiOutlined, PlayCircleOutlined,
  HistoryOutlined, RocketOutlined, CloudServerOutlined, HomeOutlined,
  FileTextOutlined, FolderOpenOutlined, EyeOutlined,
} from '@ant-design/icons';
import { templateSkillApi, type PackagedSkill } from '../services/templateSkillApi';

const { Title, Text, Paragraph } = Typography;

// Skill 状态配置
type SkillStatus = 'packaged' | 'training' | 'ready' | 'deployed' | 'deprecated';

// @AI_GENERATED
const STATUS_CONFIG: Record<SkillStatus, { labelKey: string; color: string; icon: React.ReactNode }> = {
  packaged: { labelKey: 'skillDetail.packaged', color: 'default', icon: <CodeOutlined /> },
  training: { labelKey: 'skillDetail.training', color: 'processing', icon: <SyncOutlined spin /> },
  ready: { labelKey: 'skillDetail.ready', color: 'success', icon: <CheckCircleOutlined /> },
  deployed: { labelKey: 'skillDetail.deployed', color: 'blue', icon: <CloudServerOutlined /> },
  deprecated: { labelKey: 'skillDetail.deprecated', color: 'error', icon: <ClockCircleOutlined /> },
};
// @AI_GENERATED: end

// 模拟文件内容
const MOCK_FILES: Record<string, { content: string; language: string }> = {
  'program.md': {
    language: 'markdown',
    content: `# 光伏发电功率预测 Skill

这是一个自主研究实验，让 LLM Agent 优化光伏发电功率预测模型。

## 目标

**核心指标：MAPE（平均绝对百分比误差）**

目标是在固定时间预算内，通过修改模型架构、超参数、特征工程等方式，获得最低的 MAPE。

## 实验规则

**你可以做的：**
- 修改 \`train.py\` — 这是唯一可编辑的文件
- 修改模型架构（LSTM、GRU、Transformer、集成模型等）
- 修改超参数（学习率、批次大小、隐藏层维度等）

**你不能做的：**
- 修改 \`prepare.py\` — 它是只读的
- 安装新的依赖包
- 使用未来数据（数据泄露）
`,
  },
  'train.py': {
    language: 'python',
    content: `# @AI_GENERATED: Kiro v1.0
"""
光伏发电功率预测 - 训练脚本（Agent 可编辑）
"""
import numpy as np
from prepare import load_pv_data, evaluate_mape, MinMaxScaler

# 超参数（可修改）
MODEL_TYPE = "linear"    # 可选: "linear", "lstm", "mlp"
HIDDEN_SIZE = 64
NUM_LAYERS = 2
LEARNING_RATE = 0.001
BATCH_SIZE = 32
NUM_EPOCHS = 100

class LinearModel:
    """简单线性回归模型（基线）"""
    def __init__(self, input_dim, output_dim):
        self.weights = None
        self.bias = None
    
    def fit(self, X, y):
        X_flat = X.reshape(X.shape[0], -1)
        X_bias = np.hstack([X_flat, np.ones((X_flat.shape[0], 1))])
        solution = np.linalg.lstsq(X_bias, y, rcond=None)[0]
        self.weights = solution[:-1]
        self.bias = solution[-1]
        return self
    
    def predict(self, X):
        X_flat = X.reshape(X.shape[0], -1)
        return X_flat @ self.weights + self.bias

if __name__ == "__main__":
    # 训练和评估
    results = train_and_evaluate()
    print(f"mape: {results['mape']:.4f}")
# @AI_GENERATED: end
`,
  },
  'prepare.py': {
    language: 'python',
    content: `# @AI_GENERATED: Kiro v1.0
"""
光伏发电功率预测 - 数据准备和评估模块（只读）
"""
import numpy as np
import pandas as pd

TIME_BUDGET = 300        # 训练时间预算（秒）
FORECAST_HORIZON = 4     # 预测步长
SEQUENCE_LENGTH = 96     # 输入序列长度

def load_pv_data(data_path=None):
    """加载光伏发电数据"""
    df = pd.read_csv(data_path, parse_dates=['timestamp'])
    return df

def evaluate_mape(y_true, y_pred, ignore_zero=True):
    """计算 MAPE（主要评估指标）"""
    y_true = np.array(y_true).flatten()
    y_pred = np.array(y_pred).flatten()
    if ignore_zero:
        mask = y_true > 0
        y_true = y_true[mask]
        y_pred = y_pred[mask]
    return np.mean(np.abs((y_true - y_pred) / y_true)) * 100

class MinMaxScaler:
    """Min-Max 标准化器"""
    def fit_transform(self, X):
        self.min_ = X.min(axis=0)
        self.max_ = X.max(axis=0)
        return (X - self.min_) / (self.max_ - self.min_)
# @AI_GENERATED: end
`,
  },
};

const SkillDetailPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const { skillId } = useParams<{ skillId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [skill, setSkill] = useState<PackagedSkill | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  useEffect(() => {
    if (skillId) {
      loadSkill(skillId);
    }
  }, [skillId]);

  const loadSkill = async (id: string) => {
    setLoading(true);
    try {
      const data = await templateSkillApi.getSkill(id);
      setSkill(data);
    } catch (error) {
      message.error(t('skillDetail.loadFailed'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleStartTraining = () => {
    message.info(t('skillDetail.startTraining', { name: skill?.skill_name }));
  };

  const handleDeploy = () => {
    message.info(t('skillDetail.deploying', { name: skill?.skill_name }));
  };

  // Skill 文件列表
  const skillFiles = [
    { name: 'program.md', type: 'file', description: 'Agent 指令文档', editable: false },
    { name: 'train.py', type: 'file', description: '训练脚本（Agent 可编辑）', editable: true },
    { name: 'prepare.py', type: 'file', description: '数据准备和评估（只读）', editable: false },
    { name: 'README.md', type: 'file', description: '使用文档', editable: false },
    { name: 'data/', type: 'directory', description: '数据目录' },
    { name: 'results.tsv', type: 'file', description: '实验结果记录', editable: true },
  ];

  // 训练历史
  const trainingHistory = [
    { id: 1, commit: 'a1b2c3d', mape: 12.34, rmse: 156.78, status: 'keep', description: 'baseline - 线性回归', time: '2026-03-23 10:00' },
    { id: 2, commit: 'b2c3d4e', mape: 8.54, rmse: 125.67, status: 'keep', description: 'LSTM 2层 hidden=64', time: '2026-03-23 10:05' },
    { id: 3, commit: 'c3d4e5f', mape: 15.00, rmse: 200.00, status: 'discard', description: 'GRU 效果更差', time: '2026-03-23 10:10' },
    { id: 4, commit: 'd4e5f6g', mape: 7.82, rmse: 118.45, status: 'keep', description: 'LSTM + 时间特征', time: '2026-03-23 10:15' },
    { id: 5, commit: 'e5f6g7h', mape: 6.95, rmse: 105.23, status: 'keep', description: 'LSTM + 气象特征', time: '2026-03-23 10:20' },
  ];

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!skill) {
    return (
      <div style={{ padding: 24 }}>
        <Empty description={t('skillDetail.notFound')} />
        <Button onClick={() => navigate('/template-library')}>{t('skillDetail.backToLibrary')}</Button>
      </div>
    );
  }

  const statusConfig = STATUS_CONFIG[skill.status as SkillStatus] || STATUS_CONFIG.packaged;

  return (
    <div style={{ padding: 24 }}>
      {/* 面包屑导航 */}
      <Breadcrumb style={{ marginBottom: 16 }}>
        <Breadcrumb.Item href="/home"><HomeOutlined /> 首页</Breadcrumb.Item>
        <Breadcrumb.Item href="/template-library"><ThunderboltOutlined /> 模板库</Breadcrumb.Item>
        <Breadcrumb.Item>{skill.skill_name}</Breadcrumb.Item>
      </Breadcrumb>

      {/* 页面标题 */}
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/template-library')}>
                返回
              </Button>
              <ThunderboltOutlined style={{ fontSize: 24, color: '#722ed1' }} />
              <Title level={4} style={{ margin: 0 }}>{skill.skill_name}</Title>
              <Tag color={statusConfig.color} icon={statusConfig.icon}>
                {t(statusConfig.labelKey)}
              </Tag>
              <Text code>v{skill.skill_version}</Text>
            </Space>
          </Col>
          <Col>
            <Space>
              {skill.training_config.enabled && skill.status === 'packaged' && (
                <Button icon={<PlayCircleOutlined />} onClick={handleStartTraining}>
                  开始训练
                </Button>
              )}
              {skill.status === 'ready' && (
                <Button type="primary" icon={<RocketOutlined />} onClick={handleDeploy}>
                  部署
                </Button>
              )}
            </Space>
          </Col>
        </Row>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          {skill.description || t('skillDetail.noDescription')}
        </Paragraph>
      </Card>

      {/* 主内容区 */}
      <Row gutter={16}>
        {/* 左侧：文件列表 */}
        <Col span={6}>
          <Card title={<><FolderOpenOutlined /> {t('skillDetail.fileStructure')}</>} size="small">
            <List
              size="small"
              dataSource={skillFiles}
              renderItem={file => (
                <List.Item
                  style={{
                    cursor: file.type === 'file' ? 'pointer' : 'default',
                    background: selectedFile === file.name ? '#e6f7ff' : 'transparent',
                  }}
                  onClick={() => file.type === 'file' && setSelectedFile(file.name)}
                >
                  <Space>
                    {file.type === 'directory' ? <FolderOpenOutlined /> : <FileTextOutlined />}
                    <Text>{file.name}</Text>
                    {file.editable && <Tag color="green" style={{ fontSize: 10 }}>{t('skillDetail.editable')}</Tag>}
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>

        {/* 右侧：内容区 */}
        <Col span={18}>
          <Card>
            <Tabs activeKey={activeTab} onChange={setActiveTab}>
              {/* 概览 Tab */}
              <Tabs.TabPane tab={<><EyeOutlined /> {t('skillDetail.overview')}</>} key="overview">
                <Row gutter={16}>
                  <Col span={12}>
                    <Descriptions title={t('skillDetail.basicInfo')} bordered size="small" column={1}>
                      <Descriptions.Item label={t('skillDetail.skillId')}>{skill.skill_id}</Descriptions.Item>
                      <Descriptions.Item label={t('skillDetail.version')}>v{skill.skill_version}</Descriptions.Item>
                      <Descriptions.Item label={t('skillDetail.sourceTemplate')}>{skill.source_template_name}</Descriptions.Item>
                      <Descriptions.Item label={t('skillDetail.templateVersion')}>{skill.source_template_version}</Descriptions.Item>
                      <Descriptions.Item label={t('skillDetail.creator')}>{skill.created_by}</Descriptions.Item>
                      <Descriptions.Item label={t('skillDetail.createdAt')}>{new Date(skill.created_at).toLocaleString()}</Descriptions.Item>
                    </Descriptions>
                  </Col>
                  <Col span={12}>
                    <Descriptions title={t('skillDetail.configInfo')} bordered size="small" column={1}>
                      <Descriptions.Item label={t('skillDetail.enableTraining')}>{skill.training_config.enabled ? '是' : '否'}</Descriptions.Item>
                      <Descriptions.Item label={t('skillDetail.minSamples')}>{skill.training_config.min_samples}</Descriptions.Item>
                      <Descriptions.Item label={t('skillDetail.defaultEpochs')}>{skill.training_config.default_epochs}</Descriptions.Item>
                      <Descriptions.Item label="CPU">{skill.resource_config.cpu} 核</Descriptions.Item>
                      <Descriptions.Item label="内存">{skill.resource_config.memory}</Descriptions.Item>
                      <Descriptions.Item label="GPU">{skill.resource_config.gpu}</Descriptions.Item>
                    </Descriptions>
                  </Col>
                </Row>
              </Tabs.TabPane>

              {/* 代码 Tab */}
              <Tabs.TabPane tab={<><CodeOutlined /> {t('skillDetail.code')}</>} key="code">
                {selectedFile && MOCK_FILES[selectedFile] ? (
                  <div>
                    <Alert
                      message={`文件: ${selectedFile}`}
                      description={skillFiles.find(f => f.name === selectedFile)?.description}
                      type="info"
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                    <pre style={{
                      background: '#1e1e1e',
                      color: '#d4d4d4',
                      padding: 16,
                      borderRadius: 4,
                      overflow: 'auto',
                      maxHeight: 500,
                      fontSize: 13,
                      lineHeight: 1.5,
                    }}>
                      {MOCK_FILES[selectedFile].content}
                    </pre>
                  </div>
                ) : (
                  <Empty description={t('skillDetail.selectFileToView')} />
                )}
              </Tabs.TabPane>

              {/* 训练历史 Tab */}
              <Tabs.TabPane tab={<><HistoryOutlined /> {t('skillDetail.trainingHistory')}</>} key="history">
                {skill.training_config.enabled ? (
                  <List
                    size="small"
                    dataSource={trainingHistory}
                    renderItem={item => (
                      <List.Item>
                        <List.Item.Meta
                          avatar={<Text code>{item.commit}</Text>}
                          title={
                            <Space>
                              <Text>MAPE: {item.mape.toFixed(2)}%</Text>
                              <Text type="secondary">RMSE: {item.rmse.toFixed(2)}</Text>
                              <Tag color={item.status === 'keep' ? 'green' : 'red'}>{item.status}</Tag>
                            </Space>
                          }
                          description={
                            <Space>
                              <Text type="secondary">{item.description}</Text>
                              <Text type="secondary">| {item.time}</Text>
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description={t('skillDetail.trainingNotSupported')} />
                )}
              </Tabs.TabPane>

              {/* API Tab */}
              <Tabs.TabPane tab={<><ApiOutlined /> API</>} key="api">
                <Alert
                  message="Skill API 端点"
                  description="以下是此 Skill 的 API 调用示例"
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                />
                <Card size="small" title={t('skillDetail.trainingApi')} style={{ marginBottom: 16 }}>
                  <Paragraph>
                    <Text code>POST /api/skills/{skill.skill_id}/train</Text>
                  </Paragraph>
                  <pre style={{ background: '#1e1e1e', color: '#d4d4d4', padding: 12, borderRadius: 4 }}>
{`{
  "data_path": "/path/to/training/data.csv",
  "epochs": ${skill.training_config.default_epochs},
  "batch_size": ${skill.training_config.default_batch_size}
}`}
                  </pre>
                </Card>
                <Card size="small" title={t('skillDetail.inferenceApi')}>
                  <Paragraph>
                    <Text code>POST /api/skills/{skill.skill_id}/predict</Text>
                  </Paragraph>
                  <pre style={{ background: '#1e1e1e', color: '#d4d4d4', padding: 12, borderRadius: 4 }}>
{`{
  "input_data": [
    {"timestamp": "2026-03-23T10:00:00", "irradiance": 800, "temperature": 25}
  ],
  "model_version": "latest"
}`}
                  </pre>
                </Card>
              </Tabs.TabPane>
            </Tabs>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default SkillDetailPage;
// @AI_GENERATED: end
