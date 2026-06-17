import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import './RegisterPage.css';

const { Title, Text } = Typography;

interface RegisterFormValues {
  username: string;
  password: string;
  confirmPassword: string;
  email?: string;
}

/**
 * 注册页面
 * 
 * 响应式设计：
 * - 超大屏（≥1600px）：卡片宽度 450px，大字体
 * - 桌面端（≥768px）：卡片宽度 400px，标准字体
 * - 平板端（576-767px）：卡片宽度 90%，中等字体
 * - 移动端（<576px）：卡片宽度 100%，大触控区域
 */
const RegisterPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end

  const onFinish = async (values: RegisterFormValues) => {
    setLoading(true);
    try {
      // 调用后端注册 API
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: values.username,
          password: values.password,
          email: values.email || null,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        message.success(t('login.registerSuccess'));
        // 跳转到登录页面
        navigate('/login');
      } else {
        message.error(data.detail || t('login.registerFailed'));
      }
    } catch (error) {
      console.error('注册失败:', error);
      message.error(t('login.networkError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="register-page">
      <Card className="register-card">
        <div className="register-header">
          <Title 
            level={2} 
            className="register-title"
          >
            {t('login.registerTitle')}
          </Title>
          <Text type="secondary" className="register-subtitle">
            {t('login.welcome')}
          </Text>
        </div>

        <Form
          name="register"
          onFinish={onFinish}
          autoComplete="off"
          size="middle"
          className="register-form"
        >
          <Form.Item
            name="username"
            rules={[
              { required: true, message: t('login.usernameRequired') },
              { min: 3, message: t('login.usernameMin') },
              { max: 50, message: t('login.usernameMin') },
              {
                pattern: /^[a-zA-Z0-9_]+$/,
                message: t('login.usernameRequired'),
              },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={t('login.username')}
              autoComplete="username"
              className="register-input"
            />
          </Form.Item>

          <Form.Item
            name="email"
            rules={[
              { type: 'email', message: 'Email' },
            ]}
          >
            <Input
              prefix={<MailOutlined />}
              placeholder="Email"
              autoComplete="email"
              className="register-input"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: t('login.passwordRequired') },
              { min: 6, message: t('login.passwordMin') },
              { max: 100, message: t('login.passwordMin') },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('login.password')}
              autoComplete="new-password"
              className="register-input"
            />
          </Form.Item>

          <Form.Item
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: t('login.confirmPasswordRequired') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t('login.passwordMismatch')));
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('login.confirmPassword')}
              autoComplete="new-password"
              className="register-input"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              className="register-button"
            >
              {t('login.registerBtn')}
            </Button>
          </Form.Item>

          <div className="register-footer">
            <Text type="secondary" className="register-footer-text">
              {t('login.hasAccount')}{' '}
              <Link to="/login" className="register-link">{t('login.loginNow')}</Link>
            </Text>
          </div>
        </Form>
      </Card>
    </div>
  );
};

export default RegisterPage;
