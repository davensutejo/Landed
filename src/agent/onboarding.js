// Full-screen onboarding: one question at a time, visual choice cards, a live seller
// profile that fills in as you answer, and a last screen that prices a typical product
// from the seller's niche using their answers. Every answer changes something real in
// the workspace (see landed/profile.py for what each field does).

import { esc } from '../lib/markdown.js';
import { postJSON } from '../lib/agentStream.js';
import { EU, isEU, marketName } from '../lib/markets.js';

const icon = (d, extra = '') => `<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}${extra}</svg>`;
const ICONS = {
  apparel: icon('<path d="M8 4 3 7l2 4 3-1v10h8V10l3 1 2-4-5-3c-.5 1.5-2 2.5-4 2.5S8.5 5.5 8 4z"/>'),
  electronics: icon('<rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/>'),
  kitchen: icon('<path d="M4 10h16v6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4v-6z"/><path d="M2 10h20M9 6c0-2 2-2 2-4M14 6c0-2 2-2 2-4"/>'),
  beauty: icon('<path d="M9 22V13h6v9M10 13V8l2-5 2 5v5M7 22h10"/>'),
  toys: icon('<path d="M3 13h8v8H3zM13 13h8v8h-8zM8 3h8v8H8z"/>'),
  home: icon('<path d="m3 11 9-8 9 8M5 10v10h14V10M10 20v-6h4v6"/>'),
  other: icon('<path d="m3 7 9-4 9 4v10l-9 4-9-4V7zM3 7l9 4 9-4M12 11v10"/>'),
  duty: icon('<path d="M6 3h9l3 3v15H6zM9 10h6M9 14h6"/>'),
  fx: icon('<path d="M4 8h14l-3-3M20 16H6l3 3"/>'),
  returns: icon('<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>'),
  freight: icon('<path d="M2 7h11v9H2zM13 10h4l3 3v3h-7"/><circle cx="6" cy="18" r="1.6"/><circle cx="16.5" cy="18" r="1.6"/>'),
  fee: icon('<path d="M5 19 19 5"/><circle cx="7" cy="7" r="2.2"/><circle cx="17" cy="17" r="2.2"/>'),
  compliance: icon('<path d="m12 3 8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="m8.5 12 2.5 2.5 5-5"/>')
};

const CATS = [
  ['apparel', '服饰鞋包', 'Apparel & bags'],
  ['electronics', '3C 电子', 'Electronics'],
  ['kitchen', '厨房餐饮', 'Kitchen & dining'],
  ['beauty', '美妆个护', 'Beauty & care'],
  ['toys', '母婴玩具', 'Baby & toys'],
  ['home', '家居百货', 'Home goods'],
  ['other', '其他', 'Something else']
];
// id, zh, en, sample zh, sample en, typical cost (CNY), weight (kg)
const NICHES = {
  apparel: [
    ['basics', '袜子 · 内衣', 'Socks & underwear', '棉袜 5 双装', 'Cotton socks 5-pack', 12, 0.25],
    ['tops', 'T 恤 · 卫衣', 'T-shirts & hoodies', '纯棉 T 恤', 'Cotton T-shirt', 28, 0.2],
    ['dresses', '连衣裙 · 外套', 'Dresses & outerwear', '针织连衣裙', 'Knit dress', 55, 0.5],
    ['shoes_bags', '鞋 · 包', 'Shoes & bags', '帆布托特包', 'Canvas tote bag', 24, 0.35],
    ['accessories', '发饰 · 配饰', 'Hair & fashion accessories', '发夹 6 个装', 'Hair clips 6-pack', 6, 0.1]
  ],
  electronics: [
    ['phone_acc', '手机配件', 'Phone accessories', '手机壳', 'Phone case', 6, 0.05],
    ['audio', '耳机 · 音频', 'Earbuds & audio', '蓝牙耳机', 'Bluetooth earbuds', 45, 0.15],
    ['lighting', '灯具', 'Lighting', 'LED 台灯', 'LED desk lamp', 35, 0.7],
    ['gadgets', '小电器 · 充电器', 'Gadgets & chargers', '快充充电器', 'Fast charger', 20, 0.15]
  ],
  kitchen: [
    ['kitchen_appliance', '厨房小家电', 'Small appliances', '便携榨汁杯', 'Portable blender', 38, 0.6],
    ['utensils', '厨具 · 餐具', 'Utensils & tableware', '硅胶锅铲套装', 'Silicone utensil set', 18, 0.4],
    ['drinkware', '水杯 · 保温杯', 'Drinkware', '不锈钢保温杯', 'Insulated bottle', 26, 0.45],
    ['food_storage', '收纳 · 保鲜', 'Food storage', '玻璃保鲜盒', 'Glass food container', 22, 0.6]
  ],
  beauty: [
    ['skincare', '护肤 · 彩妆', 'Skincare & makeup', '保湿面膜 10 片装', 'Sheet mask 10-pack', 15, 0.3],
    ['beauty_tools', '美妆工具', 'Beauty tools', '化妆刷套装', 'Makeup brush set', 22, 0.2],
    ['beauty_devices', '美容仪器', 'Beauty devices', '电动洁面仪', 'Facial cleansing brush', 48, 0.25]
  ],
  toys: [
    ['toys_games', '玩具 · 益智', 'Toys & games', '积木玩具', 'Building blocks', 30, 0.6],
    ['plush', '毛绒玩具', 'Plush toys', '毛绒玩具', 'Plush toy', 20, 0.35],
    ['baby_care', '母婴用品', 'Baby care', '婴儿围兜 3 件装', 'Baby bibs 3-pack', 14, 0.15]
  ],
  home: [
    ['home_textiles', '家纺 · 布艺', 'Home textiles', '棉麻抱枕套', 'Cushion cover', 12, 0.2],
    ['decor', '装饰摆件', 'Decor', '香薰蜡烛', 'Scented candle', 18, 0.4],
    ['storage', '收纳整理', 'Storage & organisers', '折叠收纳盒', 'Foldable storage box', 16, 0.5]
  ],
  other: [['other_niche', '其他品类', 'Something else', '手机壳', 'Phone case', 6, 0.05]]
};
export const NICHE_LIST = Object.values(NICHES).flat();
export const nicheInfo = (id) => NICHE_LIST.find((n) => n[0] === id);
export const catLabel = (id, lang) => (CATS.find((c) => c[0] === id) || [])[lang === 'zh' ? 1 : 2];
export const nicheLabel = (id, lang) => (nicheInfo(id) || [])[lang === 'zh' ? 1 : 2];
export const COST_BANDS = { lt20: 12, '20_60': 38, '60_150': 90, gt150: 220 };

