import gsap from 'gsap';
import { BAYER4 } from '../lib/dither.js';

// 24x14 bitmap of the Landed mark: an L standing on a ground line, with a sparkle above it
const MONOGRAM_COORDS = new Set([
  '8,3','8,4','8,5','8,6','8,7','8,8','8,9','8,10',
  '9,10','10,10','11,10','12,10','13,10','14,10','15,10','16,10','5,12','6,12','7,12','8,12','9,12','10,12','11,12','12,12','13,12','14,12','15,12','16,12','17,12','18,12','19,12','12,3','13,3','12,4','13,4'
]);

export function initPreloader() {
  const root = document.getElementById('preloader');
  const grid = document.getElementById('preloader-grid');
  const counterEl = document.getElementById('preloader-counter');
  const startTime = performance.now();

  const cols = 24;
  const rows = 14;
  const cells = [];

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cell = document.createElement('div');
      cell.className = 'preloader__cell';
      if (MONOGRAM_COORDS.has(`${c},${r}`)) {
        cell.classList.add('is-monogram');
      }
      const bayerVal = BAYER4[(r % 4) * 4 + (c % 4)] / 16;
      grid.appendChild(cell);
      cells.push({ el: cell, threshold: bayerVal });
    }
  }

  // Sort cells by Bayer threshold so loading itself is ordered dithering
  const sortedCells = [...cells].sort((a, b) => a.threshold - b.threshold);
  const state = { progress: 0, displayProgress: 0 };

  const updateVisuals = (val) => {
    const num = Math.round(val * 100);
    if (counterEl) {
      counterEl.textContent = String(num).padStart(4, '0');
    }
    const litCount = Math.floor(val * sortedCells.length);
    for (let i = 0; i < sortedCells.length; i++) {
      const item = sortedCells[i];
      if (i <= litCount) {
        item.el.style.opacity = '1';
        item.el.style.transform = 'scale(1)';
      }
    }
  };

  // Also populate the inline 8x8 pixel loader used in CTA button
  const inlineLoader = document.getElementById('cta-inline-loader');
  if (inlineLoader) {
    for (let i = 0; i < 64; i++) {
      const dot = document.createElement('i');
      dot.style.animationDelay = `${(i % 8) * 0.08}s`;
      inlineLoader.appendChild(dot);
    }
  }

  return {
    setProgress(p) {
      state.progress = Math.max(state.progress, p);
      gsap.to(state, {
        displayProgress: state.progress,
        duration: 0.45,
        ease: 'power2.out',
        onUpdate: () => updateVisuals(state.displayProgress)
      });
    },
    complete(onHeroStart) {
      return new Promise((resolve) => {
        const elapsed = performance.now() - startTime;
        const wait = Math.max(0, 1800 - elapsed);
        let heroTriggered = false;

        // Safety net: if rAF is throttled (background tab, headless capture),
        // never let the preloader block the page.
        setTimeout(() => {
          if (!root.isConnected) return;
          if (!heroTriggered && onHeroStart) onHeroStart();
          heroTriggered = true;
          root.remove();
          resolve();
        }, wait + 2500);

        setTimeout(() => {
          updateVisuals(1);
          const allDomCells = cells.map((c) => c.el);

          gsap.to(allDomCells, {
            scale: 0,
            opacity: 0,
            duration: 0.85,
            ease: 'medici',
            stagger: {
              grid: [rows, cols],
              from: 'center',
              amount: 0.55
            },
            onUpdate() {
              if (!heroTriggered && this.progress() >= 0.7) {
                heroTriggered = true;
                if (onHeroStart) onHeroStart();
              }
            },
            onComplete: () => {
              gsap.to(root, {
                opacity: 0,
                duration: 0.35,
                onComplete: () => {
                  root.remove();
                  resolve();
                }
              });
            }
          });
        }, wait);
      });
    }
  };
}