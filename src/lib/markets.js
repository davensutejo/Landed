// EU destination countries (code, English, Chinese, extra search words). Keep in step with landed/markets.py.
export const EU = [
  ['DE', 'Germany', '德国', 'german|deutschland'],
  ['AT', 'Austria', '奥地利', 'austria'],
  ['BE', 'Belgium', '比利时', 'belgium'],
  ['BG', 'Bulgaria', '保加利亚', 'bulgaria'],
  ['HR', 'Croatia', '克罗地亚', 'croatia'],
  ['CY', 'Cyprus', '塞浦路斯', 'cyprus'],
  ['CZ', 'Czechia', '捷克', 'czech'],
  ['DK', 'Denmark', '丹麦', 'denmark'],
  ['EE', 'Estonia', '爱沙尼亚', 'estonia'],
  ['FI', 'Finland', '芬兰', 'finland'],
  ['FR', 'France', '法国', 'france'],
  ['GR', 'Greece', '希腊', 'greece'],
  ['HU', 'Hungary', '匈牙利', 'hungary'],
  ['IE', 'Ireland', '爱尔兰', 'ireland'],
  ['IT', 'Italy', '意大利', 'italy'],
  ['LV', 'Latvia', '拉脱维亚', 'latvia'],
  ['LT', 'Lithuania', '立陶宛', 'lithuania'],
  ['LU', 'Luxembourg', '卢森堡', 'luxembourg'],
  ['MT', 'Malta', '马耳他', 'malta'],
  ['NL', 'Netherlands', '荷兰', 'netherlands|holland'],
  ['PL', 'Poland', '波兰', 'poland'],
  ['PT', 'Portugal', '葡萄牙', 'portugal'],
  ['RO', 'Romania', '罗马尼亚', 'romania'],
  ['SK', 'Slovakia', '斯洛伐克', 'slovakia'],
  ['SI', 'Slovenia', '斯洛文尼亚', 'slovenia'],
  ['ES', 'Spain', '西班牙', 'spain'],
  ['SE', 'Sweden', '瑞典', 'sweden']
];

export const isEU = (m) => EU.some((c) => c[0] === m);

export function marketName(m, lang) {
  if (m === 'US') return lang === 'zh' ? '美国' : 'United States';
  const c = EU.find((x) => x[0] === m);
  if (!c) return m;
  return lang === 'zh' ? c[2] : c[1];
}

/** The EU country a sentence names, or null. A bare "EU" / "Europe" is Germany. */
export function euCountryIn(text) {
  for (const [code, , zh, words] of EU) {
    if (new RegExp(`\\b(${words})`, 'i').test(text) || (zh === '爱尔兰' ? /(?<!北)爱尔兰/ : new RegExp(zh)).test(text)) return code;
  }
  return /\bEU\b|欧盟|欧洲|europe/i.test(text) ? 'DE' : null;
}