const PLATFORMS = [
  ['amazon', 'Amazon', 'Amazon'],
  ['kaufland', 'Kaufland', 'Kaufland'],
  ['ebay', 'eBay', 'eBay'],
  ['otto', 'OTTO', 'OTTO'],
  ['bol', 'bol.com', 'bol.com'],
  ['allegro', 'Allegro', 'Allegro'],
  ['cdiscount', 'Cdiscount', 'Cdiscount'],
  ['walmart', 'Walmart', 'Walmart'],
  ['etsy', 'Etsy', 'Etsy'],
  ['tiktok', 'TikTok Shop', 'TikTok Shop'],
  ['temu', 'Temu', 'Temu'],
  ['shein', 'SHEIN', 'SHEIN'],
  ['own_site', '独立站', 'Own store'],
  ['other', '其他', 'Other']
];
const PLATFORM_ALIAS = { amazon_de: 'amazon' };
export const platformLabel = (id, lang) => (PLATFORMS.find((p) => p[0] === (PLATFORM_ALIAS[id] || id)) || [])[lang === 'zh' ? 1 : 2];

// Which platforms exist in a market, and what each charges (sourced; see data/platforms.json).
const platformCache = {};
export const cachedPlatforms = (market, category) => platformCache[`${market}/${category || ''}`] || null;
export async function platformsFor(market, category) {
  const key = `${market}/${category || ''}`;
  if (!platformCache[key]) {
    try {
      const res = await fetch(`/api/platforms?market=${market}${category ? `&category=${category}` : ''}`);
      const list = res.ok ? (await res.json()).platforms : null;
      if (!Array.isArray(list)) throw new Error('no platform list'); // e.g. an API server that predates this endpoint
      platformCache[key] = list;
    } catch {
      // Not cached, so the next visit retries. The list is every platform with no fees, flagged as failed.
      return Object.assign(PLATFORMS.map(([id]) => ({ id, fee: null })), { failed: true });
    }
  }
  return platformCache[key];
}
const FLAG_SHORT = {
  gpsr_eu: ['欧盟责任人（GPSR）', 'EU responsible person'],
  textile_label_eu: ['纤维成分标签', 'Fibre label'],
  un3481: ['锂电池运输', 'Battery shipping'],
  food_contact_eu: ['食品接触材料', 'Food-contact materials'],
  ce_eu: ['CE 标志', 'CE marking'],
  weee_battery_eu: ['WEEE / 电池注册', 'WEEE & battery registration'],
  packaging_epr_eu: ['包装登记（PPWR）', 'Packaging registration (PPWR)'],
  cosmetic_eu: ['化妆品责任人与 CPNP 备案', 'Cosmetics: responsible person & CPNP'],
  toy_eu: ['玩具安全合规', 'Toy safety'],
  fcc_us: ['FCC 认证', 'FCC'],
  us_china_tariffs: ['对华加征关税', 'China-origin tariffs']
};

