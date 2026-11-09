import { prepareWithSegments, layoutNextLine } from '@chenglou/pretext';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Draggable } from 'gsap/Draggable';
import { ditherCanvas, PALETTES, BAYER4 } from '../lib/dither.js';
import { isReducedMotion } from '../lib/a11y.js';

function drawCameoMedallion(canvas) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const cx = w * 0.5;
  const cy = h * 0.5;

  // Full-bleed radial chiaroscuro glow so the art fills the entire squircle frame edge-to-edge
  const rad = ctx.createRadialGradient(cx * 0.78, cy * 0.72, 4, cx, cy, w * 0.72);
  rad.addColorStop(0, '#FAF6EC');
  rad.addColorStop(0.38, '#E8643C');
  rad.addColorStop(0.74, '#2B3A8C');
  rad.addColorStop(1, '#14110F');
  ctx.fillStyle = rad;
  ctx.fillRect(0, 0, w, h);

  // Armillary rings across the medallion
  ctx.save();
  ctx.translate(cx, cy);
  ctx.strokeStyle = '#FAF6EC';
  ctx.lineWidth = 6;
  ctx.rotate(-0.4);
  ctx.beginPath();
  ctx.ellipse(0, 0, w * 0.42, h * 0.2, 0, 0, Math.PI * 2);
  ctx.stroke();

  ctx.rotate(0.85);
  ctx.strokeStyle = '#E8643C';
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.ellipse(0, 0, w * 0.38, h * 0.18, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();

  ditherCanvas(ctx, {
    palette: PALETTES.atelier,
    matrix: BAYER4,
    scale: 2
  });
}

