// Landing-page language: 'zh' or 'en'. Shared with the agent page through the same storage key
// ('landed-lang'), so a choice made on either page carries to the other.
//
// English is the markup itself: index.html is the original English page, untouched. The Chinese copy
// lives in i18n/zh.js and is applied over it. The language can change while the page is open (no
// reload): static text is swapped from the remembered English or the zh dictionary, and modules that
// draw their own text (canvases, cost card, manifesto layout) re-render through onLang() hooks.
// The inline script in index.html <head> sets <html lang> and data-lang before first paint, so the
// zh typography in styles/zh.css applies with no flash.

import { ZH, ZH_ATTR } from './i18n/zh.js';

export const STORAGE_KEY = 'landed-lang';

function detect() {
  try {
    const q = new URLSearchParams(location.search).get('lang');
    if (q === 'zh' || q === 'en') return q;
  } catch {
    /* no URL API */
  }
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'zh' || v === 'en') return v;
  } catch {
    /* storage blocked */
  }
  try {
    return /^zh/i.test(navigator.language || '') ? 'zh' : 'en';
  } catch {
    return 'en';
  }
}

const initial = document.documentElement.dataset.lang;
let lang = initial === 'zh' || initial === 'en' ? initial : detect();

export const getLang = () => lang;
export const isZh = () => lang === 'zh';
/** Pick the string for the current language (evaluated at call time). */
export const L = (en, zh) => (lang === 'zh' ? zh : en);

// ---------------------------------------------------------------------------
// Modules that build text in code register here.
//   prepare(lang): optional, async; runs while the old text is fading out (e.g. load font glyphs)
//   apply(lang):   re-render in the new language; runs after the static swap, before the fade-in
const hooks = [];
export function onLang(hook) {
  hooks.push(hook);
}
export const langHooks = () => hooks;

// ---------------------------------------------------------------------------
// English originals, keyed by i18n key so marquee clones (which copy the data-i18n attribute) restore too.
const EN_HTML = new Map();
const EN_ATTR = new Map(); // "attr|key" -> value
const EN_FOLIO = new WeakMap();
let EN_DESC = null;
let captured = false;

const FOLIO_ZH = { 'I.': '壹', 'I.b': '壹·二', 'I.c': '壹·三', 'II.': '贰', 'III.': '叁', 'IV.': '肆', 'V.': '伍', 'VI.': '陆' };

function attrPairs(el) {
  return el.dataset.i18nAttr
    .split(';')
    .map((pair) => pair.split(':').map((s) => s.trim()))
    .filter(([a, k]) => a && k);
}

/** Remember the English markup once, before anything is translated. */
function captureEnglish() {
  if (captured) return;
  captured = true;
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const k = el.dataset.i18n;
    if (!EN_HTML.has(k)) EN_HTML.set(k, el.innerHTML);
  });
  document.querySelectorAll('[data-i18n-attr]').forEach((el) => {
    attrPairs(el).forEach(([a, k]) => {
      const id = `${a}|${k}`;
      if (!EN_ATTR.has(id)) EN_ATTR.set(id, el.getAttribute(a));
    });
  });
  document.querySelectorAll('.folio-tag').forEach((el) => EN_FOLIO.set(el, el.textContent));
  EN_DESC = document.querySelector('meta[name="description"]')?.getAttribute('content') ?? null;
}

// Children that modules hold references to (inputs, data-cc output slots, ids) survive a swap:
// the new markup's matching placeholder is replaced by the existing node, keeping its listeners,
// state and current value.
function liveKey(n) {
  if (n.id) return `#${n.id}`;
  if (n.dataset && n.dataset.cc) return `cc:${n.dataset.cc}`;
  return null;
}
function swapHTML(el, html) {
  if (el.innerHTML === html) return;
  const live = new Map();
  el.querySelectorAll('[id], [data-cc]').forEach((n) => {
    const k = liveKey(n);
    if (k) live.set(k, n);
  });
  el.innerHTML = html;
  if (!live.size) return;
  el.querySelectorAll('[id], [data-cc]').forEach((n) => {
    const old = live.get(liveKey(n));
    if (old && old !== n) n.replaceWith(old);
  });
}

/** Write every static string for `to`, from the zh dictionary or the remembered English. */
export function applyStatic(to) {
  captureEnglish();
  const zh = to === 'zh';
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const k = el.dataset.i18n;
    const v = zh ? ZH[k] : EN_HTML.get(k);
    if (v != null) {
      swapHTML(el, v);
      // GSAP SplitText labels the element it splits (the hero heading) with its text. Keep that
      // label in step with the new text, or a screen reader would read the old language.
      if (el.hasAttribute('aria-label') && !/(^|;)\s*aria-label:/.test(el.dataset.i18nAttr || '')) {
        el.setAttribute('aria-label', el.textContent.trim());
      }
    } else if (zh) console.warn('i18n: missing zh for', k);
  });
  document.querySelectorAll('[data-i18n-attr]').forEach((el) => {
    attrPairs(el).forEach(([a, k]) => {
      const v = zh ? ZH_ATTR[k] : EN_ATTR.get(`${a}|${k}`);
      if (v == null) {
        if (zh) console.warn('i18n: missing zh attr', k);
        return;
      }
      if (el.getAttribute(a) !== v) el.setAttribute(a, v);
    });
  });
  // Section folios: Chinese ordinals (壹 贰 叁) instead of Roman numerals
  document.querySelectorAll('.folio-tag').forEach((el) => {
    const en = EN_FOLIO.get(el) ?? el.textContent;
    const v = zh ? FOLIO_ZH[en.trim()] || en : en;
    if (el.textContent !== v) el.textContent = v;
  });
  if (zh) {
    document.title = ZH_ATTR['meta.title'];
    document.querySelector('meta[name="description"]')?.setAttribute('content', ZH_ATTR['meta.description']);
  } else if (EN_DESC != null) {
    document.querySelector('meta[name="description"]')?.setAttribute('content', EN_DESC);
  }
}

/** Plain text of a static key in either language (for preloading glyphs before the swap). */
export function textFor(key, to) {
  captureEnglish();
  const html = to === 'zh' ? ZH[key] : EN_HTML.get(key);
  if (html == null) return '';
  const t = document.createElement('template');
  t.innerHTML = html;
  return t.content.textContent.replace(/\s+/g, ' ').trim();
}

/** Set <html lang> / data-lang and the in-memory language. Does not touch text. */
export function setDocumentLang(to) {
  lang = to;
  const root = document.documentElement;
  root.lang = to === 'zh' ? 'zh-CN' : 'en';
  root.dataset.lang = to;
}

export function storeLang(to) {
  try {
    localStorage.setItem(STORAGE_KEY, to);
  } catch {
    /* storage blocked: the choice lasts for this page view */
  }
  // A ?lang= link would win over the stored choice on the next reload; drop it so the choice sticks.
  try {
    const url = new URL(location.href);
    if (url.searchParams.has('lang')) {
      url.searchParams.delete('lang');
      history.replaceState(history.state, '', url.toString());
    }
  } catch {
    /* no history API */
  }
}

/** First paint: called once from boot(), before any module builds text. */
export function applyStaticI18n() {
  setDocumentLang(lang);
  captureEnglish();
  if (lang === 'zh') applyStatic('zh');
}
