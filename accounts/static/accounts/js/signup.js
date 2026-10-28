/*
  accounts/static/accounts/js/signup.js
  The sign-up form still posts to Django (signup_view), which does the real
  validation. This file only adds the same extras as the login page:
    - Day / Night button (shared cq_home_theme key)
    - show / hide for both password fields
    - a live "passwords match" hint
    - quick e-mail and agreement checks, then a loading state on submit
*/
(function () {
    "use strict";

    var KEY = "cq_home_theme";
    var root = document.documentElement;
    var form = document.getElementById("signup-form");
    if (!form) return;

    var email = document.getElementById("id_email");
    var password = document.getElementById("id_password");
    var confirm = document.getElementById("id_confirm_password");
    var agree = document.getElementById("id_ethical_agreement");
    var confirmStatus = document.getElementById("confirm-status");
    var submitBtn = document.getElementById("signup-submit");
    var feedback = document.getElementById("signup-feedback");
    var feedbackText = document.getElementById("signup-feedback-text");
    var themeBtn = document.getElementById("theme-toggle");
    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var sending = false;

    /* ---- Day / Night ---- */
    function isNight() { return root.getAttribute("data-theme") === "night"; }
    function syncThemeLabel() {
        var night = isNight();
        themeBtn.setAttribute("aria-label", night ? "Switch to day mode" : "Switch to night mode");
        themeBtn.querySelector(".lq-theme-text").textContent = night ? "Day" : "Night";
    }
    if (themeBtn) {
        themeBtn.addEventListener("click", function () {
            var next = isNight() ? "day" : "night";
            root.setAttribute("data-theme", next);
            try { localStorage.setItem(KEY, next === "day" ? "light" : "dark"); } catch (e) { /* ignore */ }
            syncThemeLabel();
        });
        syncThemeLabel();
    }

    /* ---- Show / hide passwords ---- */
    document.querySelectorAll(".lq-eye[data-eye-for]").forEach(function (btn) {
        var input = document.getElementById(btn.getAttribute("data-eye-for"));
        if (!input) return;
        btn.addEventListener("click", function () {
            var show = input.type === "password";
            input.type = show ? "text" : "password";
            btn.setAttribute("aria-pressed", show ? "true" : "false");
            btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
        });
    });

    /* ---- Passwords match ---- */
    function syncMatch() {
        if (!confirm.value) {
            confirmStatus.textContent = "";
            confirmStatus.className = "sq-hint";
            return;
        }
        var same = confirm.value === password.value;
        confirmStatus.textContent = same ? "Passwords match." : "Passwords do not match yet.";
        confirmStatus.className = "sq-hint " + (same ? "is-ok" : "is-bad");
    }
    password.addEventListener("input", syncMatch);
    confirm.addEventListener("input", syncMatch);

    /* ---- Messages ---- */
    function showError(text, focusEl) {
        feedbackText.textContent = text;
        feedback.hidden = false;
        if (focusEl) focusEl.focus();
    }

    /* Same rule as accounts/validators.py (the server checks it again). */
    function acceptedEmail(value) {
        var v = value.trim().toLowerCase();
        var parts = v.split("@");
        if (parts.length !== 2 || !parts[0] || !parts[1]) return false;
        var domain = parts[1];
        return ["gmail.com", "hotmail.com", "outlook.com"].indexOf(domain) !== -1 || /\.edu$/.test(domain);
    }

    /* ---- Submit ---- */
    form.addEventListener("submit", function (event) {
        if (sending) { event.preventDefault(); return; }
        feedback.hidden = true;
        if (!acceptedEmail(email.value)) {
            event.preventDefault();
            showError("Please use a Gmail, Hotmail, Outlook, or .edu email address.", email);
            return;
        }
        if (password.value && confirm.value && password.value !== confirm.value) {
            event.preventDefault();
            showError("Passwords do not match.", confirm);
            return;
        }
        if (!agree.checked) {
            event.preventDefault();
            showError("Please accept the ethical use agreement to create your account.", agree);
            return;
        }
        sending = true;
        submitBtn.disabled = true;
        submitBtn.classList.add("is-loading");
        submitBtn.querySelector(".lq-btn-text").textContent = "Creating account...";
        if (!reduced) {
            /* Let the button repaint before the browser leaves the page. */
            event.preventDefault();
            window.setTimeout(function () { form.submit(); }, 120);
        }
    });

    /* Coming back with the back button? Re-enable everything. */
    window.addEventListener("pageshow", function (event) {
        if (!event.persisted) return;
        sending = false;
        submitBtn.disabled = false;
        submitBtn.classList.remove("is-loading");
        submitBtn.querySelector(".lq-btn-text").textContent = "Create Account";
    });
})();
