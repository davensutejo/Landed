let reducedMotion = false;

export function initA11y() {
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
  reducedMotion = mq.matches;
  mq.addEventListener('change', (e) => {
    reducedMotion = e.matches;
  });
}

export function isReducedMotion() {
  return reducedMotion;
}

export function isTouchDevice() {
  return window.matchMedia('(pointer: coarse)').matches;
}