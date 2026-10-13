(function (global) {
  "use strict";

  // SVG rotate() is clockwise. The hand shows elapsed time, so it leaves 12
  // and travels clockwise as the digital countdown falls. Mapping remaining
  // time directly made the hand travel counter-clockwise, and remaining
  // time modulo 60 snapped a full minute back to 0 degrees.
  function countdownAngle(remainingMs, limitMs) {
    var limit = limitMs > 0 ? limitMs : 60000;
    var remaining = Math.max(0, Math.min(limit, remainingMs));
    var elapsed = limit - remaining;
    return (elapsed / limit) * 360;
  }

  function AnalogClock(root) {
    this.hand = root.querySelector("[data-hand='second']");
  }

  AnalogClock.prototype.setRemaining = function (ms, limitMs) {
    if (!this.hand) return;
    var angle = countdownAngle(ms, limitMs);
    this.hand.setAttribute("transform", "rotate(" + angle + " 100 100)");
  };

  global.CQAnalogClock = AnalogClock;
  global.CQCountdownAngle = countdownAngle;
})(window);
