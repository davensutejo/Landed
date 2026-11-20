import gsap from 'gsap';
import { isZh, L, onLang } from '../i18n.js';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { isReducedMotion } from '../lib/a11y.js';

const RAMP = ' ·.:-=+IVXLCDM#@';

export function initShowreel(onFrame) {
  const section = document.getElementById('showreel');
  const stage = document.getElementById('showreel-stage');
  const video = document.getElementById('showreel-video');
  const procCanvas = document.getElementById('showreel-proc-canvas');
  const asciiCanvas = document.getElementById('showreel-ascii-canvas');
  const lens = document.getElementById('showreel-lens');
  const hud = document.getElementById('showreel-hud');
  // The HUD starts with its static line; once the scrub has written a count, a language switch
  // re-writes that count rather than the static line.
  let hudMerged = null;
  const writeHud = () => {
    if (!hud || hudMerged == null) return;
    const next = hudMerged >= 8 ? L('8 INPUTS → 1 LANDED PRICE', '8 项输入 → 1 个到岸价') : L(`${hudMerged}/8 INPUTS MERGED`, `已合并 ${hudMerged}/8 项`);
    if (hud.textContent !== next) hud.textContent = next; // a text change dirties layout: skip repeats
  };
  onLang({ apply: writeHud });
  if (!section || !stage || !asciiCanvas || !procCanvas) return;

  const isMobile = window.matchMedia('(max-width: 767px)').matches;
  const state = {
    cellSize: isMobile ? 28 : 22,
    asciiOpacity: 1,
    useVideo: false,
    visible: false,
    merge: isReducedMotion() ? 1 : 0,
    lensX: -999,
    lensY: -999
  };

  // Probe optional /media/showreel.mp4; automatically fall back to procedural canvas
  if (video) {
    video.addEventListener('loadeddata', () => {
      if (video.videoWidth > 0) {
        state.useVideo = true;
        procCanvas.style.display = 'none';
        video.play().catch(() => {});
      }
    });
    video.addEventListener('error', () => {
      state.useVideo = false;
      video.style.display = 'none';
    });
  }

  const procCtx = procCanvas.getContext('2d');
  const asciiCtx = asciiCanvas.getContext('2d');
  const sampleCanvas = document.createElement('canvas');
  const sampleCtx = sampleCanvas.getContext('2d', { willReadFrequently: true });

  const resize = () => {
    const rect = stage.getBoundingClientRect();
    procCanvas.width = 640;
    procCanvas.height = 360;
    asciiCanvas.width = Math.max(320, Math.floor(rect.width));
    asciiCanvas.height = Math.max(180, Math.floor(rect.height));
  };
  resize();
  new ResizeObserver(resize).observe(stage);

  const io = new IntersectionObserver((entries) => {
    state.visible = entries[0]?.isIntersecting ?? false;
  });
  io.observe(section);

  // The eight inputs a seller stitches together. Same eight as the section copy.
  const FRAGMENTS = [
    { en: 'HS CODE', zh: 'HS 编码', ax: 0.12, ay: 0.2 },
    { en: 'DUTY', zh: '关税', ax: 0.84, ay: 0.16 },
    { en: 'VAT 19%', zh: '增值税 19%', ax: 0.08, ay: 0.72 },
    { en: 'FREIGHT', zh: '头程运费', ax: 0.88, ay: 0.7 },
    { en: 'FEES', zh: '平台佣金', ax: 0.3, ay: 0.9 },
    { en: '¥→€ FX', zh: '¥→€ 汇率', ax: 0.7, ay: 0.88 },
    { en: 'RETURNS', zh: '退货', ax: 0.28, ay: 0.1 },
    { en: 'LISTING', zh: '商品页', ax: 0.66, ay: 0.08 }
  ].map((f, i) => ({ ...f, phase: i * 0.83, orbit: 14 + (i % 3) * 7 }));

  // Fragments start scattered and drifting (the spreadsheet chaos) and slide into
  // one price tag as the scroll-scrub progresses. `merge` runs 0 → 1.
  function renderProceduralFrame(time) {
    const w = procCanvas.width;
    const h = procCanvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const merge = state.merge;
    const ease = merge * merge * (3 - 2 * merge);

    procCtx.fillStyle = '#0A0910';
    procCtx.fillRect(0, 0, w, h);

    procCtx.textAlign = 'center';
    procCtx.textBaseline = 'middle';

    // Price tag: fades in as fragments arrive
    const tagW = 190;
    const tagH = 92;
    procCtx.save();
    procCtx.globalAlpha = 0.25 + ease * 0.75;
    procCtx.strokeStyle = '#C9A24B';
    procCtx.lineWidth = 5;
    procCtx.beginPath();
    procCtx.roundRect(cx - tagW / 2, cy - tagH / 2, tagW, tagH, 18);
    procCtx.stroke();
    procCtx.fillStyle = `rgba(232, 100, 60, ${0.15 + ease * 0.85})`;
    procCtx.beginPath();
    procCtx.arc(cx - tagW / 2 + 20, cy, 6, 0, Math.PI * 2); // tag hole
    procCtx.fill();
    procCtx.fillStyle = '#FAF6EC';
    procCtx.font = isZh() ? '600 44px "Noto Serif SC", "Songti SC", serif' : '700 46px "JetBrains Mono", monospace';
    procCtx.fillText(merge > 0.97 ? L('ONE PRICE', '一个价') : L('PRICE ?', '售价？'), cx + 10, cy + 2);
    procCtx.restore();

    // Fragments
    procCtx.font = '700 22px "JetBrains Mono", monospace';
    for (const f of FRAGMENTS) {
      const sx = f.ax * w + Math.cos(time * 0.9 + f.phase) * f.orbit;
      const sy = f.ay * h + Math.sin(time * 1.1 + f.phase) * f.orbit;
      // Merged position: stacked in the tag's slot, tiny jitter so it never looks frozen
      const tx = cx + 10 + Math.cos(time * 2 + f.phase) * 3;
      const ty = cy + 2 + Math.sin(time * 2 + f.phase) * 3;
      const x = sx + (tx - sx) * ease;
      const y = sy + (ty - sy) * ease;
      procCtx.save();
      procCtx.translate(x, y);
      procCtx.rotate((1 - ease) * Math.sin(time * 0.7 + f.phase) * 0.35);
      procCtx.globalAlpha = 1 - ease * 0.85;
      procCtx.fillStyle = '#F3EDE0';
      procCtx.fillText(L(f.en, f.zh), 0, 0);
      procCtx.restore();
    }
  }

  let lastFrameTime = 0;
  onFrame((time) => {
    if (!state.visible && lastFrameTime > 0) return;
    if (time - lastFrameTime < 1 / 30) return; // Throttled 30fps
    lastFrameTime = time;

    if (!state.useVideo) {
      renderProceduralFrame(isReducedMotion() ? 1.2 : time);
    }

    const w = asciiCanvas.width;
    const h = asciiCanvas.height;
    const cellW = Math.max(5, Math.round(state.cellSize));
    const cellH = Math.round(cellW * 1.65);
    const cols = Math.max(10, Math.floor(w / cellW));
    const rows = Math.max(6, Math.floor(h / cellH));

    sampleCanvas.width = cols;
    sampleCanvas.height = rows;
    const source = state.useVideo ? video : procCanvas;
    sampleCtx.drawImage(source, 0, 0, cols, rows);
    const pixels = sampleCtx.getImageData(0, 0, cols, rows).data;

    asciiCtx.clearRect(0, 0, w, h);
    if (state.asciiOpacity <= 0.02) return;

    asciiCtx.globalAlpha = state.asciiOpacity;
    asciiCtx.fillStyle = '#0A0910';
    asciiCtx.fillRect(0, 0, w, h);

    asciiCtx.font = `400 ${cellW + 2}px "JetBrains Mono", monospace`;
    asciiCtx.textBaseline = 'top';

    const lensRadiusSq = 75 * 75;

    for (let r = 0; r < rows; r++) {
      const py = r * cellH;
      for (let c = 0; c < cols; c++) {
        const px = c * cellW;
        const dx = px - state.lensX;
        const dy = py - state.lensY;
        if (dx * dx + dy * dy < lensRadiusSq) continue; // Liquid glass lens punches through ASCII

        const i = (r * cols + c) * 4;
        const lum = (0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2]) / 255;
        const charIdx = Math.min(RAMP.length - 1, Math.floor(lum * RAMP.length));
        const ch = RAMP[charIdx];
        if (ch === ' ') continue;

        asciiCtx.fillStyle = lum > 0.92 ? '#E8643C' : '#F3EDE0';
        asciiCtx.fillText(ch, px, py);
      }
    }
  });

  // Pointer lens tracking
  stage.addEventListener('pointermove', (e) => {
    const rect = stage.getBoundingClientRect();
    state.lensX = e.clientX - rect.left;
    state.lensY = e.clientY - rect.top;
    if (lens) {
      lens.style.opacity = '1';
      lens.style.left = `${state.lensX}px`;
      lens.style.top = `${state.lensY}px`;
    }
  });

  stage.addEventListener('pointerleave', () => {
    state.lensX = -999;
    state.lensY = -999;
    if (lens) lens.style.opacity = '0';
  });

  // Pinned Scroll-Scrub: cell size 22px -> 5px, then cross-fade ASCII out (0.55 -> 0.9)
  if (!isReducedMotion()) {
    const maxCell = isMobile ? 28 : 22;
    const minCell = isMobile ? 10 : 5;
    ScrollTrigger.create({
      trigger: section,
      start: 'top top',
      end: '+=130%',
      pin: true,
      scrub: 1,
      onUpdate: (self) => {
        const p = self.progress;
        // Fragments converge over the first 70% of the scrub, while the cells shrink
        state.merge = Math.min(1, p / 0.7);
        state.cellSize = gsap.utils.interpolate(maxCell, minCell, Math.min(1, p / 0.75));
        if (p > 0.55) {
          state.asciiOpacity = Math.max(0, 1 - (p - 0.55) / 0.35);
        } else {
          state.asciiOpacity = 1;
        }
        hudMerged = Math.round(state.merge * 8);
        writeHud();
      }
    });
  }
}