import type { ThemeConfig } from 'antd';

/** 光伏故障诊断黑橙白主题主色 */
export const PV_FAULT_PRIMARY = '#FF6A00';
export const PV_FAULT_PRIMARY_HOVER = '#E85D00';
/** 完成/正常态 — 用深炭灰替代 AntD 默认绿 */
export const PV_FAULT_OK = '#374151';
export const PV_FAULT_OK_BG = '#F3F4F6';

/** Ant Design ConfigProvider 主题 — 供 PV 工作区页面使用 */
export const pvFaultAntdTheme: ThemeConfig = {
  token: {
    colorPrimary: PV_FAULT_PRIMARY,
    colorLink: PV_FAULT_PRIMARY,
    colorInfo: PV_FAULT_PRIMARY,
    colorSuccess: PV_FAULT_OK,
    colorSuccessBg: PV_FAULT_OK_BG,
    colorSuccessBorder: '#D1D5DB',
    colorWarning: '#D97706',
    colorWarningBg: '#FFFBEB',
    colorError: '#DC2626',
    borderRadius: 8,
  },
  components: {
    Button: {
      primaryShadow: '0 2px 0 rgba(255, 106, 0, 0.12)',
    },
    Tabs: {
      inkBarColor: PV_FAULT_PRIMARY,
      itemSelectedColor: PV_FAULT_PRIMARY,
      itemHoverColor: PV_FAULT_PRIMARY_HOVER,
    },
    Tag: {
      defaultBg: '#FFF4EB',
      defaultColor: '#B45309',
    },
    Progress: {
      defaultColor: PV_FAULT_PRIMARY,
    },
  },
};
