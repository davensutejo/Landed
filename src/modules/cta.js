import * as THREE from 'three';
import { createManagedRenderer, getDPR } from '../lib/gl.js';
import { GLSL_BAYER_CHUNK } from '../lib/dither.js';
import { isReducedMotion } from '../lib/a11y.js';

export function initCta(onFrame) {
  const section = document.getElementById('cta');
  const canvas = document.getElementById('cta-gl');

  // Monet Impressionist Water-Lily Shader Background
  if (canvas && section) {
    const managed = createManagedRenderer(canvas);
    if (managed) {
      const { renderer } = managed;
      const isMobile = window.matchMedia('(max-width: 767px)').matches;
      const scale = isMobile ? 0.5 : 1.0;

      const setSize = () => {
        const w = Math.max(300, Math.floor(section.clientWidth * scale));
        const h = Math.max(300, Math.floor(section.clientHeight * scale));
        renderer.setPixelRatio(Math.min(getDPR(), 1.5));
        renderer.setSize(w, h, false);
      };
      setSize();
      new ResizeObserver(setSize).observe(section);

      const ripples = [
        new THREE.Vector3(0.5, 0.5, -10),
        new THREE.Vector3(0.5, 0.5, -10),
        new THREE.Vector3(0.5, 0.5, -10)
      ];
      let rippleIdx = 0;

      const uniforms = {
        uTime: { value: 0 },
        uRipples: { value: ripples }
      };

      const scene = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

      // Full-screen triangle
      const triGeo = new THREE.BufferGeometry();
      triGeo.setAttribute(
        'position',
        new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3)
      );
      triGeo.setAttribute(
        'uv',
        new THREE.BufferAttribute(new Float32Array([0, 0, 2, 0, 0, 2]), 2)
      );

      const mat = new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3,
        uniforms,
        vertexShader: /* glsl */ `
          out vec2 vUv;
          void main() {
            vUv = uv;
            gl_Position = vec4(position, 1.0);
          }
        `,
        fragmentShader: /* glsl */ `
          precision highp float;
          in vec2 vUv;
          out vec4 fragColor;
          uniform float uTime;
          uniform vec3 uRipples[3];
          ${GLSL_BAYER_CHUNK}

          float hash(vec2 p) {
            return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
          }

          float noise(vec2 p) {
            vec2 i = floor(p);
            vec2 f = fract(p);
            vec2 u = f * f * (3.0 - 2.0 * f);
            return mix(
              mix(hash(i + vec2(0.0, 0.0)), hash(i + vec2(1.0, 0.0)), u.x),
              mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
              u.y
            );
          }

          float fbm(vec2 p) {
            float v = 0.0;
            float a = 0.5;
            for (int i = 0; i < 4; i++) {
              v += a * noise(p);
              p = p * 2.02 + vec2(1.7, 9.2);
              a *= 0.5;
            }
            return v;
          }

          void main() {
            vec2 uv = vUv;
            for (int i = 0; i < 3; i++) {
              float age = uTime - uRipples[i].z;
              if (age > 0.0 && age < 3.0) {
                vec2 d = uv - uRipples[i].xy;
                float dist = length(d);
                float wave = sin(dist * 38.0 - age * 7.0) * exp(-dist * 6.0) * (1.0 - age / 3.0);
                uv += normalize(d + 0.0001) * wave * 0.018;
              }
            }

            float t = uTime * 0.04;
            vec2 q = vec2(fbm(uv * 2.5 + t), fbm(uv * 2.5 + vec2(5.2, 1.3) - t));
            vec2 r = vec2(fbm(uv * 3.0 + 2.0 * q + vec2(1.7, 9.2)), fbm(uv * 3.0 + 2.0 * q + vec2(8.3, 2.8)));
            float f = fbm(uv * 2.5 + r * 1.6);

            // Anisotropic brushstroke dab
            float angle = f * 6.2831;
            vec2 dir = vec2(cos(angle), sin(angle));
            float brush = noise(vec2(dot(uv * 48.0, dir), dot(uv * 12.0, vec2(-dir.y, dir.x))));
            f = clamp(f + (brush - 0.5) * 0.14, 0.0, 1.0);

            vec3 cHaze = vec3(0.812, 0.847, 0.910);
            vec3 cPeri = vec3(0.663, 0.725, 0.871);
            vec3 cLily = vec3(0.498, 0.655, 0.627);
            vec3 cSage = vec3(0.718, 0.788, 0.604);
            vec3 cRose = vec3(0.910, 0.718, 0.761);
            vec3 cGold = vec3(0.949, 0.851, 0.627);

            vec3 col = mix(cHaze, cPeri, smoothstep(0.0, 0.28, f));
            col = mix(col, cLily, smoothstep(0.25, 0.5, f));
            col = mix(col, cSage, smoothstep(0.45, 0.68, f));
            col = mix(col, cRose, smoothstep(0.65, 0.85, f));
            col = mix(col, cGold, smoothstep(0.82, 1.0, f));

            // Faint canvas weave + Bayer finishing grain
            float weave = sin(gl_FragCoord.x * 1.4) * sin(gl_FragCoord.y * 1.4) * 0.015;
            float dither = (bayer4(gl_FragCoord.xy, 2.0) - 0.5) * 0.03;
            col += weave + dither;

            fragColor = vec4(col, 1.0);
          }
        `
      });

      scene.add(new THREE.Mesh(triGeo, mat));

      section.addEventListener('pointermove', (e) => {
        const rect = section.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = 1.0 - (e.clientY - rect.top) / rect.height;
        ripples[rippleIdx].set(x, y, uniforms.uTime.value);
        rippleIdx = (rippleIdx + 1) % 3;
      });

      onFrame((time) => {
        if (!managed.isVisible()) return;
        uniforms.uTime.value = isReducedMotion() ? 4.0 : time;
        renderer.render(scene, camera);
      });
    }
  }

  // Form submission is handled by modules/console.js (live agent).
}