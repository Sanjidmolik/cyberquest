(function () {
  "use strict";

  var button = document.querySelector("[data-review-toggle]");
  var extras = Array.prototype.slice.call(document.querySelectorAll("[data-review-extra]"));
  if (!button || !extras.length) return;

  function setOpen(open) {
    extras.forEach(function (card) { card.hidden = !open; });
    button.setAttribute("aria-expanded", open ? "true" : "false");
    button.textContent = open
      ? "Show fewer answers"
      : "View all answers (" + (extras.length + document.querySelectorAll(".cq-review-card:not([data-review-extra])").length) + ")";
  }

  setOpen(false);
  button.addEventListener("click", function () {
    var open = button.getAttribute("aria-expanded") !== "true";
    setOpen(open);
    if (open) {
      var first = extras[0];
      var heading = first && first.querySelector(".cq-review-q");
      if (heading) heading.focus();
    }
  });
})();
