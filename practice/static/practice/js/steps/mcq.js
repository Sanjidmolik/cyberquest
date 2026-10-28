/* mcq step (design: Decision). Answer: the chosen option index. */
CQSteps.register("mcq", function (step, ui) {
  var h = ui.h, tips = step.tips || {}, choice = null, checked = false;
  var c = ui.coach(128, tips.start || "Pick the best response.", "think");
  var buttons = step.options.map(function (text, i) {
    var b = ui.tile("cqs-option rise", { "aria-pressed": "false", style: { animationDelay: (0.1 + i * 0.08) + "s" } }, [
      h("span", { class: "cqs-option-key" }, [String(i + 1)]), h("span", null, [text])
    ]);
    b.addEventListener("click", function () {
      if (checked) return;
      choice = i;
      buttons.forEach(function (x, j) { ui.setState(x, j === i ? "sel" : ""); x.setAttribute("aria-pressed", j === i ? "true" : "false"); });
      c.say(tips.ready || "Locked in? Hit Check.");
      c.face("neutral");
      ui.changed();
    });
    return b;
  });
  var el = h("div", { style: { display: "flex", flexDirection: "column", gap: "24px" } }, [
    h("span", { class: "cqs-eyebrow cqs-eyebrow--warn" }, [step.eyebrow || "ONE CHOICE"]),
    c.el,
    h("div", { class: "cqs-options", role: "group", "aria-label": "Options" }, buttons)
  ]);
  return {
    el: el, width: "860", footer: "check",
    ready: function () { return choice !== null; },
    answer: function () { return choice; },
    onResult: function (res) {
      checked = true;
      var right = [].concat(res.reveal ? res.reveal.correct : []);   // one index or several
      buttons.forEach(function (b, i) {
        b.disabled = true;
        if (right.indexOf(i) !== -1) ui.setState(b, "right");
        else if (i === choice) ui.setState(b, "wrong", "shake");
        else ui.setState(b, "dim");
      });
      c.say(res.correct ? (tips.good || "Nice!") : (tips.bad || "Not quite."));
      c.face(res.correct ? "correct" : "wrong");
    }
  };
});
