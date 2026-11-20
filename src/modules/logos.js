import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import gsap from 'gsap';
import { isZh, onLang } from '../i18n.js';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { createManagedRenderer } from '../lib/gl.js';
import { isReducedMotion } from '../lib/a11y.js';

// The fragments a seller stitches together today. Each becomes one table row
// with source_url + snapshot_date in Landed.
const STUDIOS_ZH = ['欧盟 TARIC 税则', '美国 HTS 税则', '美国 CBP 预裁定', '欧盟 BTI 裁定', 'WCO 归类总规则', '欧盟增值税 · IOSS', '欧洲央行汇率', 'IATA PI 967', '物流商报价', '平台佣金表'];
const STUDIOS_EN = [
  'EU TARIC',
  'USITC HTS',
  'CBP CROSS rulings',
  'EU BTI rulings',
  'WCO GRI 1–6',
  'EU VAT · IOSS',
  'ECB FX rates',
  'IATA PI 967',
  'Carrier rate cards',
  'Platform fee tables'
];
const studios = () => (isZh() ? STUDIOS_ZH : STUDIOS_EN);

export function initLogos(onFrame) {
  const grid = document.getElementById('logos-grid');
  const discoCanvas = document.getElementById('disco-canvas');
  if (!grid) return;

  // Build 10 squircle studio wordmark tiles with internal corner sparkles
  const tiles = studios().map((name, i) => {
    const tile = document.createElement('div');
    tile.className = 'logo-tile squircle';
    tile.dataset.squircle = '24';
    tile.innerHTML = `
      <svg class="logo-tile__sparkle logo-tile__sparkle--tl" viewBox="0 0 24 24" aria-hidden="true"><use href="#sparkle"></use></svg>
      <svg class="logo-tile__sparkle logo-tile__sparkle--br" viewBox="0 0 24 24" aria-hidden="true"><use href="#sparkle"></use></svg>
      <svg class="logo-tile__glyph" viewBox="0 0 16 16" aria-hidden="true">
        ${
          i % 2 === 0
            ? '<polygon points="8,1 15,8 8,15 1,8" fill="none" stroke="currentColor" stroke-width="1.4"/>'
            : '<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.4"/>'
        }
      </svg>
      <span class="logo-tile__word">${name}</span>
    `;
    tile.addEventListener('pointerenter', () => flashTile(tile));
    grid.appendChild(tile);
    return tile;
  });

  function flashTile(tile) {
    if (tile.classList.contains('is-flashing')) return;
    tile.classList.add('is-flashing');

    if (!isReducedMotion()) {
      const sparkles = tile.querySelectorAll('.logo-tile__sparkle');
      gsap.fromTo(
        sparkles,
        { scale: 0, rotation: 0, opacity: 0.9 },
        {
          scale: 1.1,
          rotation: 45,
          opacity: 0,
          duration: 1.35,
          stagger: 0.18,
          ease: 'power2.out'
        }
      );
    }

    clearTimeout(tile._flashTimer);
    tile._flashTimer = setTimeout(() => {
      tile.classList.remove('is-flashing');
    }, 1850);
  }

  // Calm, unhurried single-tile glint every 1.2s, only while the grid is on screen
  if (!isReducedMotion()) {
    let sweepIndex = 0;
    let gridVisible = false;
    new IntersectionObserver((entries) => {
      gridVisible = entries[0]?.isIntersecting ?? false;
    }).observe(grid);
    setInterval(() => {
      if (!gridVisible || document.hidden) return;
      flashTile(tiles[sweepIndex % tiles.length]);
      sweepIndex++;
    }, 1200);
  }

  // Desktop Three.js faceted mirror disco ball (slowed rotation to 0.16 rad/s)
  const isMobile = window.matchMedia('(max-width: 767px)').matches;
  if (discoCanvas && !isMobile) {
    const managed = createManagedRenderer(discoCanvas);
    if (managed) {
      const { renderer } = managed;
      renderer.setSize(180, 180, false);
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 20);
      camera.position.set(0, 0, 3.6);

      const pmrem = new THREE.PMREMGenerator(renderer);
      scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

      const geo = new THREE.IcosahedronGeometry(1, 3);
      const mat = new THREE.MeshStandardMaterial({
        color: 0xfaf6ec,
        metalness: 1.0,
        roughness: 0.08,
        flatShading: true
      });
      const ball = new THREE.Mesh(geo, mat);
      scene.add(ball);

      const key = new THREE.DirectionalLight(0xffdf9e, 3.0);
      key.position.set(3, 4, 3);
      const rim = new THREE.DirectionalLight(0xe8643c, 2.0);
      rim.position.set(-3, -2, 2);
      scene.add(key, rim);

      // Compile the shaders now, behind the preloader. Left to the first visible frame, compiling the
      // metallic PBR material stalled the scroll as the section came into view.
      renderer.compile(scene, camera);
      renderer.render(scene, camera);

      onFrame((time) => {
        if (!managed.isVisible()) return;
        if (!isReducedMotion()) {
          ball.rotation.y = time * 0.16;
          ball.rotation.x = Math.sin(time * 0.12) * 0.1;
        }
        renderer.render(scene, camera);
      });
    }
  }

  // Stats count-up on viewport entry. Prefix and suffix are read on every update: a language switch
  // changes them (¥2.84T → 2.84万亿元).
  const counters = [];
  document.querySelectorAll('.stat-box__num').forEach((numEl) => {
    const target = parseFloat(numEl.dataset.count || '0');
    const decimals = parseInt(numEl.dataset.decimals || '0', 10);
    const counter = { val: 0, started: false };
    const write = () => {
      const formatted =
        decimals > 0
          ? counter.val.toFixed(decimals)
          : Math.round(counter.val).toLocaleString('en-US');
      numEl.textContent = `${numEl.dataset.prefix || ''}${formatted}${numEl.dataset.suffix || ''}`;
    };
    counters.push({ counter, write });

    ScrollTrigger.create({
      trigger: numEl,
      start: 'top 88%',
      once: true,
      onEnter: () => {
        counter.started = true;
        gsap.to(counter, {
          val: target,
          duration: 1.4,
          ease: 'medici',
          onUpdate: write
        });
      }
    });
  });

  // Language switch: tile words in place (the tiles keep their reveal and hover state), and any
  // number that has already counted is re-written with the new prefix and suffix
  onLang({
    apply: () => {
      const names = studios();
      tiles.forEach((tile, i) => {
        const w = tile.querySelector('.logo-tile__word');
        if (w) w.textContent = names[i];
      });
      counters.forEach((c) => c.counter.started && c.write());
    }
  });
}
