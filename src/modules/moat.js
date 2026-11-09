import gsap from 'gsap';
import { isReducedMotion } from '../lib/a11y.js';

// Moat cards: diagrams start animating when scrolled into view; cards tilt toward
// the pointer on hover. Reduced motion gets the static diagrams and no tilt.
export function initMoat() {
  const cards = document.querySelectorAll('.moat-card');
  if (!cards.length) return;

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add('is-in');
          io.unobserve(e.target);
        }
      });
    },
    { threshold: 0.35 }
  );
  cards.forEach((c) => io.observe(c));

  if (isReducedMotion() || !window.matchMedia('(hover: hover)').matches) return;

  cards.forEach((card) => {
    card.addEventListener('pointermove', (e) => {
      const r = card.getBoundingClientRect();
      const nx = (e.clientX - r.left) / r.width - 0.5;
      const ny = (e.clientY - r.top) / r.height - 0.5;
      gsap.to(card, { rotateY: nx * 6, rotateX: -ny * 6, y: -4, duration: 0.4, ease: 'power3.out', transformPerspective: 900 });
    });
    card.addEventListener('pointerleave', () => {
      gsap.to(card, { rotateY: 0, rotateX: 0, y: 0, duration: 0.6, ease: 'medici' });
    });
  });
}
