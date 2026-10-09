(function () {
  var nav = document.getElementById("cq-nav") || document.getElementById("pc-nav") || document.getElementById("nav");
  // The homepage toggle is already handled by home_page/js/app.js. A second
  // listener here toggles .open twice, so the menu never opens.
  var toggle = document.getElementById("cq-nav-toggle");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* Same threshold the homepage used: in flow at the top, glass capsule after a short scroll. */
  var bars = [];
  if (nav) bars.push(nav);
  document.querySelectorAll(".topnav, .child-topbar").forEach(function (bar) {
    if (bars.indexOf(bar) === -1) bars.push(bar);
  });
  bars.forEach(function (bar) {
    if (bar.dataset.cqFloat) return;
    bar.dataset.cqFloat = "1";
    var hold = document.createElement("div");
    hold.className = "cq-nav-hold";
    hold.setAttribute("aria-hidden", "true");
    hold.hidden = true;
    bar.parentNode.insertBefore(hold, bar);
    var frame = 0;
    function y() {
      if (window.lenis && typeof window.lenis.scroll === "number") return window.lenis.scroll;
      return window.scrollY || document.documentElement.scrollTop || 0;
    }
    function apply() {
      frame = 0;
      var on = y() > 30;
      if (on === bar.classList.contains("scrolled")) return;
      if (on) {
        var cs = getComputedStyle(bar);
        hold.style.height = bar.offsetHeight + "px";
        hold.style.marginTop = cs.marginTop;
        hold.style.marginBottom = cs.marginBottom;
        hold.hidden = false;
        bar.classList.add("scrolled");
      } else {
        bar.classList.remove("scrolled");
        hold.hidden = true;
      }
    }
    function queue() {
      if (frame) return;
      frame = window.requestAnimationFrame(apply);
    }
    window.addEventListener("scroll", queue, { passive: true });
    if (window.lenis && typeof window.lenis.on === "function") window.lenis.on("scroll", queue);
    apply();
  });

  document.querySelectorAll(".cq-toast").forEach(function (toast) {
    var remove = function () {
      if (!toast.isConnected) return;
      toast.classList.add("is-out");
      window.setTimeout(function () { toast.remove(); }, 280);
    };
    var close = toast.querySelector(".cq-toast-x");
    if (close) close.addEventListener("click", remove);
    window.setTimeout(remove, 3500);
  });
})();
