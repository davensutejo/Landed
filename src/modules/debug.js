const EXPECTED_CONCEPTS = [
  '1-dithering',
  '2-ascii-video',
  '3-infinite-canvas',
  '4-disco-logos',
  '5-renaissance-branding',
  '6-monet-backgrounds',
  '7-dark-gradient-hero',
  '8-pixel-loaders',
  '9-instrument-serif',
  '10-one-italic-word',
  '11-cream-backgrounds',
  '12-all-caps-eyebrows',
  '13-pulsing-live-dots',
  '14-sparkle-icons',
  '15-liquid-glass',
  '16-three-icon-cards',
  '17-decorative-flowcharts',
  '18-endless-marquees',
  '19-squircles',
  '20-pretext-wrapping'
];

export function initDebug() {
  // Development aid only: the concept overlay and QA checks run on ?debug=concepts, never by accident.
  if (new URLSearchParams(window.location.search).get('debug') !== 'concepts') return;
  // 1. Assert all 20 concepts exist in the DOM (preloader is #8, tracked at boot)
  const found = new Set(['8-pixel-loaders']);
  document.querySelectorAll('[data-concept]').forEach((el) => {
    found.add(el.getAttribute('data-concept'));
  });

  const missing = EXPECTED_CONCEPTS.filter((c) => !found.has(c));
  if (missing.length > 0) {
    console.error('[Medici QA] Missing data-concept tags:', missing);
  } else {
    console.info('[Medici QA] All 20 concepts verified in DOM.');
  }

  // 2. Assert every heading (h1, h2, h3) has EXACTLY ONE <em class="ital">
  const headings = document.querySelectorAll('h1, h2, h3');
  headings.forEach((h) => {
    const itals = h.querySelectorAll('em.ital');
    if (itals.length !== 1) {
      console.error(
        `[Medici QA] Heading italic rule violation (${itals.length} .ital found):`,
        h.textContent.trim()
      );
    }
  });

  let active = false;
  const chips = [];

  function toggleConceptOverlay() {
    active = !active;
    if (active) {
      document.querySelectorAll('[data-concept]').forEach((el) => {
        el.classList.add('debug-highlight');
        const chip = document.createElement('span');
        chip.className = 'debug-chip';
        chip.textContent = el.getAttribute('data-concept').toUpperCase();
        if (getComputedStyle(el).position === 'static') {
          el.style.position = 'relative';
        }
        el.appendChild(chip);
        chips.push(chip);
      });
    } else {
      document.querySelectorAll('[data-concept]').forEach((el) => {
        el.classList.remove('debug-highlight');
      });
      chips.splice(0).forEach((c) => c.remove());
    }
  }

  window.addEventListener('keydown', (e) => {
    if (
      (e.key === 'c' || e.key === 'C') &&
      !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName || '')
    ) {
      toggleConceptOverlay();
    }
  });

  if (new URLSearchParams(window.location.search).get('debug') === 'concepts') {
    toggleConceptOverlay();
  }
}