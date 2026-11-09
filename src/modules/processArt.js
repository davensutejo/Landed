import gsap from 'gsap';
import { DEMO } from '../data/landed.js';
import { waterfall } from '../lib/engine.js';
import { isReducedMotion } from '../lib/a11y.js';

// One purpose-drawn, looping illustration per agent-loop step. Each canvas only
// animates while on screen. Under reduced motion every scene is drawn once at its
// finished state.

const INK = '#14110F';
const PAPER = '#FAF6EC';
const GOLD = '#C9A24B';
const VERM = '#E8643C';
const MONO = '"JetBrains Mono", monospace';

const clamp01 = (v) => Math.min(1, Math.max(0, v));
const seg = (t, a, b) => clamp01((t - a) / (b - a));
const ease = (x) => 1 - Math.pow(1 - x, 3);

function frame(ctx, w, h) {
  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(20,17,15,0.06)';
  ctx.lineWidth = 1;
  for (let x = 20; x < w; x += 20) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  for (let y = 20; y < h; y += 20) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
}

function pill(ctx, x, y, w, h, r, fill, stroke) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
}

// I. Describe: the seller's sentence is typed into a chat bubble
const SENTENCE = ['500 ml blender, built-in battery,', '¥38, 0.6 kg. Price for Germany,', '25% margin?'];
const SENTENCE_LEN = SENTENCE.join('').length;

function drawDescribe(ctx, w, h, t) {
  frame(ctx, w, h);
  pill(ctx, 28, 28, w - 56, 126, 18, '#FFFFFF', INK);
  // tail
  ctx.beginPath();
  ctx.moveTo(w - 80, 154);
  ctx.lineTo(w - 62, 176);
  ctx.lineTo(w - 54, 154);
  ctx.closePath();
  ctx.fillStyle = '#FFFFFF';
  ctx.fill();
  ctx.strokeStyle = INK;
  ctx.stroke();

  let chars = Math.floor(ease(seg(t, 0.3, 3.6)) * SENTENCE_LEN);
  ctx.font = `15px ${MONO}`;
  ctx.fillStyle = INK;
  ctx.textBaseline = 'top';
  ctx.textAlign = 'left';
  let caret = null;
  SENTENCE.forEach((line, i) => {
    const part = line.slice(0, Math.max(0, chars));
    chars -= line.length;
    ctx.fillText(part, 46, 48 + i * 30);
    if (part.length > 0 && part.length <= line.length && chars <= 0 && !caret) {
      caret = { x: 46 + ctx.measureText(part).width + 2, y: 48 + i * 30 };
    }
  });
  if (caret && (Math.floor(t * 2.2) % 2 === 0 || t > 3.6)) {
    ctx.fillStyle = VERM;
    ctx.fillRect(caret.x, caret.y, 2, 18);
  }

  // Language chips + "untrusted" badge appear once typing is done
  const a = ease(seg(t, 3.7, 4.4));
  ctx.globalAlpha = a;
  pill(ctx, 28, 196 - (1 - a) * 8, 70, 28, 14, null, INK);
  pill(ctx, 106, 196 - (1 - a) * 8, 70, 28, 14, null, INK);
  ctx.font = `11px ${MONO}`;
  ctx.fillStyle = INK;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('中文', 63, 210 - (1 - a) * 8);
  ctx.fillText('ENGLISH', 141, 210 - (1 - a) * 8);
  pill(ctx, w - 214, 196 - (1 - a) * 8, 186, 28, 14, 'rgba(232,100,60,0.12)', VERM);
  ctx.fillStyle = VERM;
  ctx.fillText('PASTED TEXT = DATA, NOT ORDERS', w - 121, 210 - (1 - a) * 8);
  ctx.globalAlpha = 1;
}

// II. Classify: candidates narrow to one code after the clarifying question
const CANDIDATES = [
  { code: '8509.40', note: 'food grinders & mixers', win: true },
  { code: '8516.79', note: 'electro-thermic, other' },
  { code: '8509.90', note: 'parts (separate base)' }
];

