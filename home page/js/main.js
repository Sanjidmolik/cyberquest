/* Landing page scroll animations (GSAP + ScrollTrigger) */

// Sprinkle twinkling stars into any [data-stars] container
document.querySelectorAll('[data-stars]').forEach(box => {
  const n = +box.dataset.stars;
  for (let i = 0; i < n; i++) {
    const s = document.createElement('i');
    s.style.left = Math.random() * 100 + '%';
    s.style.top = Math.random() * 100 + '%';
    s.style.animationDelay = (Math.random() * 4).toFixed(2) + 's';
    s.dataset.depth = (Math.random() * 0.8 + 0.2).toFixed(2);
    box.appendChild(s);
  }
});

// Place orbit items evenly around the central circle
const orbitItems = [...document.querySelectorAll('.orbit-item')];
function layoutOrbit() {
  const stage = document.getElementById('coreStage');
  if (!stage) return;
  const radius = stage.offsetWidth * 0.44;
  orbitItems.forEach((el, i) => {
    const a = (i / orbitItems.length) * Math.PI * 2 - Math.PI / 2;
    const x = Math.cos(a) * radius, y = Math.sin(a) * radius;
    if (window.gsap) gsap.set(el, { x, y });
    else el.style.transform = `translate(${x}px, ${y}px)`;
  });
}
layoutOrbit();
addEventListener('resize', layoutOrbit);

// Decorative QR code for the demo certificate (not a real, scannable code)
(function drawQr() {
  const box = document.getElementById('certQr');
  if (!box) return;
  const n = 25;
  let seed = 7;
  const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const finder = (x, y) => [[0, 0], [n - 7, 0], [0, n - 7]].some(([fx, fy]) => x >= fx && x < fx + 7 && y >= fy && y < fy + 7);
  const finderOn = (x, y) => {
    for (const [fx, fy] of [[0, 0], [n - 7, 0], [0, n - 7]]) {
      const dx = x - fx, dy = y - fy;
      if (dx < 0 || dy < 0 || dx > 6 || dy > 6) continue;
      return dx === 0 || dy === 0 || dx === 6 || dy === 6 || (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4);
    }
  };
  let rects = '';
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const on = finder(x, y) ? finderOn(x, y) : rand() > 0.52;
    if (on) rects += `<rect x="${x}" y="${y}" width="1" height="1"/>`;
  }
  box.innerHTML = `<svg viewBox="0 0 ${n} ${n}" fill="#1b1030" shape-rendering="crispEdges">${rects}</svg>`;
})();

