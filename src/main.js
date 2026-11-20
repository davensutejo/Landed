import '@fontsource/instrument-serif/400.css';
import '@fontsource/instrument-serif/400-italic.css';
import '@fontsource-variable/instrument-sans';
import '@fontsource/jetbrains-mono/400.css';
// Chinese serif for headings, self-hosted (works on the mainland). Split by unicode-range, so a page only
// downloads the glyph chunks it uses, and an English visitor downloads none.
import '@fontsource/noto-serif-sc/400.css';
import '@fontsource/noto-serif-sc/600.css';

import './styles/tokens.css';
import './styles/base.css';
import './styles/glass.css';
import './styles/preloader.css';
import './styles/header.css';
import './styles/section.css';
import './styles/hero.css';
import './styles/marquee.css';
import './styles/showreel.css';
import './styles/logos.css';
import './styles/manifesto.css';
import './styles/process.css';
import './styles/canvas.css';
import './styles/cta.css';
import './styles/costcard.css';
import './styles/footer.css';
import './styles/cursor.css';
import './styles/debug.css';
import './styles/responsive.css';
import './styles/a11y.css';
import './styles/zh.css';

import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { SplitText } from 'gsap/SplitText';
import { DrawSVGPlugin } from 'gsap/DrawSVGPlugin';
import { MotionPathPlugin } from 'gsap/MotionPathPlugin';
import { Draggable } from 'gsap/Draggable';
import { InertiaPlugin } from 'gsap/InertiaPlugin';
import { Observer } from 'gsap/Observer';
import { CustomEase } from 'gsap/CustomEase';
import { Flip } from 'gsap/Flip';
import Lenis from 'lenis';

import { CONFIG, applyConfigToDOM } from './config.js';
import { applyStaticI18n } from './i18n.js';
import { initLangSwitch, showLangSwitch } from './lib/langTransition.js';
import { isReducedMotion, initA11y } from './lib/a11y.js';
import { initSquircles } from './lib/squircle.js';
import { initLiquidGlass } from './lib/liquidGlass.js';
import { initSparkles } from './lib/sparkle.js';
import { initMarquees, updateMarquees } from './lib/marquee.js';
import { initPreloader } from './modules/preloader.js';
import { initHeader } from './modules/header.js';
import { initCursor } from './modules/cursor.js';

gsap.registerPlugin(
  ScrollTrigger,
  SplitText,
  DrawSVGPlugin,
  MotionPathPlugin,
  Draggable,
  InertiaPlugin,
  Observer,
  CustomEase,
  Flip
);

CustomEase.create('medici', '0.16, 1, 0.3, 1');

const frameSubscribers = new Set();
export function onFrame(fn) {
  frameSubscribers.add(fn);
  return () => frameSubscribers.delete(fn);
}

async function boot() {
  document.documentElement.classList.remove('no-js');
  applyConfigToDOM(CONFIG);
  applyStaticI18n(); // before any module builds text, so everything is created in the page language
  initA11y();

  const preloader = initPreloader();
  preloader.setProgress(0.12);

  // Smooth scroll setup (disabled when prefers-reduced-motion)
  let lenis = null;
  if (!isReducedMotion()) {
    lenis = new Lenis({
      lerp: 0.09,
      smoothWheel: true,
      wheelMultiplier: 1.0
    });
    lenis.on('scroll', ScrollTrigger.update);
  }

  // Single unified RAF clock driven by gsap.ticker
  gsap.ticker.lagSmoothing(0);
  gsap.ticker.add((time, deltaTime, frame) => {
    if (lenis) lenis.raf(time * 1000);
    for (const fn of frameSubscribers) {
      fn(time, deltaTime, frame);
    }
  });

  // Top scroll progress bar
  const progressBar = document.getElementById('scroll-progress');
  ScrollTrigger.create({
    start: 0,
    end: 'max',
    onUpdate: (self) => {
      if (progressBar) {
        gsap.set(progressBar, { scaleX: self.progress });
      }
      updateMarquees(self.getVelocity(), self.direction);
    }
  });

  // Load fonts and core UI systems in parallel with dynamic heavy modules
  const fontsPromise = document.fonts ? document.fonts.ready : Promise.resolve();
  initSquircles();
  initLiquidGlass();
  initSparkles();
  initHeader(lenis);
  initCursor();
  initMarquees();

  preloader.setProgress(0.35);

  const [
    heroMod,
    showreelMod,
    logosMod,
    manifestoMod,
    processMod,
    canvasMod,
    ctaMod,
    footerMod,
    debugMod,
    costcardMod,
    consoleMod,
    moatMod,
    revealMod
  ] = await Promise.all([
    import('./modules/hero.js'),
    import('./modules/showreel.js'),
    import('./modules/logos.js'),
    import('./modules/manifesto.js'),
    import('./modules/process.js'),
    import('./modules/canvas.js'),
    import('./modules/cta.js'),
    import('./modules/footer.js'),
    import('./modules/debug.js'),
    import('./modules/costcard.js'),
    import('./modules/console.js'),
    import('./modules/moat.js'),
    import('./modules/reveal.js'),
    fontsPromise
  ]);

  preloader.setProgress(0.68);

  const heroCtrl = await heroMod.initHero(onFrame);
  preloader.setProgress(0.84);

  showreelMod.initShowreel(onFrame);
  logosMod.initLogos(onFrame);
  await manifestoMod.initManifesto(onFrame);
  processMod.initProcess();
  canvasMod.initCanvas(onFrame);
  ctaMod.initCta(onFrame);
  footerMod.initFooter();
  debugMod.initDebug();
  costcardMod.initCostCard();
  consoleMod.initConsole();
  moatMod.initMoat();
  initGlobalParallax();
  initLangSwitch({ lenis }); // every module has registered its language hook by now

  preloader.setProgress(1.0);
  await preloader.complete(() => {
    heroCtrl.playEntrance();
  });

  // cosmetic entrances: must never block or break the page, so they run last and are isolated
  try {
    revealMod.initReveal();
  } catch (err) {
    console.warn('reveal skipped', err);
    document.querySelectorAll('.section-header *, #logos-grid > *, .stats-strip > *, #evidence-list > *, .moat__grid > *, .sample-prompts > *').forEach((el) => {
      el.style.opacity = '';
      el.style.visibility = '';
    });
  }
  ScrollTrigger.refresh();
  showLangSwitch();
  window.addEventListener('orientationchange', () => {
    setTimeout(() => ScrollTrigger.refresh(), 250);
  });
}

function initGlobalParallax() {
  if (isReducedMotion()) return;
  document.querySelectorAll('[data-speed]').forEach((el) => {
    const speed = parseFloat(el.dataset.speed || '0');
    gsap.to(el, {
      yPercent: speed * 100,
      ease: 'none',
      scrollTrigger: {
        trigger: el.closest('.section') || el,
        start: 'top bottom',
        end: 'bottom top',
        scrub: 1
      }
    });
  });
}


boot();