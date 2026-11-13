// Deterministic landed-cost engine + seeded Monte Carlo (browser mirror of the
// Python engine). No LLM touches anything in this file.
//
// Price P is VAT-inclusive (EU B2C). Net revenue N = P / (1 + vat).
// Goods cost   G = (COGS + freight) / fx + duty          (EUR per unit)
// Returns      R = r * G                                  (returned unit written off)
// Fee          F = feeRate * P
// Profit       π = N − F − G − R
// Margin       m = π / N
// Because π is linear in P, the price that hits target margin m* is closed-form:
//   P* = G(1 + r) / (1/(1+vat) − feeRate − m*/(1+vat))

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function normal(rand) {
  let u = 0;
  while (u === 0) u = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand());
}

// Marsaglia–Tsang gamma sampler (shape ≥ 1), used to draw Beta variates.
function gamma(rand, k) {
  const d = k - 1 / 3;
  const c = 1 / Math.sqrt(9 * d);
  for (;;) {
    let x, v;
    do {
      x = normal(rand);
      v = 1 + c * x;
    } while (v <= 0);
    v = v * v * v;
    const u = rand();
    if (u < 1 - 0.0331 * x ** 4) return d * v;
    if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
  }
}

function beta(rand, a, b) {
  const x = gamma(rand, a);
  return x / (x + gamma(rand, b));
}

function quantile(sorted, q) {
  const i = (sorted.length - 1) * q;
  const lo = Math.floor(i);
  const hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

// Same refusals as the Python engine: never return a number it cannot stand behind.
export class EngineError extends Error {}

function denom(p) {
  if (!(p.targetMargin > 0 && p.targetMargin < 0.8)) throw new EngineError('target margin must be between 0 and 0.8');
  const d = 1 / (1 + p.vat) - p.feeRate - p.targetMargin / (1 + p.vat);
  if (d <= 0) throw new EngineError('Target margin is unreachable with these fee and VAT rates');
  return d;
}

const feeFixed = (p) => p.feeFixed ?? 0;           // per-order platform fee, EUR
const flatThreshold = (p) => p.flatThreshold ?? 150; // EU flat EUR 3 regime ceiling

// Deterministic point estimate (mean FX, mean return rate).
export function waterfall(p, { categories }) {
  const fx = p.fxMean;
  const r = p.returnAlpha / (p.returnAlpha + p.returnBeta);
  const cogs = p.cogsCny / fx;
  const freight = (p.freightCnyPerKg * p.weightKg) / fx;
  const duty = p.eu3PerCategory * categories;
  const G = cogs + freight + duty;
  const returns = r * G;
  const price = (G + returns + feeFixed(p)) / denom(p);
  if (price > flatThreshold(p)) {
    // Above EUR 150 the conventional duty of the exact code applies; like the backend, abstain.
    throw new EngineError(`The price would be about EUR ${Math.round(price)}, above the EUR ${flatThreshold(p)} ceiling of the flat EUR 3 duty`);
  }
  const net = price / (1 + p.vat);
  const vat = price - net;
  const fee = p.feeRate * price + feeFixed(p);
  const margin = net - fee - G - returns;
  return {
    price,
    net,
    marginPct: margin / net,
    steps: [
      { key: 'cogs', label: 'COGS', value: cogs, src: null },
      { key: 'freight', label: 'Freight', value: freight, src: 'freight' },
      { key: 'duty', label: `EU €3 × ${categories}`, value: duty, src: 'eu3' },
      { key: 'returns', label: 'Returns', value: returns, src: 'returns' },
      { key: 'fee', label: 'Platform fee', value: fee, src: 'fee' },
      { key: 'vat', label: `VAT ${+(p.vat * 100).toFixed(1)}%`, value: vat, src: 'deVat' },
      { key: 'margin', label: 'Margin', value: margin, src: null }
    ]
  };
}

// Monte Carlo over FX and return rate. Returns the margin distribution at a
// fixed list price, plus the 95% risk-buffered floor price.
export function simulate(p, { categories, price }) {
  const rand = mulberry32(p.seed + categories);
  const n = p.paths;
  const margins = new Float64Array(n);
  const required = new Float64Array(n);
  const net = price / (1 + p.vat);
  const fee = p.feeRate * price + feeFixed(p);
  const D = denom(p);
  let losses = 0;
  for (let i = 0; i < n; i++) {
    const fx = p.fxMean * (1 + p.fxSd * normal(rand));
    const r = beta(rand, p.returnAlpha, p.returnBeta);
    const G = (p.cogsCny + p.freightCnyPerKg * p.weightKg) / fx + p.eu3PerCategory * categories;
    const profit = net - fee - G * (1 + r);
    margins[i] = profit / net;
    required[i] = (G * (1 + r) + feeFixed(p)) / D;
    if (profit < 0) losses++;
  }
  margins.sort();
  required.sort();
  return {
    margins,
    p5: quantile(margins, 0.05),
    p50: quantile(margins, 0.5),
    pBelowTarget: margins.filter((m) => m < p.targetMargin).length / n,
    pLoss: losses / n,
    floor95: quantile(required, 0.95)
  };
}

// Deterministic shock table at a fixed price.
export function stress(p, { categories, price }) {
  const margin = (q) => {
    const net = price / (1 + q.vat);
    const r = q.returnAlpha / (q.returnAlpha + q.returnBeta);
    const G = (q.cogsCny + q.freightCnyPerKg * q.weightKg) / q.fxMean + q.eu3PerCategory * categories;
    return (net - q.feeRate * price - feeFixed(q) - G * (1 + r)) / net;
  };
  const baseRet = p.returnAlpha / (p.returnAlpha + p.returnBeta);
  const stressRet = Math.max(0.15, baseRet + 0.1);
  return [
    { label: 'Base case', m: margin(p) },
    { label: 'CNY +5% vs destination currency', m: margin({ ...p, fxMean: p.fxMean * 0.95 }) },
    { label: `Return rate ${Math.round(stressRet * 100)}%`, m: margin({ ...p, returnAlpha: 100 * stressRet, returnBeta: 100 * (1 - stressRet) }) },
    { label: 'Freight +30% (peak season)', m: margin({ ...p, freightCnyPerKg: p.freightCnyPerKg * 1.3 }) },
    { label: 'Add a different kind of item, e.g. a free gift (+EUR 3 duty)', m: margin({ ...p, eu3PerCategory: p.eu3PerCategory + 3 / categories }) }
  ];
}
