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

  if (theme) {
    theme.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("cq_home_theme", next); } catch (e) {}
    });
  }
})();
