// @AI_GENERATED
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  Card, 
  Space, 
  Typography, 
  Grid, 
  Form, 
  Input, 
  Button, 
  Switch,
  Select,
  message,
  Divider,
  InputNumber,
  Radio,
  Popconfirm,
  Tabs,
  ConfigProvider
} from 'antd';
import { 
  SaveOutlined, 
  ReloadOutlined,
  DeleteOutlined,
  SettingOutlined,
  AppstoreOutlined,
  DatabaseOutlined,
  InfoCircleOutlined
} from '@ant-design/icons';
import './SettingsPage.css';
// @AI_GENERATED: end

const { Text, Title } = Typography;
const { useBreakpoint } = Grid;
const { TextArea } = Input;

interface SystemConfig {
  projectName: string;
  projectDescription: string;
  environment: string;
  frontendPort: number;
  backendPort: number;
}

interface AppSettings {
  theme: 'light' | 'dark';
  language: 'zh-CN' | 'en-US';
  enableNotifications: boolean;
  autoSave: boolean;
  autoSaveInterval: number;
}

const toShortLang = (fullLang: 'zh-CN' | 'en-US'): 'zh' | 'en' => (
  fullLang === 'en-US' ? 'en' : 'zh'
);

const toFullLang = (shortLang: string): 'zh-CN' | 'en-US' => (
  shortLang.toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN'
);

/**
 * 系统配置页面
 * 
 * 功能：
 * - Tab 1: 系统信息 - 项目基本信息和端口配置
 * - Tab 2: 应用设置 - 主题、语言、通知和性能设置
 * - Tab 3: 数据管理 - 缓存管理和配置导入导出
 * - Tab 4: 使用说明 - 功能说明和注意事项
 */