export async function initManifesto(onFrame) {
  const stage = document.getElementById('manifesto-stage');
  const sourceEl = document.getElementById('manifesto-source');
  const linesContainer = document.getElementById('manifesto-lines');
  const cameo = document.getElementById('manifesto-cameo');
  const cameoCanvas = document.getElementById('cameo-canvas');
  if (!stage || !sourceEl || !linesContainer || !cameo) return;

  // Guarantee (0,0) CSS origin so transforms and hole coordinates never desync
  cameo.style.top = '0px';
  cameo.style.left = '0px';

  if (cameoCanvas) {
    drawCameoMedallion(cameoCanvas);
  }

  const text = sourceEl.textContent.trim();
  if (document.fonts && document.fonts.load) {
    await document.fonts.load('400 34px "Instrument Serif"');
  }

  let prepared = null;
  let isMobile = window.matchMedia('(max-width: 767px)').matches;
  const getFontSpec = () =>
    isMobile
      ? { font: '400 22px "Instrument Serif"', lineHeight: 32, r: 54 }
      : { font: '400 34px "Instrument Serif"', lineHeight: 46, r: 78 };

  let spec = getFontSpec();
  try {
    prepared = prepareWithSegments(text, spec.font);
  } catch {
    stage.classList.add('manifesto__Body-fallback');
    return;
  }

  // Span pool (48 spans)
  const pool = [];
  for (let i = 0; i < 48; i++) {
    const span = document.createElement('span');
    span.className = 'manifesto__line';
    span.style.display = 'none';
    linesContainer.appendChild(span);
    pool.push(span);
  }

  const initW = stage.clientWidth || 860;
  const cameoState = {
    anchorX: initW * 0.48,
    anchorY: isMobile ? 120 : 165,
    offsetX: 0,
    offsetY: 0,
    dragging: false,
    scrollProgress: 0.45
  };

  gsap.set(cameo, {
    x: cameoState.anchorX - spec.r,
    y: cameoState.anchorY - spec.r
  });

  const [dragInstance] = Draggable.create(cameo, {
    type: 'x,y',
    bounds: stage,
    inertia: true,
    onPress() {
      cameoState.dragging = true;
    },
    onDrag() {
      cameoState.anchorX = this.x + spec.r - cameoState.offsetX;
      cameoState.anchorY = this.y + spec.r - cameoState.offsetY;
      runPretextLayout();
    },
    onThrowUpdate() {
      cameoState.anchorX = this.x + spec.r - cameoState.offsetX;
      cameoState.anchorY = this.y + spec.r - cameoState.offsetY;
      runPretextLayout();
    },
    onRelease() {
      cameoState.dragging = false;
    },
    onThrowComplete() {
      cameoState.dragging = false;
    }
  });

  function runPretextLayout() {
    const maxW = stage.clientWidth || 860;
    const { lineHeight, r } = spec;
    const pad = 18;
    const totalR = r + pad;

    // Read actual rendered center of cameo relative to stage so hole & ball match 100%
    const stageRect = stage.getBoundingClientRect();
    const cameoRect = cameo.getBoundingClientRect();
    const cx =
      stageRect.width > 0
        ? cameoRect.left - stageRect.left + cameoRect.width * 0.5
        : cameoState.anchorX + cameoState.offsetX;
    const cy =
      stageRect.height > 0
        ? cameoRect.top - stageRect.top + cameoRect.height * 0.5
        : cameoState.anchorY + cameoState.offsetY;

    let cursor = { segmentIndex: 0, graphemeIndex: 0 };
    let y = 0;
    let spanIdx = 0;
    let safety = 0;

    while (cursor && safety < 65) {
      safety++;
      const lineMidY = y + lineHeight * 0.5;
      const dy = Math.abs(lineMidY - cy);

      const slots = [];
      if (dy < totalR) {
        const halfChord = Math.sqrt(totalR * totalR - dy * dy);
        const leftEnd = Math.max(0, cx - halfChord);
        const rightStart = Math.min(maxW, cx + halfChord);
        if (leftEnd >= 90) {
          slots.push({ x: 0, w: leftEnd });
        }
        if (maxW - rightStart >= 90) {
          slots.push({ x: rightStart, w: maxW - rightStart });
        }
      } else {
        slots.push({ x: 0, w: maxW });
      }

      if (slots.length === 0) {
        y += lineHeight;
        continue;
      }

      for (const slot of slots) {
        if (!cursor) break;
        const line = layoutNextLine(prepared, cursor, slot.w);
        if (!line) {
          cursor = null;
          break;
        }
        const span = pool[spanIdx++];
        if (span) {
          if (span.style.display === 'none') span.style.display = 'block';
          if (span.textContent !== line.text) span.textContent = line.text;
          span.style.transform = `translate3d(${slot.x.toFixed(1)}px, ${y}px, 0)`;
        }
        cursor = line.end;
      }
      y += lineHeight;
    }

    for (let i = spanIdx; i < pool.length; i++) {
      pool[i].style.display = 'none';
    }

    for (let i = 0; i < spanIdx; i++) {
      const share = i / Math.max(1, spanIdx);
      const lit = share <= cameoState.scrollProgress ? 1 : 0.28;
      pool[i].style.opacity = String(lit);
    }

    const targetMinH = Math.max(460, y + 24);
    if (Math.abs((parseFloat(stage.style.minHeight) || 0) - targetMinH) > 40) {
      stage.style.minHeight = `${targetMinH}px`;
    }
  }

  let visible = false;
  const io = new IntersectionObserver((entries) => {
    visible = entries[0]?.isIntersecting ?? false;
  });
  io.observe(stage);

  ScrollTrigger.create({
    trigger: stage,
    start: 'top 80%',
    end: 'bottom 30%',
    scrub: 1,
    onUpdate: (self) => {
      cameoState.scrollProgress = 0.15 + self.progress * 0.9;
    }
  });

  onFrame((time) => {
    if (!visible) return;
    if (!cameoState.dragging && !isReducedMotion()) {
      const maxW = stage.clientWidth || 860;
      const maxH = stage.clientHeight || 460;
      cameoState.offsetX = Math.sin(time * 0.75) * (maxW * 0.18);
      cameoState.offsetY = Math.cos(time * 0.55) * 68;

      const targetX = gsap.utils.clamp(
        spec.r + 8,
        maxW - spec.r - 8,
        cameoState.anchorX + cameoState.offsetX
      );
      const targetY = gsap.utils.clamp(
        spec.r + 8,
        maxH - spec.r - 8,
        cameoState.anchorY + cameoState.offsetY
      );

      gsap.set(cameo, {
        x: targetX - spec.r,
        y: targetY - spec.r
      });
      if (dragInstance) dragInstance.update();
    }
    runPretextLayout();
  });

  window.addEventListener('resize', () => {
    const nowMobile = window.matchMedia('(max-width: 767px)').matches;
    if (nowMobile !== isMobile) {
      isMobile = nowMobile;
      spec = getFontSpec();
      prepared = prepareWithSegments(text, spec.font);
    }
    runPretextLayout();
  });

  runPretextLayout();
}