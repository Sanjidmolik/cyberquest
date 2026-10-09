/*
  accounts/static/accounts/js/login_v2.js
  The login form still posts to Django (login_view) exactly as before.
  This file only adds the extras from the design:
    - Day / Night button (remembered in the browser)
    - show / hide password
    - quick e-mail check before sending
    - the "slash" animation and loading state when signing in
*/
(function () {
    "use strict";

    var KEY = "cq_home_theme";
    var root = document.documentElement;
    var form = document.getElementById("login-form");
    if (!form) return;

    var email = document.getElementById("id_email");
    var password = document.getElementById("id_password");
    var submitBtn = document.getElementById("login-submit");
    var feedback = document.getElementById("login-feedback");
    var feedbackText = document.getElementById("login-feedback-text");
    var themeBtn = document.getElementById("theme-toggle");
    var eyeBtn = document.getElementById("toggle-password");
    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var sending = false;

    function store(dayNight) {
        try { localStorage.setItem(KEY, dayNight === "day" ? "light" : "dark"); } catch (e) { /* ignore */ }
    }

    /* ---- Day / Night (same cq_home_theme key as the rest of CyberQuest) ---- */
    function isNight() { return root.getAttribute("data-theme") === "night"; }
    function syncThemeLabel() {
        var night = isNight();
        themeBtn.setAttribute("aria-label", night ? "Switch to day mode" : "Switch to night mode");
        themeBtn.querySelector(".lq-theme-text").textContent = night ? "Day" : "Night";
    }
    themeBtn.addEventListener("click", function () {
        var next = isNight() ? "day" : "night";
        root.setAttribute("data-theme", next);
        store(next);
        syncThemeLabel();
    });
    syncThemeLabel();

    /* ---- Show / hide password ---- */
    eyeBtn.addEventListener("click", function () {
        var show = password.type === "password";
        password.type = show ? "text" : "password";
        eyeBtn.setAttribute("aria-pressed", show ? "true" : "false");
        eyeBtn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });

    /* ---- Messages ---- */
    function showError(text) {
        feedbackText.textContent = text;
        feedback.hidden = false;
    }
    function hideError() { feedback.hidden = true; }

    /* Same rule as accounts/validators.py (the server checks it again). */
    function acceptedEmail(value) {
        var v = value.trim().toLowerCase();
        var parts = v.split("@");
        if (parts.length !== 2 || !parts[0] || !parts[1]) return false;
        var domain = parts[1];
        return ["gmail.com", "hotmail.com", "outlook.com"].indexOf(domain) !== -1 || /\.edu$/.test(domain);
    }

    function slash() {
        if (reduced) return;
        var overlay = document.createElement("div");
        overlay.className = "lq-slash";
        overlay.setAttribute("aria-hidden", "true");
        overlay.innerHTML = '<span class="lq-slash-line"></span>';
        document.body.appendChild(overlay);
        window.setTimeout(function () { overlay.remove(); }, 900);
    }

    /* ---- Submit ---- */
    form.addEventListener("submit", function (event) {
        if (sending) { event.preventDefault(); return; }
        hideError();
        if (!acceptedEmail(email.value)) {
            event.preventDefault();
            showError("Please use a Gmail, Hotmail, Outlook, or .edu email address.");
            email.focus();
            return;
        }
        if (!password.value) {
            event.preventDefault();
            showError("Please enter your password.");
            password.focus();
            return;
        }
        /* Looks fine: play the animation, then send the form to Django. */
        event.preventDefault();
        sending = true;
        submitBtn.disabled = true;
        submitBtn.classList.add("is-loading");
        submitBtn.querySelector(".lq-btn-text").textContent = "Signing in...";
        slash();
        window.setTimeout(function () { form.submit(); }, reduced ? 0 : 650);
    });

    /* Coming back from the server with an error? Re-enable everything. */
    window.addEventListener("pageshow", function (event) {
        if (!event.persisted) return;
        sending = false;
        submitBtn.disabled = false;
        submitBtn.classList.remove("is-loading");
        submitBtn.querySelector(".lq-btn-text").textContent = "Sign in";
    });
})();
