import gsap from 'gsap';

export const BAYER2 = [0, 2, 3, 1];

export const BAYER4 = [
  0,  8,  2, 10,
  12, 4, 14,  6,
  3, 11,  1,  9,
  15, 7, 13,  5
];

export const BAYER8 = [
   0, 32,  8, 40,  2, 34, 10, 42,
  48, 16, 56, 24, 50, 18, 58, 26,
  12, 44,  4, 36, 14, 46,  6, 38,
  60, 28, 52, 20, 62, 30, 54, 22,
   3, 35, 11, 43,  1, 33,  9, 41,
  51, 19, 59, 27, 49, 17, 57, 25,
  15, 47,  7, 39, 13, 45,  5, 37,
  63, 31, 55, 23, 61, 29, 53, 21
];

export const PALETTES = {
  atelier: [
    [20, 17, 15],
    [43, 58, 140],
    [232, 100, 60],
    [243, 237, 224]
  ],
  ember: [
    [10, 9, 16],
    [27, 16, 56],
    [232, 100, 60],
    [201, 162, 75]
  ],
  sepia: [
    [20, 17, 15],
    [120, 96, 62],
    [201, 162, 75],
    [250, 246, 236]
  ]
};

export const GLSL_BAYER_CHUNK = /* glsl */ `
const float BAYER4[16] = float[16](0.,8.,2.,10., 12.,4.,14.,6., 3.,11.,1.,9., 15.,7.,13.,5.);
float bayer4(vec2 fragCoord, float cell){
  vec2 p = floor(fragCoord / cell);
  int i = int(mod(p.x,4.)) + 4*int(mod(p.y,4.));
  return (BAYER4[i] + 0.5) / 16.;
}
`;

export function ditherCanvas(ctx, { palette = PALETTES.atelier, matrix = BAYER4, scale = 2 } = {}) {
  const { width, height } = ctx.canvas;
  const imgData = ctx.getImageData(0, 0, width, height);
  const data = imgData.data;
  const dim = Math.sqrt(matrix.length);
  const maxVal = matrix.length;
  const stops = palette.length;

  for (let y = 0; y < height; y += scale) {
    for (let x = 0; x < width; x += scale) {
      const idx = (y * width + x) * 4;
      const r = data[idx];
      const g = data[idx + 1];
      const b = data[idx + 2];
      let lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;

      const mx = Math.floor(x / scale) % dim;
      const my = Math.floor(y / scale) % dim;
      const threshold = (matrix[my * dim + mx] + 0.5) / maxVal;

      lum = Math.min(0.999, Math.max(0, lum + (threshold - 0.5) / stops));
      const colorIdx = Math.floor(lum * stops);
      const [pr, pg, pb] = palette[colorIdx];

      for (let sy = 0; sy < scale && y + sy < height; sy++) {
        for (let sx = 0; sx < scale && x + sx < width; sx++) {
          const sIdx = ((y + sy) * width + (x + sx)) * 4;
          data[sIdx] = pr;
          data[sIdx + 1] = pg;
          data[sIdx + 2] = pb;
          data[sIdx + 3] = 255;
        }
      }
    }
  }
  ctx.putImageData(imgData, 0, 0);
}

export function makeDitheredArt(canvas, seed = 1, paletteName = 'atelier', scale = 2) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  // Background gradient
  const grad = ctx.createLinearGradient(0, 0, w, h);
  grad.addColorStop(0, '#181412');
  grad.addColorStop(1, '#D8CEBE');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // Classical architectural motif based on seed
  const mode = seed % 4;
  ctx.save();
  if (mode === 0) {
    // Classical arch + lit sphere
    ctx.fillStyle = '#2A2520';
    ctx.fillRect(w * 0.18, h * 0.2, w * 0.64, h * 0.8);
    ctx.beginPath();
    ctx.arc(w * 0.5, h * 0.45, w * 0.24, Math.PI, 0);
    ctx.fillStyle = '#F3EDE0';
    ctx.fill();
  } else if (mode === 1) {
    // Fluted columns
    for (let i = 0; i < 4; i++) {
      const cx = w * (0.2 + i * 0.2);
      const colGrad = ctx.createLinearGradient(cx - 18, 0, cx + 18, 0);
      colGrad.addColorStop(0, '#14110F');
      colGrad.addColorStop(0.5, '#FAF6EC');
      colGrad.addColorStop(1, '#2A2520');
      ctx.fillStyle = colGrad;
      ctx.fillRect(cx - 18, h * 0.12, 36, h * 0.76);
    }
  } else if (mode === 2) {
    // Chiaroscuro sphere
    const rad = ctx.createRadialGradient(w * 0.42, h * 0.38, 4, w * 0.5, h * 0.5, Math.min(w, h) * 0.4);
    rad.addColorStop(0, '#FFFFFF');
    rad.addColorStop(0.6, '#777067');
    rad.addColorStop(1, '#100D0B');
    ctx.fillStyle = rad;
    ctx.beginPath();
    ctx.arc(w * 0.5, h * 0.5, Math.min(w, h) * 0.36, 0, Math.PI * 2);
    ctx.fill();
  } else {
    // Laurel arc & golden ratio rings
    ctx.strokeStyle = '#FAF6EC';
    ctx.lineWidth = 14;
    ctx.beginPath();
    ctx.arc(w * 0.5, h * 0.52, Math.min(w, h) * 0.32, 0.2 * Math.PI, 0.8 * Math.PI);
    ctx.stroke();
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.arc(w * 0.5, h * 0.48, Math.min(w, h) * 0.2, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();

  ditherCanvas(ctx, {
    palette: PALETTES[paletteName] || PALETTES.atelier,
    matrix: BAYER4,
    scale
  });
}

export function ditherReveal(el, { duration = 0.9 } = {}) {
  const state = { step: 5 };
  gsap.fromTo(
    el,
    { opacity: 0, filter: 'contrast(220%) brightness(1.3)' },
    {
      opacity: 1,
      filter: 'contrast(100%) brightness(1)',
      duration,
      ease: 'medici',
      onUpdate() {
        state.step = Math.max(1, Math.round((1 - this.progress()) * 6));
      }
    }
  );
}