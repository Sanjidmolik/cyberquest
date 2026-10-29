/* Practice Studio, Check & publish and Version history: the publish confirmation dialog and
   "are you sure" prompts for archive and restore. The server checks permissions and the
   checklist again on every POST; this script only asks before sending. */
(function () {
  "use strict";

  var dialog = document.getElementById("st-publish-dialog");
  var open = document.getElementById("st-publish-open");
  if (dialog && open) {
    open.addEventListener("click", function () {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else if (window.confirm("Students will see this version immediately.")) dialog.querySelector("form").submit();
    });
    document.getElementById("st-publish-cancel").addEventListener("click", function () { dialog.close(); });
  }

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
    });
  });
})();
