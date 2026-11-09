import gsap from 'gsap';
import { Draggable } from 'gsap/Draggable';
import { makeDitheredArt, ditherReveal } from '../lib/dither.js';

// The audit trail: every tool call, source and flag behind one answer.
const CARDS_DATA = [
  { type: 'chat', title: 'SELLER: "500ml portable blender + spare Tritan cup, ¥38, 0.6 kg. EU price for 25% margin?"', x: -720, y: -420, depth: 1.0 },
  { type: 'note', title: 'ASK: Is the motor self-contained? Is the battery built in, and what is its Wh rating?', x: -340, y: -460, depth: 1.15 },
  { type: 'gold', title: 'hs_disambiguate → 8509.40 (food mixer, self-contained motor) · confirmed by seller', x: 80, y: -380, depth: 0.9 },
  { type: 'specimen', title: 'WCO GRI 3(b) · goods put up in sets for retail sale', x: 520, y: -440, depth: 1.05 },
  { type: 'art', title: 'Fig. Waterfall · COGS → freight → €3 duty → fee → VAT', x: 920, y: -360, depth: 0.85, seed: 3 },
  { type: 'gold', title: 'SOURCE: EU €3 per item tariff category · ec.europa.eu · 2026-11-08', x: -820, y: 20, depth: 1.1 },
  { type: 'art', title: 'Fig. 5,000-path margin distribution · P5 marked', x: -380, y: 60, depth: 0.95, seed: 4 },
  { type: 'chat', title: 'cost_engine(price, categories=2) → deterministic · no LLM', x: 60, y: 40, depth: 1.2 },
  { type: 'art', title: 'Fig. Stress table · CNY +5% · returns 15% · freight +30%', x: 480, y: 80, depth: 1.0, seed: 5 },
  { type: 'note', title: 'FLAG: UN 3481 · IATA PI 967 · Li-ion packed in equipment', x: 900, y: 60, depth: 1.12 },
  { type: 'art', title: 'Fig. Localized listing · de-DE', x: -700, y: 460, depth: 0.88, seed: 6 },
  { type: 'specimen', title: 'GUARDRAIL: no source_url → abstain, never invent a rate', x: -260, y: 500, depth: 1.04 },
  { type: 'art', title: 'Fig. HS top-3 with legal reasoning', x: 180, y: 460, depth: 0.92, seed: 7 },
  { type: 'gold', title: 'SOURCE: DE VAT 19% · IOSS · snapshot 2026-11-08', x: 600, y: 520, depth: 1.18 },
  { type: 'note', title: 'FLAG: food-contact material: EU Reg. 1935/2004 declaration needed', x: 980, y: 440, depth: 0.96 },
  { type: 'chat', title: 'listing_localize(lang="de") → copy only · numbers injected from engine', x: -40, y: -180, depth: 1.08 }
];

const COLLABS = [
  { name: 'HS TOOL', color: '#E8643C', phase: 0 },
  { name: 'COST ENGINE', color: '#2B3A8C', phase: 2.1 },
  { name: 'LISTING', color: '#C9A24B', phase: 4.2 }
];

