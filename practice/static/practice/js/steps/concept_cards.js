/* concept_cards step (design: Learn). Not graded: every card must be flipped once to continue. */
CQSteps.register("concept_cards", function (step, ui) {
  var h = ui.h, tips = step.tips || {}, seen = {}, total = step.cards.length;
  var c = ui.coach(120, tips.start || "Tap each card to flip it.", "talk");
  var counter = h("span", { class: "cqs-count" }, ["0 of " + total + " flipped"]);

  function count() { return Object.keys(seen).length; }

  var cards = step.cards.map(function (card, i) {
    var b = h("button", { type: "button", class: "flip rise", "aria-pressed": "false", style: { animationDelay: (0.1 * (i + 1)) + "s" } }, [
      h("div", { class: "flip-inner" }, [
        h("div", { class: "face front" }, [
          h("div", { class: "cqs-card-icon" }, [ui.icon(card.icon, 46)]),
          h("span", { class: "cqs-card-title" }, [card.title]),
          h("span", { class: "cqs-card-hint" }, ["Tap to flip"])
        ]),
        h("div", { class: "face back" }, [
          h("span", { class: "cqs-card-why" }, ["WHY IT MATTERS"]),
          h("span", { class: "cqs-card-back" }, [card.back])
        ])
      ])
    ]);
    b.addEventListener("click", function () {
      var on = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", on ? "true" : "false");
      seen[i] = true;
      var n = count();
      counter.textContent = n + " of " + total + " flipped";
      var all = n === total;
      c.say(all ? (tips.done || "You’ve got the basics!") : (tips.progress || "Nice! Keep flipping."));
      c.face(all ? "happy" : "smile");
      ui.changed();
    });
    return b;
  });

  var el = h("div", { style: { display: "flex", flexDirection: "column", gap: "24px" } }, [
    c.el,
    h("div", { class: "cqs-head-row" }, [h("h1", { class: "cqs-h1" }, [step.title]), counter]),
    h("div", { class: "cqs-flip-grid" }, cards)
  ]);

  return {
    el: el, footer: "continue",
    note: function () { return count() === total ? "All cards flipped" : "Flip all " + total + " cards to continue"; },
    ready: function () { return count() === total; },
    answer: function () { return { flipped: total }; }
  };
});
