import { useState, FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import i18n from '../i18n';
// @AI_GENERATED: end
import './LoginPageNew.css';

/**
 * 全新的登录页面
 * 使用原生 HTML 表单元素，避免 Ant Design Input 组件的字体问题
 */
const LoginPageNew: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  const navigate = useNavigate();

  const validateForm = (): boolean => {
    const newErrors: { username?: string; password?: string } = {};

    if (!username) {
      newErrors.username = t('loginNew.usernameRequired');
    } else if (username.length < 3) {
      newErrors.username = t('loginNew.usernameMin');
    }

    if (!password) {
      newErrors.password = t('loginNew.passwordRequired');
    } else if (password.length < 6) {
      newErrors.password = t('loginNew.passwordMin');
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username,
          password,
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

        message.success(t('loginNew.success'));
        navigate('/home');
      } else {
        message.error(data.detail || t('loginNew.failed'));
      }
    } catch (error) {
      console.error('登录失败:', error);
      message.error(t('loginNew.networkError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page-new">
      <div className="login-card-new">
        <div className="login-header-new">
          <h1 className="login-title-new">{t('loginNew.title')}</h1>
          <p className="login-subtitle-new">{t('loginNew.welcome')}</p>
        </div>

        <form className="login-form-new" onSubmit={handleSubmit}>
          <div className="form-item-new">
            <div className="input-wrapper-new">
              <span className="input-prefix-new">
                <UserOutlined />
              </span>
              <input
                type="text"
                className="input-new"
                placeholder={t('loginNew.usernamePlaceholder')}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
            </div>
            {errors.username && (
              <div className="error-message-new">{errors.username}</div>
            )}
          </div>

          <div className="form-item-new">
            <div className="input-wrapper-new">
              <span className="input-prefix-new">
                <LockOutlined />
              </span>
              <input
                type="password"
                className="input-new"
                placeholder={t('loginNew.passwordPlaceholder')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            {errors.password && (
              <div className="error-message-new">{errors.password}</div>
            )}
          </div>

          <button
            type="submit"
            className={`login-button-new ${loading ? 'loading' : ''}`}
            disabled={loading}
          >
            {loading ? t('loginNew.loggingIn') : t('loginNew.loginBtn')}
          </button>

          <div className="login-footer-new">
            <span className="footer-text-new">
              {t('loginNew.noAccount')}{' '}
              <Link to="/register" className="login-link-new">
                {t('loginNew.register')}
              </Link>
            </span>
          </div>
        </form>
      </div>
    </div>
  );
};

export default LoginPageNew;
