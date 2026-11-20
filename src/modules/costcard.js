import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { DEMO, SOURCES, SNAPSHOT, EVIDENCE, SOURCES_ZH, EVIDENCE_ZH } from '../data/landed.js';
import { isZh, L, onLang } from '../i18n.js';
import { waterfall, simulate, stress } from '../lib/engine.js';
import { isReducedMotion } from '../lib/a11y.js';

const eur = (v) => `€${v.toFixed(2)}`;
const pct = (v) => `${(v * 100).toFixed(1)}%`;
const NS = 'http://www.w3.org/2000/svg';

function el(tag, attrs = {}, text) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
}

const STATUS_LABEL = {
  en: { verified: 'VERIFIED', secondary: 'VERIFY', assumption: 'ASSUMPTION' },
  zh: { verified: '已核实', secondary: '待核实', assumption: '占位值' }
};
const statusLabel = (status) => STATUS_LABEL[isZh() ? 'zh' : 'en'][status];

// Engine labels are English; the Chinese page names each step the way sellers do.
const WF_ZH = { cogs: '货值', freight: '头程运费', returns: '退货损耗', fee: '平台佣金', margin: '利润' };
function stepLabel(s) {
  if (!isZh()) return s.label;
  if (s.key === 'duty') return s.label.replace(/EU €3 × (\d+)/, '关税 €3×$1');
  if (s.key === 'vat') return s.label.replace('VAT', '增值税');
  return WF_ZH[s.key] || s.label;
}
function stressLabel(label) {
  if (!isZh()) return label;
  if (label === 'Base case') return '基准情景';
  if (label.startsWith('CNY +5%')) return '人民币升值 5%';
  if (label.startsWith('Return rate')) return label.replace(/Return rate (\d+)%/, '退货率升至 $1%');
  if (label.startsWith('Freight +30%')) return '旺季运费上涨 30%';
  if (label.startsWith('Add a different kind')) return '多放一种不同商品（如赠品）：多交 €3 关税';
  return label;
}

function renderWaterfall(svg, wf, animate) {
  svg.replaceChildren();
  const W = 640;
  const H = 300;
  const padL = 8;
  const padB = 54;
  const padT = 28;
  const n = wf.steps.length + 1;
  const slot = (W - padL) / n;
  const bw = slot * 0.62;
  const max = wf.price * 1.08;
  const y = (v) => padT + (H - padT - padB) * (1 - v / max);

  svg.appendChild(el('line', { x1: 0, x2: W, y1: y(0), y2: y(0), class: 'wf-axis' }));

  let acc = 0;
  const bars = [];
  wf.steps.forEach((s, i) => {
    const x = padL + i * slot + (slot - bw) / 2;
    const top = y(acc + s.value);
    const h = y(acc) - top;
    const cls = s.key === 'margin' ? 'wf-bar wf-bar--margin' : s.key === 'duty' ? 'wf-bar wf-bar--duty' : 'wf-bar';
    const rect = el('rect', { x, y: top, width: bw, height: Math.max(h, 1), rx: 4, class: cls });
    svg.appendChild(rect);
    bars.push(rect);
    svg.appendChild(el('text', { x: x + bw / 2, y: top - 8, class: 'wf-val', 'text-anchor': 'middle' }, eur(s.value)));
    svg.appendChild(el('text', { x: x + bw / 2, y: H - padB + 20, class: 'wf-lbl', 'text-anchor': 'middle' }, stepLabel(s)));
    if (i < wf.steps.length - 1) {
      svg.appendChild(
        el('line', { x1: x + bw, x2: x + slot, y1: top, y2: top, class: 'wf-link' })
      );
    }
    acc += s.value;
  });

  const x = padL + (n - 1) * slot + (slot - bw) / 2;
  const total = el('rect', { x, y: y(wf.price), width: bw, height: y(0) - y(wf.price), rx: 4, class: 'wf-bar wf-bar--total' });
  svg.appendChild(total);
  bars.push(total);
  svg.appendChild(el('text', { x: x + bw / 2, y: y(wf.price) - 8, class: 'wf-val wf-val--strong', 'text-anchor': 'middle' }, eur(wf.price)));
  svg.appendChild(el('text', { x: x + bw / 2, y: H - padB + 20, class: 'wf-lbl', 'text-anchor': 'middle' }, L('List price', '售价')));

  if (animate && !isReducedMotion()) {
    gsap.from(bars, { scaleY: 0, transformOrigin: '50% 100%', duration: 0.8, stagger: 0.06, ease: 'medici' });
  }
}

