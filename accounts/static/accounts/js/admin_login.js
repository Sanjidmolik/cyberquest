/* Administrator sign-in: password visibility, Caps Lock hint, and one-click submit. */
(function () {
  "use strict";
  var form = document.getElementById("al-form");
  var password = document.getElementById("id_password");
  var reveal = document.getElementById("al-reveal");
  var caps = document.getElementById("caps-note");
  var submit = document.getElementById("al-submit");
  if (!form || !password || !submit) return;

  if (reveal) {
    reveal.addEventListener("click", function () {
      var show = password.type === "password";
      password.type = show ? "text" : "password";
      reveal.setAttribute("aria-pressed", show ? "true" : "false");
      reveal.setAttribute("aria-label", show ? "Hide password" : "Show password");
      password.focus();
    });
  }

  function capsCheck(event) {
    if (!caps || typeof event.getModifierState !== "function") return;
    caps.hidden = !event.getModifierState("CapsLock");
  }
  password.addEventListener("keydown", capsCheck);
  password.addEventListener("keyup", capsCheck);
  password.addEventListener("blur", function () { if (caps) caps.hidden = true; });

  var label = submit.querySelector(".al-submit-label");
  var idle = label ? label.textContent : "";

  function setBusy(busy) {
    submit.setAttribute("aria-busy", busy ? "true" : "false");
    submit.disabled = busy;
    if (label) label.textContent = busy ? label.getAttribute("data-busy") : idle;
  }

  form.addEventListener("submit", function (event) {
    // Let the browser explain empty or malformed fields before sending.
    if (!form.checkValidity()) {
      event.preventDefault();
      form.reportValidity();
      return;
    }
    if (password.type === "text") password.type = "password";
    if (submit.disabled) { event.preventDefault(); return; }
    setBusy(true);
  });

  // Back/forward cache restores the page with the button still disabled.
  window.addEventListener("pageshow", function () { setBusy(false); });
})();
