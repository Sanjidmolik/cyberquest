/* match step (design: Recap). Tap a problem, then the fix it pairs with; the server checks
   every pair at once so the answers never reach the browser early.
   Answer: [[leftId, rightId], ...]. */
CQSteps.register("match", function (step, ui) {
  var h = ui.h, tips = step.tips || {}, checked = false;
  var pairs = [];          // [{l, r, n}]
  var pickL = null, pickR = null;
  var c = ui.coach(120, tips.start || "Tap a problem, then the fix that solves it.", "smile");
  var leftBtns = {}, rightBtns = {};

  function pairOf(side, id) { return pairs.filter(function (p) { return p[side] === id; })[0]; }

  function paint() {
    Object.keys(leftBtns).forEach(function (id) { paintOne(leftBtns[id], "l", id, pickL === id); });
    Object.keys(rightBtns).forEach(function (id) { paintOne(rightBtns[id], "r", id, pickR === id); });
    var all = pairs.length === step.left.length;
    c.say(all ? (tips.ready || "All paired up? Check your matches.") : (pairs.length ? (tips.progress || "Keep pairing.") : (tips.start || "")));
    ui.changed();
  }

  function paintOne(btn, side, id, picked) {
    var p = pairOf(side, id);
    var tag = btn.querySelector(".cqs-pair-tag");
    btn.classList.remove("is-paired");
    ui.setState(btn, picked ? "sel" : "");
    if (p) { btn.classList.add("is-paired"); tag.hidden = false; tag.textContent = String(p.n); }
    else tag.hidden = true;
    btn.setAttribute("aria-pressed", picked ? "true" : "false");
  }

  function relabel() { pairs.forEach(function (p, i) { p.n = i + 1; }); }

  function tap(side, id) {
    if (checked) return;
    var existing = pairOf(side, id);
    if (existing) {               // tapping a paired item undoes that pair
      pairs.splice(pairs.indexOf(existing), 1);
      relabel(); pickL = pickR = null; paint(); return;
    }
    if (side === "l") pickL = pickL === id ? null : id; else pickR = pickR === id ? null : id;
    if (pickL !== null && pickR !== null) {
      pairs.push({ l: pickL, r: pickR, n: pairs.length + 1 });
      pickL = pickR = null;
    }
    paint();
  }

  function column(items, side, store, label) {
    return h("div", { class: "cqs-match-col" }, [h("span", { class: "cqs-label", style: { letterSpacing: "1px" } }, [label])].concat(items.map(function (item) {
      var b = ui.tile("cqs-match-item", { "aria-pressed": "false" }, [h("span", null, [item.text]), h("span", { class: "cqs-pair-tag", hidden: true, "aria-hidden": "true" })]);
      b.addEventListener("click", function () { tap(side, String(item.id)); });
      store[String(item.id)] = b;
      return b;
    })));
  }

  var el = h("div", { style: { display: "flex", flexDirection: "column", gap: "26px" } }, [
    h("span", { class: "cqs-eyebrow" }, [step.eyebrow || "RECAP · MATCH THE PAIRS"]),
    c.el,
    h("div", { class: "cqs-match-grid" }, [
      column(step.left, "l", leftBtns, step.left_label || "PROBLEM"),
      column(step.right, "r", rightBtns, step.right_label || "FIX")
    ])
  ]);

  return {
    el: el, width: "900", footer: "check",
    ready: function () { return pairs.length === step.left.length; },
    answer: function () { return pairs.map(function (p) { return [p.l, p.r]; }); },
    onResult: function (res) {
      checked = true;
      ((res.reveal && res.reveal.pairs) || []).forEach(function (m) {
        var ok = m[2];
        [leftBtns[m[0]], rightBtns[m[1]]].forEach(function (b) {
          b.disabled = true; b.classList.remove("is-paired");
          ui.setState(b, ok ? "right" : "wrong", ok ? "pop-in" : "shake");
        });
      });
      c.say(res.correct ? (tips.good || "Perfect match!") : (tips.bad || "Nearly."));
      c.face(res.correct ? "correct" : "wrong");
    }
  };
});
