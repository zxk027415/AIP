import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, message, Grid, ConfigProvider } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import i18n from '../i18n';
// @AI_GENERATED: end
import './LoginPage.css';

const { Title, Text } = Typography;
const { useBreakpoint } = Grid;

interface LoginFormValues {
  username: string;
  password: string;
}

/**
 * 登录页面
 * 
 * 字体修复说明：
 * 1. 使用 ConfigProvider 全局配置字体大小（14px）
 * 2. 使用系统字体与浏览器自动填充保持一致
 * 3. JavaScript 强制修复自动填充的字体样式
 * 
 * 已知问题：
 * - 手动输入时点击后字符可能轻微变宽（视觉效果，实际宽度未变）
 * - 这是浏览器渲染层面的问题，不影响功能使用
 */
const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end

  // 修复浏览器自动填充的字体样式
  useEffect(() => {
    const fixAutofillFont = () => {
      const inputs = document.querySelectorAll('input[type="text"], input[type="password"]');
      inputs.forEach((input) => {
        const element = input as HTMLInputElement;
        // 强制设置字体 - 使用系统字体与自动填充保持一致
        element.style.setProperty('font-family', '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif', 'important');
        element.style.setProperty('font-size', '14px', 'important');
        element.style.setProperty('font-weight', '400', 'important');
        element.style.setProperty('letter-spacing', '0px', 'important');
      });
    };

    // 页面加载时立即执行
    fixAutofillFont();
    
    // 延迟执行，确保浏览器自动填充完成后再修复
    setTimeout(fixAutofillFont, 100);
    setTimeout(fixAutofillFont, 500);
    setTimeout(fixAutofillFont, 1000);
    
    // 监听动画事件（浏览器自动填充会触发动画）
    const handleAnimationStart = (e: AnimationEvent) => {
      if (e.animationName === 'onAutoFillStart') {
        setTimeout(fixAutofillFont, 50);
      }
    };
    
    document.addEventListener('animationstart', handleAnimationStart as any);
    
    return () => {
      document.removeEventListener('animationstart', handleAnimationStart as any);
    };
  }, []);

  const onFinish = async (values: LoginFormValues) => {
    setLoading(true);
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: values.username,
          password: values.password,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        const isFirstLogin = localStorage.getItem('hasLoggedInBefore') !== 'true';
        if (isFirstLogin) {
          localStorage.setItem('lang', 'zh');
          try {
            const raw = localStorage.getItem('appSettings');
            const settings = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
            settings.language = 'zh-CN';
            localStorage.setItem('appSettings', JSON.stringify(settings));
          } catch {
            localStorage.setItem('appSettings', JSON.stringify({ language: 'zh-CN' }));
          }
          i18n.changeLanguage('zh');
        }
        localStorage.setItem('hasLoggedInBefore', 'true');
        localStorage.setItem('isLoggedIn', 'true');
        localStorage.setItem('username', data.username);
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('userId', data.user_id.toString());

        message.success(t('login.success'));
        navigate('/home');
      } else {
        message.error(data.detail || t('login.failed'));
      }
    } catch (error) {
      console.error('登录失败:', error);
      message.error(t('login.networkError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <ConfigProvider
      theme={{
        token: {
          fontSize: 14,
          lineHeight: 1.5715,
          // 强制使用整数边框宽度
          lineWidth: 1,
        },
        components: {
          Input: {
            paddingBlock: 4,
            paddingInline: 11,
            // 强制边框宽度为 1px
            lineWidth: 1,
            lineType: 'solid',
          },
        },
      }}
    >
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          padding: isMobile ? '20px' : '40px',
        }}
      >
        <Card
          style={{
            width: '100%',
            maxWidth: isMobile ? '100%' : '400px',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12)',
            borderRadius: isMobile ? '8px' : '12px',
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: '32px' }}>
            <Title level={isMobile ? 4 : 2} style={{ marginBottom: '8px' }}>
              {t('login.title')}
            </Title>
            <Text type="secondary">{t('login.welcome')}</Text>
          </div>

          <Form
            name="login"
            onFinish={onFinish}
            autoComplete="off"
            size="middle"
          >
            <Form.Item
              name="username"
              rules={[
                { required: true, message: t('login.usernameRequired') },
                { min: 3, message: t('login.usernameMin') },
              ]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder={t('login.username')}
                autoComplete="username"
                style={{ 
                  fontSize: '14px',
                  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif'
                }}
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: t('login.passwordRequired') },
                { min: 6, message: t('login.passwordMin') },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder={t('login.password')}
                autoComplete="current-password"
                style={{ 
                  fontSize: '14px',
                  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif'
                }}
              />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                style={{ height: isMobile ? '44px' : '40px' }}
              >
                {t('login.loginBtn')}
              </Button>
            </Form.Item>

            <div style={{ textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: isMobile ? '12px' : '14px' }}>
                {t('login.noAccount')}{' '}
                <Link to="/register">{t('login.register')}</Link>
              </Text>
            </div>
          </Form>
        </Card>
      </div>
    </ConfigProvider>
  );
};

export default LoginPage;
