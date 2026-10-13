(function (global) {
  "use strict";

  var reduced = false;
  try {
    reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (err) {
    reduced = false;
  }

  function show(node, text) {
    if (!node) return;
    node.hidden = false;
    node.textContent = text;
  }

  function hide(node) {
    if (!node) return;
    node.hidden = true;
    node.textContent = "";
  }

  global.CQComic = {
    reduced: reduced,
    show: show,
    hide: hide,
  };
})(window);
