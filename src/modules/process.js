import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { initProcessArt } from './processArt.js';
import { isReducedMotion } from '../lib/a11y.js';

export function initProcess() {
  const pinWrap = document.getElementById('process-pin-wrap');
  const track = document.getElementById('process-track');
  const flowchart = document.getElementById('process-flowchart');
  const panels = gsap.utils.toArray('.process-panel');
  const flowPaths = document.querySelectorAll('.flow-path');
  const flowNodes = gsap.utils.toArray('.flow-node');
  const token = document.getElementById('flowchart-token');
  const mainPath = document.getElementById('flowchart-main-path');

  // Per-step illustrations (typed sentence, HS narrowing, engine waterfall, listing + flags)
  initProcessArt();

  if (isReducedMotion() || !pinWrap || !track) return;

  const mm = gsap.matchMedia();

  // Desktop Pinned Horizontal Scroll with generous 3.5x viewport scroll budget
  mm.add('(min-width: 768px)', () => {
    const getHorizontalOverflow = () =>
      Math.max(window.innerWidth * 0.6, track.scrollWidth - window.innerWidth);

    // Guarantee at least 3.4 viewport heights of scroll distance even on 2560px monitors
    const getPinScrollDistance = () =>
      Math.max(window.innerHeight * 3.4, getHorizontalOverflow() * 1.65);

    const tl = gsap.timeline({
      scrollTrigger: {
        trigger: pinWrap,
        start: 'top top',
        end: () => `+=${getPinScrollDistance()}`,
        pin: true,
        scrub: 1.1,
        anticipatePin: 1,
        invalidateOnRefresh: true,
        onToggle: (self) => {
          window.dispatchEvent(
            new CustomEvent('medici:process-pin', { detail: { active: self.isActive } })
          );
        },
        onUpdate: (self) => {
          // Light up decorative flowchart nodes as scroll progresses
          const activeIdx = Math.floor(self.progress * flowNodes.length);
          flowNodes.forEach((node, idx) => {
            node.classList.toggle('is-active', idx <= activeIdx);
          });
        }
      }
    });

    // 8% entry hold -> 84% horizontal travel -> 8% exit hold on Step IV
    tl.to(track, { x: 0, duration: 0.08, ease: 'none' }, 0);
    tl.to(
      track,
      {
        x: () => -getHorizontalOverflow(),
        duration: 0.84,
        ease: 'none'
      },
      0.08
    );
    tl.to(track, { x: () => -getHorizontalOverflow(), duration: 0.08, ease: 'none' }, 0.92);

    // Parallax the background flowchart at 0.45x track speed so it glides behind the cards
    if (flowchart) {
      tl.to(
        flowchart,
        {
          x: () => -getHorizontalOverflow() * 0.45,
          duration: 0.84,
          ease: 'none'
        },
        0.08
      );
    }

    // Scrub decorative flowchart paths and vermilion live token along main path
    gsap.fromTo(
      flowPaths,
      { drawSVG: '0%' },
      {
        drawSVG: '100%',
        ease: 'none',
        scrollTrigger: {
          trigger: pinWrap,
          start: 'top top',
          end: () => `+=${getPinScrollDistance()}`,
          scrub: 1.1,
          invalidateOnRefresh: true
        }
      }
    );

    if (token && mainPath) {
      gsap.to(token, {
        motionPath: {
          path: mainPath,
          align: mainPath,
          alignOrigin: [0.5, 0.5]
        },
        ease: 'none',
        scrollTrigger: {
          trigger: pinWrap,
          start: 'top top',
          end: () => `+=${getPinScrollDistance()}`,
          scrub: 1.1,
          invalidateOnRefresh: true
        }
      });
    }

    // Separate per-panel entrance animations driven by containerAnimation
    panels.forEach((panel, i) => {
      if (i === 0) return;
      gsap.from(panel, {
        y: 36,
        opacity: 0.3,
        scale: 0.94,
        duration: 0.5,
        ease: 'medici',
        scrollTrigger: {
          trigger: panel,
          containerAnimation: tl,
          start: 'left 88%',
          end: 'left 55%',
          scrub: true
        }
      });
    });
  });

  // Mobile Vertical Sequence Fallback
  mm.add('(max-width: 767px)', () => {
    panels.forEach((panel) => {
      gsap.from(panel, {
        y: 32,
        opacity: 0,
        duration: 0.85,
        ease: 'medici',
        scrollTrigger: {
          trigger: panel,
          start: 'top 85%'
        }
      });
    });
  });
}