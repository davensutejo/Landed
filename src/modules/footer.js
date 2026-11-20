import gsap from 'gsap';
import { isReducedMotion } from '../lib/a11y.js';
import { onLang } from '../i18n.js';

export function initFooter() {
  const footer = document.getElementById('site-footer');
  const wordmark = document.getElementById('footer-wordmark');
  // Queried on use: a language switch replaces the letters (Landed ↔ 到岸)
  const letters = () => (wordmark ? wordmark.querySelectorAll(':scope > span') : []);
  if (!footer || !wordmark || !letters().length) return;

  // Per-letter hover lift handled by GSAP so CSS transform transitions never conflict
  const letterOf = (e) => {
    const span = e.target instanceof Element ? e.target.closest('#footer-wordmark > span') : null;
    return span && wordmark.contains(span) ? span : null;
  };
  wordmark.addEventListener('pointerover', (e) => {
    const span = letterOf(e);
    if (!span || isReducedMotion() || (e.relatedTarget && span.contains(e.relatedTarget))) return;
    gsap.to(span, { y: -16, duration: 0.4, ease: 'medici', overwrite: 'auto' });
  });
  wordmark.addEventListener('pointerout', (e) => {
    const span = letterOf(e);
    if (!span || isReducedMotion() || (e.relatedTarget && span.contains(e.relatedTarget))) return;
    gsap.to(span, { y: 0, duration: 0.45, ease: 'medici', overwrite: 'auto' });
  });

  if (isReducedMotion()) return;

  let revealed = false;
  gsap.set(letters(), { y: 60, opacity: 0 });
  // New letters wait hidden for the rise, like the ones they replace
  onLang({
    apply: () => {
      if (!revealed) gsap.set(letters(), { y: 60, opacity: 0 });
    }
  });

  const io = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting) {
        revealed = true;
        gsap.to(letters(), {
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
