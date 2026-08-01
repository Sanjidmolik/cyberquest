/*
  courses/static/courses/js/intro.js
  --------------------------------------
  Runs a fake "boot sequence" that types itself out, THEN reveals the
  actual page content. This is the page's signature interactive moment --
  everything else on the page stays static/disciplined by comparison.

  This file is isolated to the courses app; it has no effect on any
  other page (login/dashboard have their own JS if they ever need it).
*/

document.addEventListener("DOMContentLoaded", function () {
    const bootLines = [
        "> BOOTING CYBERQUEST TRAINING MODULE...",
        "> LOADING SECURITY PROTOCOLS... OK",
        "> ESTABLISHING SANDBOXED ENVIRONMENT... OK",
        "> VERIFYING TRAINEE CLEARANCE... OK",
        "> SYSTEM READY.",
        "",
    ];

    const bootEl = document.getElementById("boot-sequence");
    const mainEl = document.getElementById("main-content");

    let lineIndex = 0;
    let charIndex = 0;

    // Types one character at a time, line by line, then shows the main content.
    function typeNextChar() {
        if (lineIndex >= bootLines.length) {
            // Boot sequence finished -- reveal the real page content
            mainEl.classList.remove("hidden");
            startReadTimer();
            return;
        }

        const currentLine = bootLines[lineIndex];

        if (charIndex < currentLine.length) {
            bootEl.textContent += currentLine.charAt(charIndex);
            charIndex++;
            setTimeout(typeNextChar, 18); // typing speed (ms per character)
        } else {
            bootEl.textContent += "\n";
            lineIndex++;
            charIndex = 0;
            setTimeout(typeNextChar, 150); // pause between lines
        }
    }

    /*
      Countdown that disables the "Continue" button until the user has
      had the page open for CQ_MINIMUM_READ_SECONDS. This is a UX nudge
      only -- the real enforcement happens server-side in courses/views.py,
      since anyone could otherwise just re-enable the button via dev tools.
    */
    function startReadTimer() {
        // Skip the timer entirely if this user already completed the
        // course before (they're just revisiting the page).
        if (typeof CQ_ALREADY_COMPLETED !== "undefined" && CQ_ALREADY_COMPLETED) {
            return;
        }

        const btn = document.getElementById("continue-btn");
        const countdownEl = document.getElementById("countdown");
        if (!btn || !countdownEl) return;

        let secondsLeft = CQ_MINIMUM_READ_SECONDS;

        const timerId = setInterval(function () {
            secondsLeft--;
            countdownEl.textContent = secondsLeft;

            if (secondsLeft <= 0) {
                clearInterval(timerId);
                btn.disabled = false;
                btn.textContent = "> INITIALIZE_TRAINING.EXE";
            }
        }, 1000);
    }

    typeNextChar();
});
