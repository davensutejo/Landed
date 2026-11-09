import '@fontsource-variable/instrument-sans';
import '../styles/tokens.css';
import '../styles/ask.css';
import '../styles/agent.css';
import '../styles/onboarding.css';

import { esc, renderMarkdown } from '../lib/markdown.js';
import { streamChat, postJSON } from '../lib/agentStream.js';
import { histogram, riskCurve, money, pct } from './charts.js';
import { renderHSQuiz, renderAskForm, detectLang } from '../lib/askWidgets.js';
import { createPersonal } from './personal.js';
import { nicheInfo, COST_BANDS, platformLabel, platformsFor, cachedPlatforms } from './onboarding.js';
import { EU, isEU, marketName, euCountryIn } from '../lib/markets.js';

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ copy
const T = {
  zh: {
    snapshot: '税率快照 2026-11-08 · 所有数字由规则引擎计算，并标注来源',
    example: '看示例',
    exampleLong: '看一个示例：便携榨汁杯 + 备用杯',
    exampleNiche: (n) => `看一个你的品类的示例：${n}`,
    langBtn: 'EN',
    tabChat: '对话',
    tabResult: '结果',
    introTitle: '你好，我是到岸。',
    introBody: '告诉我卖什么、卖到哪（欧盟国家或美国）、单件成本、重量和目标毛利。信息齐了我直接给售价，只有会影响价格的问题我才会问。',
    startersLabel: '试试这些：',
    starters: [
      '棉袜 5 双装，一包成本 12 元，重 0.25 kg，卖德国，目标毛利 30%',
      '便携榨汁杯，成本 ¥38，重 0.6 kg，卖德国，目标毛利 25%',
      '手机壳成本 6 元，重 50 克，想卖到德国，怎么定价？'
    ],
    inputLabel: '输入消息',
    placeholder: '产品、成本、重量、卖到哪、目标毛利',
    send: '发送',
    working: (s) => `正在计算… ${s}s`,
    answered: (s) => `${s} 秒内完成`,
    tool: { classify_hs: '识别 HS 编码', landed_cost: '计算到岸售价', compliance_flags: '检查合规要求', ask_seller: '整理需要补充的信息' },
    seeResult: '查看完整结果 →',
    guardrail: (x) => `以下内容在任何数据来源和你的消息里都找不到，请不要直接使用：${x}`,
    unavailable: () => '暂时连不上 AI，请稍后再试。你仍然可以点「看示例」使用计算引擎，所有数字都不经过 AI。',
    busy: 'AI 服务暂时繁忙，请稍后再试。你仍然可以点「看示例」使用计算引擎。',
    rateLimited: '发送太频繁了，请等几分钟再试。右侧面板里的数字仍可直接修改，计算引擎不受影响。',
    emptyTitle: '说出你的产品，拿到能直接用的售价',
    step1T: '告诉我 4 个数',
    step1: '单件成本、重量、市场（欧盟国家或美国）、目标毛利',
    step2T: '得到到岸售价',
    step2: '关税、增值税、运费、平台佣金、退货全部算进去，每个数字都有来源',
    step3T: '看清风险和必做事项',
    step3: '汇率、退货、运费变化会吃掉多少利润；上架前必须完成哪些合规',
    emptyNote: 'AI 只负责理解你的话和写回复；所有数字都由确定性的规则引擎计算。',
    hsTitle: 'HS 编码',
    hsStatus: { ambiguous: '待确认', needs_confirmation: '待确认', resolved: '已匹配', out_of_scope: '不在编码表内' },
    hsNoteDE: '欧盟 €150 以下的订单按每类商品 €3 计关税，与具体编码无关，所以不影响售价；报关单上仍需填写 6 位编码。',
    hsNoteUS: '美国关税按具体编码计，所以美国定价需要确认编码。',
    hsOut: '这个产品不在到岸的 HS 编码表里（目前覆盖搅拌机、榨汁机及配件）。欧盟定价不需要编码；报关编码请查目的国海关税则或咨询报关行。',
    priceLabelDE: '建议售价',
    priceLabelUS: '参考价（美国）',
    priceLabelUSLow: '参考底价',
    priceSubDE: (v) => `含 ${v} 增值税 · 达到目标毛利的售价`,
    priceSubUS: '不含销售税 · 已含 12.5% 对华 301 附加税（CBP 公告），旧清单税率待核实',
    priceSubUSLow: '不含销售税 · 旧 301 清单税率未计入，实际售价应更高',
    profit: '每件利润',
    margin: (m) => `毛利率 ${m}（按不含税收入算）`,
    safer: '稳妥价',
    saferNote: '95% 的模拟情景下不低于目标毛利',
    loss: '亏损概率',
    lossNote: '5,000 次情景模拟',
    marketDE: '德国 · IOSS',
    marketUS: '美国',
    hsChip: (h) => `HS ${h}`,
    hsNone: '未填 HS 编码 · 不影响欧盟定价',
    hsNoneUS: '未填 HS 编码 · 美国基础关税未载入',
    kinds: (n) => `${n} 种商品 / 包裹`,
    demoChip: '仍用占位值',
    yourChip: '已使用你的设置',
    emptyYou: '按你的设置报价：',
    emptyYouTail: '只需告诉我成本和重量。',
    vatChip: (v) => `增值税按 ${v} 标准税率（部分商品如食品、图书适用低税率）`,
    multiT: (s) => `多件装可以摊薄关税：€3 关税占这个售价的 ${s}`,
    multiRow: (n, pack, per, save) => `<tr><td>${n} 件装</td><td>${pack}</td><td>每件 ${per}</td><td>每件便宜 ${save}</td></tr>`,
    multiNote: '欧盟按商品种类收 €3，不按件数。只有完全相同的商品才算 1 类；改成多件装会改变你的商品形式，请先确认需求和平台规则。',
    bundleT: (save) => `作为零售套装申报，可能只按 1 类计税（每件约便宜 ${save}）`,
    bundleNote: '套装归类（WCO GRI 3(b)）需要判断，发货前请向报关行或 BTI 裁定确认。',
    badNumber: (lo, hi) => (hi ? `请输入 ${lo} 到 ${hi} 之间的数字，价格未更新。` : `请输入不小于 ${lo} 的数字，价格未更新。`),
    usRange: (a, b) => `如果这条税号还要加旧 301 清单税：7.5% 时约 ${a}，25% 时约 ${b}。具体是否适用，请让报关行确认。`,
    usAssumed: (c) => `HS 编码 ${c} 是按产品描述假设的、卖家未确认，请让报关行核对；不同税号的关税可能不同。`,
    usBaseUnknown: '这个产品的基础关税尚未载入，目前只计入 12.5% 对华 301 附加税，实际税会更高。',
    warnUS: '美国价格是最低价：这条税号对应的旧 301 清单税（7.5% 或 25%）尚未载入。已计入 12.5% 对华 301 附加税。',
    warnUSKnown: '美国价格已含 12.5% 对华 301 附加税（CBP 公告）和 25% 清单税；该税号是否在清单上、两者是否叠加，来源为二手资料，请与报关行确认。',
    warnAbove: '售价超过 €150，€3 统一关税不适用，已改按该编码的常规关税计算。',
    breakdownTitle: '售价构成',
    breakdownHint: (p) => `售价 ${p} 都去了哪里（百分比为占售价比例）`,
    wf: { cogs: '货值', freight: '头程运费', duty: '关税', returns: '退货损耗', fee: '平台佣金', vat: '增值税', margin: '利润' },
    riskTitle: '什么会吃掉你的利润',
    riskHint: (p) => `按 ${p} 售价计算`,
    stress: {
      'CNY +5%': '人民币升值 5%',
      'Return rate 15%': '退货率升到 15%',
      'Freight +30%': '旺季运费上涨 30%',
      'Add a different kind': '包裹里多放一种不同商品（如赠品）：多交 €3 关税',
      'Duty +10': '关税提高 10 个百分点',
      'Platform fee at the high end': '平台佣金升到区间高位'
    },
    riskMore: '查看利润分布和不同售价的达标概率',
    histCaption: '目标售价下的利润率分布（5,000 次模拟）',
    curveCaption: '不同售价下，达到目标毛利（绿）和亏损（红）的概率',
    chart: { target: '目标', p5: 'P5', conf: '95% 达标线', hit: '■ 达到目标毛利', loss: '■ 亏损', price: '目标售价' },
    curveReadout: (p, hit, p5, loss) => `售价 <b>${p}</b>：达到目标毛利的概率 <b>${hit}</b> · 最差 5% 情景毛利 ${p5} · 亏损概率 ${loss}`,
    flagsTitle: '上架前必须完成',
    flagsHint: '按目的国法规，点「来源」查看原文',
    flagsNone: '按你提供的信息，没有额外的合规事项。',
    sev: { blocker: '必须', warning: '注意', opportunity: '机会' },
    source: '来源',
    adjustTitle: '调整数字',
    adjustHint: '改任何一项，售价立刻重算（不经过 AI）',
    yours: '你的数据',
    demo: '默认假设（可改）',
    demoTag: '换成你的真实报价',
    f: { cogs_cny: '单件成本', weight_kg: '重量', target_margin: '目标毛利', item_categories: '商品种类 / 包裹', fee_rate: '平台佣金', freight_cny_per_kg: '头程运费', return_rate: '退货率', fx: '汇率' },
    fxUnit: (c) => `元 / ${c}`,
    market: '市场',
    eu: '欧盟',
    euCountry: '目的国',
    soldOn: '销售平台',
    platformNone: '未选择（先用 15% 占位）',
    us: '美国',
    usNeedsHS: '美国定价需要 HS 编码',
    compareUS: (p) => `同样的商品卖美国：约 ${p}（含对华 301 附加税，税率待核实）。`,
    compareDE: (p, n) => `同样的商品卖${n}：建议售价 ${p}。`,
    compareNoUS: '美国关税按具体编码计算；这个产品没有已确认的编码，所以暂不计算美国价格。',
    sourcesTitle: '数据来源与记录',
    sourcesHint: '每个数字的出处、状态和本次的计算过程',
    th: ['项目', '数值', '状态', '来源'],
    status: { verified: '已核实', secondary: '待核实', assumption: '占位值', seller_input: '你的数据', unknown: '未加载' },
    prov: { 'FX CNY per EUR': '汇率（元/欧元）', 'FX CNY per USD': '汇率（元/美元）', 'FX volatility': '汇率波动', 'Platform fee': '平台佣金', 'Platform fixed fee': '平台每单固定费', 'Freight CNY/kg': '头程运费（元/kg）', 'Return-rate prior': '退货率', VAT: '增值税', 'EU flat duty per tariff category': '欧盟统一关税（每类商品）', 'EU conventional duty': '欧盟常规关税（€150 以上）', 'US HTSUS duty': '美国关税', 'US de minimis': '美国小额免税' },
    timelineTitle: '本次计算过程',
    export: '导出记录 (JSON)',
    print: '打印报告',
    disclaimer: '定价决策辅助工具，不是持牌报关服务。标为「占位值」的数据请换成你自己的数字；「待核实」是第三方资料，请对照官方来源。',
    watchTag: '你关心的',
    abstainT: '这个价格我不能给',
    abstainAbove: (p, code) => `算出来的售价约 €${p}，超过 €150，不适用 €3 统一关税；要按具体编码的常规关税计算，而${code ? ` ${code} 的` : '这个产品的编码和'}税率不在已核实的数据里。请先确认 HS 编码并咨询报关行。`,
    abstainUSnoHS: '美国关税按具体编码计算，需要先确认 HS 编码。',
    hsTitles: {
      '8509.40': '内置电机的家用电动器具：食品研磨机、搅拌机、果汁榨汁器',
      '8516.79': '其他家用电热器具（如带加热的料理机）',
      '8509.90': '85.09 品目家用电动器具的零件（如需外接底座的杯组）',
      '8438.80': '工业 / 商用食品加工机器',
      '3924.10': '塑料餐具及厨房用具（如单独销售的杯子）'
    },
    tl: { user: '你的消息', tool: '调用', answer: '回复', example: '载入示例', lab: '重新计算', hs: '你的回答' }
  },
  en: {
    snapshot: 'Rates snapshot 2026-11-08 · every number comes from a rules engine, with its source',
    example: 'Example',
    exampleLong: 'See an example: portable blender + spare cup',
    exampleNiche: (n) => `See an example for your niche: ${n}`,
    langBtn: '中文',
    tabChat: 'Chat',
    tabResult: 'Result',
    introTitle: 'Hi, I’m Landed.',
    introBody: 'Tell me what you sell, where (an EU country or the US), the unit cost, weight and your target margin. With those I give you a price right away, and I only ask questions that change it.',
    startersLabel: 'Try one:',
    starters: [
      'Cotton socks 5-pack, cost ¥12 per pack, 0.25 kg, Germany, 30% target margin',
      'Portable blender, cost ¥38, 0.6 kg, Germany, 25% target margin',
      'My phone case costs ¥6 and weighs 50 g. What should I charge in Germany?'
    ],
    inputLabel: 'Message',
    placeholder: 'Product, cost, weight, market, margin',
    send: 'Send',
    working: (s) => `Working… ${s}s`,
    answered: (s) => `Done in ${s}s`,
    tool: { classify_hs: 'Checking the HS code', landed_cost: 'Pricing', compliance_flags: 'Checking requirements', ask_seller: 'Preparing questions' },
    seeResult: 'See the full result →',
    guardrail: (x) => `Not found in any source or in your messages, so don’t rely on: ${x}`,
    unavailable: () => 'The AI is unavailable right now. Please try again shortly. You can still use the engine with “Example”: no number goes through the AI.',
    busy: 'The AI service is busy. Please try again shortly. You can still use the engine with “Example”.',
    rateLimited: 'You are sending messages too fast. Please wait a few minutes. The numbers in the side panel can still be edited; the engine is not affected.',
    emptyTitle: 'Describe a product, get a price you can actually use',
    step1T: 'Tell me 4 numbers',
    step1: 'Unit cost, weight, market (an EU country or the US) and target margin',
    step2T: 'Get the landed price',
    step2: 'Duty, VAT, freight, platform fee and returns included, every figure with its source',
    step3T: 'See the risks and the must-dos',
    step3: 'How much FX, returns or freight could cost you, and what you must do before listing',
    emptyNote: 'The AI only reads your message and writes the reply. Every number is computed by a deterministic rules engine.',
    hsTitle: 'HS code',
    hsStatus: { ambiguous: 'needs an answer', needs_confirmation: 'confirm', resolved: 'matched', out_of_scope: 'not in the table' },
    hsNoteDE: 'Below €150, the EU duty is €3 per kind of item whatever the code, so it does not change an EU price. The customs declaration still needs a 6-digit code.',
    hsNoteUS: 'US duty depends on the exact code, so a US price needs a confirmed code.',
    hsOut: 'This product is not in Landed’s HS table (blenders, juicers and their parts for now). An EU price doesn’t need the code; for the declaration, check the destination’s tariff database or a broker.',
    priceLabelDE: 'Recommended price',
    priceLabelUS: 'Reference price (US)',
    priceLabelUSLow: 'Lower-bound price',
    priceSubDE: (v) => `VAT (${v}) included · hits your target margin`,
    priceSubUS: 'Excl. sales tax · includes the 12.5% China Section 301 duty (CBP notice); list-duty status to confirm',
    priceSubUSLow: 'Excl. sales tax · older Section 301 list duty not included, so the real price is higher',
    profit: 'Profit per unit',
    margin: (m) => `${m} margin (on revenue excl. VAT)`,
    safer: 'Safer price',
    saferNote: 'keeps your margin in 95% of simulated cases',
    loss: 'Chance of a loss',
    lossNote: '5,000 simulated scenarios',
    marketDE: 'Germany · IOSS',
    marketUS: 'United States',
    hsChip: (h) => `HS ${h}`,
    hsNone: 'No HS code · doesn’t change the EU price',
    hsNoneUS: 'No HS code · US base duty not loaded',
    kinds: (n) => `${n} kind${n > 1 ? 's' : ''} of item per parcel`,
    demoChip: 'Still placeholders',
    yourChip: 'Using your settings',
    emptyYou: 'Pricing with your settings: ',
    emptyYouTail: 'just give me the cost and weight.',
    vatChip: (v) => `VAT at the standard ${v} (some goods, e.g. food and books, use a reduced rate)`,
    multiT: (s) => `A multipack spreads the duty: the €3 is ${s} of this price`,
    multiRow: (n, pack, per, save) => `<tr><td>${n}-pack</td><td>${pack}</td><td>${per} each</td><td>${save} less each</td></tr>`,
    multiNote: 'The EU charges €3 per kind of item, not per unit. Only identical items count as one kind. A multipack changes your offer: check demand and the platform’s rules first.',
    bundleT: (save) => `Declared as a retail set, it may count as one kind (about ${save} less per unit)`,
    bundleNote: 'Set classification (WCO GRI 3(b)) is a judgment call: confirm with a customs broker or a BTI ruling before shipping.',
    badNumber: (lo, hi) => `Enter a number ${hi ? `from ${lo} to ${hi}` : `of ${lo} or more`}. The price was not updated.`,
    usRange: (a, b) => `If an older Section 301 list duty applies on top: about ${a} at 7.5%, or ${b} at 25%. Whether it applies depends on the exact line; confirm with a customs broker.`,
    usAssumed: (c) => `HS ${c} was assumed from your product description, not confirmed. A different line can carry a different duty: have a customs broker check it.`,
    usBaseUnknown: 'The base duty for this product is not loaded, so only the 12.5% China Section 301 duty is included. The real duty will be higher.',
    warnUS: 'The US price is a floor: the older Section 301 list duty (7.5% or 25%) for this HTS line is not loaded. The 12.5% China Section 301 duty is included.',
    warnUSKnown: 'The US price includes the 12.5% China Section 301 duty (CBP notice) and a 25% list duty. That this line is on the list and that the two stack comes from secondary sources: confirm with a customs broker.',
    warnAbove: 'The price is above €150, so the €3 flat duty does not apply; the conventional duty for this code is used instead.',
    breakdownTitle: 'Where the price goes',
    breakdownHint: (p) => `Breakdown of ${p} (percent of the price)`,
    wf: { cogs: 'Product cost', freight: 'Freight', duty: 'Duty', returns: 'Returns', fee: 'Platform fee', vat: 'VAT', margin: 'Profit' },
    riskTitle: 'What could eat your margin',
    riskHint: (p) => `at ${p}`,
    stress: {
      'CNY +5%': 'Yuan strengthens 5%',
      'Return rate 15%': 'Returns rise to 15%',
      'Freight +30%': 'Peak-season freight +30%',
      'Add a different kind': 'Adding a different item (e.g. a free gift): +€3 duty',
      'Duty +10': 'Duty +10 percentage points',
      'Platform fee at the high end': 'Platform fee at the high end of its range'
    },
    riskMore: 'Show the margin distribution and the odds at other prices',
    histCaption: 'Margin at the recommended price, 5,000 simulated scenarios',
    curveCaption: 'Chance of hitting your margin (green) and of a loss (red) at each price',
    chart: { target: 'target', p5: 'P5', conf: '95% line', hit: '■ hits target margin', loss: '■ loss', price: 'recommended' },
    curveReadout: (p, hit, p5, loss) => `At <b>${p}</b>: ${hit} chance of hitting your margin · worst-5% margin ${p5} · chance of a loss ${loss}`,
    flagsTitle: 'Before you list',
    flagsHint: 'From the destination’s rules; “source” opens the legal text',
    flagsNone: 'Nothing extra for what you’ve told me.',
    sev: { blocker: 'Required', warning: 'Note', opportunity: 'Opportunity' },
    source: 'source',
    adjustTitle: 'Adjust the numbers',
    adjustHint: 'Change anything and the price updates instantly (no AI involved)',
    yours: 'Your numbers',
    demo: 'Default assumptions (editable)',
    demoTag: 'replace with your real quotes',
    f: { cogs_cny: 'Unit cost', weight_kg: 'Weight', target_margin: 'Target margin', item_categories: 'Kinds of item / parcel', fee_rate: 'Platform fee', freight_cny_per_kg: 'Freight', return_rate: 'Return rate', fx: 'FX' },
    fxUnit: (c) => `CNY / ${c}`,
    market: 'Market',
    eu: 'EU',
    euCountry: 'Destination',
    soldOn: 'Sold on',
    platformNone: 'Not chosen (15% placeholder)',
    us: 'US',
    usNeedsHS: 'A US price needs an HS code',
    compareUS: (p) => `The same product in the US: about ${p} (includes the China Section 301 duty; rates to confirm).`,
    compareDE: (p, n) => `The same product in ${n}: recommended price ${p}.`,
    compareNoUS: 'US duty depends on the exact code. This product has no confirmed code, so there is no US price yet.',
    sourcesTitle: 'Sources and record',
    sourcesHint: 'where each number comes from, and how this result was produced',
    th: ['Figure', 'Value', 'Status', 'Source'],
    status: { verified: 'verified', secondary: 'to confirm', assumption: 'placeholder', seller_input: 'your number', unknown: 'not loaded' },
    prov: {},
    timelineTitle: 'How this result was produced',
    export: 'Export record (JSON)',
    print: 'Print report',
    disclaimer: 'Pricing decision support, not licensed customs brokerage. Replace anything marked “placeholder” with your own number, and check “to confirm” figures against the official source.',
    watchTag: 'your pick',
    abstainT: 'I can’t give this price',
    abstainAbove: null,
    abstainUSnoHS: null,
    hsTitles: {},
    tl: { user: 'Your message', tool: 'Tool', answer: 'Reply', example: 'Example loaded', lab: 'Recalculated', hs: 'Your answer' }
  }
};