function drawClassify(ctx, w, h, t) {
  frame(ctx, w, h);
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';

  // chapter path: 85 → 8509
  const path = ['85', '8509'];
  path.forEach((c, i) => {
    const a = ease(seg(t, i * 0.4, i * 0.4 + 0.5));
    ctx.globalAlpha = a;
    ctx.font = `13px ${MONO}`;
    ctx.fillStyle = INK;
    ctx.fillText(c, 24 + i * 52, 26);
    if (i === 0) {
      ctx.fillStyle = GOLD;
      ctx.fillText('›', 24 + 28, 26);
    }
  });
  ctx.globalAlpha = 1;

  const decided = ease(seg(t, 3.0, 3.7));
  CANDIDATES.forEach((c, i) => {
    const y = 52 + i * 44;
    const appear = ease(seg(t, 0.8 + i * 0.25, 1.4 + i * 0.25));
    const dim = c.win ? 0 : decided;
    ctx.globalAlpha = appear * (1 - dim * 0.7);
    pill(ctx, 24, y, w - 48, 36, 10, c.win && decided > 0.5 ? 'rgba(232,100,60,0.12)' : '#FFFFFF', c.win && decided > 0.5 ? VERM : 'rgba(20,17,15,0.4)');
    ctx.font = `14px ${MONO}`;
    ctx.fillStyle = INK;
    ctx.fillText(c.code, 40, y + 18);
    ctx.font = `12px ${MONO}`;
    ctx.fillStyle = 'rgba(20,17,15,0.6)';
    ctx.fillText(c.note, 120, y + 18);
    // reasoning bar fills before the answer lands, then favours the winner
    const base = ease(seg(t, 1.4 + i * 0.25, 2.4)) * (c.win ? 0.55 : 0.4 - i * 0.08);
    const bar = c.win ? base + decided * 0.4 : base * (1 - decided * 0.6);
    ctx.fillStyle = c.win ? VERM : GOLD;
    ctx.fillRect(w - 150, y + 14, 100 * bar, 8);
    if (c.win && decided > 0.8) {
      ctx.strokeStyle = VERM;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(w - 40, y + 18);
      ctx.lineTo(w - 35, y + 23);
      ctx.lineTo(w - 27, y + 13);
      ctx.stroke();
    }
  });
  ctx.globalAlpha = 1;

  // the one clarifying question
  const q = ease(seg(t, 2.2, 2.8));
  ctx.globalAlpha = q;
  pill(ctx, 24, 192, w - 48, 36, 18, INK, null);
  ctx.font = `12px ${MONO}`;
  ctx.fillStyle = PAPER;
  ctx.textAlign = 'center';
  ctx.fillText(t < 3.0 ? 'Is the motor built into the product?' : 'Self-contained motor: yes  →  8509.40', w / 2, 210);
  ctx.globalAlpha = 1;
}

// III. Compute: the real waterfall from the engine, bars grow in sequence
const WF = waterfall(DEMO, { categories: 2 });

function drawCompute(ctx, w, h, t) {
  frame(ctx, w, h);
  const steps = [...WF.steps.filter((s) => s.key !== 'vat'), { key: 'vat', label: 'VAT', value: WF.steps.find((s) => s.key === 'vat').value }];
  const n = steps.length + 1;
  const padL = 14;
  const base = h - 42;
  const top = 30;
  const slot = (w - padL * 2) / n;
  const bw = slot * 0.64;
  const scale = (base - top) / (WF.price * 1.05);
  let acc = 0;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  steps.forEach((s, i) => {
    const grow = ease(seg(t, 0.3 + i * 0.35, 0.9 + i * 0.35));
    const x = padL + i * slot + (slot - bw) / 2;
    const y0 = base - acc * scale;
    const hh = s.value * scale * grow;
    ctx.fillStyle = s.key === 'margin' ? VERM : s.key === 'duty' ? GOLD : INK;
    ctx.globalAlpha = s.key === 'cogs' || s.key === 'freight' || s.key === 'duty' || s.key === 'returns' ? 0.85 : 1;
    ctx.fillRect(x, y0 - hh, bw, hh);
    ctx.globalAlpha = 1;
    ctx.font = `9px ${MONO}`;
    ctx.fillStyle = 'rgba(20,17,15,0.7)';
    ctx.fillText(s.label.replace('Platform fee', 'Fee').replace(/EU €3 × \d/, 'Duty'), x + bw / 2, base + 16);
    if (grow > 0.95) ctx.fillText(`€${s.value.toFixed(0)}`, x + bw / 2, y0 - hh - 5);
    acc += s.value;
  });
  // total bar
  const x = padL + (n - 1) * slot + (slot - bw) / 2;
  const grow = ease(seg(t, 0.3 + steps.length * 0.35, 1.1 + steps.length * 0.35));
  ctx.fillStyle = PAPER;
  ctx.strokeStyle = INK;
  ctx.lineWidth = 2;
  ctx.fillRect(x, base - WF.price * scale * grow, bw, WF.price * scale * grow);
  ctx.strokeRect(x, base - WF.price * scale * grow, bw, WF.price * scale * grow);
  ctx.fillStyle = INK;
  ctx.font = `9px ${MONO}`;
  ctx.fillText('Price', x + bw / 2, base + 16);
  if (grow > 0.95) {
    ctx.font = `bold 11px ${MONO}`;
    ctx.fillText(`€${WF.price.toFixed(2)}`, x + bw / 2, base - WF.price * scale - 6);
  }
  ctx.strokeStyle = INK;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padL, base);
  ctx.lineTo(w - padL, base);
  ctx.stroke();
  ctx.font = `10px ${MONO}`;
  ctx.textAlign = 'left';
  ctx.fillStyle = 'rgba(20,17,15,0.55)';
  ctx.fillText('computed by code · no LLM', padL, 20);
}

