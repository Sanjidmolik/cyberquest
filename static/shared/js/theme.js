/* Shared dark/light toggle — same storage key as the homepage. */
(function () {
  var KEY = "cq_home_theme";
  var COLORS = { dark: "#701fd3", light: "#f7f1ff" };
  var root = document.documentElement;
  var btn = document.getElementById("themeToggle");
  var meta = document.querySelector('meta[name="theme-color"]');

  function current() {
    return root.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function sync() {
    var t = current();
    if (meta) meta.setAttribute("content", COLORS[t]);
    if (btn) {
      var label = t === "dark" ? "Switch to day mode" : "Switch to dark mode";
      btn.setAttribute("aria-label", label);
      btn.title = label;
    }
  }

  function apply(t) {
    root.setAttribute("data-theme", t);
    try { localStorage.setItem(KEY, t); } catch (e) {}
    sync();
  }

  if (btn) {
    btn.addEventListener("click", function () {
      apply(current() === "dark" ? "light" : "dark");
    });
  }
  sync();

})();