const FLAG_TEXT = {
  gpsr_eu: {
    zh: ['指定欧盟责任人（GPSR）', '没有设在欧盟的责任人（进口商、授权代表或履约服务商）就不能在欧盟销售；商品页必须写明制造商和责任人的名称、邮寄地址和电子联系方式。'],
    en: ['EU responsible person (GPSR)']
  },
  textile_label_eu: {
    zh: ['纤维成分标签', '用法规规定的纤维名称和重量百分比标注，按含量从高到低；只有单一纤维的产品才能写「100%」或「纯」。'],
    en: ['Fibre composition label']
  },
  un3481: { zh: ['锂电池运输（UN 3481）', '空运按 IATA PI 967 申报；电芯须通过 UN 38.3 测试，并把测试摘要交给承运人。'], en: ['Lithium battery shipping (UN 3481)'] },
  food_contact_eu: { zh: ['食品接触材料', '须符合 (EC) No 1935/2004；Tritan 等塑料部件还需按 (EU) No 10/2011 出具符合性声明。'], en: ['Food-contact materials'] },
  ce_eu: { zh: ['CE 标志', '电器需加贴 CE 标志并出具欧盟符合性声明（EMC 2014/30/EU、RoHS 2011/65/EU，充电器等低压部件按 LVD 2014/35/EU）。'], en: ['CE marking'] },
  weee_battery_eu: { zh: ['WEEE 与电池注册', '远程销售电器和电池，须在每个目的国注册生产者并指定当地授权代表；各国登记处不同（德国 stiftung ear，法国 SYDEREP）。欧盟电池法规 (EU) 2023/1542 自 2025-08-18 起适用。'], en: ['WEEE and battery registration'] },
  packaging_epr_eu: { zh: ['包装生产者责任登记（PPWR）', '自 2026-08-12 起，非欧盟卖家直接向消费者销售，须在目的国登记并指定当地授权代表（逐国）；各国另有登记处（德国 LUCID + 双轨系统，法国 SYDEREP，西班牙 MITECO 等）。平台可能要求登记号。来源为行业文章，请核对法规原文。'], en: ['Packaging producer registration (PPWR)'] },
  eu_flat_duty_set: { zh: ['套装可能只按 1 类计税', '包裹里有多种商品时，每类都收 €3；作为零售套装申报可能只算 1 类，需报关行确认。'], en: ['A retail set may count as one kind'] },
  fcc_us: { zh: ['FCC 认证', '带电子部件的产品在美国销售前需符合 FCC 射频设备规定。'], en: ['FCC equipment authorization'] },
  cosmetic_eu: {
    zh: ['化妆品：欧盟责任人与 CPNP 备案', '须有欧盟境内责任人；上市前必须完成化妆品安全评估并出具安全报告，并在欧盟 CPNP 系统备案。'],
    en: ['Cosmetics: responsible person & CPNP']
  },
  toy_eu: {
    zh: ['玩具安全合规', '须按欧盟玩具安全规则做符合性评估，加贴 CE 标志，准备技术文件和欧盟符合性声明（现行为指令 2009/48/EC，2030 年 8 月 1 日起由法规 (EU) 2025/2509 取代）。请按你玩具的年龄段和材料确认具体步骤。'],
    en: ['Toy safety']
  },
  us_china_tariffs: { zh: ['对华加征关税', '2026-07-24 起对华加征 12.5% 的 301 附加税（CBP 公告），价格已计入；另有 7.5%/25% 的旧清单税，按税号而定，请核实。'], en: ['China-origin additional tariffs'] }
};

