// Plain-SVG charts for the agent workspace (no chart library).

const NS = 'http://www.w3.org/2000/svg';

export function sym(cur) {
  return cur === 'USD' ? '$' : cur === 'CNY' ? '¥' : '€';
}
export function money(v, cur = 'EUR') {
  return `${sym(cur)}${Number(v).toFixed(2)}`;
}
export function pct(v, d = 1) {
  return `${(v * 100).toFixed(d)}%`;
}

function el(tag, attrs = {}, text) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
}

export function waterfall(svg, wf) {
  svg.replaceChildren();
  const W = 640, H = 300, padT = 26, padB = 50;
  const steps = wf.steps;
  const n = steps.length + 1;
  const slot = W / n;
  const bw = slot * 0.62;
  const max = wf.price * 1.1;
  const y = (v) => padT + (H - padT - padB) * (1 - v / max);
  svg.appendChild(el('line', { x1: 0, x2: W, y1: y(0), y2: y(0), class: 'ax' }));
  let acc = 0;
  steps.forEach((s, i) => {
    const x = i * slot + (slot - bw) / 2;
    const top = y(acc + s.value);
    const cls = s.key === 'margin' ? 'bar bar--margin' : s.key === 'duty' ? 'bar bar--duty' : s.key === 'vat' ? 'bar bar--tax' : 'bar';
    const r = el('rect', { x, y: top, width: bw, height: Math.max(1, y(acc) - top), rx: 4, class: cls });
    r.appendChild(el('title', {}, `${s.label}: ${money(s.value, wf.currency)}`));
    svg.appendChild(r);
    svg.appendChild(el('text', { x: x + bw / 2, y: top - 7, class: 'val', 'text-anchor': 'middle' }, money(s.value, wf.currency)));
    svg.appendChild(el('text', { x: x + bw / 2, y: H - padB + 18, class: 'lbl', 'text-anchor': 'middle' }, s.label));
    if (i < steps.length - 1) svg.appendChild(el('line', { x1: x + bw, x2: x + slot, y1: top, y2: top, class: 'link' }));
    acc += s.value;
  });
  const x = (n - 1) * slot + (slot - bw) / 2;
  svg.appendChild(el('rect', { x, y: y(wf.price), width: bw, height: y(0) - y(wf.price), rx: 4, class: 'bar bar--total' }));
  svg.appendChild(el('text', { x: x + bw / 2, y: y(wf.price) - 7, class: 'val val--strong', 'text-anchor': 'middle' }, money(wf.price, wf.currency)));
  svg.appendChild(el('text', { x: x + bw / 2, y: H - padB + 18, class: 'lbl', 'text-anchor': 'middle' }, 'List price'));
}

export function histogram(svg, hist, { p5, target, labels = {} }) {
  const L = { target: 'target', p5: 'P5', ...labels };
  svg.replaceChildren();
  const W = 640, H = 220, padB = 30, padT = 10;
  const { counts, edges } = hist;
  const lo = Math.min(edges[0], target - 0.02);
  const hi = Math.max(edges[edges.length - 1], target + 0.02);
  const x = (m) => ((m - lo) / (hi - lo)) * W;
  const cmax = Math.max(...counts);
  counts.forEach((c, i) => {
    const a = edges[i], b = edges[i + 1];
    const h = (c / cmax) * (H - padB - padT);
    const mid = (a + b) / 2;
    const cls = mid < 0 ? 'hbar hbar--loss' : mid < p5 ? 'hbar hbar--tail' : mid < target ? 'hbar hbar--below' : 'hbar';
    svg.appendChild(el('rect', { x: x(a) + 0.5, y: H - padB - h, width: Math.max(0.5, x(b) - x(a) - 1), height: h, class: cls }));
  });
  svg.appendChild(el('line', { x1: 0, x2: W, y1: H - padB, y2: H - padB, class: 'ax' }));
  const marks = [
    { v: p5, t: `${L.p5} ${pct(p5)}`, cls: 'mark mark--p5', dy: 0 },
    { v: target, t: `${L.target} ${pct(target)}`, cls: 'mark', dy: 0 }
  ];
  if (lo < 0 && hi > 0) marks.push({ v: 0, t: '0%', cls: 'mark mark--zero', dy: 0 });
  const tooClose = Math.abs(x(p5) - x(target)) < 80;
  marks.forEach((m, i) => {
    svg.appendChild(el('line', { x1: x(m.v), x2: x(m.v), y1: padT, y2: H - padB, class: m.cls }));
    const anchor = tooClose && i === 0 ? 'end' : tooClose && i === 1 ? 'start' : 'middle';
    svg.appendChild(el('text', { x: x(m.v) + (anchor === 'end' ? -4 : anchor === 'start' ? 4 : 0), y: H - 10, class: 'lbl', 'text-anchor': anchor }, m.t));
  });
}

