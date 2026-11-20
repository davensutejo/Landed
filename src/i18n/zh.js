// Chinese landing page copy. Written for Chinese cross-border sellers, not translated line by line:
// benefit first, short paragraphs, the words sellers use (头程运费, 平台佣金, 毛利率), Chinese dates and
// number units, emphasis by colour (Chinese has no italics). Keys match data-i18n / data-i18n-attr in
// index.html. Academic citations stay in their original form, as is normal in Chinese writing.

const star = (s = 22) => `<svg class="marquee-star" width="${s}" height="${s}"><use href="#sparkle"></use></svg>`;
const em = (t) => `<em class="zh-em">${t}</em>`;
// Headings use word-break: keep-all, so they break only here (phrase boundaries), never inside a word.
const br = '<wbr>';
// Dates and figures that must not split across lines (7月1 / 日).
const nw = (t) => `<span class="nw">${t}</span>`;

export const ZH = {
  // ---------- header ----------
  'skip': '跳到正文',
  'nav.1': '<em>痛点</em>',
  'nav.2': '<em>算例</em>',
  'nav.3': '<em>方法</em>',
  'nav.4': '<em>优势</em>',
  'header.cta': '免费试用',
  'menu.label': '菜单',
  'mnav.1': '壹　痛点',
  'mnav.2': '贰　算例',
  'mnav.3': '叁　方法',
  'mnav.4': '肆　优势',
  'preloader.label': '加载中',

  // ---------- hero ----------
  'hero.folio': '序',
  'hero.eyebrow': '跨境卖家的到岸成本助手 · 欧盟 27 国 + 美国',
  'hero.title': `到岸价，${br}${em('一分钟')}算清。`,
  'hero.sub':
    '说出你卖什么、卖到哪、成本多少、多重，立刻得到建议售价：关税、增值税、头程运费、平台佣金、退货损耗全部算进去，' +
    '再给一个在 95% 的模拟情景下都守得住目标毛利的稳妥价。<b>每个数字都由规则引擎计算</b>，并标明来源、核实日期和可信度。',
  'hero.cta1': '免费开始核算',
  'hero.cta2': '先看一个真实算例 ↓',
  'hero.snapshot': `数据快照 ${nw('2026年11月8日')}`,
  'hero.scroll': '向下滚动 <span class="pixel-arrow" aria-hidden="true">↓</span>',

  // ---------- marquee ----------
  'marquee.top':
    `<span>HS 编码</span>${star()}<span>关税</span>${star()}<em class="marquee-ital">增值税</em>${star()}<span>头程运费</span>${star()}` +
    `<span>平台佣金</span>${star()}<em class="marquee-ital">汇率</em>${star()}<span>退货</span>${star()}<span>商品页</span>${star()}`,

  // ---------- I. pain ----------
  'showreel.eyebrow': '痛点 · 为什么定价这么难',
  'showreel.title': `八项输入，${br}三种语言，${br}${em('一张')}谁都看不懂的${br} Excel。`,
  'showreel.lede':
    '想回答一句“该卖多少钱”，卖家得自己拼凑：HS 编码、关税、增值税、运费区间、平台佣金、汇率、退货成本，' +
    '还有一份写清电池和标签要求的当地语言商品页。而且这一步再也绕不过去了：' +
    `美国 ${nw('2025年8月29日')} 取消小额包裹免税；欧盟 ${nw('2026年7月1日')} 取消 150 欧元免税，改为<b>每类商品征收 3 欧元关税</b>。` +
    '从此每个小包裹都要申报 HS 编码。',
  'showreel.hud': '8 项输入 · 3 种语言 · 1 个价格',
  'showreel.caption': '图一　每进入一个新市场，卖家都要先拼凑这些碎片。',

  // ---------- I.b evidence ----------
  'logos.eyebrow': '证据 · 有据可查',
  'logos.title': `问题是真实的，${br}${em('数据')}是可查的。`,
  'logos.lede': '每一块都是到岸读取的一个数据源。下面是这套设计所依据的公开研究和官方数据，均附原文链接。',
  'stat.1': 'GPT-5-Thinking 判对完整 10 位 HS 编码的比例（ATLAS，2025）',
  'stat.2': '2026年7月1日起，欧盟 150 欧元以下包裹每类商品征收的关税',
  'stat.3.num': '2.84万亿元',
  'stat.3': '2025 年中国跨境电商进出口额（海关总署）',

  // ---------- I.c thesis ----------
  'manifesto.mark': '第零条原则',
  'manifesto.eyebrow': '原则 · 第零条',
  'manifesto.title': `数字，${br}${em('永远')}不来自${br}大模型。`,
  'manifesto.text':
    '大模型擅长语言，却不擅长它没法核对的算术。在 200 条美国海关有约束力的归类裁定上，最强的推理模型只有四分之一能选对完整的 10 位税号；' +
    '咨询顾问在 AI 能力边界之外的任务上用 AI，正确率反而下降 19 个百分点。所以到岸把工作拆开：' +
    '模型负责读懂杂乱的产品描述、决定调用哪个工具、追问缺失的信息（只有当编码会改变价格时，才问那个能定案的问题），并写出当地语言的商品页；' +
    '每一个税率、费用和价格，都由确定性代码从数据表中读取，表里每一行都写明来源、可信度（已核实、待核实或占位值）和核实日期。' +
    '表里没有的数字，助手会直说没有，绝不编造。',

  // ---------- II. worked example ----------
  'cc.eyebrow': '算例 · 在你的浏览器里实时计算',
  'cc.title': `一个带电池的${br}榨汁杯，${br}${em('卖到德国')}。`,
  'cc.lede':
    '这张卡片由助手背后同一套确定性引擎的 JavaScript 版本实时计算：公式相同，不经过 AI。' +
    '（蒙特卡洛的随机数生成器不同，与服务器结果相差约 0.2% 以内。）' +
    '勾选<b>零售套装</b>，看欧盟“每类商品 3 欧元”的规则怎么改变售价；拖动汇率和退货滑块，看售价不变时利润分布怎么移动。',
  'cc.prompt':
    '<b>&gt;</b> 500ml 便携榨汁杯，内置锂电池，另配一个 Tritan 备用杯 · 成本 ¥38 · 0.6 kg · <b>卖德国（欧盟），目标毛利 25%</b> · HS 8509.40（已确认）',
  'cc.head1a': '售价构成 · 每件（欧元）',
  'cc.head1b': '确定性计算',
  'cc.head2a': '该售价下的毛利率 · <b data-cc="paths">5,000</b> 次蒙特卡洛模拟',
  'cc.head2b': '汇率 ~ 正态 · 退货 ~ Beta 分布',
  'cc.fx': '人民币对欧元升值',
  'cc.ret': '平均退货率',
  'cc.reset': '重置',
  'cc.toggle': '<input type="checkbox" id="cc-set-toggle" /> 把榨汁杯和备用杯作为一个零售套装申报（WCO 归类总规则 3(b)）',
  'cc.kpi.price': '建议售价（含增值税）',
  'cc.kpi.floor': '稳妥价（95% 情景守住目标）',
  'cc.kpi.p5': '最差 5% 情景的毛利（P5）',
  'cc.kpi.pbelow': '达不到目标毛利的概率',
  'cc.ploss': '按建议售价亏损的概率：<strong data-cc="ploss">—</strong>',
  'cc.prov': '数据来源',
  'cc.disclaimer': '标为“占位值”的数字请换成你自己的报价。本工具是定价决策辅助，不是持牌报关服务。',

  // ---------- III. method ----------
  'process.mark': '≤ 6 步工具调用',
  'process.eyebrow': '方法 · 助手如何工作',
  'process.title': `从一句话，${br}到一个${em('可审计')}的价格。`,
  'flow.0': '描述',
  'flow.1': '归类',
  'flow.2': '追问',
  'flow.3': '已确认？',
  'flow.4': '计算',
  'flow.5': '文案+合规',
  'p1.eyebrow': '第 1 步 · 描述',
  'p1.title': '一句话描述',
  'p1.caption': '图　中文或英文，一句话说清楚就行。',
  'p1.copy':
    '“500ml 便携榨汁杯，内置电池，另配一个备用杯，成本 38 元，0.6 kg，卖德国，想要 25% 毛利，该定多少？”' +
    '你粘贴进来的商品页只当作数据处理，绝不当作指令执行。',
  'p2.eyebrow': '第 2 步 · 归类',
  'p2.title': '只在必要时归类',
  'p2.caption': '图　从手工整理的 HS 品目和章注中缩小候选编码。',
  'p2.copy':
    '目前覆盖搅拌机、榨汁机一带的 5 个候选编码。只有编码真正影响价格时才会用到：卖德国、150 欧元以下的订单，任何商品都直接定价，不多问一句。' +
    '编码确实影响价格时（比如美国关税），助手只追问能定下编码的那个属性。',
  'p3.eyebrow': '第 3 步 · 计算',
  'p3.title': '代码计算',
  'p3.caption': '图　售价构成、蒙特卡洛和压力测试，全部由代码完成。',
  'p3.copy': '成本引擎给出数字，模型只负责解释，从不改动。',
  'p4.eyebrow': '第 4 步 · 本地化',
  'p4.title': '商品页与合规',
  'p4.caption': '图　当地语言商品页，以及所有可能卡住清关的事项。',
  'p4.copy':
    '当地语言的商品文案；锂电池按 UN 3481 / PI 967 运输；食品接触材料的符合性声明；' +
    '如果作为零售套装申报（归类总规则 3(b)）能少交“每类 3 欧元”的关税，也会提示你。',

  // ---------- IV. moat ----------
  'moat.eyebrow': '优势 · 为什么不只是一个 Excel',
  'moat.title': `税率表${br}人人都能下载，${br}${em('判断逻辑')}抄不走。`,
  'm1.eyebrow': '01 · 数据',
  'm1.tag': '建设中',
  'm1.title': '只问会改变价格的问题',
  'm1.copy':
    '欧盟新规下，150 欧元以下的包裹按商品<b>种类</b>收关税，每类 3 欧元，与编码无关。所以卖德国的订单，助手对任何商品都直接定价，' +
    '不会问电机、材质这类不影响价格的问题；它关心的是一个包裹里有几种不同的商品。HS 编码只在影响钱的地方出现：美国关税和报关单本身。' +
    '150 欧元以上的订单要按具体编码的常规税率计算，助手不给价格。为此它记录了 HS 法律注释和 WCO 归类总规则用来区分相邻编码的属性' +
    '（目前人工整理了搅拌机一类的 5 个编码；从美国 CBP 和欧盟 BTI 的有约束力裁定中扩充，正在建设中）。',
  'm2.eyebrow': '02 · 方法',
  'm2.tag': '已上线',
  'm2.title': `按风险定价，${br}而不是做加法`,
  'm2.copy':
    '不是简单的<code>货值 + 运费 + 关税</code>，而是在不确定性下定价：95% 风险缓冲价、达不到目标毛利的概率、确定性压力测试，' +
    '以及懂规则的建议——同款多件装只交一次 3 欧元（一个成本 6 元、50 克的手机壳，做成 2 件装后每件售价从 €9.24 降到 €5.87，毛利不变），' +
    '而送一个不同种类的赠品，就要多交 3 欧元。',
  'm3.eyebrow': '03 · 数据飞轮',
  'm3.tag': '规划中',
  'm3.title': '已清关先例回写',
  'm3.copy':
    '卖家记录一票顺利清关、未被调整的货物时，到岸会保存<code>（规格，市场，HS 编码，日期）</code>这条记录。' +
    '日积月累，就成了一份由卖家共同验证的归类对照表——这是任何计算器都复制不了的。',
  'm4.eyebrow': '04 · 监测',
  'm4.tag': '已上线',
  'm4.title': '税率变动自动复核',
  'm4.copy':
    '每个税率都带着核实日期，所以保存过的产品每次打开都会按当天的汇率和税率重新核算：哪个数变了、原售价下毛利从多少变成多少、' +
    `要回到目标毛利该改成什么价，一目了然。欧盟“每类 3 欧元”的规则计划在 ${nw('2028年7月1日')} 到期，正是需要这种复核的变化。`,
  'moat.svg.kinds': '种类',
  'moat.svg.us': '美国编码',
  'moat.svg.spec': '规格 · 编码',
  'moat.svg.moved': '税率变了',

  // ---------- V. audit ----------
  'canvas.eyebrow': '审计 · 全程留痕',
  'canvas.title': `每一步，${br}都${em('有据可查')}。`,
  'canvas.hint': '拖动浏览 · 双指或 ⌘ + 滚轮缩放',

  // ---------- VI. CTA ----------
  'cta.eyebrow': '试用 · 现在就算一个',
  'cta.title': `你卖什么？${br}${em('卖到哪里？')}`,
  'cta.sub': '写下产品、单件成本、重量和目标市场。故意漏掉一项，看助手怎么追问。',
  'cta.link': '打开完整工作台 →',
  'cta.label': '产品与目标市场',
  'cta.submit': '计算到岸价',
  'chip.1': '① 欧盟定价 · 毛利 25%',
  'chip.2': '② 压力测试',
  'chip.3': '③ 德语商品页 + 合规',
  'chip.4': '④ 故意缺信息 · 看它追问',
  'chip.5': '⑤ 竞品卖 €29.99，我能赚吗',

  // ---------- footer ----------
  'footer.marquee':
    `<span>只问不猜</span>${star(18)}<em class="marquee-ital">数字来自代码</em>${star(18)}<span>每个数字都有出处</span>${star(18)}`,
  'footer.col1': '产品',
  'footer.l1': '工作流程',
  'footer.l2': '真实算例',
  'footer.l3': '审计记录',
  'footer.l4': '立即试用',
  'footer.col2': '依据',
  'footer.l5': '参考文献',
  'footer.l6': '核心优势',
  'footer.l7': '设计原则',
  'footer.col3': '覆盖范围',
  'footer.s1': '欧盟 27 国（各国增值税分别计算）：150 欧元以下任意商品',
  'footer.s2': '美国：参考底价，含 12.5% 对华 301 附加税；已核实 9 类商品的基础关税',
  'footer.s3': `数据快照 ${nw('2026年11月8日')}`,
  'footer.col4': '声明',
  'footer.s4': '定价决策辅助，不是报关服务。发货前请向报关行核实。',
  'footer.wordmark': '<span>到</span><span>岸</span>',
  'footer.status': '数字来自代码 · 计算不经过 AI'
};