const EXAMPLE = {
  inputs: { market: 'DE', hs_code: '8509.40', cogs_cny: 38, weight_kg: 0.6, target_margin: 0.25, item_categories: 2 },
  description: '500ml portable blender with built-in battery + spare Tritan travel cup',
  attributes: { has_electric_motor: true, motor_self_contained: true, has_heating_element: false, domestic_use: true, is_accessory_only: false },
  flagAttrs: { battery_builtin: true, food_contact: true, has_electric_motor: true }
};

// ------------------------------------------------------------------ state
const state = {
  lang: readLang(),
  inputs: null,
  overrides: {},
  defaults: {},
  result: null,
  sweep: null,
  compare: null,
  hs: null,
  flags: null,
  flagAttrs: null,
  history: [],
  timeline: [],
  busy: false,
  askedMarket: null,
  pane: 'chat'
};

// ------------------------------------------------------------------ personalisation
const personal = createPersonal({
  getLang: () => state.lang,
  toggleLang: () => toggleLang(),
  send: (text) => send(text),
  toast: (msg) => toast(msg),
  snapshot: () => snapshotProduct(),
  openProduct: (data) => openProduct(data),
  onChange: () => onProfileChange()
});

function ownOverrides(market) {
  const o = personal.overrides();
  if (isEU(personal.profile().market) !== isEU(market)) delete o.fx; // CNY per EUR is not CNY per USD
  return o;
}

