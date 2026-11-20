// Landed: single source of truth for every figure shown on the landing page.
// Rule: every number carries a source, a snapshot date and a status.
//   verified   = read from the primary/official source on SNAPSHOT
//   secondary  = from a reputable secondary source; verify on the primary before shipping
//   assumption = a placeholder the seller replaces with their own figure
// The Python backend (/data) will load the same records from CSV.

export const SNAPSHOT = '2026-11-08';

export const SOURCES = {
  eu3: {
    label: 'EU €3 flat customs duty on low-value parcels (≤ €150), per item tariff category, from 1 Jul 2026 to 1 Jul 2028',
    url: 'https://commission.europa.eu/news-and-media/news/ensuring-fairness-and-safety-eur3-customs-duty-low-value-parcels-2026-06-29_en',
    status: 'verified',
    note: '"Per item, based on tariff classification and not quantity": 5 T-shirts = €3, 3 T-shirts + a watch = €6.'
  },
  deVat: {
    label: 'Germany standard VAT 19% (collected via IOSS for consignments ≤ €150)',
    url: 'https://taxation-customs.ec.europa.eu/taxation/vat/vat-directive/vat-rates_en',
    status: 'verified'
  },
  hs850940: {
    label: 'HS 8509.40 food grinders & mixers: EU conventional duty about 2.2% (unconfirmed; only applies above €150 / outside the flat regime, so not used in the demo price)',
    url: 'https://ec.europa.eu/taxation_customs/dds2/taric/taric_consultation.jsp',
    status: 'secondary',
    note: 'Seen via TARIC-derived aggregator; confirm the 10-digit CN line on TARIC.'
  },
  usDeMinimis: {
    label: 'US duty-free de minimis suspended for all countries from 29 Aug 2025 (EO 14324; CBP implementation notice, 90 FR 42418, 2 Sep 2025)',
    url: 'https://www.govinfo.gov/content/pkg/FR-2025-09-02/pdf/2025-16802.pdf',
    status: 'verified'
  },
  un3481: {
    label: 'Lithium-ion cells packed in equipment: UN 3481, IATA Packing Instruction 967',
    url: 'https://www.iata.org/en/programs/cargo/dgr/lithium-batteries/',
    status: 'verified'
  },
  fx: {
    label: 'CNY per EUR 7.4485 (ECB reference rate, 6 Nov 2026) and a 2.8% volatility over about 60 days (computed from the ECB daily rates since Oct 2024)',
    url: 'https://data-api.ecb.europa.eu/service/data/EXR/D.CNY.EUR.SP00.A',
    status: 'verified'
  },
  fee: {
    label: 'Marketplace referral fee 15% of VAT-inclusive price: a generic placeholder. In the app each platform has its own sourced fee; enter the one from your seller panel',
    url: null,
    status: 'assumption'
  },
  freight: {
    label: 'Express small-parcel freight about ¥45/kg (forwarders publish USD 6-10/kg, roughly ¥40-67): replace with your carrier quote',
    url: 'https://www.tonlexing.com/shipping-cost-from-china-to-germany/',
    status: 'secondary'
  },
  returns: {
    label: 'Return rate Beta(8, 92), mean 8%: about 7% of European e-commerce revenue and 5-10% for electronics; fashion is far higher (20-40%)',
    url: 'https://eightx.co/blog/eu-ecommerce-return-rate-benchmark',
    status: 'secondary'
  }
};

// Demo SKU used on the landing page (prompt #1 of the pitch).
export const DEMO = {
  product: '500 ml portable blender, built-in Li-ion battery, + spare Tritan travel cup',
  market: 'Germany (EU), B2C via IOSS',
  hs: '8509.40',
  cogsCny: 38,
  weightKg: 0.6,
  freightCnyPerKg: 45,
  targetMargin: 0.25,
  vat: 0.19,
  feeRate: 0.15,
  eu3PerCategory: 3,
  fxMean: 7.4485,   // CNY per EUR, ECB reference rate 2026-11-06
  fxSd: 0.028,      // relative sd of ~60-day changes, computed from ECB daily rates
  returnAlpha: 8,
  returnBeta: 92,
  paths: 5000,
  seed: 20261108
};

