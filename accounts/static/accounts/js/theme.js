/*
  Shared Day / Night toggle for accounts pages.
  Uses the same localStorage key as the login page (cq_login_theme).
*/
(function () {
    "use strict";
    var KEY = "cq_login_theme";
    var root = document.documentElement;
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;

    function store(value) {
        try { localStorage.setItem(KEY, value); } catch (e) { /* ignore */ }
    }

    function syncLabel() {
        var night = root.getAttribute("data-theme") === "night";
        btn.setAttribute("aria-label", night ? "Switch to day mode" : "Switch to night mode");
        var text = btn.querySelector(".cq-theme-text");
        if (text) text.textContent = night ? "Day" : "Night";
        var moon = btn.querySelector(".cq-ico-moon");
        var sun = btn.querySelector(".cq-ico-sun");
        if (moon) moon.hidden = night;
        if (sun) sun.hidden = !night;
    }

    btn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "night" ? "day" : "night";
        root.setAttribute("data-theme", next);
        store(next);
        syncLabel();
    });
    syncLabel();
})();