// The worked example is a product from the seller's own niche when we know it (the blender otherwise).
// The worked example is priced for the seller's own EU country when they chose one.
function exampleMarket() {
  const m = personal.profile().market;
  return isEU(m) ? m : 'DE';
}

function exampleConfig() {
  const p = personal.profile();
  const info = p.niche && p.niche !== 'kitchen_appliance' ? nicheInfo(p.niche) : null;
  if (!info) return null;
  let mine = null;
  try {
    const s = JSON.parse(localStorage.getItem('landed.myproduct.v1') || 'null');
    if (s && s.niche === p.niche && s.cost > 0 && s.kg > 0) mine = s;
  } catch { /* storage blocked */ }
  return {
    description: mine ? mine.name : state.lang === 'zh' ? info[3] : info[4],
    inputs: {
      market: exampleMarket(),
      hs_code: null,
      cogs_cny: mine ? mine.cost : p.cost_band ? COST_BANDS[p.cost_band] : info[5],
      weight_kg: mine ? mine.kg : info[6],
      target_margin: p.target_margin || 0.25,
      item_categories: p.parcel === 'mixed' ? 2 : 1
    }
  };
}

function paintEmptyYou() {
  const ex = exampleConfig();
  const btn = document.querySelector('.empty [data-load-example]');
  if (btn) btn.textContent = ex ? t('exampleNiche')(ex.description) : t('exampleLong');
  const el = $('empty-you');
  if (!el) return;
  if (!personal.hasProfile()) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.textContent = t('emptyYou') + personal.summary().join(' · ') + (state.lang === 'zh' ? '。' : '; ') + t('emptyYouTail');
}

function onProfileChange() {
  paintEmptyYou();
  if (state.inputs) {
    state.overrides = ownOverrides(state.inputs.market);
    buildAdjust();
    recalc();
  }
}

let toastTimer;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 2600);
}

function snapshotProduct() {
  if (!state.result || !state.inputs) return null;
  const wf = state.result.waterfall;
  const lastUser = [...state.history].reverse().find((m) => m.role === 'user')?.content || '';
  return {
    name: (lastUser || EXAMPLE.description).replace(/\s+/g, ' ').slice(0, 24),
    data: {
      inputs: { ...state.inputs },
      overrides: { ...state.overrides },
      flagAttrs: state.flagAttrs ? { ...state.flagAttrs } : null,
      priceText: money(wf.price, wf.currency),
      savedAt: Date.now()
    }
  };
}

function openProduct(data) {
  state.inputs = { ...data.inputs };
  state.overrides = { ...(data.overrides || {}) };
  state.flagAttrs = data.flagAttrs || null;
  state.hs = null;
  $('sec-hs').hidden = true;
  logTimeline('example', data.priceText || '');
  buildAdjust();
  recalc();
  if (isNarrow()) showPane('result');
  $('pane-result').scrollTop = 0;
}

function readLang() {
  try {
    const v = localStorage.getItem('landed-lang');
    if (v === 'zh' || v === 'en') return v;
  } catch {
    /* storage blocked */
  }
  try {
    return /^zh/i.test(navigator.language || 'zh') ? 'zh' : 'en'; // follow the browser until the seller chooses
  } catch {
    return 'zh';
  }
}
const t = (k) => T[state.lang][k];

// ------------------------------------------------------------------ static copy
function applyCopy() {
  document.documentElement.lang = state.lang === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const v = t(el.dataset.i18n);
    if (typeof v === 'string') el.textContent = v;
  });
  $('lw-lang').textContent = t('langBtn');
  $('chat-input').placeholder = t('placeholder');
  $('chat-send').setAttribute('aria-label', t('send'));
  personal.relabel();
  paintEmptyYou();
  if (state.hs) renderHS(state.hs);
  if (state.result) renderPrice(state.result);
  if (state.flags) renderFlags(state.flags);
  if (state.inputs) buildAdjust();
  if (state.compare !== null && state.result) renderCompare();
  renderTimeline();
}

// ------------------------------------------------------------------ panes (mobile)
function showPane(name) {
  state.pane = name;
  $('pane-chat').classList.toggle('is-shown', name === 'chat');
  $('pane-result').classList.toggle('is-shown', name === 'result');
  document.querySelectorAll('.lw-tab').forEach((b) => b.classList.toggle('is-on', b.dataset.pane === name));
  if (name === 'result') $('tab-dot').hidden = true;
}
const isNarrow = () => window.matchMedia('(max-width: 880px)').matches;

function showResult() {
  $('empty').hidden = true;
  $('result').hidden = false;
  if (isNarrow() && state.pane !== 'result') $('tab-dot').hidden = false;
}

// ------------------------------------------------------------------ helpers
function logTimeline(kind, text) {
  state.timeline.push({ t: Date.now(), kind, text });
  renderTimeline();
}
function renderTimeline() {
  const t0 = state.timeline[0]?.t || Date.now();
  $('timeline').innerHTML = state.timeline
    .map((e) => `<li><span class="t">+${((e.t - t0) / 1000).toFixed(1)}s</span><span>${esc(t('tl')[e.kind] || e.kind)} · ${esc(e.text)}</span></li>`)
    .join('');
}
const debounce = (fn, ms) => {
  let h;
  return (...a) => {
    clearTimeout(h);
    h = setTimeout(() => fn(...a), ms);
  };
};
function stressLabel(s) {
  const rr = /^Return rate (\d+%)/.exec(s);
  if (rr) return state.lang === 'zh' ? `退货率升到 ${rr[1]}` : `Returns rise to ${rr[1]}`;
  const map = t('stress');
  const key = Object.keys(map).find((k) => s.startsWith(k));
  return key ? map[key] : s;
}
function provLabel(l) {
  const map = t('prov');
  const key = Object.keys(map).find((k) => l.startsWith(k));
  const who = /^Platform (?:fixed )?fee.*?\((.+?)\)/.exec(l);
  if (key && who) return `${map[key]}（${who[1]}）`;
  return key ? map[key] + (l.match(/\d{4}\.\d{2}/) ? ` ${l.match(/\d{4}\.\d{2}/)[0]}` : '') : l;
}
function tag(status) {
  const cls = { verified: 'good', secondary: 'warn', assumption: 'warn', seller_input: '', unknown: 'bad' }[status] ?? '';
  return `<span class="tag ${cls ? 'tag--' + cls : ''}">${esc(t('status')[status] || status)}</span>`;
}
function hostname(u) {
  try {
    return new URL(u).hostname.replace(/^www\./, '');
  } catch {
    return u;
  }
}

// ------------------------------------------------------------------ defaults
async function loadDefaults() {
  try {
    const rows = await fetch('/api/sources').then((r) => r.json());
    const get = (k, m = 'ALL') => rows.find((r) => r.key === k && r.market === m)?.value;
    const a = get('return_alpha');
    const b = get('return_beta');
    state.defaults = {
      fee_rate: get('platform_fee'),
      freight_cny_per_kg: get('freight_cny_per_kg'),
      return_rate: a && b ? a / (a + b) : 0.08,
      fx: { DE: get('fx_cny_per_eur', 'EU'), US: get('fx_cny_per_usd', 'US') }
    };
  } catch {
    state.defaults = { fee_rate: 0.15, freight_cny_per_kg: 45, return_rate: 0.08, fx: { DE: 7.4485, US: 6.6713 } };
  }
}