// Verified research figures for the evidence strip and the references list.
export const EVIDENCE = [
  {
    key: 'atlas',
    figure: '25%',
    claim: 'Exact 10-digit HTS accuracy of GPT-5-Thinking on 200 held-out U.S. CBP CROSS rulings. A fine-tuned 70B model reaches 40%.',
    cite: 'Yuvraj & Devarakonda (2025), ATLAS, arXiv:2509.18400',
    url: 'https://arxiv.org/abs/2509.18400'
  },
  {
    key: 'eu3',
    figure: '€3',
    claim: 'EU flat duty per item tariff category on low-value consignments up to €150, in force since 1 Jul 2026. Low-value parcels now need an HS code.',
    cite: 'European Commission (29 Jun 2026); Council Regulation (EU) 2026/382',
    url: SOURCES.eu3.url
  },
  {
    key: 'us',
    figure: '29·08·25',
    claim: 'The United States suspended duty-free de minimis for all countries.',
    cite: 'Executive Order 14324; 90 FR (2 Sep 2025)',
    url: SOURCES.usDeMinimis.url
  },
  {
    key: 'gacc',
    figure: '¥2.84T',
    claim: 'China cross-border e-commerce imports and exports in 2025, up 4.8% on the year.',
    cite: 'GACC figures presented at the State Council Information Office briefing, 22 Jul 2026 (Guangming Daily text)',
    url: 'https://m.gmw.cn/2026-07/22/content_1304536447.htm'
  },
  {
    key: 'hl',
    figure: '> ⅓',
    claim: 'Share of China’s 2000–05 export growth to the US explained by removing tariff-policy uncertainty, not by lower tariffs.',
    cite: 'Handley & Limão (2017), American Economic Review 107(9)',
    url: 'https://doi.org/10.1257/aer.20141419'
  },
  {
    key: 'mt',
    figure: '+10.9%',
    claim: 'Increase in eBay exports after machine translation lowered the language barrier.',
    cite: 'Brynjolfsson, Hui & Liu (2019), Management Science 65(12)',
    url: 'https://doi.org/10.1287/mnsc.2019.3388'
  },
  {
    key: 'novice',
    figure: '+34%',
    claim: 'Productivity gain from generative AI for novice workers, versus +14% on average. A seller entering a new market is the novice.',
    cite: 'Brynjolfsson, Li & Raymond (2025), Quarterly Journal of Economics 140(2)',
    url: 'https://doi.org/10.1093/qje/qjae044'
  },
  {
    key: 'jagged',
    figure: '−19 pp',
    claim: 'Drop in correctness when consultants used AI on a task outside the model’s frontier. Why our numbers come from code, not the LLM.',
    cite: 'Dell’Acqua et al. (2026), Organization Science 37(2)',
    url: 'https://papers.ssrn.com/abstract=4573321'
  }
];

// Chinese labels for the same records (figures, URLs and statuses are shared above).
export const SOURCES_ZH = {
  eu3: '欧盟低价值包裹（≤ €150）统一关税：每类商品 3 欧元，2026年7月1日 至 2028年7月1日',
  deVat: '德国标准增值税 19%（€150 以下包裹通过 IOSS 代征）',
  hs850940: 'HS 8509.40 食品研磨机、搅拌机：欧盟常规关税约 2.2%（未核实；仅适用于 €150 以上或统一关税之外，演示售价未使用）',
  usDeMinimis: '美国自 2025年8月29日 起对所有国家暂停小额包裹免税（第 14324 号行政令；CBP 实施公告 90 FR 42418）',
  un3481: '设备内装锂离子电池：UN 3481，IATA 包装说明 967',
  fx: '欧元兑人民币 7.4485（欧洲央行参考汇率，2026年11月6日），约 60 天波动率 2.8%（据 2024年10月 以来欧洲央行日度汇率计算）',
  fee: '平台佣金按含税售价的 15%：通用占位值。工作台里每个平台有各自有出处的费率，请填你后台的实际费率',
  freight: '小包快递头程约 ¥45/kg（货代公开报价约 6–10 美元/kg，即 ¥40–67）：请换成你的物流报价',
  returns: '退货率 Beta(8, 92)，均值 8%：欧洲电商退货约占营收 7%，电子产品 5–10%；服装高得多（20–40%）'
};

export const EVIDENCE_ZH = {
  atlas: { figure: '25%', claim: 'GPT-5-Thinking 在 200 条美国 CBP 预裁定上判对完整 10 位 HTS 编码的比例；微调后的 70B 模型为 40%。' },
  eu3: { figure: '€3', claim: '2026年7月1日起，欧盟对 €150 以下的低价值包裹按每类商品征收 3 欧元关税。小包裹从此必须申报 HS 编码。' },
  us: { figure: '2025.8.29', claim: '美国对所有国家暂停小额包裹免税（de minimis）。' },
  gacc: { figure: '2.84万亿', claim: '2025 年中国跨境电商进出口额，同比增长 4.8%。' },
  hl: { figure: '> ⅓', claim: '2000–2005 年中国对美出口增长中，有三分之一以上来自关税政策不确定性的消除，而不是关税下降。' },
  mt: { figure: '+10.9%', claim: '机器翻译降低语言门槛后，eBay 上的出口增长幅度。' },
  novice: { figure: '+34%', claim: '生成式 AI 让新手的效率提升 34%，平均只有 14%。刚进入新市场的卖家，就是那个新手。' },
  jagged: { figure: '−19 pp', claim: '咨询顾问在 AI 能力边界之外的任务上使用 AI，正确率下降 19 个百分点。这就是我们的数字来自代码、而不是大模型的原因。' }
};
