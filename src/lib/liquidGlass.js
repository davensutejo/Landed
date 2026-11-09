const mapCache = new Map();

function createDisplacementDataURL(w, h, bevel = 16) {
  const key = `${w}x${h}`;
  if (mapCache.has(key)) return mapCache.get(key);

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(w, h);
  const d = img.data;

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const dxLeft = x;
      const dxRight = w - 1 - x;
      const dyTop = y;
      const dyBottom = h - 1 - y;
      const minDist = Math.min(dxLeft, dxRight, dyTop, dyBottom);

      let rx = 128;
      let ry = 128;

      if (minDist < bevel) {
        const norm = 1 - minDist / bevel;
        const profile = Math.sin(norm * (Math.PI / 2));
        const dirX = dxLeft < dxRight ? -1 : 1;
        const dirY = dyTop < dyBottom ? -1 : 1;
        rx = Math.round(128 + dirX * profile * 64);
        ry = Math.round(128 + dirY * profile * 64);
      }

      const i = (y * w + x) * 4;
      d[i] = rx;
      d[i + 1] = ry;
      d[i + 2] = 128;
      d[i + 3] = 255;
    }
  }

  ctx.putImageData(img, 0, 0);
  const url = canvas.toDataURL();
  mapCache.set(key, url);
  return url;
}

export function initLiquidGlass() {
  const isChromium = !!window.chrome && /Chrome|Chromium|Edg/.test(navigator.userAgent);
  const defs = document.getElementById('liquid-glass-defs');
  const elements = document.querySelectorAll('.liquid-glass');

  // Pointer angle tracking for rotating specular ring
  window.addEventListener(
    'pointermove',
    (e) => {
      elements.forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.bottom < 0 || rect.top > window.innerHeight) return;
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const angle = (Math.atan2(e.clientY - cy, e.clientX - cx) * 180) / Math.PI + 90;
        el.style.setProperty('--pointer-angle', `${angle.toFixed(1)}deg`);
      });
    },
    { passive: true }
  );

  if (!isChromium || !defs) return;

  const ro = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const el = entry.target;
      const id = el.dataset.glassId;
      if (!id) continue;
      const w = Math.max(32, Math.round(el.offsetWidth));
      const h = Math.max(24, Math.round(el.offsetHeight));
      const filterId = `lg-${id}`;
      const dataUrl = createDisplacementDataURL(w, h, 16);

      let filterEl = document.getElementById(filterId);
      if (!filterEl) {
        filterEl = document.createElementNS('http://www.w3.org/2000/svg', 'filter');
        filterEl.setAttribute('id', filterId);
        filterEl.setAttribute('x', '0%');
        filterEl.setAttribute('y', '0%');
        filterEl.setAttribute('width', '100%');
        filterEl.setAttribute('height', '100%');
        filterEl.innerHTML = `
          <feImage href="${dataUrl}" result="dispMap" preserveAspectRatio="none" />
          <feDisplacementMap in="SourceGraphic" in2="dispMap" scale="34" xChannelSelector="R" yChannelSelector="G" />
        `;
        defs.appendChild(filterEl);
      } else {
        const feImg = filterEl.querySelector('feImage');
        if (feImg) feImg.setAttribute('href', dataUrl);
      }
      el.style.backdropFilter = `url(#${filterId}) blur(8px) saturate(165%)`;
    }
  });

  elements.forEach((el) => {
    if (el.dataset.glassId) ro.observe(el);
  });
}