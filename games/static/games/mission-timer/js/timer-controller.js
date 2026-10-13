(function (global) {
  "use strict";

  function TimerController(options) {
    this.remainingAtStart = options.remainingMs;
    this.startedAt = performance.now();
    this.onFrame = options.onFrame;
    this.raf = 0;
    this.stopped = false;
  }

  TimerController.prototype.remaining = function () {
    return Math.max(0, this.remainingAtStart - (performance.now() - this.startedAt));
  };

  TimerController.prototype.resync = function (remainingMs) {
    this.remainingAtStart = remainingMs;
    this.startedAt = performance.now();
  };

  TimerController.prototype.start = function () {
    var self = this;
    function frame() {
      if (self.stopped) return;
      self.onFrame(self.remaining());
      self.raf = window.requestAnimationFrame(frame);
    }
    this.raf = window.requestAnimationFrame(frame);
  };

  TimerController.prototype.stop = function () {
    this.stopped = true;
    if (this.raf) window.cancelAnimationFrame(this.raf);
  };

  global.CQTimerController = TimerController;
})(window);
