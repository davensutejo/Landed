// Live language switch with a "text dissolve": the text on screen softly blurs and fades out,
// headings first; the page swaps language underneath without moving; then the new text rises in
// with the same stagger. Only on-screen text animates, so the switch costs the same anywhere on
// the page, and nothing reloads. Reduced motion: the same swap, instantly.
//
// The animation uses the Web Animations API, not GSAP: it composes over whatever inline styles
// GSAP (scroll reveals, parallax) has set, and cancelling it leaves those styles exactly as they were.

import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { getLang, applyStatic, setDocumentLang, storeLang, langHooks, textFor } from '../i18n.js';
import { getConfig, applyConfigToDOM } from '../config.js';
import { isReducedMotion } from './a11y.js';

// Text-bearing blocks. Containers whose content is redrawn by code (charts, the manifesto
// layout, canvases, audit cards) animate as one unit.
const UNITS = [
  '#cc-waterfall', '#cc-mc', '#manifesto-lines', '.canvas-card', '.collab-cursor__tag',
  '.process-art-canvas', '#showreel-proc-canvas', '.footer__wordmark', '.marquee-item'
];
const TEXT = [
  'h1', 'h2', 'h3', 'p', 'li', 'figcaption', 'label', 'th', 'td', 'a', 'button',
  '[data-i18n]', '.eyebrow', '.folio-tag', '.folio-num', '.marginalia', '.cc-panel__title', '.cc-kpi__lbl',
  '.cc-prompt', '.stat-box__num', '.stat-box__label', '.build-tag', '.showreel__hud', '.scroll-cue',
  '.footer__status', '.footer__legal', '.flow-label', '.moat-art text'
];
const HEADING = 'h1, h2, h3, .display-title, .section-title, .footer__wordmark';
// Never animated: the switch itself, overlays, and screen-reader-only text
const SKIP = '.lang-fab, #custom-cursor, #preloader, .sr-only, .manifesto__sr-text, #mobile-menu-sheet, [aria-hidden="true"] .sr-only';

// The serif (Noto Serif SC) carries these in Chinese; their glyphs are fetched before the swap.
const SERIF_KEYS_SEL = '.display-title, .section-title, .moat-card__title, .process-panel__title, .marquee-item, .mobile-sheet__link, .footer__wordmark';

const OUT_MS = 300;
const IN_MS = 500;
// Blur is for text-sized blocks; a large unit (a chart, a card) only fades, so the effect stays
// cheap enough to run at full frame rate on a phone.
const BLUR_MAX_AREA = 120000;
const BODY_LAG = 80; // body text follows the headings by this much
const EASE_OUT = 'cubic-bezier(0.4, 0, 1, 1)';
const EASE_IN = 'cubic-bezier(0.22, 1, 0.36, 1)';

let busy = false;
let lenisRef = null;
const warmed = new Set();

/** Elements to animate: on screen, visible, and not inside another chosen element. */
function collect(knownOpacity) {
  const vh = window.innerHeight;
  const vw = window.innerWidth;
  const chosen = new Set();
  const all = document.querySelectorAll([...UNITS, ...TEXT].join(','));
  const units = new Set(document.querySelectorAll(UNITS.join(',')));
  for (const el of all) {
    if (el.closest(SKIP)) continue;
    // a unit swallows everything inside it; otherwise the outermost text block wins
    let p = el.parentElement;
    let inside = false;
    while (p && p !== document.body) {
      if (units.has(p) || chosen.has(p)) {
        inside = true;
        break;
      }
      p = p.parentElement;
    }
    if (inside) continue;
    chosen.add(el);
  }
  const out = [];
  for (const el of chosen) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    if (r.bottom <= 0 || r.top >= vh || r.right <= 0 || r.left >= vw) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const opacity = knownOpacity?.has(el) ? knownOpacity.get(el) : parseFloat(cs.opacity);
    if (!(opacity > 0.01)) continue;
    out.push({ el, opacity, top: r.top, left: r.left, heading: el.matches(HEADING), blur: r.width * r.height <= BLUR_MAX_AREA });
  }
  // reading order: top to bottom, then left to right
  out.sort((a, b) => (Math.abs(a.top - b.top) > 8 ? a.top - b.top : a.left - b.left));
  return out;
}

/** Stagger: headings lead, body text follows BODY_LAG ms behind; the whole wave stays short. */
function delays(items, step, maxSpread) {
  const heads = items.filter((i) => i.heading);
  const body = items.filter((i) => !i.heading);
  const hs = heads.length > 1 ? Math.min(step, maxSpread / heads.length) : 0;
  const bs = body.length > 1 ? Math.min(step, maxSpread / body.length) : 0;
  const d = new Map();
  heads.forEach((i, n) => d.set(i, n * hs));
  body.forEach((i, n) => d.set(i, BODY_LAG + n * bs));
  return d;
}

