import gsap from 'gsap';
import { isReducedMotion } from '../lib/a11y.js';

export function initFooter() {
  const footer = document.getElementById('site-footer');
  const letters = document.querySelectorAll('#footer-wordmark span');
  if (!footer || !letters.length) return;

  // Per-letter hover lift handled by GSAP so CSS transform transitions never conflict
  letters.forEach((span) => {
    span.addEventListener('pointerenter', () => {
      if (isReducedMotion()) return;
      gsap.to(span, { y: -16, duration: 0.4, ease: 'medici', overwrite: 'auto' });
    });
    span.addEventListener('pointerleave', () => {
      if (isReducedMotion()) return;
      gsap.to(span, { y: 0, duration: 0.45, ease: 'medici', overwrite: 'auto' });
    });
  });

  if (isReducedMotion()) return;

  gsap.set(letters, { y: 60, opacity: 0 });

  const io = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting) {
        gsap.to(letters, {
          y: 0,
          opacity: 1,
          duration: 1.0,
          stagger: 0.06,
          ease: 'medici',
          overwrite: 'auto'
        });
        io.disconnect();
      }
    },
    { threshold: 0.15 }
  );

  io.observe(footer);
}