// ------------------------------------------------------------------ HS
function renderHS(r) {
  state.hs = r;
  showResult();
  $('sec-hs').hidden = false;
  const st = r.status;
  $('hs-tag').className = `tag tag--${st === 'resolved' ? 'good' : st === 'out_of_scope' ? 'bad' : 'warn'}`;
  $('hs-tag').textContent = t('hsStatus')[st] || st;
  if (st === 'out_of_scope') {
    $('hs-body').innerHTML = `<p class="hs-note">${esc(t('hsOut'))}</p>`;
    return;
  }
  const cands = (r.candidates || [])
    .map(
      (c, i) => `<li class="hs-cand ${st === 'resolved' && i === 0 ? 'is-win' : ''}"><b>${esc(c.hs)}</b>
        <details><summary>${esc(t('hsTitles')[c.hs] || c.title)}</summary><p>${esc(c.reasoning)} · <a href="${esc(c.source_url)}" target="_blank" rel="noopener">${esc(t('source'))}</a></p></details></li>`
    )
    .join('');
  const market = state.inputs?.market || state.askedMarket;
  const note = market === 'US' ? t('hsNoteUS') : t('hsNoteDE');
  $('hs-body').innerHTML = `<ul class="hs-cands">${cands}</ul><p class="hs-note">${esc(note)}</p>`;
}

// ------------------------------------------------------------------ abstain / notice
function localizeAbstain(text) {
  const above = /about EUR (\d+), above the EUR 150/.exec(text || '');
  if (above && t('abstainAbove')) {
    const code = /for (\d{4}\.\d{2})/.exec(text);
    return t('abstainAbove')(above[1], code ? code[1] : null);
  }
  if (/needs a confirmed HS code/i.test(text || '') && t('abstainUSnoHS')) return t('abstainUSnoHS');
  return text;
}

function renderNotice(text) {
  showResult();
  text = localizeAbstain(text);
  const n = $('notice');
  if (!text) {
    n.hidden = true;
    return;
  }
  n.hidden = false;
  n.innerHTML = `<b>${esc(t('abstainT'))}</b>${esc(text)}`;
}
function hidePrice() {
  ['sec-price', 'sec-breakdown', 'sec-risk'].forEach((id) => ($(id).hidden = true));
}

