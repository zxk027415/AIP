// @AI_GENERATED
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zh from './locales/zh.json';
import en from './locales/en.json';
import archDiagramZh from './locales/architecture-diagram.zh.json';
import archDiagramEn from './locales/architecture-diagram.en.json';

const zhResources = {
  ...zh,
  architecture: {
    ...zh.architecture,
    diagram: archDiagramZh,
  },
} as typeof zh;

const enResources = {
  ...en,
  architecture: {
    ...en.architecture,
    diagram: archDiagramEn,
  },
} as typeof en;

function resolveInitialLang(): string {
  const direct = localStorage.getItem('lang');
  if (direct === 'en' || direct === 'zh') return direct;
  try {
    const raw = localStorage.getItem('appSettings');
    if (raw) {
      const { language } = JSON.parse(raw) as { language?: string };
      if (language === 'en-US') return 'en';
      if (language === 'zh-CN') return 'zh';
    }
  } catch {
    /* ignore */
  }
  return 'zh';
}

i18n.use(initReactI18next).init({
  resources: {
    zh: { translation: zhResources },
    en: { translation: enResources },
  },
  lng: resolveInitialLang(),
  fallbackLng: 'zh',
  interpolation: { escapeValue: false },
});

export default i18n;
// @AI_GENERATED: end