const T = {
  zh: {
    skip: '跳过，直接进入',
    back: '返回',
    next: '继续',
    finish: '进入工作台',
    save: '保存并返回',
    editTitle: '修改你的设置',
    yourProfile: '你的卖家档案',
    empty: '回答问题后，这里会逐步变成你的档案',
    step: (i, n) => `第 ${i} / ${n} 步`,
    q: {
      category: ['你主要卖什么？', '选最接近的一类，后面会细化'],
      niche: ['具体是哪一类？', '不同品类需要的合规检查不一样，我们会自动带上'],
      market: ['主要卖到哪里？', '选了平台，我们就用它的公开佣金作起点；不知道自己的费率也没关系，之后随时可改'],
      parcel: ['你的包裹通常是怎样的？', '欧盟 €3 关税按「商品种类」收，不是按件数'],
      cost: ['单件成本大概多少？', '用来判断 €3 关税占售价多大比例，以及会不会超过 €150'],
      worries: ['你最担心什么？', '可多选。我们会把这些放在结果最前面'],
      numbers: ['最后：目标毛利和你的真实数字', '数字越真实，报价越准；不确定的可以留空']
    },
    parcel: { single: ['单件发货', '一个包裹一件商品'], multipack: ['多件同款', '同款商品一包多件'], mixed: ['搭配 / 赠品', '一个包裹里有不同种类的商品'] },
    cost: { lt20: ['¥20 以下', '低价小件'], '20_60': ['¥20 – 60', '中低价'], '60_150': ['¥60 – 150', '中高价'], gt150: ['¥150 以上', '高价或大件'] },
    market: { EU: ['欧盟 27 国', '含 IOSS，€150 以下统一关税，增值税按国家'], US: ['美国', '关税按具体 HS 编码计算'] },
    platformLabel: '平台（按你选的国家显示）',
    feeKnown: (name, typ, lo, hi, fixed, cur) => `${name}：佣金约 ${typ}${lo !== hi ? `（区间 ${lo}–${hi}）` : ''}${fixed ? `，另加每单固定 ${cur}${fixed}` : ''}。数据来自第三方指南、尚未对照平台官网，请以卖家后台为准；不知道也没关系，我们先用这个数。`,
    feeUnknown: (name) => `${name}：没有找到可靠的公开费率，先用 15% 占位并在结果里标注。请填入卖家后台的佣金。`,
    feeFail: '没能加载这个国家的平台和佣金数据（服务器可能没有更新，请重启后端后刷新）。下面列出了所有平台，佣金先按 15% 占位，请自己填写。',
    feeOwn: '独立站没有平台佣金；3% 只是支付通道费的占位，请按你的支付服务商填写。',
    worries: { duty: '关税', fx: '汇率波动', returns: '退货', freight: '运费', fee: '平台佣金', compliance: '合规 / 被下架' },
    margin: '目标毛利',
    marginOther: '其他',
    own: '我有自己的数字（选填）',
    ownHint: '填了之后每次报价都用你的数字，不再用默认值。',
    fee: (p) => `${p ? p + ' ' : ''}平台佣金（%）`,
    freight: '头程运费（元/kg）',
    returns: '退货率（%）',
    euCountry: '目的国',
    fx: (m) => (m === 'US' ? '汇率（元/美元）' : '汇率（元/欧元）'),
    revealEyebrow: '为你准备好了',
    revealTitle: (s) => `一个典型的「${s}」`,
    mineTitle: '试算你的产品',
    mineHint: (s) => `已按「${s}」预填。改成你自己的产品、成本和重量，下面的价格会跟着变。`,
    fName: '产品', fCost: '单件成本 ¥', fKg: '重量 kg',
    usLow: '美国价格是参考底价：这类产品的基础关税未载入，只计入了 12.5% 对华附加税。',
    revealSub: (c, w, m) => `成本 ¥${c} · 重 ${w} kg · 目标毛利 ${m}%`,
    price: '建议售价',
    profit: '每件利润',
    loading: '正在按你的情况计算…',
    insights: '对你最重要的三件事',
    dutyShare: (s, save) => `€3 关税占你这类产品售价的 ${s}。做成 2 件装，每件可便宜约 ${save}。`,
    dutySmall: (s) => `€3 关税只占售价的 ${s}，对你影响不大，重点看汇率和退货。`,
    mixedTip: (save) => `混合包裹每多一种商品多 €3；作为零售套装申报可能只按 1 类计税（约便宜 ${save}），需报关行确认。`,
    above150: '这类产品的售价很可能超过 €150：€3 统一关税不适用，要按具体 HS 编码计算，工作台会提示你。',
    usNote: '美国关税按具体 HS 编码计算：到美国定价时，我会先帮你确认编码。',
    checks: (n) => `上架前会自动检查 ${n} 项要求：`,
    checksNone: '这一类按你提供的信息没有额外的合规事项。',
    watch: '你最关心：',
    watchTail: '，工作台会把它们放在最前面。',
    calcFail: '预览暂时算不出来，但你的设置已经保存，进入后直接报价即可。',
    chipNone: ''
  },
  en: {
    skip: 'Skip, take me in',
    back: 'Back',
    next: 'Continue',
    finish: 'Open my workspace',
    save: 'Save and return',
    editTitle: 'Edit your setup',
    yourProfile: 'Your seller profile',
    empty: 'This fills in as you answer',
    step: (i, n) => `Step ${i} of ${n}`,
    q: {
      category: ['What do you mainly sell?', 'Pick the closest one; we narrow it down next'],
      niche: ['Which kind exactly?', 'Each niche has different compliance checks; we add the right ones automatically'],
      market: ['Where do you mainly sell?', 'Pick a platform and we start from its published commission; if you don’t know your own rate, change it any time'],
      parcel: ['What does a typical parcel look like?', 'The EU’s €3 duty is per kind of item, not per unit'],
      cost: ['Roughly what does one unit cost you?', 'Tells us how big the €3 duty is next to your price, and whether you may pass €150'],
      worries: ['What worries you most?', 'Pick any. We put these first in your results'],
      numbers: ['Last: your target margin and real numbers', 'The more real the numbers, the better the price; leave blank if unsure']
    },
    parcel: { single: ['One item', 'One product per parcel'], multipack: ['Multipacks', 'Several of the same item'], mixed: ['Sets & gifts', 'Different kinds of item in one parcel'] },
    cost: { lt20: ['Under ¥20', 'Low-price small items'], '20_60': ['¥20 – 60', 'Mid-low'], '60_150': ['¥60 – 150', 'Mid-high'], gt150: ['Over ¥150', 'High-price or bulky'] },
    market: { EU: ['EU · 27 countries', 'IOSS, flat duty below €150, VAT per country'], US: ['United States', 'Duty depends on the exact HS code'] },
    platformLabel: 'Platform (shown for your country)',
    feeKnown: (name, typ, lo, hi, fixed, cur) => `${name}: commission about ${typ}${lo !== hi ? ` (range ${lo}–${hi})` : ''}${fixed ? `, plus ${cur}${fixed} fixed per order` : ''}. From third-party guides, not yet checked against the platform's own page: confirm in your seller panel. Don't know yours? We start from this figure.`,
    feeUnknown: (name) => `${name}: no reliable public rate found, so a 15% placeholder is used and flagged. Enter the commission from your seller panel.`,
    feeFail: 'Could not load the platforms and fees for this country (the server may be out of date: restart the backend and refresh). All platforms are listed, with a 15% placeholder fee: enter your own.',
    feeOwn: 'An own store has no marketplace commission; 3% is only a placeholder for payment-processor fees, so enter your processor’s rate.',
    worries: { duty: 'Duty', fx: 'FX swings', returns: 'Returns', freight: 'Freight', fee: 'Platform fee', compliance: 'Compliance / delisting' },
    margin: 'Target margin',
    marginOther: 'Other',
    own: 'I have my own numbers (optional)',
    ownHint: 'Once set, every price uses your numbers instead of the defaults.',
    fee: (p) => `${p ? p + ' ' : ''}platform fee (%)`,
    freight: 'Freight (¥/kg)',
    returns: 'Return rate (%)',
    euCountry: 'Destination country',
    fx: (m) => (m === 'US' ? 'FX (CNY per USD)' : 'FX (CNY per EUR)'),
    revealEyebrow: 'Ready for you',
    revealTitle: (s) => `A typical “${s}”`,
    mineTitle: 'Price your product',
    mineHint: (s) => `Pre-filled with a typical “${s}”. Change it to your own product, cost and weight and the price below follows.`,
    fName: 'Product', fCost: 'Unit cost ¥', fKg: 'Weight kg',
    usLow: 'The US price is a floor: the base duty for this kind of product is not loaded, only the 12.5% China surcharge is included.',
    revealSub: (c, w, m) => `cost ¥${c} · ${w} kg · ${m}% target margin`,
    price: 'Recommended price',
    profit: 'Profit per unit',
    loading: 'Pricing it for your setup…',
    insights: 'The three things that matter most for you',
    dutyShare: (s, save) => `The €3 duty is ${s} of your typical price. As a 2-pack, each unit gets about ${save} cheaper.`,
    dutySmall: (s) => `The €3 duty is only ${s} of the price, so it matters little: watch FX and returns instead.`,
    mixedTip: (save) => `Each extra kind of item in a parcel adds €3; declared as a retail set it may count as one kind (about ${save} less): confirm with a broker.`,
    above150: 'Products like this will likely price above €150: the flat €3 duty no longer applies and the exact HS code decides. The workspace will flag it.',
    usNote: 'US duty depends on the exact HS code: when you price for the US, I’ll confirm the code with you first.',
    checks: (n) => `${n} requirement${n === 1 ? '' : 's'} will be checked automatically before you list:`,
    checksNone: 'No extra compliance items for this niche from what you’ve told me.',
    watch: 'You care most about: ',
    watchTail: '. The workspace puts them first.',
    calcFail: 'The preview can’t be computed right now, but your setup is saved: just ask for a price.',
    chipNone: ''
  }
};

