import * as THREE from 'three';

const activeContexts = [];
const MAX_CONTEXTS = 3;

export function getDPR() {
  const isMobile = window.matchMedia('(max-width: 767px)').matches;
  return Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2);
}

export function isWebGL2Available() {
  try {
    const canvas = document.createElement('canvas');
    return !!(window.WebGL2RenderingContext && canvas.getContext('webgl2'));
  } catch {
    return false;
  }
}

export function createManagedRenderer(canvas, options = {}) {
  if (!isWebGL2Available()) return null;

  if (activeContexts.length >= MAX_CONTEXTS) {
    const oldest = activeContexts.shift();
    if (oldest && oldest.dispose) oldest.dispose();
  }

  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: false,
    powerPreference: 'high-performance',
    alpha: true,
    ...options
  });
  renderer.setPixelRatio(getDPR());

  const state = { visible: true, renderer };

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        state.visible = entry.isIntersecting;
      });
    },
    { rootMargin: '100px' }
  );
  io.observe(canvas);

  const handle = {
    renderer,
    isVisible: () => state.visible,
    dispose() {
      io.disconnect();
      renderer.dispose();
    }
  };

  activeContexts.push(handle);
  return handle;
}