(function () {
  var button = document.getElementById("ops-menu");
  var side = document.getElementById("ops-side");
  var scrim = document.getElementById("ops-scrim");
  var theme = document.getElementById("ops-theme");

  function setOpen(open) {
    if (!side || !button) return;
    side.classList.toggle("is-open", open);
    if (scrim) scrim.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (button && side) {
    button.addEventListener("click", function () {
      setOpen(!side.classList.contains("is-open"));
    });
    if (scrim) scrim.addEventListener("click", function () { setOpen(false); });
    side.addEventListener("click", function (event) {
      if (event.target.closest("a")) setOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") setOpen(false);
    });
  }

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var root = document.documentElement;

  function currentTheme() {
    return root.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function applyTheme(next) {
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("cq_home_theme", next); } catch (e) {}
    if (theme) {
      var label = next === "dark" ? "Switch to day mode" : "Switch to dark mode";
      theme.setAttribute("aria-label", label);
      theme.title = label;
    }
  }

  function switchTheme(next, x, y) {
    if (reduced) {
      applyTheme(next);
      return;
    }
    if (document.startViewTransition) {
      var radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
      var vt = document.startViewTransition(function () { applyTheme(next); });
      vt.ready.then(function () {
        root.animate(
          {
            clipPath: [
              "circle(0px at " + x + "px " + y + "px)",
              "circle(" + radius + "px at " + x + "px " + y + "px)"
            ]
          },
          { duration: 700, easing: "cubic-bezier(.2,.8,.2,1)", pseudoElement: "::view-transition-new(root)" }
        );
      }).catch(function () {});
      return;
    }
    root.classList.add("theme-fade");
    applyTheme(next);
    window.setTimeout(function () { root.classList.remove("theme-fade"); }, 500);
  }

  if (theme) {
    applyTheme(currentTheme());
    theme.addEventListener("click", function () {
      var next = currentTheme() === "light" ? "dark" : "light";
      var rect = theme.getBoundingClientRect();
      switchTheme(next, rect.left + rect.width / 2, rect.top + rect.height / 2);
    });
  }

  window.addEventListener("storage", function (event) {
    if (event.key === "cq_home_theme" && (event.newValue === "light" || event.newValue === "dark")) {
      root.setAttribute("data-theme", event.newValue);
      if (theme) applyTheme(event.newValue);
    }
  });
})();
