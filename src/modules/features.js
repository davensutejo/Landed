import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { makeDitheredArt } from '../lib/dither.js';
import { isReducedMotion } from '../lib/a11y.js';

export function initFeatures() {
  const cards = document.querySelectorAll('.feature-card');

  cards.forEach((card, index) => {
    const glowCanvas = card.querySelector('.feature-card__dither-glow');
    if (glowCanvas) {
      makeDitheredArt(glowCanvas, index + 1, 'ember', 2);
    }

    if (isReducedMotion()) return;

    const iconPaths = card.querySelectorAll('.draw-icon');
    const star = card.querySelector('.feature-card__twinkle');

    card.addEventListener('pointerenter', () => {
      gsap.fromTo(
        iconPaths,
        { drawSVG: '0%' },
        { drawSVG: '100%', duration: 0.65, stagger: 0.08, ease: 'medici' }
      );
      if (star) {
        gsap.fromTo(
          star,
          { scale: 0.4, rotation: 0 },
          { scale: 1.25, rotation: 90, duration: 0.45, yoyo: true, repeat: 1 }
        );
      }
    });

    if (!window.matchMedia('(hover: hover) and (min-width: 1101px)').matches) return;

    card.addEventListener('pointermove', (e) => {
      const rect = card.getBoundingClientRect();
      const nx = (e.clientX - rect.left) / rect.width - 0.5;
      const ny = (e.clientY - rect.top) / rect.height - 0.5;
      gsap.to(card, {
        rotateY: nx * 10,
        rotateX: -ny * 10,
        duration: 0.35,
        ease: 'power3.out'
      });
    });

    card.addEventListener('pointerleave', () => {
      gsap.to(card, {
        rotateY: 0,
        rotateX: 0,
        duration: 0.5,
        ease: 'medici'
      });
    });
  });

  if (!isReducedMotion()) {
    gsap.from(cards, {
      y: 48,
      opacity: 0,
      duration: 1.0,
      stagger: 0.12,
      ease: 'medici',
      scrollTrigger: {
        trigger: '#features-row',
        start: 'top 82%'
      }
    });
  }
}