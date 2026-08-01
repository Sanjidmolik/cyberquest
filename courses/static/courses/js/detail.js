/*
  courses/static/courses/js/detail.js
  ---------------------------------------
  Countdown timer for an individual course's reading page. Simpler than
  intro.js (no boot-sequence animation here -- the lesson content itself
  is the focus of this page).
*/

document.addEventListener("DOMContentLoaded", function () {
    if (typeof CQ_ALREADY_COMPLETED !== "undefined" && CQ_ALREADY_COMPLETED) {
        return; // already completed -- button is already enabled server-side
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
            btn.textContent = "> MARK AS COMPLETE";
        }
    }, 1000);
});