export function riskCurve(svg, sw, { onHover, chosen, labels = {} } = {}) {
  const L = { conf: '95% confidence', hit: '■ P(margin ≥ target)', loss: '■ P(loss)', price: 'target-margin price', ...labels };
  svg.replaceChildren();
  const W = 640, H = 300, padL = 44, padR = 12, padT = 14, padB = 40;
  const ps = sw.prices;
  const x = (p) => padL + ((p - ps[0]) / (ps[ps.length - 1] - ps[0])) * (W - padL - padR);
  const y = (v) => padT + (1 - v) * (H - padT - padB);
  [0, 0.25, 0.5, 0.75, 1].forEach((g) => {
    svg.appendChild(el('line', { x1: padL, x2: W - padR, y1: y(g), y2: y(g), class: g === 0 ? 'ax' : 'grid' }));
    svg.appendChild(el('text', { x: padL - 6, y: y(g) + 4, class: 'lbl', 'text-anchor': 'end' }, `${g * 100}%`));
  });
  for (let i = 0; i < ps.length; i += Math.ceil(ps.length / 6)) {
    svg.appendChild(el('text', { x: x(ps[i]), y: H - padB + 18, class: 'lbl', 'text-anchor': 'middle' }, money(ps[i], sw.currency)));
  }
  const line = (vals, cls) => {
    const d = vals.map((v, i) => `${i ? 'L' : 'M'}${x(ps[i]).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    svg.appendChild(el('path', { d, class: cls }));
  };
  // shaded area under P(hit)
  const area = `M${x(ps[0])},${y(0)} ` + sw.p_hit_target.map((v, i) => `L${x(ps[i]).toFixed(1)},${y(v).toFixed(1)}`).join(' ') + ` L${x(ps[ps.length - 1])},${y(0)} Z`;
  svg.appendChild(el('path', { d: area, class: 'area' }));
  line(sw.p_hit_target, 'curve curve--hit');
  line(sw.p_loss, 'curve curve--loss');
  // target price marker
  svg.appendChild(el('line', { x1: x(sw.target_price), x2: x(sw.target_price), y1: padT, y2: H - padB, class: 'mark' }));
  svg.appendChild(el('text', { x: x(sw.target_price) + 4, y: y(0.12), class: 'lbl' }, `${L.price} ${money(sw.target_price, sw.currency)}`));
  // 95% line
  svg.appendChild(el('line', { x1: padL, x2: W - padR, y1: y(0.95), y2: y(0.95), class: 'mark mark--p5' }));
  svg.appendChild(el('text', { x: W - padR, y: y(0.95) + 14, class: 'lbl', 'text-anchor': 'end' }, L.conf));
  // legend
  svg.appendChild(el('text', { x: padL + 6, y: H - 4, class: 'lbl legend legend--hit' }, L.hit));
  svg.appendChild(el('text', { x: padL + 170, y: H - 4, class: 'lbl legend legend--loss' }, L.loss));

  const cross = el('line', { x1: 0, x2: 0, y1: padT, y2: H - padB, class: 'cross', visibility: 'hidden' });
  const dot = el('circle', { r: 5, class: 'cross-dot', visibility: 'hidden' });
  svg.appendChild(cross);
  svg.appendChild(dot);
  const hit = el('rect', { x: padL, y: padT, width: W - padL - padR, height: H - padT - padB, fill: 'transparent' });
  svg.appendChild(hit);

  const show = (i) => {
    const px = x(ps[i]);
    cross.setAttribute('x1', px);
    cross.setAttribute('x2', px);
    cross.setAttribute('visibility', 'visible');
    dot.setAttribute('cx', px);
    dot.setAttribute('cy', y(sw.p_hit_target[i]));
    dot.setAttribute('visibility', 'visible');
    if (onHover) onHover(i);
  };
  const idxFromEvent = (e) => {
    const r = svg.getBoundingClientRect();
    const sx = ((e.clientX - r.left) / r.width) * W;
    const t = (sx - padL) / (W - padL - padR);
    return Math.max(0, Math.min(ps.length - 1, Math.round(t * (ps.length - 1))));
  };
  hit.addEventListener('pointermove', (e) => show(idxFromEvent(e)));
  // default readout: first price that reaches 95%, else the target price
  const i95 = sw.p_hit_target.findIndex((v) => v >= 0.95);
  const iDefault = chosen != null ? chosen : i95 >= 0 ? i95 : ps.findIndex((p) => p >= sw.target_price);
  if (iDefault >= 0) show(iDefault);
}