/**
 * What the reader is looking at: the text block at the centre of the viewport (or, inside a
 * pinned section, its pin-spacer), and where it sits. Elements that carry data-i18n survive the
 * swap (only their content changes), so they are preferred; the enclosing section is the fallback.
 */
function anchor() {
  const main = document.getElementById('main-content');
  const at = document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2);
  let fine = at && main?.contains(at) ? at.closest('[data-i18n]') || at : null;
  // pinned content does not move with scroll: hold the pin-spacer, which keeps the pin's progress
  const spacer = at?.closest('.pin-spacer');
  let coarse = spacer || null;
  if (spacer) fine = null;
  if (!coarse) for (let n = at; n && n !== main; n = n.parentElement) if (n.parentElement === main) coarse = n;
  if (!coarse && main) {
    for (const el of main.children) {
      const r = el.getBoundingClientRect();
      if (r.height > 0 && r.bottom > window.innerHeight * 0.5) {
        coarse = el;
        break;
      }
    }
  }
  const top = (el) => (el ? el.getBoundingClientRect().top : 0);
  return {
    fine,
    fineTop: top(fine),
    coarse,
    coarseTop: top(coarse),
    atStart: window.scrollY < 2,
    atEnd: window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2
  };
}

function restore(a) {
  if (!a) return;
  let delta = 0;
  if (a.atStart) delta = -window.scrollY; // at the top of the page, stay at the top
  else if (a.fine?.isConnected) delta = a.fine.getBoundingClientRect().top - a.fineTop;
  else if (a.coarse?.isConnected) delta = a.coarse.getBoundingClientRect().top - a.coarseTop;
  else return;
  lenisRef?.resize(); // its scroll limit is stale after the page changed height
  let y = window.scrollY + delta;
  if (a.atEnd) y = Math.max(y, document.documentElement.scrollHeight); // at the end of the page, stay at the end
  if (Math.abs(y - window.scrollY) < 1) return;
  if (lenisRef) lenisRef.scrollTo(y, { immediate: true, force: true });
  else window.scrollTo(0, y);
  ScrollTrigger.update();
}

/** Fetch the glyphs the target language needs before it is shown. */
function prepare(to) {
  const jobs = [];
  if (to === 'zh' && document.fonts && document.fonts.load && !warmed.has('zh')) {
    warmed.add('zh');
    const keys = new Set();
    document.querySelectorAll(SERIF_KEYS_SEL).forEach((el) => {
      const k = el.closest('[data-i18n]')?.dataset.i18n || el.querySelector('[data-i18n]')?.dataset.i18n;
      if (k) keys.add(k);
    });
    const text = [...keys].map((k) => textFor(k, 'zh')).join('') + '壹贰叁肆伍陆二三';
    for (const w of [400, 600]) jobs.push(document.fonts.load(`${w} 32px "Noto Serif SC"`, text).catch(() => {}));
  }
  for (const h of langHooks()) {
    if (h.prepare) {
      try {
        jobs.push(Promise.resolve(h.prepare(to)).catch(() => {}));
      } catch {
        /* a hook failing to prepare must not block the switch */
      }
    }
  }
  return Promise.all(jobs);
}

function swap(to) {
  setDocumentLang(to);
  applyConfigToDOM(getConfig());
  applyStatic(to);
  for (const h of langHooks()) {
    try {
      h.apply(to);
    } catch (e) {
      console.error('i18n hook failed', e);
    }
  }
  syncButtons();
}

function syncButtons() {
  const lang = getLang();
  document.querySelectorAll('[data-lang-switch]').forEach((btn) => {
    btn.setAttribute('aria-pressed', String(btn.dataset.langSwitch === lang));
  });
}

function announce(to) {
  const live = document.getElementById('lang-announce');
  if (!live) return;
  live.lang = to === 'zh' ? 'zh-CN' : 'en';
  live.textContent = to === 'zh' ? '已切换为中文' : 'Switched to English';
}

const timeout = (ms) => new Promise((r) => setTimeout(r, ms));
const frame = () => new Promise((r) => requestAnimationFrame(() => r()));
const settle = async () => {
  await frame();
  if (document.fonts?.ready) await Promise.race([document.fonts.ready, timeout(600)]);
  await frame();
};

