import gsap from 'gsap';
import { isReducedMotion } from './a11y.js';

export function twinkle(nodes) {
  if (isReducedMotion()) return;
  const list = Array.from(nodes);
  list.forEach((node) => {
    gsap.to(node, {
      scale: () => 0.65 + Math.random() * 0.55,
      rotation: () => (Math.random() > 0.5 ? 45 : -45),
      duration: () => 0.9 + Math.random() * 1.1,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut',
      delay: Math.random() * 1.5
    });
  });
}

export function initSparkles() {
  const icons = document.querySelectorAll('.icon-sparkle, .marquee-star');
  twinkle(icons);
}