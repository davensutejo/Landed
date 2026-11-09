import * as THREE from 'three';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { SplitText } from 'gsap/SplitText';
import { createManagedRenderer, getDPR } from '../lib/gl.js';
import { GLSL_BAYER_CHUNK, makeDitheredArt } from '../lib/dither.js';
import { isReducedMotion } from '../lib/a11y.js';

export async function initHero(onFrame) {
  const section = document.getElementById('hero');
  const canvas = document.getElementById('hero-gl');
  const sparkleContainer = document.getElementById('hero-sparkles');

  // Background glow drift
  if (!isReducedMotion()) {
    gsap.to('.hero__glow--violet', {
      xPercent: 8,
      yPercent: 6,
      duration: 32,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut'
    });
    gsap.to('.hero__glow--ember', {
      xPercent: -10,
      yPercent: -8,
      duration: 36,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut'
    });
    gsap.fromTo(
      '.hero__vitruvian .draw-path',
      { drawSVG: '0%' },
      { drawSVG: '100%', duration: 2.2, stagger: 0.15, ease: 'medici' }
    );
  }

  // Pooled pointer sparkle trail (12 nodes max)
  const isMobile = window.matchMedia('(max-width: 767px)').matches;
  if (sparkleContainer && !isReducedMotion() && !isMobile) {
    const poolSize = 12;
    const pool = [];
    for (let i = 0; i < poolSize; i++) {
      const el = document.createElement('div');
      el.className = 'hero__sparkle-node';
      el.innerHTML = '<svg width="14" height="14"><use href="#sparkle"></use></svg>';
      gsap.set(el, { scale: 0, opacity: 0 });
      sparkleContainer.appendChild(el);
      pool.push(el);
    }
    let idx = 0;
    let lastSpawn = 0;
    section.addEventListener('pointermove', (e) => {
      const now = performance.now();
      if (now - lastSpawn < 55) return;
      lastSpawn = now;
      const node = pool[idx % poolSize];
      idx++;
      const rect = section.getBoundingClientRect();
      gsap.killTweensOf(node);
      gsap.fromTo(
        node,
        {
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
          scale: 0,
          rotation: 0,
          opacity: 1
        },
        {
          scale: 1.15,
          rotation: 45,
          opacity: 0,
          duration: 0.75,
          ease: 'power2.out'
        }
      );
    });
  }

  // WebGL Armillary Sphere with Bayer Dither Post-Process Pass
  const ditherUniforms = {
    tDiffuse: { value: null },
    uCell: { value: 2.0 },
    uLevels: { value: 4.0 }
  };

  const managed = createManagedRenderer(canvas);
  if (managed) {
    const { renderer } = managed;
    const width = canvas.clientWidth || 640;
    const height = canvas.clientHeight || 640;
    renderer.setSize(width, height, false);

    const rt = new THREE.WebGLRenderTarget(
      Math.floor(width * getDPR()),
      Math.floor(height * getDPR())
    );
    ditherUniforms.tDiffuse.value = rt.texture;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 50);
    camera.position.set(0, 0, 6.2);

    const rig = new THREE.Group();
    scene.add(rig);

    const matGold = new THREE.MeshStandardMaterial({
      color: 0xc9a24b,
      roughness: 0.28,
      metalness: 0.85
    });
    const matInk = new THREE.MeshStandardMaterial({
      color: 0xe8643c,
      roughness: 0.4,
      metalness: 0.3,
      flatShading: true
    });

    const ringSpecs = [
      { r: 1.95, tube: 0.045, rx: 0.5, ry: 0.2 },
      { r: 1.55, tube: 0.04, rx: -0.6, ry: 0.8 },
      { r: 1.18, tube: 0.035, rx: 1.1, ry: -0.4 }
    ];
    const rings = ringSpecs.map((s) => {
      const geo = new THREE.TorusGeometry(s.r, s.tube, 18, 72);
      const mesh = new THREE.Mesh(geo, matGold);
      mesh.rotation.set(s.rx, s.ry, 0);
      rig.add(mesh);
      return mesh;
    });

    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.62, 1), matInk);
    rig.add(core);

    const keyLight = new THREE.DirectionalLight(0xfff0d0, 3.2);
    keyLight.position.set(4, 5, 4);
    const rimLight = new THREE.DirectionalLight(0x6a48d0, 2.0);
    rimLight.position.set(-4, -3, -2);
    scene.add(keyLight, rimLight, new THREE.AmbientLight(0x1b1038, 1.1));

    // Full-screen Bayer Dither Post-Process Pass (GLSL3)
    const postScene = new THREE.Scene();
    const postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const postMat = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      uniforms: ditherUniforms,
      vertexShader: /* glsl */ `
        out vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = vec4(position.xy, 0.0, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        precision highp float;
        in vec2 vUv;
        out vec4 fragColor;
        uniform sampler2D tDiffuse;
        uniform float uCell;
        uniform float uLevels;
        ${GLSL_BAYER_CHUNK}
        void main() {
          vec4 tex = texture(tDiffuse, vUv);
          if (tex.a < 0.05) {
            fragColor = vec4(0.0);
            return;
          }
          float lum = dot(tex.rgb, vec3(0.299, 0.587, 0.114));
          lum += (bayer4(gl_FragCoord.xy, uCell) - 0.5) / uLevels;
          lum = clamp(lum, 0.0, 0.999);
          int idx = int(floor(lum * 4.0));
          vec3 c0 = vec3(0.039, 0.035, 0.063); // night
          vec3 c1 = vec3(0.106, 0.063, 0.220); // violet-deep
          vec3 c2 = vec3(0.910, 0.392, 0.235); // vermilion
          vec3 c3 = vec3(0.953, 0.929, 0.878); // cream
          vec3 col = idx == 0 ? c0 : (idx == 1 ? c1 : (idx == 2 ? c2 : c3));
          fragColor = vec4(col, tex.a);
        }
      `,
      transparent: true
    });
    postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), postMat));

    renderer.compile(scene, camera);

    const rotXTo = gsap.quickTo(rig.rotation, 'x', { duration: 0.6, ease: 'power3.out' });
    const rotYTo = gsap.quickTo(rig.rotation, 'y', { duration: 0.6, ease: 'power3.out' });

    window.addEventListener(
      'pointermove',
      (e) => {
        const nx = (e.clientX / window.innerWidth - 0.5) * 0.7;
        const ny = (e.clientY / window.innerHeight - 0.5) * 0.7;
        rotYTo(nx);
        rotXTo(ny);
      },
      { passive: true }
    );

    onFrame((time) => {
      if (!managed.isVisible()) return;
      if (!isReducedMotion()) {
        rings[0].rotation.z = time * 0.35;
        rings[1].rotation.x = -0.6 + time * 0.28;
        rings[2].rotation.y = -0.4 - time * 0.42;
        core.rotation.y = time * 0.5;
      }
      renderer.setRenderTarget(rt);
      renderer.clear();
      renderer.render(scene, camera);
      renderer.setRenderTarget(null);
      renderer.render(postScene, postCam);
    });
  } else {
    // 2D Dithered Fallback
    canvas.width = 480;
    canvas.height = 480;
    makeDitheredArt(canvas, 2, 'ember', 3);
  }

  // Scroll-scrubbed dither degradation (uCell 2px -> 9px) + Hero Curtain scale/dim
  ScrollTrigger.create({
    trigger: section,
    start: 'top top',
    end: 'bottom top',
    scrub: 1,
    onUpdate: (self) => {
      ditherUniforms.uCell.value = 2 + self.progress * 7;
      if (!isReducedMotion()) {
        gsap.set(section, {
          scale: 1 - self.progress * 0.06,
          filter: `brightness(${1 - self.progress * 0.35})`
        });
      }
    }
  });

  return {
    playEntrance() {
      if (isReducedMotion()) return;
      const h1 = document.getElementById('hero-heading');
      const ital = h1?.querySelector('.ital');
      const split = new SplitText(h1, { type: 'lines' });

      gsap.from(split.lines, {
        yPercent: 100,
        opacity: 0,
        duration: 1.15,
        stagger: 0.07,
        ease: 'medici'
      });

      if (ital) {
        gsap.fromTo(
          ital,
          { opacity: 0, rotation: 6, y: 14 },
          { opacity: 1, rotation: 0, y: 0, duration: 1.0, delay: 0.24, ease: 'medici' }
        );
      }

      gsap.from('.hero__sub, .hero__ctas, .hero__meta', {
        y: 24,
        opacity: 0,
        duration: 1.0,
        stagger: 0.08,
        delay: 0.18,
        ease: 'medici'
      });
    }
  };
}