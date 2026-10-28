/* configure step (design: Configure). Pick one option per setting, then check (the label comes from check_label).
   Which option is secure stays on the server, so the attack simulator reports its score and
   threat levels after the run instead of live. Answer: {settingKey: optionIndex}. */
CQSteps.register("configure", function (step, ui) {
  var h = ui.h, tips = step.tips || {}, picks = {}, checked = false;
  var c = ui.coach(112, tips.start || "Choose the safest option in each row, then check.", "think");
  var rows = {};
  var CIRC = 276.5;

  function picked() { return step.settings.every(function (s) { return picks[s.key] !== undefined; }); }

  var settings = step.settings.map(function (s) {
    var opts = s.options.map(function (label, i) {
      var b = ui.tile("", { role: "radio", "aria-checked": "false" }, [label]);
      b.addEventListener("click", function () {
        if (checked) return;
        picks[s.key] = i;
        opts.forEach(function (o, j) { ui.setState(o, j === i ? "sel" : ""); o.setAttribute("aria-checked", j === i ? "true" : "false"); });
        if (picked()) { c.say(tips.progress || "Happy with every row? Run the attack."); c.face("smile"); }
        ui.changed();
      });
      return b;
    });
    rows[s.key] = opts;
    return h("div", { class: "cqs-setting" }, [
      h("div", null, [h("span", { class: "cqs-setting-name" }, [s.label]), s.hint ? h("span", { class: "cqs-setting-hint" }, [s.hint]) : null]),
      h("div", { class: "cqs-setting-opts", role: "radiogroup", "aria-label": s.label }, opts)
    ]);
  });

  var ringFill = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  var ringSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  ringSvg.setAttribute("width", "110"); ringSvg.setAttribute("height", "110"); ringSvg.setAttribute("viewBox", "0 0 110 110");
  ringSvg.setAttribute("role", "img"); ringSvg.setAttribute("aria-label", (step.score_label || "Score") + " not tested yet");
  var track = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  [["cx", 55], ["cy", 55], ["r", 44], ["fill", "none"], ["stroke", "#EDE8FB"], ["stroke-width", 12]].forEach(function (a) { track.setAttribute(a[0], a[1]); });
  [["cx", 55], ["cy", 55], ["r", 44], ["fill", "none"], ["stroke", "#D9480F"], ["stroke-width", 12], ["stroke-linecap", "round"],
   ["stroke-dasharray", CIRC], ["stroke-dashoffset", CIRC], ["transform", "rotate(-90 55 55)"], ["class", "ring-fill"]].forEach(function (a) { ringFill.setAttribute(a[0], a[1]); });
  ringSvg.appendChild(track); ringSvg.appendChild(ringFill);
  var ringNum = h("span", { class: "cqs-ring-num" }, ["?"]);
  var ringNote = h("span", { class: "cqs-ring-note" }, ["Run the attack to test your settings"]);

  var threatEls = (step.threats || []).map(function (t) {
    var pill = h("span", { class: "cqs-threat-pill" }, ["NOT TESTED"]);
    var row = h("div", { class: "cqs-threat" }, [
      h("div", { class: "cqs-threat-name" }, [h("div", { class: "cqs-threat-ic" }, [ui.icon(t.icon || "shield", 20)]), h("span", null, [t.label])]),
      pill
    ]);
    row._pill = pill;
    return row;
  });

  var el = h("div", { style: { display: "flex", flexDirection: "column", gap: "22px" } }, [
    c.el,
    h("h1", { class: "cqs-h1" }, [step.title]),
    h("div", { class: "cqs-split" }, [
      h("section", { class: "cqs-card cqs-console rise" }, [
        h("div", { class: "cqs-console-bar" }, [
          h("i", { style: { background: "#F25F7A" } }), h("i", { style: { background: "#FFB020" } }), h("i", { style: { background: "#3DD9A4" } }),
          h("span", null, [step.console_title || "Admin console"])
        ])
      ].concat(settings)),
      h("aside", { class: "cqs-card cqs-sim rise" }, [
        h("span", { class: "cqs-label" }, [step.sim_title || "RESULT"]),
        h("div", { class: "cqs-ring-row" }, [
          h("div", { class: "cqs-ring" }, [ringSvg, ringNum]),
          h("div", null, [h("span", { class: "cqs-ring-title" }, [step.score_label || "Score"]), ringNote])
        ])
      ].concat(threatEls))
    ])
  ]);

  return {
    el: el, footer: "check", checkLabel: step.check_label || "Check",
    ready: picked,
    answer: function () { var a = {}; Object.keys(picks).forEach(function (k) { a[k] = picks[k]; }); return a; },
    onResult: function (res) {
      checked = true;
      var r = res.reveal || {};
      var score = r.score || 0;
      ringFill.setAttribute("stroke-dashoffset", String(CIRC - CIRC * Math.min(score, 100) / 100));
      ringFill.setAttribute("stroke", score >= 100 ? "#0B8A5F" : (score >= 50 ? "#FFB020" : "#D9480F"));
      ringSvg.setAttribute("aria-label", (step.score_label || "Score") + " " + score + " out of 100");
      ringNum.textContent = String(score);
      ringNote.textContent = res.correct ? "Everything secure" : (score >= 50 ? "Getting there" : "Wide open");
      var LV = ["EXPOSED", "PARTIAL", "BLOCKED"];
      (r.threats || []).forEach(function (lvl, i) {
        var row = threatEls[i]; if (!row) return;
        row.className = "cqs-threat lvl-" + lvl + (lvl < 2 ? " shake" : " pop-in");
        row._pill.textContent = LV[lvl];
      });
      step.settings.forEach(function (s) {
        rows[s.key].forEach(function (b, j) {
          b.disabled = true;
          if (j === picks[s.key]) ui.setState(b, r.secure && r.secure[s.key] ? "right" : "wrong");
        });
      });
      c.say(res.correct ? (tips.good || "All secure. Great work!") : (tips.bad || "Something is still weak. Check the orange rows."));
      c.face(res.correct ? "correct" : "wrong");
    }
  };
});