// ------------------------------------------------------------------ price
function renderPrice(res) {
  state.result = res;
  showResult();
  renderNotice('');
  ['sec-price', 'sec-breakdown', 'sec-risk', 'sec-adjust', 'sec-sources'].forEach((id) => ($(id).hidden = false));
  const wf = res.waterfall;
  const mc = res.monte_carlo;
  const cur = wf.currency;
  const inp = res.inputs;
  const us = inp.market === 'US';
  const price = money(wf.price, cur);
  const marginStep = wf.steps.find((s) => s.key === 'margin');

  const lowBound = us && !(res.provenance || []).some((r) => /list duty/i.test(r.label || ''));
  $('price-label').textContent = us ? t(lowBound ? 'priceLabelUSLow' : 'priceLabelUS') : t('priceLabelDE');
  $('price-value').textContent = price;
  const vatRow = (res.provenance || []).find((r) => r.label === 'VAT');
  $('price-sub').textContent = us ? t(lowBound ? 'priceSubUSLow' : 'priceSubUS') : t('priceSubDE')(vatRow ? `${+(vatRow.value * 100).toFixed(1)}%` : '');
  $('price-stats').innerHTML = [
    ['', t('profit'), money(marginStep ? marginStep.value : 0, cur), t('margin')(pct(wf.margin_pct))],
    ['', t('safer'), money(mc.floor_price_95, cur), t('saferNote')],
    [mc.p_loss > 0.01 ? 'stat--bad' : '', t('loss'), mc.p_loss < 0.0005 ? '< 0.1%' : pct(mc.p_loss), t('lossNote')]
  ]
    .map(([c, l, v, s]) => `<div class="stat ${c}"><dt>${esc(l)}</dt><dd>${esc(v)}<small>${esc(s)}</small></dd></div>`)
    .join('');

  const demoLabels = [...new Set((res.provenance || []).filter((p) => p.status === 'assumption' && !/volatility/i.test(p.label)).map((p) => provLabel(p.label)))];
  const usesMine = (res.provenance || []).some((p) => p.status === 'seller_input');
  const chips = [
    `<span class="chip">${esc(us ? t('marketUS') : `${marketName(inp.market, state.lang)} · IOSS`)}</span>`,
    `<span class="chip">${esc(inp.hs_code ? t('hsChip')(inp.hs_code) : t(us ? 'hsNoneUS' : 'hsNone'))}</span>`,
    !us ? `<span class="chip">${esc(t('kinds')(inp.item_categories || 1))}</span>` : '',
    !us && !inp.hs_code ? `<span class="chip">${esc(t('vatChip')(vatRow ? `${+(vatRow.value * 100).toFixed(1)}%` : ''))}</span>` : '',
    usesMine ? `<span class="chip chip--good">${esc(t('yourChip'))}</span>` : '',
    demoLabels.length ? `<span class="chip chip--warn">${esc(t('demoChip'))}：${esc(demoLabels.join(state.lang === 'zh' ? '、' : ', '))}</span>` : ''
  ];
  $('price-chips').innerHTML = chips.join('');

  const tips = [];
  if (res.multipack_tip) {
    const m = res.multipack_tip;
    tips.push(
      `<div class="tip"><b>${esc(t('multiT')(pct(m.duty_share_of_price, 0)))}</b><table>${m.options
        .map((o) => t('multiRow')(o.units, money(o.pack_price, cur), money(o.price_per_unit, cur), money(o.saving_per_unit, cur)))
        .join('')}</table><small>${esc(t('multiNote'))}</small></div>`
    );
  }
  if (res.bundle_tip) {
    const b = res.bundle_tip;
    tips.push(`<div class="tip"><b>${esc(t('bundleT')(money(b.price_reduction, cur)))}</b><small>${esc(t('bundleNote'))}</small></div>`);
  }
  (res.warnings || []).forEach((w) => {
    if (/^US figure is a LOWER BOUND/i.test(w)) {
      let extra = '';
      if (res.us_scenarios) extra = ` ${t('usRange')(money(res.us_scenarios.list_duty_7_5, cur), money(res.us_scenarios.list_duty_25, cur))}`;
      tips.push(`<div class="tip tip--warn">${esc(t('warnUS') + extra)}</div>`);
    } else if (/^HS .* was assumed/i.test(w)) tips.push(`<div class="tip tip--warn">${esc(t('usAssumed')((w.match(/^HS (\S+)/) || [])[1] || ''))}</div>`);
    else if (/^The base duty for this product/i.test(w)) tips.push(`<div class="tip tip--warn">${esc(t('usBaseUnknown'))}</div>`);
    else if (/^US duty assumes/i.test(w)) tips.push(`<div class="tip tip--warn">${esc(t('warnUSKnown'))}</div>`);
    else if (/^Above the EUR/i.test(w)) tips.push(`<div class="tip tip--warn">${esc(t('warnAbove'))}</div>`);
  });
  $('tips').innerHTML = tips.join('');

  // breakdown
  $('breakdown-hint').textContent = t('breakdownHint')(price);
  const steps = wf.steps.filter((s) => s.value > 0);
  $('stack').innerHTML = steps.map((s) => `<span class="c-${s.key}" style="width:${((s.value / wf.price) * 100).toFixed(2)}%" title="${esc(t('wf')[s.key] || s.label)}"></span>`).join('');
  $('stack').setAttribute('aria-label', steps.map((s) => `${t('wf')[s.key] || s.label} ${money(s.value, cur)}`).join(', '));
  const watch = new Set(personal.profile().worries || []);
  $('legend').innerHTML = steps
    .map(
      (s) => `<li class="${s.key === 'margin' ? 'is-profit' : ''} ${watch.has(s.key) ? 'is-watch' : ''}"><i class="c-${s.key}"></i><span>${esc(t('wf')[s.key] || s.label)}</span><span class="v">${money(s.value, cur)}</span><span class="p">${pct(s.value / wf.price, 0)}</span></li>`
    )
    .join('');

  // risks
  $('risk-hint').textContent = t('riskHint')(price);
  const WATCH_ROW = { fx: /CNY/, returns: /Return/, freight: /Freight/, duty: /different kind|Duty \+/ };
  const isWatched = (name) => (personal.profile().worries || []).some((w) => WATCH_ROW[w] && WATCH_ROW[w].test(name));
  $('risks').innerHTML = res.stress
    .filter((s) => s.scenario !== 'Base case')
    .sort((a, b) => Number(isWatched(b.scenario)) - Number(isWatched(a.scenario)) || a.margin_pct - b.margin_pct)
    .map((s) => {
      const d = s.margin_pct - inp.target_margin;
      const cls = (s.margin_pct < 0 ? 'risk--bad' : d < -0.03 ? 'risk--hurt' : '') + (isWatched(s.scenario) ? ' risk--watch' : '');
      return `<li class="risk ${cls}"><span>${esc(stressLabel(s.scenario))}${isWatched(s.scenario) ? ` <em class="watch">${esc(t('watchTag'))}</em>` : ''}</span><span class="risk__m">${pct(s.margin_pct)}</span><span class="risk__d">${d >= 0 ? '+' : ''}${(d * 100).toFixed(1)} pp</span></li>`;
    })
    .join('');
  if (mc.histogram) histogram($('chart-hist'), mc.histogram, { p5: mc.p5_margin, target: inp.target_margin, labels: t('chart') });

  renderSources(res.provenance);
  // the fee box shows the platform's sourced rate (not the 15% placeholder); never overwrite what the seller is typing
  const feeBox = document.querySelector('#adjust input[data-k="fee_rate"]');
  const feeRow = (res.provenance || []).find((r) => /^Platform fee \(/.test(r.label || ''));
  if (feeBox && state.overrides.fee_rate == null && document.activeElement !== feeBox) {
    // sourced platform fee when there is one, else the generic placeholder
    feeBox.value = +(((feeRow ? feeRow.value : state.defaults.fee_rate)) * 100).toFixed(2);
  }
  applyWorries();
}

// A seller worried about compliance sees the checklist right under the price.
function applyWorries() {
  const w = personal.profile().worries || [];
  $('sec-flags').style.order = w.includes('compliance') ? '25' : '';
}

// ------------------------------------------------------------------ compliance
function renderFlags(r) {
  state.flags = r;
  showResult();
  $('sec-flags').hidden = false;
  const items = (r.flags || []).filter((f) => f.severity !== 'opportunity' || !state.result?.bundle_tip);
  $('flags-hint').textContent = t('flagsHint');
  $('flags').innerHTML = items.length
    ? items
        .map((f) => {
          const txt = FLAG_TEXT[f.id]?.[state.lang];
          const title = txt ? txt[0] : f.flag.split(':')[0];
          const desc = state.lang === 'zh' && txt?.[1] ? txt[1] : f.flag;
          const sev = { blocker: 'bad', warning: 'warn', opportunity: 'good' }[f.severity] || '';
          return `<li class="flag"><span class="tag tag--${sev}">${esc(t('sev')[f.severity] || f.severity)}</span><span class="flag__t">${esc(title)}</span>
            <span class="flag__d">${esc(desc)}</span><span class="flag__src">${tag(f.status)} <a href="${esc(f.source_url)}" target="_blank" rel="noopener">${esc(t('source'))} · ${esc(hostname(f.source_url))}</a></span></li>`;
        })
        .join('')
    : `<li class="flags__none">${esc(t('flagsNone'))}</li>`;
}
async function refreshFlags() {
  if (!state.inputs) return;
  const snap = state.flagAttrs;
  try {
    const attrs = { ...(snap || {}), item_categories: isEU(state.inputs.market) ? state.inputs.item_categories : 1 };
    const r = await postJSON('/api/compliance', { market: state.inputs.market, attributes: attrs, profile: snap ? null : personal.chatProfile() });
    if (state.flagAttrs !== snap) return; // the agent sent more specific attributes meanwhile
    renderFlags(r);
  } catch {
    /* keep previous */
  }
}

// ------------------------------------------------------------------ adjust
const FIELDS = [
  { k: 'cogs_cny', unit: '¥', step: 0.5, min: 0.1 },
  { k: 'weight_kg', unit: 'kg', step: 0.01, min: 0.01 },
  { k: 'target_margin', unit: '%', pct: true, step: 1, min: 1, max: 70 },
  { k: 'item_categories', unit: '', step: 1, min: 1, max: 6, de: true },
  { k: 'fee_rate', unit: '%', pct: true, step: 0.5, min: 0, max: 40, demo: true },
  { k: 'freight_cny_per_kg', unit: '¥/kg', step: 1, min: 1, demo: true },
  { k: 'return_rate', unit: '%', pct: true, step: 0.5, min: 0, max: 40, demo: true },
  { k: 'fx', unit: 'fx', step: 0.01, min: 0.1, demo: true }
];
function fieldValue(f) {
  if (f.demo) {
    if (state.overrides[f.k] != null) return state.overrides[f.k];
    if (f.k === 'fee_rate') {
      const row = (state.result?.provenance || []).find((r) => /^Platform fee \(/.test(r.label || ''));
      if (row) return row.value; // the platform's sourced fee, not the generic placeholder
    }
    return f.k === 'fx' ? state.defaults.fx[state.inputs.market === 'US' ? 'US' : 'DE'] : state.defaults[f.k];
  }
  return state.inputs[f.k];
}
function fieldHTML(f) {
  const raw = fieldValue(f);
  const v = f.pct ? +(raw * 100).toFixed(2) : raw;
  const unit = f.unit === 'fx' ? t('fxUnit')(state.inputs.market === 'US' ? 'USD' : 'EUR') : f.unit;
  const isDemo = f.demo && state.overrides[f.k] == null;
  return `<label class="field ${isDemo ? 'is-demo' : ''}"><span>${esc(t('f')[f.k])}</span><span class="field__box">
    <input type="number" inputmode="decimal" data-k="${f.k}" value="${v ?? ''}" step="${f.step}" min="${f.min}" ${f.max ? `max="${f.max}"` : ''} />
    ${unit ? `<span class="field__u">${esc(unit)}</span>` : ''}</span></label>`;
}
function buildAdjust() {
  const m = state.inputs.market;
  const usOK = true;
  const mine = FIELDS.filter((f) => !f.demo && (!f.de || isEU(m)));
  const demo = FIELDS.filter((f) => f.demo);
  $('adjust').innerHTML = `
    <fieldset><legend>${esc(t('market'))}</legend><div class="seg">
      <button type="button" data-market="${isEU(m) ? m : state.euPick || 'DE'}" class="${isEU(m) ? 'is-on' : ''}">${esc(t('eu'))}</button>
      <button type="button" data-market="US" class="${m === 'US' ? 'is-on' : ''}" ${usOK ? '' : `disabled title="${esc(t('usNeedsHS'))}"`}>${esc(t('us'))}</button>
    </div>${isEU(m) ? `<label class="eu-pick"><span>${esc(t('euCountry'))}</span><select data-eu>${EU.map((c) => `<option value="${c[0]}" ${c[0] === m ? 'selected' : ''}>${esc(state.lang === 'zh' ? c[2] : c[1])}</option>`).join('')}</select></label>` : ''}</fieldset>
    <fieldset><legend>${esc(t('soldOn'))}</legend><select data-platform aria-label="${esc(t('soldOn'))}"><option value="">${esc(t('platformNone'))}</option></select></fieldset>
    <fieldset><legend>${esc(t('yours'))}</legend><div class="fields">${mine.map(fieldHTML).join('')}</div></fieldset>
    <fieldset><legend>${esc(t('demo'))}<span class="tag tag--warn">${esc(t('demoTag'))}</span></legend><div class="fields">${demo.map(fieldHTML).join('')}</div></fieldset>`;

  $('adjust').querySelectorAll('input[data-k]').forEach((inp) =>
    inp.addEventListener('input', () => {
      const f = FIELDS.find((x) => x.k === inp.dataset.k);
      const n = parseFloat(inp.value);
      const bad = !(n >= (f.min ?? 0)) || (f.max && n > f.max);
      inp.setAttribute('aria-invalid', String(!!bad));
      let err = inp.closest('.field').querySelector('.field__err');
      if (bad) {
        if (!err) {
          err = document.createElement('small');
          err.className = 'field__err';
          err.setAttribute('role', 'alert');
          inp.closest('.field').appendChild(err);
        }
        err.textContent = t('badNumber')(f.min ?? 0, f.max || '');
        return;
      }
      err?.remove();
      const v = f.pct ? n / 100 : f.k === 'item_categories' ? Math.round(n) : n;
      if (f.demo) {
        state.overrides[f.k] = v;
        inp.closest('.field').classList.remove('is-demo');
      } else state.inputs[f.k] = v;
      recalcSoon();
    })
  );
  $('adjust').querySelectorAll('[data-market]').forEach((b) =>
    b.addEventListener('click', () => {
      if (b.disabled || state.inputs.market === b.dataset.market) return;
      const prev = state.inputs.market;
      state.inputs.market = b.dataset.market;
      if (isEU(b.dataset.market)) state.euPick = b.dataset.market;
      if (isEU(prev) !== isEU(b.dataset.market)) delete state.overrides.fx; // CNY per EUR is not CNY per USD
      buildAdjust();
      recalc();
    })
  );
  $('adjust').querySelector('select[data-eu]')?.addEventListener('change', (e) => {
    state.inputs.market = e.target.value;
    state.euPick = e.target.value;
    buildAdjust();
    recalc();
  });
  $('adjust').querySelector('select[data-platform]')?.addEventListener('change', (e) => {
    state.platform = e.target.value; // '' = none chosen
    recalc();
  });
  paintPlatformSelect();
}

// The platforms sold in the chosen country. The seller's saved platform is the default while it is sold there.
async function paintPlatformSelect() {
  const sel = $('adjust').querySelector('select[data-platform]');
  const market = state.inputs.market;
  if (!sel) return;
  const prof = personal.profile();
  const list = await platformsFor(market, prof.category);
  if (state.inputs.market !== market || !sel.isConnected) return;
  const cur = effectivePlatform(market);
  sel.innerHTML = `<option value="">${esc(t('platformNone'))}</option>` + list.map((p) => `<option value="${p.id}" ${p.id === cur ? 'selected' : ''}>${esc(platformLabel(p.id, state.lang))}</option>`).join('');
  if ((state.lastPlatform ?? '') !== cur) recalc(); // the price that went out before the list loaded had no platform
}
// The seller's pick (or saved platform) counts only where it is sold; elsewhere nothing is chosen.
// Their pick is kept, so going back to that country restores it.
function effectivePlatform(market = state.inputs.market) {
  const list = cachedPlatforms(market, personal.profile().category);
  if (!list) return '';
  const want = state.platform !== undefined ? state.platform : personal.profile().platform;
  return want && list.some((p) => p.id === want) ? want : '';
}

function payload(market = state.inputs.market) {
  const p = { ...state.inputs, market, ...state.overrides };
  if (market !== state.inputs.market) delete p.fx;
  if (market === 'US') {
    p.item_categories = 1;
    if (!p.hs_code) p.indicative = true; // no code: a labelled lower bound, as in the chat
  } else {
    delete p.indicative;
    delete p.hs_assumed;
  }
  if (!p.hs_code) delete p.hs_code;
  // the seller's platform gives a sourced default fee unless they typed their own
  const prof = personal.profile();
  const plat = effectivePlatform(market);
  state.lastPlatform = plat;
  if (p.fee_rate == null && plat) p.platform = plat;
  if (prof.category) p.fee_category = prof.category; // also sets the category's default return rate
  return p;
}

function renderCompare() {
  const c = state.compare;
  const el = $('compare');
  if (!c) {
    el.textContent = '';
    return;
  }
  if (c.res) {
    const p = money(c.res.waterfall.price, c.res.waterfall.currency);
    el.textContent = c.market === 'US' ? t('compareUS')(p) : t('compareDE')(p, marketName(c.market, state.lang));
  } else el.textContent = '';
}

let recalcSeq = 0;
async function recalc() {
  if (!state.inputs) return;
  const seq = ++recalcSeq;
  const other = isEU(state.inputs.market) ? 'US' : state.euPick || 'DE';
  const otherCall =
    postJSON('/api/calc', payload(other)).then((r) => ({ market: other, res: r }), () => ({ market: other, res: null }));
  try {
    const [res, sw, oth] = await Promise.all([postJSON('/api/calc', payload()), postJSON('/api/sweep', payload()), otherCall]);
    if (seq !== recalcSeq) return;
    renderPrice(res);
    state.sweep = sw;
    riskCurve($('chart-curve'), sw, { onHover: curveReadout, labels: t('chart') });
    state.compare = oth;
    renderCompare();
    refreshFlags();
    logTimeline('lab', `${res.inputs.market} ${money(res.waterfall.price, res.waterfall.currency)}`);
    saveLast();
  } catch (e) {
    if (seq !== recalcSeq) return;
    hidePrice();
    renderNotice(e.message);
  }
}
const recalcSoon = debounce(recalc, 160);

function curveReadout(i) {
  const sw = state.sweep;
  if (!sw) return;
  $('curve-readout').innerHTML = t('curveReadout')(money(sw.prices[i], sw.currency), pct(sw.p_hit_target[i]), pct(sw.p5_margin[i]), pct(sw.p_loss[i]));
}

// ------------------------------------------------------------------ sources
function renderSources(prov) {
  const [a, b, c, d] = t('th');
  $('sources').innerHTML =
    `<thead><tr><th>${a}</th><th>${b}</th><th>${c}</th><th>${d}</th></tr></thead><tbody>` +
    prov
      .map((p) => {
        const ov = state.overrides;
        let val = p.value;
        if (p.status === 'seller_input') {
          if (p.label.startsWith('FX')) val = ov.fx;
          if (p.label.startsWith('Platform fee')) val = ov.fee_rate;
          if (p.label.startsWith('Freight')) val = ov.freight_cny_per_kg;
          if (p.label.startsWith('Return')) val = ov.return_rate;
        }
        let shown;
        if (p.key === 'return_alpha') shown = p.status === 'seller_input' && val != null ? pct(val) : `${p.value}%`;
        else if (p.unit === 'ratio' || p.label.startsWith('Platform fee')) shown = val != null && val < 1 ? pct(val) : String(val);
        else shown = `${val ?? '—'} ${p.unit === 'param' ? '' : p.unit || ''}`;
        const src = p.source_url ? `<a href="${esc(p.source_url)}" target="_blank" rel="noopener">${esc(hostname(p.source_url))}</a>` : '—';
        return `<tr><td>${esc(provLabel(p.label))}${state.lang === 'en' && p.note ? `<span class="note">${esc(p.note)}</span>` : ''}</td><td class="v">${esc(shown)}</td><td>${tag(p.status)}</td><td>${src}<span class="note">${esc(p.snapshot_date || '')}</span></td></tr>`;
      })
      .join('') +
    '</tbody>';
}

// ------------------------------------------------------------------ example (no LLM)
const LAST_KEY = 'landed.last.v1';
function saveLast() {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify({
      profile: JSON.stringify(personal.profile()),
      inputs: state.inputs, overrides: state.overrides, platform: state.platform, flagAttrs: state.flagAttrs, euPick: state.euPick
    }));
  } catch { /* private mode: nothing to restore */ }
}
function readLast() {
  try {
    const s = JSON.parse(localStorage.getItem(LAST_KEY) || 'null');
    return s && s.inputs && s.inputs.cogs_cny > 0 && s.profile === JSON.stringify(personal.profile()) ? s : null;
  } catch {
    return null;
  }
}