// IV. Localize: a German listing card, then compliance flags pop in around it
const FLAGS = ['UN 3481', 'PI 967', 'FOOD CONTACT', 'GRI 3(b)'];

function drawLocalize(ctx, w, h, t) {
  frame(ctx, w, h);
  const cardW = 230;
  const cardH = 190;
  const x0 = 24;
  const y0 = 30;
  const a = ease(seg(t, 0, 0.6));
  ctx.globalAlpha = a;
  pill(ctx, x0, y0 + (1 - a) * 10, cardW, cardH, 14, '#FFFFFF', INK);
  ctx.fillStyle = 'rgba(20,17,15,0.1)';
  ctx.fillRect(x0 + 14, y0 + 14 + (1 - a) * 10, 70, 70); // product image slot
  ctx.fillStyle = VERM;
  ctx.beginPath();
  ctx.arc(x0 + 49, y0 + 49 + (1 - a) * 10, 14, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = INK;
  ctx.font = `bold 13px ${MONO}`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('Mixer to go', x0 + 96, y0 + 18 + (1 - a) * 10);
  ctx.font = `11px ${MONO}`;
  ctx.fillStyle = 'rgba(20,17,15,0.7)';
  ctx.fillText('500 ml · mit Akku', x0 + 96, y0 + 38 + (1 - a) * 10);
  ctx.globalAlpha = 1;
  // description lines "type" in
  for (let i = 0; i < 4; i++) {
    const lw = ease(seg(t, 0.6 + i * 0.3, 1.1 + i * 0.3)) * (i === 3 ? 100 : 190);
    ctx.fillStyle = 'rgba(20,17,15,0.25)';
    ctx.fillRect(x0 + 14, y0 + 104 + i * 18, lw, 7);
  }
  // flags
  FLAGS.forEach((f, i) => {
    const p = ease(seg(t, 1.8 + i * 0.5, 2.3 + i * 0.5));
    if (p <= 0) return;
    const fx = x0 + cardW + 14;
    const fy = 40 + i * 46;
    ctx.save();
    ctx.globalAlpha = p;
    ctx.translate(fx + (1 - p) * -24, fy);
    const warn = f === 'GRI 3(b)';
    pill(ctx, 0, 0, 132, 32, 16, warn ? 'rgba(201,162,75,0.2)' : 'rgba(232,100,60,0.12)', warn ? GOLD : VERM);
    ctx.fillStyle = warn ? GOLD : VERM;
    ctx.beginPath();
    ctx.arc(16, 16, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = `11px ${MONO}`;
    ctx.fillStyle = INK;
    ctx.textBaseline = 'middle';
    ctx.fillText(f, 30, 17);
    ctx.restore();
  });
  // connector from card to flags
  ctx.strokeStyle = 'rgba(20,17,15,0.25)';
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(x0 + cardW, y0 + cardH / 2);
  ctx.lineTo(x0 + cardW + 14, y0 + cardH / 2);
  ctx.stroke();
  ctx.setLineDash([]);
}

const SCENES = [
  { draw: drawDescribe, len: 6.0, done: 5 },
  { draw: drawClassify, len: 6.0, done: 4.5 },
  { draw: drawCompute, len: 6.5, done: 6 },
  { draw: drawLocalize, len: 7.0, done: 6 }
];

export function initProcessArt() {
  const canvases = document.querySelectorAll('.process-art-canvas');
  const reduced = isReducedMotion();

  canvases.forEach((canvas, idx) => {
    const scene = SCENES[idx];
    if (!scene) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;

    if (reduced) {
      scene.draw(ctx, w, h, scene.done);
      return;
    }

    let visible = false;
    let start = 0;
    new IntersectionObserver((entries) => {
      const now = entries[0]?.isIntersecting ?? false;
      if (now && !visible) start = gsap.ticker.time;
      visible = now;
    }).observe(canvas);

    scene.draw(ctx, w, h, scene.done); // never blank before first reveal
    gsap.ticker.add(() => {
      if (!visible) return;
      const t = (gsap.ticker.time - start) % scene.len;
      scene.draw(ctx, w, h, t);
    });
  });
}
