/* Studio preview: Desktop / Mobile (390 px) width, and "Restart preview" (a fresh preview
   attempt: the player starts a new one each time it loads). */
(function () {
  "use strict";
  var frame = document.getElementById("st-player");
  if (!frame) return;
  var buttons = document.querySelectorAll(".st-segment [data-width]");
  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      var mobile = button.getAttribute("data-width") === "mobile";
      frame.classList.toggle("is-mobile", mobile);
      buttons.forEach(function (b) {
        var on = b === button;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    });
  });
  document.getElementById("st-restart").addEventListener("click", function () {
    frame.src = frame.getAttribute("src");
  });
})();