function renderHistogram(svg, sim, target) {
  svg.replaceChildren();
  const W = 640;
  const H = 180;
  const padB = 30;
  const lo = Math.min(sim.margins[0], -0.05);
  const hi = Math.max(sim.margins[sim.margins.length - 1], target + 0.1);
  const bins = 48;
  const counts = new Array(bins).fill(0);
  for (const m of sim.margins) {
    const b = Math.min(bins - 1, Math.max(0, Math.floor(((m - lo) / (hi - lo)) * bins)));
    counts[b]++;
  }
  const cmax = Math.max(...counts);
  const bw = W / bins;
  const x = (m) => ((m - lo) / (hi - lo)) * W;
  const rects = [];
  counts.forEach((c, i) => {
    const h = (c / cmax) * (H - padB - 16);
    const mid = lo + ((i + 0.5) / bins) * (hi - lo);
    const cls = mid < 0 ? 'mc-bar mc-bar--loss' : mid < sim.p5 ? 'mc-bar mc-bar--tail' : 'mc-bar';
    const r = el('rect', { x: i * bw + 1, y: H - padB - h, width: bw - 2, height: Math.max(h, 0.5), class: cls });
    svg.appendChild(r);
    rects.push(r);
  });
  svg.appendChild(el('line', { x1: 0, x2: W, y1: H - padB, y2: H - padB, class: 'wf-axis' }));
  const marks = [
    { v: sim.p5, label: `P5 ${pct(sim.p5)}`, cls: 'mc-mark mc-mark--p5' },
    { v: target, label: `${L('Target', '目标')} ${pct(target)}`, cls: 'mc-mark' }
  ];
  if (lo < 0) marks.push({ v: 0, label: '0%', cls: 'mc-mark mc-mark--zero' });
  marks.forEach((mk) => {
    svg.appendChild(el('line', { x1: x(mk.v), x2: x(mk.v), y1: 6, y2: H - padB, class: mk.cls }));
    svg.appendChild(el('text', { x: x(mk.v), y: H - 10, class: 'wf-lbl', 'text-anchor': 'middle' }, mk.label));
  });
  return rects;
}

function renderEvidence() {
  const list = document.getElementById('evidence-list');
  if (!list) return;
  const items = EVIDENCE.map((e) => (isZh() && EVIDENCE_ZH[e.key] ? { ...e, ...EVIDENCE_ZH[e.key] } : e)).map(
    (e) => `<span class="evidence-list__fig">${e.figure}</span><span class="evidence-list__claim">${e.claim}<span class="evidence-list__cite"><a href="${e.url}" target="_blank" rel="noopener">${e.cite} ↗</a></span></span>`
  );
  // On a language switch, rewrite each <li> in place: the scroll reveal holds references to them.
  if (list.children.length === items.length) {
    items.forEach((html, i) => {
      if (list.children[i].innerHTML !== html) list.children[i].innerHTML = html;
    });
  } else {
    list.innerHTML = items.map((html) => `<li>${html}</li>`).join('');
  }
}

