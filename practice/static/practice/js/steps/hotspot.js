/* hotspot step (designs: Investigation = layout "flow", Evidence = layout "fields").
   Answer: the list of selected item indexes. */
CQSteps.register("hotspot", function (step, ui) {
  var h = ui.h, tips = step.tips || {}, need = step.select || 3, sel = {}, checked = false;
  var flow = step.layout !== "fields";
  // Pill wording comes from the scenario; the defaults suit any topic.
  var L = step.labels || {};
  var PICK = L.pick || "Selected", RIGHT = L.right || "Key evidence", WRONG = L.wrong || "Not relevant", MISSED = L.missed || "Missed";
  var c = ui.coach(112, tips.start || "Tap the clues.", "think");
  var counter = h("span", { class: "cqs-count" }, ["0 of " + need + " selected"]);
  var pills = [];

  function count() { return Object.keys(sel).filter(function (k) { return sel[k]; }).length; }

  var tiles = step.items.map(function (item, i) {
    var pill = h("span", { class: "cqs-pill", hidden: true });
    pills.push(pill);
    var kids = flow
      ? [h("div", { class: "cqs-node-icon" }, [ui.icon(item.icon || "lock", 28)]),
         h("span", { class: "cqs-node-label" }, [item.label]),
         h("span", { class: "cqs-node-val" }, [item.value]), pill]
      : [h("span", { class: "cqs-field-txt" }, [h("span", { class: "cqs-field-k" }, [item.label]), h("span", { class: "cqs-field-v" }, [item.value])]), pill];
    var b = ui.tile(flow ? "cqs-node" : "cqs-field", { "aria-pressed": "false" }, kids);
    b.addEventListener("click", function () {
      if (checked) return;
      sel[i] = !sel[i];
      b.setAttribute("aria-pressed", sel[i] ? "true" : "false");
      ui.setState(b, sel[i] ? "sel" : "");
      pill.hidden = !sel[i];
      pill.className = "cqs-pill cqs-pill--sel";
      pill.textContent = PICK;
      var n = count();
      counter.textContent = n + " of " + need + " selected";
      c.say(n >= need ? (tips.ready || "Happy with your picks? Hit Check.") : (n ? (tips.progress || "Good eye! Keep looking.") : (tips.start || "")));
      c.face(n ? "smile" : "think");
      ui.changed();
    });
    return b;
  });

  var board = flow
    ? h("div", { class: "cqs-flow rise" }, [h("div", { class: "cqs-flow-grid" }, [
        h("div", { class: "cqs-flow-line", "aria-hidden": "true" }),
        h("div", { class: "packet", "aria-hidden": "true" })
      ].concat(tiles))])
    : h("section", { class: "cqs-card cqs-evidence rise" }, [
        h("div", { class: "cqs-evidence-banner" }, [ui.icon("warn", 22, 2.6), h("span", null, [step.banner || ""])]),
        h("div", { class: "cqs-field-grid" }, tiles)
      ]);

  // What the learner is looking at (the email, alert or device panels), before picking the evidence.
  var context = (step.context || []).length ? h("section", { class: "cqs-card cqs-context rise" }, step.context.map(function (panel) {
    return h("div", { class: "cqs-context-panel" }, [
      h("span", { class: "cqs-label" }, [String(panel.title || "").toUpperCase()]),
      h("dl", null, panel.rows.map(function (r) {
        return h("div", { class: r.flag ? "is-flag" : "" }, [h("dt", null, [r.label]), h("dd", null, [r.value])]);
      }))
    ]);
  })) : null;

  var el = h("div", { style: { display: "flex", flexDirection: "column", gap: "24px" } }, [
    c.el,
    context,
    h("div", { class: "cqs-head-row" }, [h("h1", { class: "cqs-h1" }, [step.title]), counter]),
    board
  ]);

  return {
    el: el, footer: "check",
    ready: function () { return count() === need; },
    answer: function () { return step.items.map(function (_, i) { return i; }).filter(function (i) { return sel[i]; }); },
    onResult: function (res) {
      checked = true;
      var right = {};
      ((res.reveal && res.reveal.correct) || []).forEach(function (i) { right[i] = true; });
      tiles.forEach(function (b, i) {
        b.disabled = true;
        var pill = pills[i];
        if (right[i] && sel[i]) { ui.setState(b, "right"); pill.hidden = false; pill.className = "cqs-pill cqs-pill--good"; pill.textContent = RIGHT; }
        else if (!right[i] && sel[i]) { ui.setState(b, "wrong", "shake"); pill.hidden = false; pill.className = "cqs-pill cqs-pill--bad"; pill.textContent = WRONG; }
        else if (right[i] && !sel[i]) { ui.setState(b, "missed", "shake"); pill.hidden = false; pill.className = "cqs-pill cqs-pill--bad"; pill.textContent = MISSED; }
      });
      c.say(res.correct ? (tips.good || "Sharp eyes!") : (tips.bad || "Look at what turned orange."));
      c.face(res.correct ? "correct" : "wrong");
    }
  };
});
