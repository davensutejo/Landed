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

    // Width measured when it changes and the loop paused off screen. Reading offsetWidth every frame
    // forced a layout of the whole page whenever anything else had written a style earlier in the frame.
    let itemWidth = firstItem.offsetWidth || 600;
    new ResizeObserver(() => {
      itemWidth = firstItem.offsetWidth || 600;
    }).observe(firstItem);
    let onScreen = true;
    new IntersectionObserver((entries) => {
      onScreen = entries[0]?.isIntersecting ?? true;
    }).observe(track);

    gsap.ticker.add((_, deltaTime) => {
      if (!onScreen) return;
      const dt = Math.min(deltaTime, 50) / 16.67;
      state.x -= state.baseSpeed * state.dir * state.boost * state.hoverScale * dt;
      const wrapped = gsap.utils.wrap(-itemWidth, 0, state.x);
      track.style.transform = `translate3d(${wrapped.toFixed(2)}px, 0, 0)`;
    });

    marqueeControllers.push({ state, baseDir });
  });
}

let lastBoost = 1;
export function updateMarquees(velocity, direction) {
  if (isReducedMotion()) return;
  const speedFactor = 1 + Math.min(4, Math.abs(velocity) / 1500);
  // Called on every scroll update: only start new tweens when the boost really changes.
  const changed = Math.abs(speedFactor - lastBoost) > 0.15;
  marqueeControllers.forEach((ctrl) => {
    if (direction !== 0) {
      ctrl.state.dir = ctrl.baseDir * direction;
    }
  });
  if (!changed) return;
  lastBoost = speedFactor;
  marqueeControllers.forEach((ctrl) => {
    gsap.to(ctrl.state, {
      boost: speedFactor,
      duration: 0.25,
      overwrite: true,
      onComplete: () => {
        gsap.to(ctrl.state, { boost: 1, duration: 0.8, ease: 'power2.out', onComplete: () => (lastBoost = 1) });
      }
    });
  });
}