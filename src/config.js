import { isZh } from './i18n.js';

const CONFIGS = {
  zh: {
    BRAND_NAME: 'Landed',
    TAGLINE: '跨境电商到岸价，一分钟算清',
    PRODUCT: '跨境电商到岸成本与本地化助手',
    MOTTO: '到岸',
    YEAR_ROMAN: '2026', // Roman numerals are a Latin-typography device; Chinese pages use the year as is
    CITIES: '中国 → 欧盟 · 美国'
  },
  en: {
    BRAND_NAME: 'Landed',
    TAGLINE: '到岸价，一分钟算清。The landed price, sourced.',
    PRODUCT: 'Cross-border landed-cost and localization agent: HS disambiguation, sourced cost waterfall, 95% risk-buffered price, localized listing',
    MOTTO: '到岸',
    YEAR_ROMAN: 'MMXXVI',
    CITIES: 'CN → EU · US'
  }
};

/** The site config for the current language. */
export const getConfig = () => CONFIGS[isZh() ? 'zh' : 'en'];
export const CONFIG = getConfig();

export function applyConfigToDOM(config = CONFIG) {
  document.title = `${config.BRAND_NAME} — ${config.TAGLINE}`;
  const metaDesc = document.querySelector('meta[name="description"]');
  if (metaDesc) {
    metaDesc.setAttribute(
      'content',
      `${config.PRODUCT}. ${config.MOTTO} · ${config.YEAR_ROMAN}.`
    );
  }
  document.querySelectorAll('[data-config]').forEach((el) => {
    const key = el.getAttribute('data-config');
    if (key && config[key]) {
      el.textContent = config[key];
    }
  });
}