const SettingsPage: React.FC = () => {
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end
  const screens = useBreakpoint();
  const isMobile = !screens.md;

  const [systemForm] = Form.useForm();
  const [settingsForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('system');
  const [tabsKey, setTabsKey] = useState(0);
  const [tabsVisible, setTabsVisible] = useState(false);

  const applyLanguageChange = (fullLang: 'zh-CN' | 'en-US') => {
    const shortLang = toShortLang(fullLang);
    i18n.changeLanguage(shortLang);
    localStorage.setItem('lang', shortLang);
    try {
      const raw = localStorage.getItem('appSettings');
      const settings = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      settings.language = fullLang;
      localStorage.setItem('appSettings', JSON.stringify(settings));
    } catch {
      localStorage.setItem('appSettings', JSON.stringify({ language: fullLang }));
    }
    settingsForm.setFieldValue('language', fullLang);
  };

  // 默认系统配置
  const defaultSystemConfig: SystemConfig = {
    // @AI_GENERATED
    projectName: t('settings.defaultProjectName'),
    projectDescription: t('settings.defaultProjectDescription'),
    environment: 'Python 3.10+ / Node.js 18+ / Conda (aip_web)',
    // @AI_GENERATED: end
    frontendPort: 3001,
    backendPort: 8000,
  };

  // 默认应用设置
  const defaultAppSettings: AppSettings = {
    theme: 'light',
    language: toFullLang(i18n.language),
    enableNotifications: true,
    autoSave: true,
    autoSaveInterval: 30,
  };

  // 加载配置
  useEffect(() => {
    loadSystemConfig();
    loadAppSettings();
    
    // 延迟显示Tabs，避免初始渲染时的弹动
    requestAnimationFrame(() => {
      setTabsVisible(true);
      // 强制重新渲染Tabs以修复ink-bar位置
      setTimeout(() => {
        setTabsKey(prev => prev + 1);
      }, 0);
    });
  }, []);

  useEffect(() => {
    setTabsKey((prev) => prev + 1);
  }, [i18n.language]);

  const loadSystemConfig = () => {
    const saved = localStorage.getItem('systemConfig');
    const config = saved ? JSON.parse(saved) : defaultSystemConfig;
    systemForm.setFieldsValue(config);
  };

  const loadAppSettings = () => {
    const saved = localStorage.getItem('appSettings');
    const settings = saved ? JSON.parse(saved) : defaultAppSettings;
    settings.language = toFullLang(settings.language || i18n.language);
    settingsForm.setFieldsValue(settings);
  };

  // 保存系统配置
  const handleSaveSystemConfig = async () => {
    try {
      const values = await systemForm.validateFields();
      setLoading(true);
      
      // 保存到 localStorage
      localStorage.setItem('systemConfig', JSON.stringify(values));
      
      // 模拟API调用延迟
      setTimeout(() => {
        setLoading(false);
        // @AI_GENERATED
        message.success(t('settings.systemConfigSaved'));
        // @AI_GENERATED: end
      }, 500);
    } catch (error) {
      // @AI_GENERATED
      message.error(t('settings.saveFailed'));
      // @AI_GENERATED: end
    }
  };

  // 保存应用设置
  const handleSaveAppSettings = async () => {
    try {
      const values = await settingsForm.validateFields();
      setLoading(true);
      
      // 保存到 localStorage
      localStorage.setItem('appSettings', JSON.stringify(values));

      applyLanguageChange(values.language);

      // 应用主题设置
      if (values.theme === 'dark') {
        document.body.classList.add('dark-theme');
      } else {
        document.body.classList.remove('dark-theme');
      }
      
      setTimeout(() => {
        setLoading(false);
        // @AI_GENERATED
        message.success(t('settings.appSettingsSaved'));
        // @AI_GENERATED: end
      }, 500);
    } catch (error) {
      // @AI_GENERATED
      message.error(t('settings.saveFailed'));
      // @AI_GENERATED: end
    }
  };

  // 重置系统配置
  const handleResetSystemConfig = () => {
    systemForm.setFieldsValue(defaultSystemConfig);
    localStorage.setItem('systemConfig', JSON.stringify(defaultSystemConfig));
    // @AI_GENERATED
    message.success(t('settings.systemConfigReset'));
    // @AI_GENERATED: end
  };

  // 重置应用设置
  const handleResetAppSettings = () => {
    const resetSettings = { ...defaultAppSettings, language: toFullLang(i18n.language) };
    settingsForm.setFieldsValue(resetSettings);
    localStorage.setItem('appSettings', JSON.stringify(resetSettings));
    localStorage.setItem('lang', toShortLang(resetSettings.language));
    document.body.classList.remove('dark-theme');
    // @AI_GENERATED
    message.success(t('settings.appSettingsReset'));
    // @AI_GENERATED: end
  };

  // 清除缓存数据
  const handleClearCache = () => {
    // 清除除了登录信息外的所有缓存
    const username = localStorage.getItem('username');
    const userId = localStorage.getItem('userId');
    const isLoggedIn = localStorage.getItem('isLoggedIn');
    
    localStorage.clear();
    
    // 恢复登录信息
    if (username) localStorage.setItem('username', username);
    if (userId) localStorage.setItem('userId', userId);
    if (isLoggedIn) localStorage.setItem('isLoggedIn', isLoggedIn);
    
    // 恢复默认配置
    localStorage.setItem('systemConfig', JSON.stringify(defaultSystemConfig));
    const resetSettings = { ...defaultAppSettings, language: toFullLang(i18n.language) };
    localStorage.setItem('appSettings', JSON.stringify(resetSettings));
    localStorage.setItem('lang', toShortLang(resetSettings.language));
    
    loadSystemConfig();
    loadAppSettings();
    
    // @AI_GENERATED
    message.success(t('settings.cacheCleared'));
    // @AI_GENERATED: end
  };

  // 导出配置
  const handleExportConfig = () => {
    const systemConfig = localStorage.getItem('systemConfig');
    const appSettings = localStorage.getItem('appSettings');
    
    const config = {
      system: systemConfig ? JSON.parse(systemConfig) : defaultSystemConfig,
      app: appSettings ? JSON.parse(appSettings) : defaultAppSettings,
      exportTime: new Date().toISOString(),
    };
    
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `settings-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    // @AI_GENERATED
    message.success(t('settings.configExported'));
    // @AI_GENERATED: end
  };

  // 右上角语言按钮切换后，系统配置页 Language 下拉实时联动
  useEffect(() => {
    settingsForm.setFieldValue('language', toFullLang(i18n.language));
    try {
      const raw = localStorage.getItem('appSettings');
      const settings = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      settings.language = toFullLang(i18n.language);
      localStorage.setItem('appSettings', JSON.stringify(settings));
      localStorage.setItem('lang', toShortLang(toFullLang(i18n.language)));
    } catch {
      localStorage.setItem('appSettings', JSON.stringify({ language: toFullLang(i18n.language) }));
      localStorage.setItem('lang', toShortLang(toFullLang(i18n.language)));
    }
  }, [i18n.language, settingsForm]);

  return (
    <ConfigProvider>
      <div style={{ 
        padding: '16px',
        height: '100%',
        overflow: 'hidden'
      }}>
        <Tabs
          key={tabsKey}
          activeKey={activeTab}
          onChange={setActiveTab}
          size={isMobile ? 'small' : 'large'}
          className="settings-tabs"
          tabBarGutter={isMobile ? 16 : 32}
          style={{ 
            opacity: tabsVisible ? 1 : 0,
            transition: 'opacity 0.1s ease'
          }}
          items={[
          {
            key: 'system',
            label: (
              <span style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: isMobile ? '4px' : '8px',
                fontWeight: 500
              }}>
                <SettingOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
                {!isMobile && <span>{t('settings.systemInfo')}</span>}
              </span>
            ),
            children: (
              <Card 
                title={t('settings.systemInfoConfig')}
                extra={
                  <Space>
                    <Button 
                      icon={<ReloadOutlined />} 
                      onClick={handleResetSystemConfig}
                      size="small"
                    >
                      {t('settings.reset')}
                    </Button>
                    <Button 
                      type="primary" 
                      icon={<SaveOutlined />}
                      onClick={handleSaveSystemConfig}
                      loading={loading}
                      size="small"
                    >
                      {t('settings.save')}
                    </Button>
                  </Space>
                }
              >
                <Form
                  form={systemForm}
                  layout="vertical"
                >
                  <Form.Item
                    label={t('settings.projectName')}
                    name="projectName"
                    rules={[{ required: true, message: t('settings.projectNameRequired') }]}
                  >
                    <Input placeholder={t('settings.projectNamePlaceholder')} />
                  </Form.Item>

                  <Form.Item
                    label={t('settings.projectDescription')}
                    name="projectDescription"
                    rules={[{ required: true, message: t('settings.projectDescriptionRequired') }]}
                  >
                    <TextArea 
                      rows={3} 
                      placeholder={t('settings.projectDescriptionPlaceholder')}
                    />
                  </Form.Item>

                  <Form.Item
                    label={t('settings.devEnvironment')}
                    name="environment"
                  >
                    <Input placeholder={t('settings.devEnvironmentPlaceholder')} />
                  </Form.Item>

                  <Form.Item
                    label={t('settings.frontendPort')}
                    name="frontendPort"
                    rules={[
                      { required: true, message: t('settings.frontendPortRequired') },
                      { type: 'number', min: 1024, max: 65535, message: t('settings.portRange') }
                    ]}
                  >
                    <InputNumber 
                      style={{ width: '100%' }}
                      placeholder={t('settings.frontendPortPlaceholder')}
                    />
                  </Form.Item>

                  <Form.Item
                    label={t('settings.backendPort')}
                    name="backendPort"
                    rules={[
                      { required: true, message: t('settings.backendPortRequired') },
                      { type: 'number', min: 1024, max: 65535, message: t('settings.portRange') }
                    ]}
                  >
                    <InputNumber 
                      style={{ width: '100%' }}
                      placeholder={t('settings.backendPortPlaceholder')}
                    />
                  </Form.Item>
                </Form>
              </Card>
            ),
          },
          {
            key: 'app',
            label: (
              <span style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: isMobile ? '4px' : '8px',
                fontWeight: 500
              }}>
                <AppstoreOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
                {!isMobile && <span>{t('settings.appSettings')}</span>}
              </span>
            ),
            children: (
              <Card 
                title={t('settings.appSettings')}
                extra={
                  <Space>
                    <Button 
                      icon={<ReloadOutlined />} 
                      onClick={handleResetAppSettings}
                      size="small"
                    >
                      {t('settings.reset')}
                    </Button>
                    <Button 
                      type="primary" 
                      icon={<SaveOutlined />}
                      onClick={handleSaveAppSettings}
                      loading={loading}
                      size="small"
                    >
                      {t('settings.save')}
                    </Button>
                  </Space>
                }
              >
                <Form
                  form={settingsForm}
                  layout="vertical"
                >
                  <Title level={5}>{t('settings.appearanceSettings')}</Title>
                  <Form.Item
                    label={t('settings.themeMode')}
                    name="theme"
                  >
                    <Radio.Group>
                      <Radio.Button value="light">{t('settings.lightMode')}</Radio.Button>
                      <Radio.Button value="dark">{t('settings.darkMode')}</Radio.Button>
                    </Radio.Group>
                  </Form.Item>

                  <Form.Item
                    label={t('settings.language')}
                    name="language"
                  >
                    <Select onChange={(val: 'zh-CN' | 'en-US') => applyLanguageChange(val)}>
                      <Select.Option value="zh-CN">{t('settings.languageOptionZhCN')}</Select.Option>
                      <Select.Option value="en-US">{t('settings.languageOptionEnUS')}</Select.Option>
                    </Select>
                  </Form.Item>

                  <Divider />

                  <Title level={5}>{t('settings.featureSettings')}</Title>
                  <Form.Item
                    label={t('settings.enableNotifications')}
                    name="enableNotifications"
                    valuePropName="checked"
                    extra={t('settings.enableNotificationsExtra')}
                  >
                    <Switch />
                  </Form.Item>

                  <Form.Item
                    label={t('settings.autoSave')}
                    name="autoSave"
                    valuePropName="checked"
                    extra={t('settings.autoSaveExtra')}
                  >
                    <Switch />
                  </Form.Item>

                  <Form.Item
                    label={t('settings.autoSaveInterval')}
                    name="autoSaveInterval"
                    rules={[
                      { type: 'number', min: 10, max: 300, message: t('settings.autoSaveIntervalRange') }
                    ]}
                    extra={t('settings.autoSaveIntervalExtra')}
                  >
                    <InputNumber 
                      style={{ width: '100%' }}
                      placeholder={t('settings.autoSaveIntervalPlaceholder')}
                    />
                  </Form.Item>
                </Form>
              </Card>
            ),
          },
          {
            key: 'data',
            label: (
              <span style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: isMobile ? '4px' : '8px',
                fontWeight: 500
              }}>
                <DatabaseOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
                {!isMobile && <span>{t('settings.dataManagement')}</span>}
              </span>
            ),
            children: (
              <Card title={t('settings.dataManagement')}>
                <Space direction="vertical" style={{ width: '100%' }} size="large">
                  <div>
                    <Title level={5}>{t('settings.clearCache')}</Title>
                    <Text type="secondary">
                      {t('settings.clearCacheDesc')}
                    </Text>
                    <br />
                    <Popconfirm
                      title={t('settings.confirmClearCache')}
                      description={t('settings.confirmClearCacheDesc')}
                      onConfirm={handleClearCache}
                      okText={t('common.confirm')}
                      cancelText={t('common.cancel')}
                    >
                      <Button 
                        danger 
                        icon={<DeleteOutlined />}
                        style={{ marginTop: '12px' }}
                      >
                        {t('settings.clearCache')}
                      </Button>
                    </Popconfirm>
                  </div>

                  <Divider />

                  <div>
                    <Title level={5}>{t('settings.exportConfig')}</Title>
                    <Text type="secondary">
                      {t('settings.exportConfigDesc')}
                    </Text>
                    <br />
                    <Button 
                      icon={<SaveOutlined />}
                      onClick={handleExportConfig}
                      style={{ marginTop: '12px' }}
                    >
                      {t('settings.exportConfig')}
                    </Button>
                  </div>

                  <Divider />

                  <div>
                    <Title level={5}>{t('settings.storageInfo')}</Title>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Text>
                        <Text strong>{t('settings.configStorage')}：</Text> {t('settings.browserLocalStorage')}
                      </Text>
                      <Text>
                        <Text strong>{t('settings.templateData')}：</Text> {t('settings.backendDatabase')}
                      </Text>
                      <Text>
                        <Text strong>{t('settings.userData')}：</Text> {t('settings.backendDatabase')}
                      </Text>
                    </Space>
                  </div>
                </Space>
              </Card>
            ),
          },
          {
            key: 'help',
            label: (
              <span style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: isMobile ? '4px' : '8px',
                fontWeight: 500
              }}>
                <InfoCircleOutlined style={{ fontSize: isMobile ? '14px' : '16px' }} />
                {!isMobile && <span>{t('settings.helpGuide')}</span>}
              </span>
            ),
            children: (
              <Card title={t('settings.helpGuide')}>
                <Space direction="vertical" style={{ width: '100%' }} size="large">
                  <div>
                    <Title level={5}>{t('settings.systemInfo')}</Title>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Text>• {t('settings.helpSystemInfo1')}</Text>
                      <Text>• {t('settings.helpSystemInfo2')}</Text>
                      <Text type="warning">⚠️ {t('settings.helpSystemInfo3')}</Text>
                    </Space>
                  </div>

                  <Divider />

                  <div>
                    <Title level={5}>{t('settings.appSettings')}</Title>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Text>• {t('settings.helpAppSettings1')}</Text>
                      <Text>• {t('settings.helpAppSettings2')}</Text>
                      <Text>• {t('settings.helpAppSettings3')}</Text>
                      <Text>• {t('settings.helpAppSettings4')}</Text>
                    </Space>
                  </div>

                  <Divider />

                  <div>
                    <Title level={5}>{t('settings.dataManagement')}</Title>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Text>• {t('settings.helpDataMgmt1')}</Text>
                      <Text>• {t('settings.helpDataMgmt2')}</Text>
                      <Text>• {t('settings.helpDataMgmt3')}</Text>
                      <Text type="secondary" style={{ fontSize: '12px' }}>
                        {t('settings.helpDataMgmtNote')}
                      </Text>
                    </Space>
                  </div>

                  <Divider />

                  <div>
                    <Title level={5}>{t('settings.quickActions')}</Title>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Text>• {t('settings.helpQuickActions1')}</Text>
                      <Text>• {t('settings.helpQuickActions2')}</Text>
                      <Text>• {t('settings.helpQuickActions3')}</Text>
                    </Space>
                  </div>
                </Space>
              </Card>
            ),
          },
        ]}
      />
      </div>
    </ConfigProvider>
  );
};

export default SettingsPage;