const hasGsap = window.gsap && window.ScrollTrigger;
if (!hasGsap || document.documentElement.classList.contains('reduced')) {
  document.querySelectorAll('.reveal').forEach(el => { el.style.opacity = 1; el.style.transform = 'none'; });
  document.querySelectorAll('[data-count]').forEach(el => { el.textContent = (+el.dataset.count).toLocaleString() + (el.dataset.suffix || ''); });
} else {
  gsap.registerPlugin(ScrollTrigger);

  /* ---------- Hero intro ---------- */
  gsap.timeline({ defaults: { ease: 'power4.out' } })
    .from('.hero h1 .word', { yPercent: 110, opacity: 0, rotateX: -60, duration: 1.1, stagger: 0.07 })
    .from('.hero .lead', { y: 30, opacity: 0, duration: 0.9 }, '-=0.7')
    .from('.hero-cta .btn', { y: 20, opacity: 0, duration: 0.7, stagger: 0.1 }, '-=0.6')
    .to('.hero .eyebrow', { opacity: 1, y: 0, duration: 0.6 }, 0)
    .from('#planet', { yPercent: 25, opacity: 0, duration: 1.8, ease: 'expo.out' }, 0.2);

  /* ---------- Hero parallax: text drifts up, planet rises & rotates ---------- */
  const heroST = { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true };
  gsap.to('.hero-content', { yPercent: -60, opacity: 0, scale: 0.94, ease: 'none', scrollTrigger: heroST });
  gsap.to('#planet', { y: '-28vh', scale: 1.08, ease: 'none', scrollTrigger: heroST });
  gsap.to('.planet-ring', { rotate: 220, ease: 'none', scrollTrigger: { ...heroST, scrub: 0.6 } });
  gsap.to('.planet-grid', { rotate: -90, ease: 'none', scrollTrigger: { ...heroST, scrub: 1 } });
  gsap.utils.toArray('.hero .stars i').forEach(s => {
    gsap.to(s, { y: -220 * s.dataset.depth, ease: 'none', scrollTrigger: heroST });
  });
  // Planet ring keeps a slow idle spin as well
  gsap.to('.planet-ring', { rotate: '+=360', duration: 60, repeat: -1, ease: 'none' });

  /* ---------- Pinned rotating core ---------- */
  const coreTl = gsap.timeline({
    scrollTrigger: { trigger: '#core', start: 'top top', end: '+=160%', scrub: 1, pin: true, anticipatePin: 1 },
  });
  coreTl
    .fromTo('#coreStage', { scale: 0.6, opacity: 0.2 }, { scale: 1, opacity: 1, duration: 0.25, ease: 'power2.out' }, 0)
    .to('#orbit', { rotate: 360, duration: 1, ease: 'none' }, 0)
    .to('.orbit-item', { rotate: -360, duration: 1, ease: 'none' }, 0)  // keep labels upright
    .to('.core-ring.r1', { rotate: -180, duration: 1, ease: 'none' }, 0)
    .to('.core-ring.r2', { rotate: 540, duration: 1, ease: 'none' }, 0)
    .to('.core-ring.r3', { rotate: 120, scale: 1.08, duration: 1, ease: 'none' }, 0)
    .fromTo('#coreOrb', { rotate: -30 }, { rotate: 30, duration: 1, ease: 'none' }, 0)
    .from('.core-caption', { y: 60, opacity: 0, duration: 0.25 }, 0.05)
    .to('#coreStage', { scale: 0.85, opacity: 0.5, duration: 0.2 }, 0.8);
  gsap.to('#coreOrb', { scale: 1.06, duration: 2.4, yoyo: true, repeat: -1, ease: 'sine.inOut' });

  /* ---------- Generic reveals ---------- */
  ScrollTrigger.batch('.reveal', {
    start: 'top 88%',
    onEnter: els => gsap.to(els, { opacity: 1, y: 0, duration: 1, stagger: 0.12, ease: 'power3.out', overwrite: true }),
  });

  /* ---------- Parallax cards (different speeds) ---------- */
  gsap.utils.toArray('.cards .card[data-speed]').forEach(card => {
    gsap.fromTo(card, { yPercent: 0 }, {
      y: +card.dataset.speed, ease: 'none',
      scrollTrigger: { trigger: '.cards', start: 'top bottom', end: 'bottom top', scrub: true },
    });
  });

  /* ---------- 3D tilt on hover for cards ---------- */
  document.querySelectorAll('.cards .card').forEach(card => {
    card.addEventListener('pointermove', e => {
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      gsap.to(card, { rotateY: x * 10, rotateX: -y * 10, transformPerspective: 800, duration: 0.4 });
    });
    card.addEventListener('pointerleave', () => gsap.to(card, { rotateX: 0, rotateY: 0, duration: 0.6 }));
  });

  /* ---------- Comic panels pop in like a page being drawn ---------- */
  gsap.from('#comicPanels .panel', {
    scale: 0.6, rotate: i => (i % 2 ? 8 : -8), opacity: 0, duration: 0.9, stagger: 0.2, ease: 'back.out(1.8)',
    scrollTrigger: { trigger: '#comicPanels', start: 'top 80%' },
  });
  gsap.from('#comicPanels .bubble', {
    scale: 0, transformOrigin: 'bottom left', duration: 0.5, stagger: 0.25, delay: 0.5, ease: 'back.out(3)',
    scrollTrigger: { trigger: '#comicPanels', start: 'top 80%' },
  });
  gsap.to('#comicPanels', {
    y: -60, ease: 'none',
    scrollTrigger: { trigger: '#comics', start: 'top bottom', end: 'bottom top', scrub: true },
  });

  /* ---------- Course covers parallax ---------- */
  gsap.utils.toArray('.course-cover span').forEach(el => {
    gsap.fromTo(el, { y: 30 }, { y: -30, ease: 'none', scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: true } });
  });

  /* ---------- Certificate flips up in 3D ---------- */
  gsap.fromTo('#certCard',
    { rotateX: 35, rotateY: -20, y: 80, opacity: 0, transformPerspective: 1000 },
    { rotateX: 0, rotateY: 0, y: 0, opacity: 1, ease: 'none',
      scrollTrigger: { trigger: '#certCard', start: 'top 95%', end: 'top 40%', scrub: 1 } });

  /* ---------- Counters ---------- */
  document.querySelectorAll('[data-count]').forEach(el => {
    const obj = { v: 0 };
    gsap.to(obj, {
      v: +el.dataset.count, duration: 2, ease: 'power2.out',
      scrollTrigger: { trigger: el, start: 'top 90%', once: true },
      onUpdate: () => { el.textContent = Math.round(obj.v).toLocaleString() + (el.dataset.suffix || ''); },
    });
  });

  /* ---------- Active nav link follows the section in view ---------- */
  document.querySelectorAll('.nav-links a[href^="#"]').forEach(link => {
    const sec = document.querySelector(link.getAttribute('href'));
    if (!sec) return;
    ScrollTrigger.create({
      trigger: sec, start: 'top center', end: 'bottom center',
      onToggle: self => {
        if (!self.isActive) return;
        document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));
        link.classList.add('active');
      },
    });
  });

  addEventListener('load', () => ScrollTrigger.refresh());
}