async function restoreLast(last) {
  state.inputs = last.inputs;
  state.overrides = last.overrides || {};
  if (last.platform !== undefined) state.platform = last.platform;
  state.flagAttrs = last.flagAttrs || null;
  if (last.euPick) state.euPick = last.euPick;
  state.hs = null;
  $('sec-hs').hidden = true;
  showResult();
  buildAdjust();
  await recalc();
  if (isNarrow()) showPane('result');
  $('pane-result').scrollTop = 0;
}

async function loadExample() {
  const last = readLast();
  if (last) return restoreLast(last);
  const mine = exampleConfig();
  state.inputs = { ...(mine ? mine.inputs : EXAMPLE.inputs), market: exampleMarket() };
  state.overrides = ownOverrides(state.inputs.market);
  state.flagAttrs = mine ? null : { ...EXAMPLE.flagAttrs }; // null: the seller's niche decides the checks
  logTimeline('example', mine ? mine.description : EXAMPLE.description);
  if (mine) {
    state.hs = null;
    $('sec-hs').hidden = true;
    showResult();
  } else {
    const hsRes = await postJSON('/api/classify', { description: EXAMPLE.description, attributes: EXAMPLE.attributes });
    renderHS(hsRes);
  }
  buildAdjust();
  await recalc();
  if (isNarrow()) showPane('result');
  $('pane-result').scrollTop = 0;
}

