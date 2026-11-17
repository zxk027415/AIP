/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    // 特别包含 workflow-enhanced 组件
    './src/components/workflow-enhanced/**/*.{js,jsx,ts,tsx}',
  ],
  // 添加前缀避免与 Ant Design 冲突
  prefix: 'tw-',
  important: true,
  theme: {
    extend: {
      colors: {
        // Dify 颜色主题
        'dify-primary': '#296dff',
        'dify-success': '#17b26a',
        'dify-error': '#f04438',
        'dify-warning': '#faad14',
        'dify-gray': {
          50: '#f9fafb',
          100: '#f2f4f7',
          200: '#e5e7eb',
          300: '#d0d5dc',
          400: '#98a2b3',
          500: '#667085',
          600: '#475467',
          700: '#344054',
          800: '#1d2939',
          900: '#101828',
        },
      },
      borderRadius: {
        'dify-sm': '6px',
        'dify-md': '8px',
        'dify-lg': '12px',
      },
      boxShadow: {
        'dify-sm': '0px 1px 2px rgba(16, 24, 40, 0.05)',
        'dify-md': '0px 4px 6px -2px rgba(16, 24, 40, 0.03), 0px 12px 16px -4px rgba(16, 24, 40, 0.08)',
        'dify-lg': '0px 12px 16px -4px rgba(16, 24, 40, 0.08), 0px 4px 6px -2px rgba(16, 24, 40, 0.03)',
      },
      spacing: {
        // 4px 基准单位
        '0.5': '2px',
        '1': '4px',
        '1.5': '6px',
        '2': '8px',
        '2.5': '10px',
        '3': '12px',
        '3.5': '14px',
        '4': '16px',
        '5': '20px',
        '6': '24px',
        '7': '28px',
        '8': '32px',
        '9': '36px',
        '10': '40px',
      },
    },
  },
  plugins: [],
  // 确保与 Ant Design 共存
  corePlugins: {
    preflight: false, // 禁用 Tailwind 的基础样式重置，避免影响 Ant Design
  },
}