const STEPS = ['category', 'niche', 'market', 'parcel', 'cost', 'worries', 'numbers', 'reveal'];
const MARGINS = [0.15, 0.2, 0.25, 0.3, 0.35];

export function createOnboarding(h) {
  let root = null;
  let a = {};
  let step = 0;
  let mode = 'first'; // 'first' | 'edit'
  let revealSeq = 0;

  const L = () => T[h.getLang()];
  const lang = () => h.getLang();

  // ------------------------------------------------------------ shell
  function mount() {
    root = document.createElement('div');
    root.className = 'onb';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.innerHTML = `
      <aside class="onb__side">
        <div class="onb__brand"><svg width="26" height="26" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="16" fill="currentColor"/><path d="M22 18 V44 H44" fill="none" stroke="var(--bg)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg><span>到岸 <em>Landed</em></span></div>
        <svg class="onb__route" viewBox="0 0 320 130" aria-hidden="true">
          <path class="onb__arc" d="M40 98 C110 8 210 8 280 98"/>
          <circle cx="40" cy="98" r="7" class="onb__pt"/><circle cx="280" cy="98" r="7" class="onb__pt onb__pt--end"/>
          <text x="40" y="120" text-anchor="middle" class="onb__cap">CN</text><text id="onb-dest" x="280" y="120" text-anchor="middle" class="onb__cap">DE</text>
          <g class="onb__box"><rect x="-10" y="-8" width="20" height="16" rx="3"/><path d="M-10 -2h20M0 -8v6"/><animateMotion dur="6s" repeatCount="indefinite" path="M40 98 C110 8 210 8 280 98" rotate="0"/></g>
        </svg>
        <p class="onb__side-title" id="onb-side-title"></p>
        <div class="onb__live" id="onb-live"></div>
      </aside>
      <section class="onb__main">
        <header class="onb__top">
          <button type="button" class="onb__back" id="onb-back"></button>
          <div class="onb__bar" id="onb-bar" aria-hidden="true"></div>
          <button type="button" class="onb__lang" id="onb-lang" aria-label="Switch language"></button>
          <button type="button" class="onb__skip" id="onb-skip"></button>
        </header>
        <div class="onb__stage" id="onb-stage" tabindex="-1"></div>
        <footer class="onb__foot"><span class="onb__count" id="onb-count"></span><button type="button" class="btn btn--primary onb__next" id="onb-next"></button></footer>
      </section>`;
    document.body.appendChild(root);
    root.querySelector('#onb-back').addEventListener('click', () => go(step - 1));
    root.querySelector('#onb-next').addEventListener('click', onNext);
    root.querySelector('#onb-lang').addEventListener('click', () => h.toggleLang());
    root.querySelector('#onb-skip').addEventListener('click', () => {
      close();
      if (mode === 'first') h.onSkip();
    });
    root.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && mode === 'edit') close();
    });
  }

  function open({ edit = false } = {}) {
    mode = edit ? 'edit' : 'first';
    a = JSON.parse(JSON.stringify(h.getProfile() || {}));
    step = 0;
    if (!root) mount();
    root.hidden = false;
    document.body.classList.add('is-onboarding');
    render(true);
  }
  function close() {
    if (!root) return;
    root.hidden = true;
    document.body.classList.remove('is-onboarding');
    revealSeq++;
  }

  // ------------------------------------------------------------ render
  const stepId = () => STEPS[step];
  const isRequired = () => ({ category: !!a.category, niche: !!a.niche }[stepId()] ?? true);

  function go(i) {
    if (i < 0 || i >= STEPS.length) return;
    const dir = i > step ? 1 : -1;
    step = i;
    render(false, dir);
  }

  async function onNext() {
    if (stepId() === 'reveal') {
      try {
        if (a.my && a.my.edited && a.my.cost > 0 && a.my.kg > 0) localStorage.setItem('landed.myproduct.v1', JSON.stringify({ niche: a.niche, name: a.my.name, cost: a.my.cost, kg: a.my.kg }));
        else localStorage.removeItem('landed.myproduct.v1');
        localStorage.removeItem('landed.last.v1'); // a new onboarding starts from the new product
      } catch { /* storage blocked */ }
      close();
      await h.onDone(clean({ ...a, market: a.market || 'DE' }));
      return;
    }
    go(step + 1);
  }

  function clean(src) {
    const out = { ...src };
    Object.keys(out).forEach((k) => (out[k] === undefined || out[k] === null || out[k] === '' || (Array.isArray(out[k]) && !out[k].length)) && delete out[k]);
    return out;
  }

  function render(first, dir = 1) {
    const l = L();
    const id = stepId();
    const n = STEPS.length;
    root.querySelector('#onb-back').textContent = '← ' + l.back;
    root.querySelector('#onb-back').style.visibility = step === 0 ? 'hidden' : 'visible';
    root.querySelector('#onb-lang').textContent = lang() === 'zh' ? 'EN' : '中文';
    root.querySelector('#onb-skip').textContent = mode === 'edit' ? '×' : l.skip;
    root.querySelector('#onb-skip').setAttribute('aria-label', mode === 'edit' ? '关闭' : l.skip);
    root.querySelector('#onb-bar').innerHTML = STEPS.map((_, i) => `<i class="${i < step ? 'is-done' : i === step ? 'is-on' : ''}"></i>`).join('');
    root.querySelector('#onb-count').textContent = l.step(step + 1, n);
    root.querySelector('#onb-next').textContent = id === 'reveal' ? (mode === 'edit' ? l.save : l.finish) : l.next;
    if (id === 'market' && !a.market) a.market = 'DE'; // shown pre-selected on its own step
    const stage = root.querySelector('#onb-stage');
    stage.className = `onb__stage ${first ? '' : dir > 0 ? 'is-fwd' : 'is-back'}`;
    void stage.offsetWidth; // restart the CSS animation
    stage.innerHTML = body(id, l);
    bindStage(id);
    paintSide();
    paintNext();
    if (id === 'reveal') renderReveal();
    stage.focus({ preventScroll: true });
  }

  function paintNext() {
    const b = root.querySelector('#onb-next');
    b.disabled = !isRequired();
  }

  const opt = (v, ic, title, sub, on, attrs = '') =>
    `<button type="button" class="opt ${on ? 'is-on' : ''}" data-v="${esc(v)}" aria-pressed="${on}" ${attrs}>${ic ? `<span class="opt__ic">${ic}</span>` : ''}<span class="opt__t">${esc(title)}</span>${sub ? `<span class="opt__s">${esc(sub)}</span>` : ''}</button>`;

  function body(id, l) {
    const [qt, qs] = l.q[id] || ['', ''];
    const head = `<h1 class="onb__q">${esc(qt)}</h1><p class="onb__hint">${esc(qs)}</p>`;
    if (id === 'category') {
      return head + `<div class="grid grid--cat">${CATS.map(([v, zh, en]) => opt(v, ICONS[v], lang() === 'zh' ? zh : en, '', a.category === v)).join('')}</div>`;
    }
    if (id === 'niche') {
      const list = NICHES[a.category] || NICHES.other;
      return head + `<div class="grid grid--niche">${list.map((n) => opt(n[0], '', lang() === 'zh' ? n[1] : n[2], lang() === 'zh' ? n[3] : n[4], a.niche === n[0])).join('')}</div>`;
    }
    if (id === 'market') {
      return head + `<div class="grid grid--market">${['EU', 'US'].map((m) => opt(m, `<b class="opt__big">${m}</b>`, l.market[m][0], l.market[m][1], m === 'EU' ? isEU(a.market) : a.market === m)).join('')}</div>
        <label class="onb__country" ${isEU(a.market) ? '' : 'hidden'}><span>${esc(l.euCountry)}</span><select id="onb-eu">${EU.map((c) => `<option value="${c[0]}" ${c[0] === a.market ? 'selected' : ''}>${esc(lang() === 'zh' ? c[2] : c[1])}</option>`).join('')}</select></label>
        <p class="onb__sub">${esc(l.platformLabel)}</p><div class="pills" data-multi="platform" id="onb-plats"></div><p class="onb__hint onb__feehint" id="onb-feehint" aria-live="polite"></p>`;
    }
    if (id === 'parcel') {
      const art = {
        single: '<svg viewBox="0 0 64 40"><rect x="22" y="8" width="20" height="24" rx="3"/><path d="M22 16h20"/></svg>',
        multipack: '<svg viewBox="0 0 64 40"><rect x="8" y="12" width="14" height="18" rx="2.5"/><rect x="25" y="12" width="14" height="18" rx="2.5"/><rect x="42" y="12" width="14" height="18" rx="2.5"/></svg>',
        mixed: '<svg viewBox="0 0 64 40"><rect x="8" y="12" width="16" height="18" rx="2.5"/><circle cx="36" cy="21" r="9"/><path d="M48 30l6-18 6 18z"/></svg>'
      };
      return head + `<div class="grid grid--parcel">${['single', 'multipack', 'mixed'].map((v) => opt(v, `<span class="opt__art">${art[v]}</span>`, l.parcel[v][0], l.parcel[v][1], a.parcel === v)).join('')}</div>`;
    }
    if (id === 'cost') {
      const bars = { lt20: [6, 10], '20_60': [10, 18], '60_150': [16, 26], gt150: [22, 34] };
      return head + `<div class="grid grid--cost">${Object.keys(COST_BANDS).map((v) => opt(v, `<span class="opt__art"><svg viewBox="0 0 64 40"><rect x="22" y="${40 - bars[v][1]}" width="20" height="${bars[v][1]}" rx="3"/><rect x="8" y="${40 - bars[v][0]}" width="10" height="${bars[v][0]}" rx="2" class="soft"/></svg></span>`, l.cost[v][0], l.cost[v][1], a.cost_band === v)).join('')}</div>`;
    }
    if (id === 'worries') {
      return head + `<div class="grid grid--worry">${Object.keys(l.worries).map((v) => opt(v, ICONS[v], l.worries[v], '', (a.worries || []).includes(v))).join('')}</div>`;
    }
    if (id === 'numbers') {
      const plat = a.platform ? platformLabel(a.platform, lang()) : '';
      const pv = (v) => (v == null ? '' : +(v * 100).toFixed(2));
      const known = MARGINS.includes(a.target_margin);
      return head + `<p class="onb__sub">${esc(l.margin)}</p>
        <div class="pills pills--margin" data-multi="margin">${MARGINS.map((m) => `<button type="button" class="pill ${a.target_margin === m ? 'is-on' : ''}" data-v="${m}" aria-pressed="${a.target_margin === m}">${Math.round(m * 100)}%</button>`).join('')}
          <label class="pill pill--input ${a.target_margin && !known ? 'is-on' : ''}"><span>${esc(l.marginOther)}</span><input id="onb-margin" type="number" inputmode="decimal" min="1" max="70" step="0.5" value="${a.target_margin && !known ? +(a.target_margin * 100).toFixed(1) : ''}" placeholder="%" /></label></div>
        <details class="onb__own" ${['fee_rate', 'freight_cny_per_kg', 'return_rate', 'fx'].some((k) => a[k] != null) ? 'open' : ''}><summary>${esc(l.own)}</summary><p class="onb__hint">${esc(l.ownHint)}</p>
          <div class="fields">
            <label class="field"><span>${esc(l.fee(plat))}</span><span class="field__box"><input data-n="fee_rate" data-scale="100" type="number" inputmode="decimal" min="0" max="50" step="0.5" value="${pv(a.fee_rate)}" placeholder="15" /></span></label>
            <label class="field"><span>${esc(l.freight)}</span><span class="field__box"><input data-n="freight_cny_per_kg" type="number" inputmode="decimal" min="1" max="500" step="1" value="${a.freight_cny_per_kg ?? ''}" placeholder="45" /></span></label>
            <label class="field"><span>${esc(l.returns)}</span><span class="field__box"><input data-n="return_rate" data-scale="100" type="number" inputmode="decimal" min="0" max="50" step="0.5" value="${pv(a.return_rate)}" placeholder="8" /></span></label>
            <label class="field"><span>${esc(l.fx(a.market))}</span><span class="field__box"><input data-n="fx" type="number" inputmode="decimal" min="0.1" max="100" step="0.01" value="${a.fx ?? ''}" placeholder="7.5" /></span></label>
          </div></details>`;
    }
    return `<div class="reveal" id="onb-reveal"><p class="reveal__eyebrow">${esc(l.revealEyebrow)}</p><div class="reveal__load">${esc(l.loading)}</div></div>`;
  }

  // Platform pills for the chosen market, each with its sourced fee shown on selection.
  async function paintPlatforms() {
    const box = root.querySelector('#onb-plats');
    if (!box) return;
    const market = a.market || 'DE';
    const list = await platformsFor(market, a.category);
    if (!root || root.hidden || (a.market || 'DE') !== market || !root.querySelector('#onb-plats')) return;
    const alias = PLATFORM_ALIAS[a.platform] || a.platform;
    if (alias && alias !== a.platform) a.platform = alias;
    if (a.platform && !list.some((p) => p.id === a.platform)) {
      delete a.platform;
      paintSide();
    }
    box.innerHTML = list
      .map((p) => `<button type="button" class="pill ${a.platform === p.id ? 'is-on' : ''}" data-v="${p.id}" aria-pressed="${a.platform === p.id}">${esc(platformLabel(p.id, lang()))}</button>`)
      .join('');
    const hint = () => {
      const el = root.querySelector('#onb-feehint');
      if (!el) return;
      const p = list.find((x) => x.id === a.platform);
      const l = L();
      const pct = (v) => `${+(v * 100).toFixed(1)}%`;
      const cur = market === 'US' ? '$' : '€';
      if (list.failed) el.textContent = l.feeFail;
      else if (!p || p.id === 'other') el.textContent = '';
      else if (p.id === 'own_site') el.textContent = l.feeOwn;
      else if (!p.fee) el.textContent = l.feeUnknown(platformLabel(p.id, lang()));
      else el.textContent = l.feeKnown(platformLabel(p.id, lang()), pct(p.fee.typical), pct(p.fee.low), pct(p.fee.high), p.fee.fixed || '', cur);
    };
    box.querySelectorAll('.pill').forEach((b) =>
      b.addEventListener('click', () => {
        a.platform = a.platform === b.dataset.v ? undefined : b.dataset.v;
        box.querySelectorAll('.pill').forEach((x) => {
          x.classList.toggle('is-on', a.platform === x.dataset.v);
          x.setAttribute('aria-pressed', String(a.platform === x.dataset.v));
        });
        hint();
        paintSide();
      })
    );
    hint();
  }

  function bindStage(id) {
    const stage = root.querySelector('#onb-stage');
    const pick = (key, v, { multi } = {}) => {
      if (multi) {
        const set = new Set(a[key] || []);
        set.has(v) ? set.delete(v) : set.add(v);
        a[key] = [...set];
      } else a[key] = a[key] === v && key === 'platform' ? undefined : v;
    };
    stage.querySelectorAll('.opt').forEach((b) =>
      b.addEventListener('click', () => {
        const v = b.dataset.v;
        if (id === 'category') {
          if (a.category !== v) delete a.niche;
          a.category = v;
        } else if (id === 'niche') a.niche = v;
        else if (id === 'market') a.market = v === 'EU' ? (isEU(a.market) ? a.market : 'DE') : v;
        else if (id === 'parcel') a.parcel = v;
        else if (id === 'cost') a.cost_band = v;
        else if (id === 'worries') pick('worries', v, { multi: true });
        stage.querySelectorAll('.opt').forEach((x) => {
          const on = id === 'worries' ? (a.worries || []).includes(x.dataset.v) : (id === 'category' ? a.category : id === 'niche' ? a.niche : id === 'market' ? (x.dataset.v === 'EU' ? (isEU(a.market) ? 'EU' : '') : a.market) : id === 'parcel' ? a.parcel : a.cost_band) === x.dataset.v;
          x.classList.toggle('is-on', on);
          x.setAttribute('aria-pressed', String(on));
        });
        stage.querySelector('.onb__country')?.toggleAttribute('hidden', !isEU(a.market));
        if (id === 'market') paintPlatforms();
        paintSide();
        paintNext();
        // single-choice steps move on by themselves after a beat
        if (['category', 'niche', 'parcel', 'cost'].includes(id) && !matchMedia('(prefers-reduced-motion: reduce)').matches) setTimeout(() => stepId() === id && go(step + 1), 260);
        else if (['category', 'niche', 'parcel', 'cost'].includes(id)) go(step + 1);
      })
    );
    stage.querySelector('#onb-eu')?.addEventListener('change', (e) => {
      a.market = e.target.value;
      paintSide();
      paintPlatforms();
    });
    if (id === 'market') paintPlatforms();
    stage.querySelectorAll('[data-multi=margin] button.pill').forEach((b) =>
      b.addEventListener('click', () => {
        a.target_margin = +b.dataset.v;
        const input = stage.querySelector('#onb-margin');
        if (input) input.value = '';
        stage.querySelectorAll('[data-multi=margin] .pill').forEach((x) => x.classList.toggle('is-on', x.dataset?.v && +x.dataset.v === a.target_margin));
        stage.querySelector('.pill--input')?.classList.remove('is-on');
        paintSide();
      })
    );
    stage.querySelector('#onb-margin')?.addEventListener('input', (e) => {
      const v = parseFloat(e.target.value);
      a.target_margin = v >= 1 && v <= 70 ? +(v / 100).toFixed(4) : undefined;
      stage.querySelectorAll('[data-multi=margin] button.pill').forEach((x) => x.classList.remove('is-on'));
      e.target.closest('.pill--input').classList.toggle('is-on', !!a.target_margin);
      paintSide();
    });
    stage.querySelectorAll('input[data-n]').forEach((inp) =>
      inp.addEventListener('input', () => {
        const k = inp.dataset.n;
        const v = parseFloat(inp.value);
        const scale = +(inp.dataset.scale || 1);
        const zeroOK = k === 'fee_rate' || k === 'return_rate';
        a[k] = Number.isFinite(v) && (v > 0 || (zeroOK && v === 0)) ? +(v / scale).toFixed(4) : undefined;
        paintSide();
      })
    );
  }

  // ------------------------------------------------------------ side panel: the profile fills in live
  function chips() {
    const l = L();
    const out = [];
    if (a.category) out.push([ICONS[a.category], a.niche ? nicheLabel(a.niche, lang()) : catLabel(a.category, lang())]);
    if (a.market) out.push(['', isEU(a.market) ? marketName(a.market, lang()) : l.market[a.market][0]]);
    if (a.platform) out.push(['', platformLabel(a.platform, lang())]);
    if (a.parcel) out.push(['', l.parcel[a.parcel][0]]);
    if (a.cost_band) out.push(['', l.cost[a.cost_band][0]]);
    (a.worries || []).forEach((w) => out.push([ICONS[w], l.worries[w]]));
    if (a.target_margin) out.push(['', `${l.margin} ${+(a.target_margin * 100).toFixed(1)}%`]);
    return out;
  }
  function paintSide() {
    const l = L();
    root.querySelector('#onb-dest').textContent = a.market || 'DE';
    root.querySelector('#onb-side-title').textContent = chips().length ? l.yourProfile : l.empty;
    root.querySelector('#onb-live').innerHTML = chips().map(([ic, t]) => `<span class="live__chip">${ic ? `<span class="live__ic">${ic}</span>` : ''}${esc(t)}</span>`).join('');
  }

  // ------------------------------------------------------------ reveal: price a typical product from this niche
  async function renderReveal() {
    const seq = ++revealSeq;
    const l = L();
    const box = root.querySelector('#onb-reveal');
    const info = nicheInfo(a.niche) || NICHES.other[0];
    const typical = lang() === 'zh' ? info[3] : info[4];
    // the seller's own product, pre-filled with the niche's typical one; reset when the niche changes
    if (!a.my || a.my.niche !== a.niche) a.my = { niche: a.niche, name: typical, cost: a.cost_band ? COST_BANDS[a.cost_band] : info[5], kg: info[6], edited: false };
    const sample = a.my.name || typical;
    const cost = a.my.cost;
    const kg = a.my.kg;
    const margin = a.target_margin || 0.25;
    const market = a.market || 'DE';
    const kinds = a.parcel === 'mixed' ? 2 : 1;
    const profile = clean(a);
    const own = {};
    ['fee_rate', 'freight_cny_per_kg', 'return_rate'].forEach((k) => a[k] != null && (own[k] = a[k]));
    if (a.fx != null && isEU(market)) own.fx = a.fx;

    let calc = null;
    let err = null;
    let flags = [];
    const jobs = [
      postJSON('/api/compliance', { market, attributes: { item_categories: kinds }, profile }).then((r) => (flags = (r.flags || []).filter((f) => f.severity !== 'opportunity' && FLAG_SHORT[f.id])), () => {}),
      cost > 0 && kg > 0
        ? postJSON('/api/calc', { market, cogs_cny: cost, weight_kg: kg, target_margin: margin, item_categories: kinds, ...(market === 'US' ? { indicative: true } : {}), ...(own.fee_rate == null && a.platform ? { platform: a.platform } : {}), fee_category: a.category, ...own }).then((r) => (calc = r), (e) => (err = e))
        : Promise.resolve()
    ];
    await Promise.all(jobs);
    if (seq !== revealSeq || !root || root.hidden) return;

    const eur = (v) => `${market === 'US' ? '$' : '€'}${Number(v).toFixed(2)}`;
    const pct = (v) => `${Math.round(v * 100)}%`;
    const insights = [];
    let hero = '';
    if (calc) {
      const wf = calc.waterfall;
      const profit = wf.steps.find((s) => s.key === 'margin');
      hero = `<div class="reveal__hero"><div><span class="reveal__lbl">${esc(l.price)}</span><span class="reveal__price">${eur(wf.price)}</span></div><div><span class="reveal__lbl">${esc(l.profit)}</span><span class="reveal__profit">${eur(profit ? profit.value : 0)}</span></div></div>`;
      const duty = wf.steps.find((s) => s.key === 'duty');
      if (calc.multipack_tip) {
        const m = calc.multipack_tip;
        insights.push(l.dutyShare(pct(m.duty_share_of_price), eur(m.options[0].saving_per_unit)));
      } else if (a.parcel === 'mixed' && calc.bundle_tip) insights.push(l.mixedTip(eur(calc.bundle_tip.price_reduction)));
      else if (duty && isEU(market)) insights.push(l.dutySmall(pct(duty.value / wf.price)));
    } else if (market === 'DE' && err) {
      insights.push(l.above150);
    }
    if (market === 'US' && calc) insights.unshift(l.usLow);
    else if (market === 'US') insights.push(l.usNote);

    const names = flags.map((f) => FLAG_SHORT[f.id][lang() === 'zh' ? 0 : 1]);
    insights.push(names.length ? `${l.checks(names.length)}<span class="reveal__tags">${names.map((n) => `<span class="live__chip">${esc(n)}</span>`).join('')}</span>` : l.checksNone);
    if ((a.worries || []).length) insights.push(l.watch + (a.worries || []).map((w) => l.worries[w]).join(lang() === 'zh' ? '、' : ', ') + l.watchTail);

    // the form is drawn once so typing never loses focus; only the result below it is redrawn
    if (!box.querySelector('.rv-form')) {
      box.innerHTML = `<p class="reveal__eyebrow">${esc(l.revealEyebrow)}</p>
        <h1 class="onb__q">${esc(l.mineTitle)}</h1><p class="onb__hint" id="rv-hint"></p>
        <div class="rv-form">
          <label>${esc(l.fName)}<input id="rv-name" type="text" maxlength="60" autocomplete="off" /></label>
          <label>${esc(l.fCost)}<input id="rv-cost" type="number" inputmode="decimal" min="0.1" step="0.5" /></label>
          <label>${esc(l.fKg)}<input id="rv-kg" type="number" inputmode="decimal" min="0.01" step="0.01" /></label>
        </div>
        <p class="onb__hint" id="rv-sub"></p><div id="rv-out"></div>`;
      box.querySelector('#rv-name').value = a.my.name;
      box.querySelector('#rv-cost').value = a.my.cost;
      box.querySelector('#rv-kg').value = a.my.kg;
      let tmr;
      const edited = () => {
        a.my.name = box.querySelector('#rv-name').value.trim() || typical;
        a.my.cost = parseFloat(box.querySelector('#rv-cost').value) || 0;
        a.my.kg = parseFloat(box.querySelector('#rv-kg').value) || 0;
        a.my.edited = true;
        clearTimeout(tmr);
        tmr = setTimeout(renderReveal, 350);
      };
      box.querySelectorAll('.rv-form input').forEach((i) => i.addEventListener('input', edited));
    }
    box.querySelector('#rv-hint').textContent = l.mineHint(typical);
    box.querySelector('#rv-sub').textContent = l.revealSub(cost, kg, +(margin * 100).toFixed(1));
    box.querySelector('#rv-out').innerHTML = `${hero || (err || market === 'US' ? (err ? `<p class="onb__hint">${esc(l.calcFail)}</p>` : '') : `<p class="onb__hint">${esc(l.calcFail)}</p>`)}
      <p class="onb__sub">${esc(l.insights)}</p><ol class="reveal__list">${insights.slice(0, 3).map((t) => `<li>${t}</li>`).join('')}</ol>`;
  }

  return { open, close, relabel: () => root && !root.hidden && render(true) };
}
