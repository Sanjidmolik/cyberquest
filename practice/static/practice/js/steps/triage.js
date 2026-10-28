/* triage step (design: Triage). Alerts arrive one by one, then the learner sets a severity.
   Answer: the chosen severity index. */
CQSteps.register("triage", function (step, ui) {
  var h = ui.h, tips = step.tips || {}, sev = null, checked = false, shown = 1;
  var total = step.alerts.length;
  var c = ui.coach(104, tips.start || "Read every alert before you decide.", "surprised");
  var feed = h("div", { style: { display: "flex", flexDirection: "column", gap: "12px" }, "aria-live": "polite" });
  var feedNote = h("span", { class: "cqs-feed-note tick" }, ["1 of " + total]);
  var typing = h("div", { class: "cqs-typing" }, [h("span", { class: "tick" }, ["●"]), " New alert incoming…"]);

  function alertCard(a) {
    return h("div", { class: "cqs-alert rise" }, [
      h("div", { class: "cqs-ini", style: { background: a.bg || "#7C4DFF" } }, [a.ini]),
      h("div", { class: "cqs-alert-body" }, [
        h("div", null, [h("span", { class: "cqs-alert-from" }, [a.from]), h("span", { class: "cqs-alert-time" }, [a.time])]),
        h("span", { class: "cqs-alert-msg" }, [a.msg])
      ])
    ]);
  }
  feed.appendChild(alertCard(step.alerts[0]));

  function allIn() { return shown >= total; }

  var buttons = step.levels.map(function (lvl, i) {
    var b = ui.tile("cqs-sev", { "aria-pressed": "false" }, [
      h("span", { class: "cqs-sev-dot", style: { background: lvl.dot } }),
      h("span", null, [h("span", { class: "cqs-sev-label" }, [lvl.label]), h("span", { class: "cqs-sev-desc" }, [lvl.desc])])
    ]);
    b.addEventListener("click", function () {
      if (checked) return;
      sev = i;
      buttons.forEach(function (x, j) { ui.setState(x, j === i ? "sel" : ""); x.setAttribute("aria-pressed", j === i ? "true" : "false"); });
      if (allIn()) { c.say(tips.ready || "Locked in? Hit Check."); }
      ui.changed();
    });
    return b;
  });

  var el = h("div", { style: { display: "flex", flexDirection: "column", gap: "22px" } }, [
    h("div", { class: "cqs-head-row" }, [h("h1", { class: "cqs-h1" }, [step.title]), h("span", { class: "cqs-live-tag" }, [step.live_tag || "INCIDENT"])]),
    h("div", { class: "cqs-split" }, [
      h("section", { class: "cqs-col-main" }, [
        h("div", { class: "cqs-feed-head" }, [h("span", { class: "cqs-label" }, ["INCOMING ALERTS"]), feedNote]),
        feed, typing
      ]),
      h("aside", { class: "cqs-col-side" }, [
        c.el,
        h("div", { class: "cqs-card cqs-sev-card rise" }, [h("span", { class: "cqs-label" }, ["SET SEVERITY"])].concat(buttons))
      ])
    ])
  ]);

  return {
    el: el, footer: "check",
    mounted: function () {
      // Alerts arrive one after another, like a live feed. This paces the story only;
      // nothing is timed and nothing fails if the learner takes longer.
      var t = setInterval(function () {
        if (!document.body.contains(feed)) { clearInterval(t); return; }
        shown += 1;
        feed.appendChild(alertCard(step.alerts[shown - 1]));
        feedNote.textContent = shown + " of " + total;
        if (allIn()) {
          clearInterval(t);
          typing.remove();
          feedNote.textContent = total + " alerts";
          feedNote.classList.remove("tick");
          c.say(sev === null ? (tips.all_in || "All alerts are in. What severity is this?") : (tips.ready || "Locked in? Hit Check."));
          c.face("think");
          ui.changed();
        }
      }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 50 : 1400);
    },
    ready: function () { return sev !== null && allIn(); },
    answer: function () { return sev; },
    onResult: function (res) {
      checked = true;
      var right = res.reveal ? res.reveal.correct : null;
      buttons.forEach(function (b, i) {
        b.disabled = true;
        if (i === right) ui.setState(b, "right");
        else if (i === sev) ui.setState(b, "wrong", "shake");
        else ui.setState(b, "dim");
      });
      c.say(res.correct ? (tips.good || "Exactly.") : (tips.bad || "Read the impact again."));
      c.face(res.correct ? "correct" : "wrong");
    }
  };
});
