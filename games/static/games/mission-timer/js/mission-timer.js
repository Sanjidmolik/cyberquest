(function () {
  "use strict";

  var root = document.querySelector("[data-mission-timer]");
  var form = document.getElementById("mission-quiz");
  if (!root || !form || root.getAttribute("data-running") !== "1") return;

  var limitMs = parseInt(root.getAttribute("data-limit") || "60", 10) * 1000;
  if (!limitMs) limitMs = 60000;
  var mirrors = Array.prototype.slice.call(document.querySelectorAll("[data-clock-mirror]"));
  var faces = [root].concat(mirrors).map(function (node) {
    return {
      node: node,
      clock: new window.CQAnalogClock(node.querySelector("[data-clock]")),
      digital: node.querySelector("[data-digital]"),
    };
  });
  var label = root.querySelector("[data-time-label]");
  var caption = root.querySelector("[data-caption]");
  var actionField = form.querySelector("[data-action-field]");
  var questions = Array.prototype.slice.call(form.querySelectorAll("[data-question]"));
  var progress = form.querySelector("[data-progress]");
  var fill = form.querySelector("[data-progress-fill]");
  var prev = form.querySelector("[data-prev]");
  var next = form.querySelector("[data-next]");
  var submit = form.querySelector("[data-submit]");
  var index = 0;
  var warned15 = false;
  var warned5 = false;
  var expired = false;
  var lastSpoken = "";
  var controller = null;
  var pulse = 0;

  function format(ms) {
    var secs = Math.ceil(ms / 1000);
    if (secs < 0) secs = 0;
    if (secs > 3600) secs = 3600;
    var minutes = Math.floor(secs / 60);
    var remain = secs % 60;
    return {
      text: String(minutes).padStart(2, "0") + ":" + String(remain).padStart(2, "0"),
      secs: secs,
    };
  }

  function paint(ms) {
    var shown = format(ms);
    faces.forEach(function (face) {
      face.clock.setRemaining(ms, limitMs);
      if (face.digital && face.digital.textContent !== shown.text) face.digital.textContent = shown.text;
    });
    return shown;
  }

  function setState(name) {
    faces.forEach(function (face) {
      face.node.classList.remove("is-warn", "is-final", "is-done");
      if (name) face.node.classList.add(name);
    });
  }

  function showQuestion(nextIndex) {
    index = nextIndex;
    questions.forEach(function (panel, i) {
      var active = i === index;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    if (progress) progress.textContent = "Question " + (index + 1) + " of " + questions.length;
    if (fill) fill.style.width = ((index + 1) / questions.length * 100) + "%";
    if (prev) prev.disabled = index === 0;
    var last = index === questions.length - 1;
    if (next) next.hidden = last;
    if (submit) submit.hidden = !last;
    var prompt = questions[index] && questions[index].querySelector(".cq-prompt");
    if (prompt) prompt.focus({ preventScroll: true });
  }

  function restoreAnswers() {
    var node = document.getElementById("saved-answers");
    if (!node) return;
    var saved = {};
    try { saved = JSON.parse(node.textContent || "{}"); } catch (err) { saved = {}; }
    Object.keys(saved).forEach(function (id) {
      var input = form.querySelector("input[name='question_" + id + "'][value='" + saved[id] + "']");
      if (input) input.checked = true;
    });
  }

  function saveAnswers() {
    var data = new FormData(form);
    data.set("action", "save");
    fetch(window.location.pathname, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "fetch" },
      credentials: "same-origin",
    }).then(function (response) { return response.json(); }).then(function (payload) {
      if (!payload || expired) return;
      if (payload.expired || payload.remaining_ms === 0) finish("timeout");
      else if (typeof payload.remaining_ms === "number" && controller) controller.resync(payload.remaining_ms);
    }).catch(function () {});
  }

  function resync() {
    fetch(window.location.pathname + "?sync=1", { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (!payload || !controller || expired) return;
        controller.resync(payload.remaining_ms || 0);
        if (!payload.running) finish("timeout");
      })
      .catch(function () {});
  }

  function finish(kind) {
    if (expired) return;
    expired = true;
    window.clearInterval(pulse);
    if (controller) controller.stop();
    paint(0);
    setState("is-done");
    window.CQComic.show(caption, "TIME'S UP!");
    if (label) label.textContent = "Time is up. Submitting answers.";
    if (actionField) actionField.value = kind || "timeout";
    window.setTimeout(function () { form.submit(); }, window.CQComic.reduced ? 200 : 700);
  }

  function onFrame(ms) {
    var shown = paint(ms);
    if (label && shown.text !== lastSpoken && (shown.secs === 60 || shown.secs === 30 || shown.secs === 15 || shown.secs === 5 || shown.secs === 0)) {
      label.textContent = "Time remaining " + shown.text + ".";
      lastSpoken = shown.text;
    }
    if (ms <= 15000 && ms > 5000 && !warned15) {
      warned15 = true;
      setState("is-warn");
      window.CQComic.show(caption, "HURRY UP!");
    }
    if (ms <= 5000 && ms > 0 && !warned5) {
      warned5 = true;
      setState("is-final");
      window.CQComic.show(caption, "FINAL SECONDS!");
      if (label) {
        label.textContent = "Final seconds. Time remaining " + shown.text + ".";
        lastSpoken = shown.text;
      }
    }
    if (ms <= 0) finish("timeout");
  }

  var serverStamp = Date.parse(root.getAttribute("data-server-now") || "");
  var skew = isNaN(serverStamp) ? 0 : serverStamp - Date.now();
  var deadlineStamp = Date.parse(root.getAttribute("data-deadline") || "");

  function authoritativeRemaining() {
    if (isNaN(deadlineStamp)) return null;
    return Math.max(0, deadlineStamp - Date.now() - skew);
  }

  function arm(ms) {
    if (controller) controller.stop();
    window.clearInterval(pulse);
    controller = new window.CQTimerController({
      remainingMs: ms,
      onFrame: onFrame,
    });
    controller.start();
    pulse = window.setInterval(function () {
      if (expired || !controller) return;
      onFrame(controller.remaining());
    }, 250);
  }

  function adoptServerTime() {
    var ms = authoritativeRemaining();
    if (ms === null || expired) return;
    if (!controller || controller.stopped) arm(ms);
    else controller.resync(ms);
    if (ms <= 0) finish("timeout");
    else onFrame(controller.remaining());
    resync();
  }

  restoreAnswers();
  showQuestion(0);
  form.addEventListener("change", function (event) {
    if (event.target && event.target.type === "radio") saveAnswers();
  });
  if (prev) prev.addEventListener("click", function () { if (index > 0) showQuestion(index - 1); });
  if (next) next.addEventListener("click", function () {
    if (index < questions.length - 1) showQuestion(index + 1);
  });
  form.addEventListener("submit", function () {
    if (actionField && actionField.value === "submit") {
      expired = true;
      if (controller) controller.stop();
    }
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && !expired) adoptServerTime();
  });
  window.addEventListener("pageshow", function () {
    if (!expired) adoptServerTime();
  });

  var initial = authoritativeRemaining();
  if (initial === null) {
    initial = parseInt(root.getAttribute("data-remaining-ms") || String(limitMs), 10);
    if (isNaN(initial)) initial = limitMs;
  }
  paint(initial);
  if (initial <= 0) {
    finish("timeout");
  } else {
    arm(initial);
  }
  window.addEventListener("pagehide", function () {
    window.clearInterval(pulse);
    if (controller) controller.stop();
  });
})();