export const ZH_ATTR = {
  'footer.l4.href': '#cta',
  'meta.title': '到岸 Landed：跨境电商到岸价，一分钟算清',
  'meta.description':
    '到岸是面向中国跨境卖家的到岸成本与本地化 AI 助手：关税、增值税、头程运费、平台佣金、汇率和退货全部算进售价，每个数字标明来源；' +
    '覆盖欧盟 27 国和美国，并给出合规清单与当地语言商品页。',
  'brand.aria': '到岸首页',
  'nav.aria': '主导航',
  'menu.aria': '打开菜单',
  'preloader.aria': '到岸加载中',
  'stats.aria': '关键证据',
  'refs.aria': '参考文献',
  'wf.aria': '从货值到售价的成本构成图',
  'mc.aria': '模拟毛利率分布图',
  'stress.aria': '压力情景：建议售价下的毛利率',
  'canvas.aria': '可交互的审计记录画布。方向键平移，加号或减号缩放，0 复位。',
  'cta.placeholder': '便携榨汁杯，带电池，成本 ¥38，0.6kg，卖到德国，目标毛利 25%',
  'chips.aria': '示例问题',
  'console.aria': '助手对话',
  'chip.1.p': '便携榨汁杯，内置电池，另配一个 Tritan 备用杯，总成本 38 元，0.6 kg，卖德国，目标毛利 25%，该定价多少？',
  'chip.2.p': '如果人民币升值 5%、退货率升到 15%，哪种情况最伤我的利润？',
  'chip.3.p': '帮我写德语商品页，并告诉我有哪些问题会卡住运输或清关。',
  'chip.4.p': '我想把一个便携榨汁杯卖到德国，成本38元，怎么定价？',
  'chip.5.p': '便携榨汁杯成本 38 元，0.6 kg，亚马逊德国上竞品卖 €29.99，我的目标毛利 25%，这个价我能赚钱吗？最多能接受多少进货价？',
  'stat3.prefix': '',
  'stat3.suffix': '万亿元'
};
