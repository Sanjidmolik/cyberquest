/* Dark / Day mode for the home page.
   - The saved choice is applied by a tiny inline script in <head> (no flash).
   - This file wires up the button, remembers the choice, and plays the
     "circle of light" switch effect where the browser supports it. */
(function () {
  const KEY = 'cq_home_theme';
  const COLORS = { dark: '#701fd3', light: '#f7f1ff' };   // mobile browser bar
  const root = document.documentElement;
  const btn = document.getElementById('themeToggle');
  const meta = document.querySelector('meta[name="theme-color"]');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  const current = () => (root.getAttribute('data-theme') === 'light' ? 'light' : 'dark');

  function sync() {
    const t = current();
    if (meta) meta.setAttribute('content', COLORS[t]);
    if (btn) {
      const label = t === 'dark' ? 'Switch to day mode' : 'Switch to dark mode';
      btn.setAttribute('aria-label', label);
      btn.title = label;
    }
  }

  function apply(t) {
    root.setAttribute('data-theme', t);
    try { localStorage.setItem(KEY, t); } catch (e) { /* private mode: still works, just not remembered */ }
    sync();
  }

  function switchTo(next, x, y) {
    if (reduced) { apply(next); return; }

    // Best effect: a circle of the new theme expands from the button.
    if (document.startViewTransition) {
      const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
      const vt = document.startViewTransition(() => apply(next));
      vt.ready.then(() => {
        root.animate(
          { clipPath: ['circle(0px at ' + x + 'px ' + y + 'px)', 'circle(' + radius + 'px at ' + x + 'px ' + y + 'px)'] },
          { duration: 700, easing: 'cubic-bezier(.2,.8,.2,1)', pseudoElement: '::view-transition-new(root)' }
        );
      }).catch(() => {});
      return;
    }

    // Fallback: smooth colour fade.
    root.classList.add('theme-fade');
    apply(next);
    setTimeout(() => root.classList.remove('theme-fade'), 500);
  }

  if (btn) {
    btn.addEventListener('click', () => {
      const r = btn.getBoundingClientRect();
      switchTo(current() === 'dark' ? 'light' : 'dark', r.left + r.width / 2, r.top + r.height / 2);
    });
  }

  // Keep other open tabs in step.
  addEventListener('storage', e => {
    if (e.key === KEY && (e.newValue === 'light' || e.newValue === 'dark')) {
      root.setAttribute('data-theme', e.newValue);
      sync();
    }
  });

  sync();
})();