export function initCostCard() {
  renderEvidence();
  const root = document.getElementById('costcard');
  if (!root) return;
  const wfSvg = root.querySelector('#cc-waterfall');
  const mcSvg = root.querySelector('#cc-mc');
  const toggle = root.querySelector('#cc-set-toggle');
  const out = (id) => root.querySelector(`[data-cc="${id}"]`);

  // Provenance list (static, re-rendered on a language switch)
  const prov = root.querySelector('#cc-provenance');
  const renderProvenance = () => {
    if (!prov) return;
    const keys = ['eu3', 'deVat', 'hs850940', 'un3481', 'fx', 'fee', 'freight', 'returns'];
    prov.innerHTML = keys
      .map((k) => {
        const s = SOURCES[k];
        const link = s.url ? `<a href="${s.url}" target="_blank" rel="noopener">${L('source', '来源')} ↗</a>` : `<span>${L('seller input', '卖家自填')}</span>`;
        return `<li><span class="prov-pill prov-pill--${s.status}">${statusLabel(s.status)}</span><span class="prov-text">${isZh() ? SOURCES_ZH[k] : s.label}</span><span class="prov-meta">${link} · ${SNAPSHOT}</span></li>`;
      })
      .join('');
  };
  renderProvenance();

  // Shock sliders: the price is set from the base case, then the world moves under it.
  const fxSlider = root.querySelector('#cc-fx');
  const retSlider = root.querySelector('#cc-ret');
  const resetBtn = root.querySelector('#cc-reset');
  const baseReturn = DEMO.returnAlpha / (DEMO.returnAlpha + DEMO.returnBeta);
  const concentration = DEMO.returnAlpha + DEMO.returnBeta; // keeps the Beta's tightness fixed
  const shock = { fx: 0, ret: baseReturn };
  const shocked = () => ({
    ...DEMO,
    fxMean: DEMO.fxMean * (1 - shock.fx),
    returnAlpha: shock.ret * concentration,
    returnBeta: (1 - shock.ret) * concentration
  });

  function render(animate = false) {
    const categories = toggle && toggle.checked ? 1 : 2;
    const wf = waterfall(DEMO, { categories });
    const world = shocked();
    const sim = simulate(world, { categories, price: wf.price });
    const st = stress(world, { categories, price: wf.price });
    const alt = waterfall(DEMO, { categories: categories === 1 ? 2 : 1 });

    renderWaterfall(wfSvg, wf, animate);
    const rects = renderHistogram(mcSvg, sim, DEMO.targetMargin);
    const pathsOut = out('paths');
    if (pathsOut) pathsOut.textContent = DEMO.paths.toLocaleString('en-US');
    if (animate && !isReducedMotion()) {
      gsap.from(rects, { scaleY: 0, transformOrigin: '50% 100%', duration: 0.7, stagger: 0.014, ease: 'medici' });
      if (pathsOut) {
        const counter = { n: 0 };
        gsap.to(counter, {
          n: DEMO.paths,
          duration: 1.4,
          ease: 'power2.out',
          onUpdate: () => (pathsOut.textContent = Math.round(counter.n).toLocaleString('en-US'))
        });
      }
    }
    const note = out('shockNote');
    if (note) {
      const moved = shock.fx > 0 || Math.abs(shock.ret - baseReturn) > 1e-9;
      note.textContent = moved
        ? L(`List price held at ${eur(wf.price)}. Margin, risk and the 95% floor are re-simulated for the shocked world.`,
            `售价保持 ${eur(wf.price)} 不变，毛利、风险和 95% 稳妥价都按变化后的情况重新模拟。`)
        : L(`Drag a slider to move FX or returns under a fixed ${eur(wf.price)} price and watch the distribution shift.`,
            `售价固定在 ${eur(wf.price)}，拖动滑块改变汇率或退货率，看利润分布怎么移动。`);
    }

    out('price').textContent = eur(wf.price);
    out('floor').textContent = eur(sim.floor95);
    out('p5').textContent = pct(sim.p5);
    out('pbelow').textContent = pct(sim.pBelowTarget);
    out('ploss').textContent = sim.pLoss < 0.0005 ? '< 0.1%' : pct(sim.pLoss);
    out('stress').innerHTML = st
      .map((r) => `<tr><td>${stressLabel(r.label)}</td><td class="${r.m < DEMO.targetMargin - 1e-9 ? 'is-neg' : ''}">${pct(r.m)}</td></tr>`)
      .join('');
    const saving = Math.abs(alt.price - wf.price);
    out('bundle').textContent =
      categories === 1
        ? L(`Declared as one retail set (WCO GRI 3(b)): one tariff category, €3 duty. List price is ${eur(saving)} lower than shipping the cup as a separate category. Whether the blender and cup qualify as a set is a classification judgment, so confirm it with a customs broker or a BTI ruling before shipping.`,
            `作为一个零售套装申报（WCO 归类总规则 3(b)）：只算 1 类商品，关税 €3，售价比把杯子单独算一类低 ${eur(saving)}。能否算作套装需要归类判断，发货前请向报关行或通过 BTI 裁定确认。`)
        : L(`Blender and spare cup are declared as two tariff categories: €3 × 2 = €6 duty per parcel. If they qualify as a retail set under WCO GRI 3(b), the duty halves and the target price drops by ${eur(saving)}.`,
            `榨汁杯和备用杯按两类商品申报：每个包裹关税 €3 × 2 = €6。如果符合 WCO 归类总规则 3(b) 的零售套装，关税减半，建议售价可降 ${eur(saving)}。`);
  }

  if (toggle) toggle.addEventListener('change', () => render(false));

  let pending = 0;
  const schedule = () => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(() => render(false));
  };
  const syncSliders = () => {
    out('fx-out').textContent = `${(shock.fx * 100).toFixed(1)}%`;
    out('ret-out').textContent = `${(shock.ret * 100).toFixed(0)}%`;
  };
  if (fxSlider && retSlider) {
    fxSlider.addEventListener('input', () => {
      shock.fx = parseFloat(fxSlider.value) / 100;
      syncSliders();
      schedule();
    });
    retSlider.addEventListener('input', () => {
      shock.ret = parseFloat(retSlider.value) / 100;
      syncSliders();
      schedule();
    });
    resetBtn?.addEventListener('click', () => {
      shock.fx = 0;
      shock.ret = baseReturn;
      fxSlider.value = '0';
      retSlider.value = String(Math.round(baseReturn * 100));
      syncSliders();
      render(false);
    });
    syncSliders();
  }

  // Render immediately so the card is never empty; replay the bar animation on first view.
  render(false);
  onLang({
    apply: () => {
      renderEvidence();
      renderProvenance();
      render(false);
    }
  });
  ScrollTrigger.create({
    trigger: root,
    start: 'top 75%',
    once: true,
    onEnter: () => render(true)
  });
}
