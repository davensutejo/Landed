import gsap from 'gsap';
import { isReducedMotion } from './a11y.js';

const marqueeControllers = [];

export function initMarquees() {
  const tracks = document.querySelectorAll('.marquee-track');

  tracks.forEach((track) => {
    const firstItem = track.querySelector('.marquee-item');
    if (!firstItem) return;

    // Duplicate items so track seamlessly wraps
    for (let i = 0; i < 3; i++) {
      track.appendChild(firstItem.cloneNode(true));
    }

    if (isReducedMotion()) return;

    const baseDir = parseFloat(track.dataset.marqueeDir || '1');
    const state = {
      x: 0,
      baseSpeed: 0.9,
      dir: baseDir,
      boost: 1,
      hoverScale: 1
    };

    track.addEventListener('pointerenter', () => {
      gsap.to(state, { hoverScale: 0.2, duration: 0.4, ease: 'power3.out' });
    });
    track.addEventListener('pointerleave', () => {
      gsap.to(state, { hoverScale: 1, duration: 0.4, ease: 'power3.out' });
    });

    gsap.ticker.add((_, deltaTime) => {
      const itemWidth = firstItem.offsetWidth || 600;
      const dt = Math.min(deltaTime, 50) / 16.67;
      state.x -= state.baseSpeed * state.dir * state.boost * state.hoverScale * dt;
      const wrapped = gsap.utils.wrap(-itemWidth, 0, state.x);
      track.style.transform = `translate3d(${wrapped.toFixed(2)}px, 0, 0)`;
    });

    marqueeControllers.push({ state, baseDir });
  });
}

export function updateMarquees(velocity, direction) {
  if (isReducedMotion()) return;
  const speedFactor = 1 + Math.min(4, Math.abs(velocity) / 1500);

  marqueeControllers.forEach((ctrl) => {
    if (direction !== 0) {
      ctrl.state.dir = ctrl.baseDir * direction;
    }
    gsap.to(ctrl.state, {
      boost: speedFactor,
      duration: 0.25,
      overwrite: true,
      onComplete: () => {
        gsap.to(ctrl.state, { boost: 1, duration: 0.8, ease: 'power2.out' });
      }
    });
  });
}