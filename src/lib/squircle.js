export function buildSquirclePath(w, h, r, n = 4.6, inset = 0) {
  const iw = Math.max(4, w - inset * 2);
  const ih = Math.max(4, h - inset * 2);
  const radius = Math.min(Math.max(2, r - inset), iw / 2, ih / 2);
  const steps = 14;
  const pts = [];

  const pushCorner = (cx, cy, startAngle, endAngle) => {
    for (let i = 0; i <= steps; i++) {
      const t = startAngle + ((endAngle - startAngle) * i) / steps;
      const cos = Math.cos(t);
      const sin = Math.sin(t);
      const x = inset + cx + radius * Math.sign(cos) * Math.pow(Math.abs(cos), 2 / n);
      const y = inset + cy + radius * Math.sign(sin) * Math.pow(Math.abs(sin), 2 / n);
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
  };

  pushCorner(iw - radius, radius, -Math.PI / 2, 0);
  pushCorner(iw - radius, ih - radius, 0, Math.PI / 2);
  pushCorner(radius, ih - radius, Math.PI / 2, Math.PI);
  pushCorner(radius, radius, Math.PI, (3 * Math.PI) / 2);

  return `M ${pts.join(' L ')} Z`;
}

export function initSquircles() {
  const elements = document.querySelectorAll('.squircle');

  // Always sync --squircle-r so both the element and its ::before/::after outlines match radii
  elements.forEach((el) => {
    const r = parseFloat(el.dataset.squircle || '24');
    el.style.setProperty('--squircle-r', `${r}px`);
  });

  const supportsNative =
    typeof CSS !== 'undefined' &&
    typeof CSS.supports === 'function' &&
    CSS.supports('corner-shape', 'squircle');

  if (supportsNative) return;

  // Fallback for browsers without native corner-shape: squircle
  // Renders a matching superellipse SVG stroke on buttons & liquid-glass pills
  const ro = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const el = entry.target;
      const w = Math.round(el.offsetWidth);
      const h = Math.round(el.offsetHeight);
      if (w < 12 || h < 12) continue;

      const r = parseFloat(el.dataset.squircle || '24');
      el.style.setProperty('--squircle-r', `${r}px`);

      if (el.classList.contains('liquid-glass')) {
        el.classList.add('has-svg-squircle');
        const outerPath = buildSquirclePath(w, h, r, 4.6, 0);
        const ringPath = buildSquirclePath(w, h, r, 4.6, 1);
        el.style.clipPath = `path('${outerPath}')`;

        let svgRing = el.querySelector(':scope > .squircle-svg-ring');
        if (!svgRing) {
          svgRing = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          svgRing.setAttribute('class', 'squircle-svg-ring');
          svgRing.setAttribute('aria-hidden', 'true');
          svgRing.innerHTML = `<path fill="none" stroke="rgba(201, 162, 75, 0.65)" stroke-width="1.5" />`;
          el.appendChild(svgRing);
        }
        svgRing.setAttribute('viewBox', `0 0 ${w} ${h}`);
        const pathNode = svgRing.querySelector('path');
        if (pathNode) pathNode.setAttribute('d', ringPath);
      }
    }
  });

  elements.forEach((el) => ro.observe(el));
}