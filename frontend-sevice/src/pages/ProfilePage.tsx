import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, message, Grid, Space, Divider } from 'antd';
import { UserOutlined, MailOutlined, LockOutlined, EditOutlined, SaveOutlined, CloseOutlined } from '@ant-design/icons';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end

const { Title, Text } = Typography;
const { useBreakpoint } = Grid;

interface UserInfo {
  id: number;
  username: string;
  email: string | null;
  created_at: string;
}

/**
 * 优化后的用户信息管理页面
 * 
 * 功能：
 * - 查看用户信息（默认只读）
 * - 点击"修改"按钮后可编辑用户名和邮箱
 * - 点击"修改密码"按钮展开密码修改表单
 * - 分别保存基本信息和密码
 */
const ProfilePage: React.FC = () => {
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [editingProfile, setEditingProfile] = useState(false);
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [passwordLoading, setPasswordLoading] = useState(false);
  const navigate = useNavigate();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end

  const [profileForm] = Form.useForm();
  const [passwordForm] = Form.useForm();

  // 加载用户信息
  useEffect(() => {
    loadUserInfo();
  }, []);

  const loadUserInfo = async () => {
    const userId = localStorage.getItem('userId');
    if (!userId) {
      message.error(t('profile.notLoggedIn'));
      navigate('/login');
      return;
    }

    try {
      const response = await fetch(`/api/auth/user/${userId}`);
      if (!response.ok) {
        throw new Error(t('profile.fetchUserInfoFailed'));
      }
      const data = await response.json();
      setUserInfo(data);
      profileForm.setFieldsValue({
        username: data.username,
        email: data.email || '',
      });
    } catch (error) {
      message.error(t('profile.loadUserInfoFailed'));
      console.error(error);
    }
  };

  // 开始编辑基本信息
  const handleStartEdit = () => {
    setEditingProfile(true);
  };

  // 取消编辑基本信息
  const handleCancelEdit = () => {
    setEditingProfile(false);
    // 恢复原始值
    if (userInfo) {
      profileForm.setFieldsValue({
        username: userInfo.username,
        email: userInfo.email || '',
      });
    }
  };

  // 保存基本信息
  const handleSaveProfile = async () => {
    try {
      const values = await profileForm.validateFields(['username', 'email']);
      const userId = localStorage.getItem('userId');
      
      if (!userId) {
        message.error(t('profile.notLoggedIn'));
        return;
      }

      setProfileLoading(true);

      const response = await fetch(`/api/auth/user/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: values.username,
          email: values.email || null,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || t('profile.updateError'));
      }

      const updatedUser = await response.json();
      setUserInfo(updatedUser);
      setEditingProfile(false);
      
      // 更新 localStorage 中的用户名
      localStorage.setItem('username', updatedUser.username);
      
      message.success(t('profile.updateSuccess'));
    } catch (error: any) {
      message.error(error.message || t('profile.updateFailed'));
      console.error(error);
    } finally {
      setProfileLoading(false);
    }
  };

  // 显示/隐藏密码修改表单
  const handleTogglePasswordForm = () => {
    setShowPasswordForm(!showPasswordForm);
    if (!showPasswordForm) {
      passwordForm.resetFields();
    }
  };

  // 保存密码
  const handleSavePassword = async () => {
    try {
      const values = await passwordForm.validateFields();
      const userId = localStorage.getItem('userId');
      
      if (!userId) {
        message.error(t('profile.notLoggedIn'));
        return;
      }

      setPasswordLoading(true);

      const response = await fetch(`/api/auth/user/${userId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          current_password: values.current_password,
          new_password: values.new_password,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || t('profile.passwordChangeFailed'));
      }

      message.success(t('profile.passwordChangeSuccess'));
      passwordForm.resetFields();
      setShowPasswordForm(false);
    } catch (error: any) {
      message.error(error.message || t('profile.passwordChangeFailed'));
      console.error(error);
    } finally {
      setPasswordLoading(false);
    }
  };

  if (!userInfo) {
    return (
      <div style={{ padding: isMobile ? '16px' : '24px' }}>
        <Card loading />
      </div>
    );
  }

  return (
    <div style={{ 
      padding: '16px',
      height: '100%',
      overflow: 'auto'
    }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card>
          <Title level={3}>{t('profile.title')}</Title>
          
          {/* 基本信息表单 */}
          <Form
            form={profileForm}
            layout="vertical"
            style={{ marginTop: '24px' }}
          >
            <Form.Item
              label={t('profile.username')}
              name="username"
              rules={[
                { required: true, message: t('login.usernameRequired') },
                { min: 3, message: t('profile.usernameMin') },
                { max: 50, message: t('profile.usernameMax') },
              ]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder={t('profile.usernamePlaceholder')}
                disabled={!editingProfile}
                size="large"
              />
            </Form.Item>

            <Form.Item
              label={t('profile.email')}
              name="email"
              rules={[
                { type: 'email', message: t('profile.emailInvalid') },
              ]}
            >
              <Input
                prefix={<MailOutlined />}
                placeholder={t('profile.emailPlaceholder')}
                disabled={!editingProfile}
                size="large"
              />
            </Form.Item>

            <Form.Item label={t('profile.registeredAt')}>
              <Text type="secondary">
                {new Date(userInfo.created_at).toLocaleString('zh-CN')}
              </Text>
            </Form.Item>

            {/* 基本信息操作按钮 */}
            <Form.Item>
              {!editingProfile ? (
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Space size="middle">
                    <Button
                      danger
                      icon={<LockOutlined />}
                      onClick={handleTogglePasswordForm}
                      size="large"
                      disabled={showPasswordForm}
                    >
                      {t('profile.changePassword')}
                    </Button>
                    <Button
                      type="primary"
                      icon={<EditOutlined />}
                      onClick={handleStartEdit}
                      size="large"
                    >
                      {t('profile.editInfo')}
                    </Button>
                  </Space>
                </div>
              ) : (
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Space>
                    <Button
                      icon={<CloseOutlined />}
                      onClick={handleCancelEdit}
                      size="large"
                    >
                      {t('profile.cancel')}
                    </Button>
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      onClick={handleSaveProfile}
                      loading={profileLoading}
                      size="large"
                    >
                      {t('profile.saveInfo')}
                    </Button>
                  </Space>
                </div>
              )}
            </Form.Item>
          </Form>

          {/* 密码修改表单 */}
          {showPasswordForm && <Divider />}

          {/* 密码修改表单 */}
          {showPasswordForm && (
            <>
              <Title level={4} style={{ marginTop: '16px' }}>{t('profile.changePasswordTitle')}</Title>
              <Form
                form={passwordForm}
                layout="vertical"
                style={{ marginTop: '16px' }}
              >
                <Form.Item
                  label={t('profile.currentPassword')}
                  name="current_password"
                  rules={[{ required: true, message: t('profile.currentPasswordPlaceholder') }]}
                >
                  <Input.Password
                    prefix={<LockOutlined />}
                    placeholder={t('profile.currentPasswordPlaceholder')}
                    size="large"
                  />
                </Form.Item>

                <Form.Item
                  label={t('profile.newPassword')}
                  name="new_password"
                  rules={[
                    { required: true, message: t('profile.newPasswordPlaceholder') },
                    { min: 6, message: t('login.passwordMin') },
                  ]}
                >
                  <Input.Password
                    prefix={<LockOutlined />}
                    placeholder={t('profile.newPasswordPlaceholder')}
                    size="large"
                  />
                </Form.Item>

                <Form.Item
                  label={t('profile.confirmNewPassword')}
                  name="confirm_password"
                  dependencies={['new_password']}
                  rules={[
                    { required: true, message: t('profile.confirmNewPasswordPlaceholder') },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (!value || getFieldValue('new_password') === value) {
                          return Promise.resolve();
                        }
                        return Promise.reject(new Error(t('profile.passwordMismatch')));
                      },
                    }),
                  ]}
                >
                  <Input.Password
                    prefix={<LockOutlined />}
                    placeholder={t('profile.confirmNewPasswordPlaceholder')}
                    size="large"
                  />
                </Form.Item>

                {/* 密码操作按钮 */}
                <Form.Item>
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <Space>
                      <Button
                        icon={<CloseOutlined />}
                        onClick={handleTogglePasswordForm}
                        size="large"
                      >
                        {t('profile.cancel')}
                      </Button>
                      <Button
                        type="primary"
                        danger
                        icon={<SaveOutlined />}
                        onClick={handleSavePassword}
                        loading={passwordLoading}
                        size="large"
                      >
                        {t('profile.save')}
                      </Button>
                    </Space>
                  </div>
                </Form.Item>
              </Form>
            </>
          )}
        </Card>
      </Space>
    </div>
  );
};

export default ProfilePage;