export function initCanvas(onFrame) {
  const viewport = document.getElementById('canvas-viewport');
  const world = document.getElementById('canvas-world');
  const gridBg = document.getElementById('canvas-grid-bg');
  const collabLayer = document.getElementById('canvas-collaborators');
  const minimapDot = document.getElementById('canvas-minimap-dot');
  const a11yList = document.getElementById('canvas-a11y-list');
  if (!viewport || !world) return;

  const minZoom = 0.6;
  const maxZoom = 1.4;
  const state = {
    panX: 0,
    panY: 0,
    zoom: 1,
    visible: false
  };

  const getTileSpan = () => {
    const vw = Math.max(window.innerWidth, 2560);
    const vh = Math.max(window.innerHeight, 1440);
    return {
      w: Math.ceil((vw * 1.3 + 480) / minZoom),
      h: Math.ceil((vh * 1.3 + 480) / minZoom)
    };
  };

  // Build 16 cards + accessible list
  const cardItems = CARDS_DATA.map((item, idx) => {
    const el = document.createElement('article');
    el.className = `canvas-card squircle ${
      item.type === 'note' ? 'canvas-card--note' : item.type === 'gold' ? 'canvas-card--gold' : ''
    }`;
    el.dataset.squircle = '24';

    if (item.type === 'art') {
      el.innerHTML = `
        <div class="canvas-card__meta">STEP ${String(idx + 1).padStart(2, '0')}</div>
        <canvas width="248" height="156" class="canvas-card__art"></canvas>
        <div class="figure-caption">${item.title}</div>
      `;
      const c = el.querySelector('canvas');
      if (c) makeDitheredArt(c, item.seed || idx, 'atelier', 2);
    } else {
      el.innerHTML = `
        <div class="canvas-card__meta">${({ chat: 'TOOL CALL', note: 'FLAG', gold: 'PROVENANCE', specimen: 'RULE' })[item.type] || item.type.toUpperCase()}</div>
        <div class="figure-caption">${item.title}</div>
      `;
    }

    world.appendChild(el);

    if (a11yList) {
      const li = document.createElement('li');
      li.textContent = item.title;
      a11yList.appendChild(li);
    }

    return { ...item, el, revealed: false };
  });

  // Collaborator cursors
  const collabNodes = COLLABS.map((c) => {
    const node = document.createElement('div');
    node.className = 'collab-cursor';
    node.innerHTML = `
      <svg width="14" height="14" style="color:${c.color}"><use href="#sparkle"></use></svg>
      <div class="collab-cursor__tag">
        <span class="live-dot"></span>
        <span>${c.name}</span>
      </div>
    `;
    collabLayer?.appendChild(node);
    return { ...c, node };
  });

  // Draggable proxy with inertia
  const proxy = document.createElement('div');
  const panXTo = gsap.quickTo(state, 'panX', { duration: 0.25, ease: 'power3.out' });
  const panYTo = gsap.quickTo(state, 'panY', { duration: 0.25, ease: 'power3.out' });
  const zoomTo = gsap.quickTo(state, 'zoom', { duration: 0.25, ease: 'power3.out' });

  Draggable.create(proxy, {
    trigger: viewport,
    type: 'x,y',
    inertia: true,
    onDrag() {
      panXTo(this.x);
      panYTo(this.y);
    },
    onThrowUpdate() {
      panXTo(this.x);
      panYTo(this.y);
    }
  });

  // Wheel handling: vertical passes through to page; horizontal pans; Ctrl/Cmd + wheel zooms
  viewport.addEventListener(
    'wheel',
    (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const nextZoom = gsap.utils.clamp(minZoom, maxZoom, state.zoom - e.deltaY * 0.0015);
        zoomTo(nextZoom);
      } else if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.preventDefault();
        const nx = state.panX - e.deltaX;
        gsap.set(proxy, { x: nx });
        panXTo(nx);
      }
      // Vertical scroll intentionally passes through to page!
    },
    { passive: false }
  );

  // Keyboard navigation
  viewport.addEventListener('keydown', (e) => {
    const step = 80;
    if (e.key === 'ArrowLeft') panXTo(state.panX + step);
    else if (e.key === 'ArrowRight') panXTo(state.panX - step);
    else if (e.key === 'ArrowUp') panYTo(state.panY + step);
    else if (e.key === 'ArrowDown') panYTo(state.panY - step);
    else if (e.key === '+' || e.key === '=') zoomTo(Math.min(maxZoom, state.zoom + 0.12));
    else if (e.key === '-') zoomTo(Math.max(minZoom, state.zoom - 0.12));
    else if (e.key === '0') {
      panXTo(0);
      panYTo(0);
      zoomTo(1);
    }
  });

  const io = new IntersectionObserver((entries) => {
    state.visible = entries[0]?.isIntersecting ?? false;
  });
  io.observe(viewport);

  onFrame((time) => {
    if (!state.visible) return;
    const rect = viewport.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const span = getTileSpan();

    world.style.transform = `scale(${state.zoom.toFixed(3)})`;
    if (gridBg) {
      gridBg.style.backgroundPosition = `${(state.panX * 0.5).toFixed(1)}px ${(state.panY * 0.5).toFixed(1)}px`;
    }

    cardItems.forEach((card) => {
      const wx = gsap.utils.wrap(-span.w / 2, span.w / 2, card.x + state.panX * card.depth);
      const wy = gsap.utils.wrap(-span.h / 2, span.h / 2, card.y + state.panY * card.depth);
      const sx = cx + wx - 140;
      const sy = cy + wy - 110;
      card.el.style.transform = `translate3d(${sx.toFixed(1)}px, ${sy.toFixed(1)}px, 0)`;

      if (!card.revealed && sx > -260 && sx < rect.width + 100 && sy > -220 && sy < rect.height + 100) {
        card.revealed = true;
        ditherReveal(card.el, { duration: 0.75 });
      }
    });

    collabNodes.forEach((c, i) => {
      const x = cx + Math.sin(time * 0.55 + c.phase) * (rect.width * 0.28);
      const y = cy + Math.cos(time * 0.42 + c.phase + i) * (rect.height * 0.25);
      c.node.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
    });

    if (minimapDot) {
      const mx = gsap.utils.wrap(12, 104, 58 - state.panX * 0.03);
      const my = gsap.utils.wrap(12, 66, 39 - state.panY * 0.03);
      minimapDot.style.left = `${mx.toFixed(1)}px`;
      minimapDot.style.top = `${my.toFixed(1)}px`;
    }
  });
}