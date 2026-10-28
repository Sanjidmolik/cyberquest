/* order step (design: Respond). Tap steps into the plan in order; tap a placed step to undo.
   Answer: the list of item ids in the chosen order. */
CQSteps.register("order", function (step, ui) {
  var h = ui.h, tips = step.tips || {}, plan = [], checked = false;
  var total = step.items.length;
  var byId = {};
  step.items.forEach(function (it) { byId[String(it.id)] = it; });
  var c = ui.coach(112, tips.start || "Tap steps in the order you’d do them.", "think");
  var slotsCol = h("section", { class: "cqs-order-col" });
  var poolCol = h("section", { class: "cqs-order-col" });
  var slotBtns = [];

  function render() {
    slotsCol.innerHTML = "";
    slotsCol.appendChild(h("span", { class: "cqs-label" }, ["YOUR PLAN"]));
    slotBtns = [];
    for (var i = 0; i < total; i++) {
      var id = plan[i];
      var filled = id !== undefined;
      var b = ui.tile("cqs-slot" + (filled ? " is-sel pop-in" : " is-empty"), filled ? { "aria-label": "Step " + (i + 1) + ": " + byId[id].text + ". Tap to remove." } : { disabled: true, "aria-label": "Empty slot " + (i + 1) }, [
        h("span", { class: "cqs-slot-num" }, [String(i + 1)]),
        h("span", null, [filled ? byId[id].text : "Empty slot"])
      ]);
      if (filled) b.addEventListener("click", (function (x) { return function () { if (checked) return; plan = plan.filter(function (p) { return p !== x; }); update(); }; })(id));
      slotBtns.push(b);
      slotsCol.appendChild(b);
    }
    poolCol.innerHTML = "";
    poolCol.appendChild(h("span", { class: "cqs-label" }, ["STEPS · TAP TO ADD"]));
    var left = step.items.filter(function (it) { return plan.indexOf(String(it.id)) === -1; });
    left.forEach(function (it) {
      var b = ui.tile("cqs-pool-item pop-in", null, [it.text]);
      b.addEventListener("click", function () { if (checked) return; plan.push(String(it.id)); update(); });
      poolCol.appendChild(b);
    });
    if (!left.length) poolCol.appendChild(h("div", { class: "cqs-pool-empty" }, ["All steps placed. Tap a step in your plan to take it back."]));
  }

  function update() {
    render();
    var full = plan.length === total;
    c.say(full ? (tips.ready || "Plan ready? Check it.") : (plan.length ? (tips.progress || "Keep going.") : (tips.start || "")));
    c.face(full ? "smile" : "think");
    ui.changed();
  }
  render();

  var el = h("div", { style: { display: "flex", flexDirection: "column", gap: "22px" } }, [
    c.el,
    h("h1", { class: "cqs-h1" }, [step.title]),
    h("div", { class: "cqs-split" }, [slotsCol, poolCol])
  ]);

  return {
    el: el, footer: "check",
    ready: function () { return plan.length === total; },
    answer: function () { return plan.slice(); },
    onResult: function (res) {
      checked = true;
      var right = ((res.reveal && res.reveal.correct) || []).map(String);
      slotBtns.forEach(function (b, i) {
        b.disabled = true;
        ui.setState(b, plan[i] === right[i] ? "right" : "wrong", plan[i] === right[i] ? "" : "shake");
      });
      if (!res.correct && right.length) {
        poolCol.innerHTML = "";
        poolCol.appendChild(h("span", { class: "cqs-label" }, ["THE RIGHT ORDER"]));
        poolCol.appendChild(h("ol", { class: "cqs-answer-list" }, right.map(function (id) { return h("li", null, [byId[id].text]); })));
      }
      c.say(res.correct ? (tips.good || "Textbook!") : (tips.bad || "The orange steps are in the wrong spot."));
      c.face(res.correct ? "correct" : "wrong");
    }
  };
});