// ------------------------------------------------------------------ chat
function addMsg(cls, html) {
  const el = document.createElement('div');
  el.className = `msg ${cls}`;
  el.innerHTML = html;
  $('chat-log').appendChild(el);
  scrollChat();
  return el;
}
function scrollChat() {
  const log = $('chat-log');
  log.scrollTop = log.scrollHeight;
}

function renderTurnWidgets(turn, lang) {
  const followUp = (msg) => send(msg);
  if (turn.ask && turn.ask.status === 'awaiting_seller') {
    renderAskForm(addMsg('msg--widget', ''), { ...turn.ask, lang, onSend: followUp });
  }
  const st = turn.hs?.result?.status;
  if (turn.hs && !turn.priced && ['ambiguous', 'needs_confirmation', 'resolved'].includes(st)) {
    renderHSQuiz(addMsg('msg--widget', ''), {
      description: turn.hs.description,
      result: turn.hs.result,
      lang,
      onUpdate: (r) => {
        renderHS(r);
        logTimeline('hs', r.status);
      },
      onSend: followUp
    });
  }
  scrollChat();
}

const REFUSED = new Set(['not_needed', 'needs_input', 'out_of_scope']);

async function send(text) {
  if (state.busy || !text.trim()) return;
  state.busy = true;
  $('chat-send').disabled = true;
  personal.markStarted();
  state.history.push({ role: 'user', content: text });
  addMsg('msg--user', `<p>${esc(text)}</p>`);
  logTimeline('user', text.slice(0, 100));
  const activity = addMsg('activity', '');
  const items = {};
  const t0 = Date.now();
  const tick = () => ($('chat-status').textContent = t('working')(Math.round((Date.now() - t0) / 1000)));
  tick();
  const timer = setInterval(tick, 500);
  const pending = {};
  const turn = { hs: null, ask: null, priced: false };
  const lang = detectLang(text);
  if (/\bUS\b|\bUSA\b|united states|america|美国/i.test(text)) state.askedMarket = 'US';
  else if (/\bDE\b/.test(text) || euCountryIn(text)) state.askedMarket = euCountryIn(text) || 'DE';

  try {
    await streamChat(state.history, (ev) => {
      if (ev.type === 'tool_call') {
        pending[ev.name] = ev.args;
        const it = document.createElement('span');
        it.className = 'activity__item is-run';
        it.innerHTML = `<span class="activity__dot"></span>${esc(t('tool')[ev.name] || ev.name)}`;
        activity.appendChild(it);
        items[ev.name] = it;
        logTimeline('tool', `${ev.name} ${JSON.stringify(ev.args).slice(0, 140)}`);
      } else if (ev.type === 'tool_result') {
        const r = ev.result || {};
        const it = items[ev.name];
        if (it) {
          if (REFUSED.has(r.status) && ev.name !== 'classify_hs') it.remove();
          else it.className = `activity__item ${r.status === 'abstain' ? 'is-stop' : 'is-done'}`;
        }
        if (ev.name === 'classify_hs') {
          renderHS(r);
          turn.hs = { description: (pending.classify_hs || {}).description || text, result: r };
        }
        if (ev.name === 'ask_seller') turn.ask = r;
        if (ev.name === 'compliance_flags' && r.flags) {
          state.flagAttrs = Object.fromEntries(Object.entries(pending.compliance_flags || {}).filter(([k]) => k !== 'market'));
          renderFlags(r);
        }
        if (ev.name === 'landed_cost' && r.status === 'abstain') {
          hidePrice();
          renderNotice(r.error);
        }
        if (ev.name === 'landed_cost' && r.waterfall) {
          turn.priced = true;
          const a = pending.landed_cost || {};
          state.inputs = {
            market: a.market,
            hs_code: a.hs_code || null,
            cogs_cny: a.cogs_cny,
            weight_kg: a.weight_kg,
            target_margin: a.target_margin ?? 0.25,
            item_categories: a.item_categories ?? 1,
            ...(a.indicative ? { indicative: true } : {}),
            ...(a.hs_assumed ? { hs_assumed: true } : {})
          };
          // the panel prices with what the chat used, so the two numbers always agree
          if (a.platform) state.platform = a.platform;
          state.overrides = ownOverrides(a.market);
          ['fee_rate', 'freight_cny_per_kg', 'return_rate', 'fx'].forEach((k) => {
            if (a[k] != null) state.overrides[k] = a[k];
          });
          buildAdjust();
          recalc();
        }
        logTimeline('tool', `${ev.name} → ${r.status || (r.waterfall ? r.waterfall.price : '')}`);
      } else if (ev.type === 'answer') {
        state.history.push({ role: 'assistant', content: ev.text });
        const m = addMsg('msg--agent', renderMarkdown(ev.text));
        if (turn.priced && isNarrow()) {
          const more = document.createElement('div');
          more.className = 'msg__more';
          more.innerHTML = `<button type="button" class="btn">${esc(t('seeResult'))}</button>`;
          more.querySelector('button').addEventListener('click', () => showPane('result'));
          m.appendChild(more);
        }
        logTimeline('answer', `${ev.text.length} chars`);
      } else if (ev.type === 'guardrail') {
        addMsg('msg--warn', `<p>${esc(t('guardrail')(ev.unverified.join(', ')))}</p>`);
      } else if (ev.type === 'error') {
        logTimeline('tool', `error: ${String(ev.message).slice(0, 120)}`);
        addMsg('msg--error', `<p>${esc(t(ev.code === 'rate_limited' ? 'rateLimited' : 'busy'))}</p>`);
      }
    }, { profile: personal.chatProfile() });
    if (!activity.children.length) activity.remove();
    renderTurnWidgets(turn, lang);
  } catch (err) {
    activity.remove();
    logTimeline('tool', `error: ${String(err.message).slice(0, 120)}`);
    addMsg('msg--error', `<p>${esc(t('unavailable')())}</p>`);
  } finally {
    clearInterval(timer);
    $('chat-status').textContent = t('answered')(Math.max(1, Math.round((Date.now() - t0) / 1000)));
    state.busy = false;
    $('chat-send').disabled = false;
  }
}

// ------------------------------------------------------------------ export
function exportJSON() {
  const blob = new Blob(
    [
      JSON.stringify(
        {
          exported_at: new Date().toISOString(),
          inputs: state.inputs,
          seller_overrides: state.overrides,
          result: state.result,
          risk_curve: state.sweep,
          comparison: state.compare,
          hs_classification: state.hs,
          compliance: state.flags,
          chat: state.history,
          timeline: state.timeline
        },
        null,
        2
      )
    ],
    { type: 'application/json' }
  );
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `landed-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ------------------------------------------------------------------ boot
function autosize(el) {
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

function toggleLang() {
  state.lang = state.lang === 'zh' ? 'en' : 'zh';
  try {
    localStorage.setItem('landed-lang', state.lang);
  } catch {
    /* storage blocked */
  }
  applyCopy();
  if (state.sweep) riskCurve($('chart-curve'), state.sweep, { onHover: curveReadout, labels: t('chart') });
}

async function boot() {
  personal.bind();
  applyCopy();
  await loadDefaults();
  personal.init();
  document.addEventListener('click', (e) => {
    if (e.target.closest('[data-load-example], #lw-example')) loadExample();
    const st = e.target.closest('[data-starter]');
    if (st) send(st.textContent);
    const tab = e.target.closest('.lw-tab');
    if (tab) showPane(tab.dataset.pane);
  });
  $('lw-lang').addEventListener('click', toggleLang);
  $('lw-export').addEventListener('click', exportJSON);
  $('lw-print').addEventListener('click', () => window.print());
  const input = $('chat-input');
  input.addEventListener('input', () => autosize(input));
  $('chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = input.value;
    input.value = '';
    autosize(input);
    send(v);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $('chat-form').requestSubmit();
    }
  });
  const q = new URLSearchParams(location.search);
  if (q.get('example') === '1') loadExample();
  else if (!q.get('q') && readLast()) restoreLast(readLast()); // a reload keeps the last result
  if (q.get('q')) {
    input.value = q.get('q');
    autosize(input);
  }
}

boot();
