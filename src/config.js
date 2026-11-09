export const CONFIG = {
  BRAND_NAME: 'Landed',
  TAGLINE: '到岸价，一分钟算清。The landed price, sourced.',
  PRODUCT: 'Cross-border landed-cost and localization agent: HS disambiguation, sourced cost waterfall, 95% risk-buffered price, localized listing',
  MOTTO: '到岸',
  YEAR_ROMAN: 'MMXXVI',
  CITIES: 'CN → EU · US'
};

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