export async function switchLang(to) {
  if (busy || to === getLang() || (to !== 'zh' && to !== 'en')) return;
  busy = true;
  const main = document.getElementById('main-content');
  const fab = document.querySelector('.lang-fab');
  main?.setAttribute('aria-busy', 'true');
  fab?.setAttribute('aria-busy', 'true');
  storeLang(to);
  const ready = prepare(to);

  try {
    if (isReducedMotion()) {
      await Promise.race([ready, timeout(300)]);
      const a = anchor();
      swap(to);
      ScrollTrigger.refresh();
      restore(a);
      await settle();
      ScrollTrigger.refresh();
      restore(a);
      return;
    }

    lenisRef?.stop();
    // 1. out: blur, fade, drift up a touch
    const before = collect();
    const known = new Map(before.map((i) => [i.el, i.opacity]));
    const dOut = delays(before, 22, 220);
    const outs = before.map((i) =>
      i.el.animate(
        [
          { opacity: i.opacity, filter: i.blur ? 'blur(0px)' : 'none', translate: '0 0' },
          { opacity: 0, filter: i.blur ? 'blur(6px)' : 'none', translate: '0 -6px' }
        ],
        { duration: OUT_MS, delay: dOut.get(i), easing: EASE_OUT, fill: 'forwards' }
      )
    );
    await Promise.all([Promise.all(outs.map((a) => a.finished.catch(() => {}))), Promise.race([ready, timeout(1500)])]);

    // 2. swap underneath, holding the reader's place
    const a = anchor();
    swap(to);
    ScrollTrigger.refresh();
    restore(a);
    // glyphs and layout that arrive a moment later (font chunks, re-flowed manifesto) can still
    // move things: settle while the text is invisible, then hold the place again
    await settle();
    ScrollTrigger.refresh();
    restore(a);

    // 3. in: the new text rises from a soft blur
    const after = collect(known);
    const dIn = delays(after, 30, 260);
    const ins = after.map((i) =>
      i.el.animate(
        [
          { opacity: 0, filter: i.blur ? 'blur(8px)' : 'none', translate: '0 10px' },
          { opacity: i.opacity, filter: i.blur ? 'blur(0px)' : 'none', translate: '0 0' }
        ],
        { duration: IN_MS, delay: dIn.get(i), easing: EASE_IN, fill: 'backwards' }
      )
    );
    outs.forEach((o) => o.cancel());
    await Promise.all(ins.map((x) => x.finished.catch(() => {})));
  } finally {
    lenisRef?.start();
    main?.removeAttribute('aria-busy');
    fab?.removeAttribute('aria-busy');
    announce(to);
    busy = false;
  }
}

/** Wire the floating switch. Called once from boot(). */
export function initLangSwitch({ lenis } = {}) {
  lenisRef = lenis || null;
  syncButtons();
  document.querySelectorAll('[data-lang-switch]').forEach((btn) => {
    btn.addEventListener('click', () => switchLang(btn.dataset.langSwitch));
    // warm the other language's glyphs as soon as the reader reaches for the switch
    const warm = () => {
      if (btn.dataset.langSwitch !== getLang()) prepare(btn.dataset.langSwitch);
    };
    btn.addEventListener('pointerenter', warm, { once: true });
    btn.addEventListener('focus', warm, { once: true });
  });
}

// Controls the switch must never sit on top of. While one passes under it, the switch steps
// aside (fades out); it comes back once the control has scrolled past. Never while it has focus.
const DODGE = '#cta-email, .cta__form button, .sample-chip, #agent-console, .cc-reset, #cc-fx, #cc-ret, #cc-set-toggle, .hero__ctas a, .footer__col a';

function watchOverlap(fab) {
  let queued = false;
  const check = () => {
    queued = false;
    if (fab.matches(':focus-within')) return fab.classList.remove('is-dodging');
    const f = fab.getBoundingClientRect();
    const pad = 6;
    const over = [...document.querySelectorAll(DODGE)].some((el) => {
      if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.right > f.left - pad && r.left < f.right + pad && r.bottom > f.top - pad && r.top < f.bottom + pad;
    });
    fab.classList.toggle('is-dodging', over);
  };
  const queue = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(check);
  };
  window.addEventListener('scroll', queue, { passive: true });
  window.addEventListener('resize', queue);
  fab.addEventListener('focusin', queue);
  fab.addEventListener('focusout', queue);
  queue();
}

/** Reveal the switch once the preloader is gone. */
export function showLangSwitch() {
  const fab = document.querySelector('.lang-fab');
  if (!fab) return;
  fab.classList.add('is-ready');
  watchOverlap(fab);
}
