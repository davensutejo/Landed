import gsap from 'gsap';
import { isReducedMotion, isTouchDevice } from '../lib/a11y.js';

export function initCursor() {
  const cursor = document.getElementById('custom-cursor');
  const labelEl = document.getElementById('custom-cursor-label');
  if (!cursor || isReducedMotion() || isTouchDevice()) {
    if (cursor) cursor.style.display = 'none';
    return;
  }

  const xTo = gsap.quickTo(cursor, 'x', { duration: 0.18, ease: 'power3.out' });
  const yTo = gsap.quickTo(cursor, 'y', { duration: 0.18, ease: 'power3.out' });

  window.addEventListener(
    'pointermove',
    (e) => {
      xTo(e.clientX);
      yTo(e.clientY);
    },
    { passive: true }
  );

  document.querySelectorAll('[data-cursor]').forEach((target) => {
    target.addEventListener('pointerenter', () => {
      const text = target.getAttribute('data-cursor') || 'OPEN';
      if (labelEl) labelEl.textContent = text;
      cursor.classList.add('is-labeled');
    });
    target.addEventListener('pointerleave', () => {
      cursor.classList.remove('is-labeled');
    });
  });
}