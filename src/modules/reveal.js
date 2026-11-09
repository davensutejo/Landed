// Entrance animations for section headers and card groups that have no animation of their own.
// Content is only hidden by JS right before it is animated, so without JS (or with reduced
// motion) everything is simply visible.
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { isReducedMotion } from '../lib/a11y.js';

const HEADER_PARTS = ':scope > .folio-tag, :scope > .eyebrow, :scope > .section-title, :scope > .section-lede';
const GROUPS = ['#logos-grid', '.stats-strip', '#evidence-list', '.moat__grid', '.sample-prompts'];

export function initReveal() {
  if (isReducedMotion()) return;
  gsap.registerPlugin(ScrollTrigger);

  document.querySelectorAll('.section:not(#hero) .section-header').forEach((header) => {
    const parts = [...header.querySelectorAll(HEADER_PARTS)];
    if (!parts.length) return;
    gsap.set(parts, { autoAlpha: 0, y: 28 });
    // the marginalia has its own scroll parallax on `y`, so it only fades
    const margin = header.querySelector(':scope > .marginalia');
    if (margin) gsap.set(margin, { autoAlpha: 0 });
    const tl = gsap.timeline({ scrollTrigger: { trigger: header, start: 'top 85%', once: true } });
    tl.to(parts, { autoAlpha: 1, y: 0, duration: 0.95, ease: 'power3.out', stagger: 0.1 });
    if (margin) tl.to(margin, { autoAlpha: 1, duration: 0.8 }, 0.3);
  });

  GROUPS.forEach((sel) => {
    const box = document.querySelector(sel);
    if (!box || !box.children.length) return;
    const items = [...box.children];
    gsap.set(items, { autoAlpha: 0, y: 22 });
    gsap.to(items, {
      autoAlpha: 1,
      y: 0,
      duration: 0.75,
      ease: 'power3.out',
      stagger: Math.min(0.08, 0.6 / items.length),
      scrollTrigger: { trigger: box, start: 'top 88%', once: true },
      clearProps: 'transform'
    });
  });
}
