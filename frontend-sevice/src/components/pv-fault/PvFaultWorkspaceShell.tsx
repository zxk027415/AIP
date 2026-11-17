import React from 'react';
import { ConfigProvider } from 'antd';
import { pvFaultAntdTheme } from '../../theme/pvFaultTheme';
import '../../styles/pvFaultWorkspace.css';

interface PvFaultWorkspaceShellProps {
  className?: string;
  as?: 'div' | 'main';
  children: React.ReactNode;
  'aria-label'?: string;
}

/**
 * 光伏故障诊断工作区壳层：注入黑橙白 Ant Design 主题 + 共享 CSS 变量。
 */
const PvFaultWorkspaceShell: React.FC<PvFaultWorkspaceShellProps> = ({
  className = '',
  as: Tag = 'div',
  children,
  'aria-label': ariaLabel,
}) => (
  <ConfigProvider theme={pvFaultAntdTheme}>
    <Tag className={`pv-fault-workspace ${className}`.trim()} aria-label={ariaLabel}>
      {children}
    </Tag>
  </ConfigProvider>
);

export default PvFaultWorkspaceShell;
