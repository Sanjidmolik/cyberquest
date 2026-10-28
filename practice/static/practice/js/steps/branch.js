/* branch step (design: Branch). One choice per scene; the server returns the effects, the
   outcome and the next scene, and decides the ending. Answer per scene: {scene, choice}. */
CQSteps.register("branch", function (step, ui) {
  var h = ui.h, scenes = step.scenes, scene = 0, picks = [], busy = false;
  var meters = { sec: 50, trust: 50 };
  var LBL = { good: "Smart call", meh: "Risky call", bad: "Bad call" };
  // Meter names come from the scenario (e.g. Security / Team trust).
  var M = step.meter_labels || {};
  var SEC = M.sec || "Security", TRUST = M.trust || "Trust";
  var story = h("section", { class: "cqs-branch" });
  var secVal = h("span", null, ["50"]), trustVal = h("span", null, ["50"]);
  var secBar = h("div", { class: "meter" }), trustBar = h("div", { class: "meter" });
  var pathRows = scenes.map(function (_, i) {
    var row = h("div", { class: "cqs-path-row" }, [h("span", { class: "cqs-path-dot" }, [String(i + 1)]), h("span", null, ["Scene " + (i + 1)])]);
    return row;
  });

  function meterColor(x) { return x >= 70 ? "#0B8A5F" : (x >= 40 ? "#FFB020" : "#D9480F"); }
  function paintMeters() {
    secVal.textContent = String(meters.sec); trustVal.textContent = String(meters.trust);
    secBar.style.width = meters.sec + "%"; secBar.style.backgroundColor = meterColor(meters.sec);
    trustBar.style.width = meters.trust + "%"; trustBar.style.backgroundColor = meterColor(meters.trust);
  }
  function delta(n) { return (n > 0 ? "+" : "") + n; }

  function showScene() {
    var sc = scenes[scene];
    ui.scene("Scene " + (scene + 1) + " of " + scenes.length);
    ui.progress(scene / scenes.length * 100);
    story.innerHTML = "";
    var c = ui.coach(104, sc.tip, "neutral");
    var chat = h("div", { class: "cqs-card cqs-chat rise" }, [
      h("div", { class: "cqs-chat-bar" }, [h("span", null, [sc.title]), h("small", null, [sc.time])]),
      h("div", { class: "cqs-chat-body" }, sc.msgs.map(function (m) {
        return h("div", { class: "cqs-msg rise" }, [
          h("div", { class: "cqs-ini", style: { background: m.bg || "#7C4DFF" } }, [m.ini]),
          h("div", { style: { minWidth: 0 } }, [
            h("span", { class: "cqs-msg-from" }, [m.from + " ", h("span", { class: "cqs-msg-addr" }, [m.addr || ""])]),
            h("div", { class: "cqs-msg-text" }, [m.text])
          ])
        ]);
      }))
    ]);
    var list = h("div", { style: { display: "flex", flexDirection: "column", gap: "12px" } });
    var buttons = sc.choices.map(function (ch, i) {
      var b = ui.tile("cqs-choice rise", { style: { animationDelay: (i * 0.08) + "s" } }, [
        h("span", { class: "cqs-option-key" }, [String.fromCharCode(65 + i)]), h("span", null, [ch.text])
      ]);
      b.addEventListener("click", function () { choose(i, buttons, list, c); });
      list.appendChild(b);
      return b;
    });
    story.appendChild(chat);
    story.appendChild(c.el);
    story.appendChild(list);
  }

  function choose(i, buttons, list, c) {
    if (busy) return;
    busy = true;
    buttons.forEach(function (b) { b.disabled = true; });
    ui.answer({ scene: scene, choice: i }).then(function (res) {
      var kind = res.effects.kind;
      picks.push(kind);
      meters = res.meters;
      paintMeters();
      var row = pathRows[scene];
      row.className = "cqs-path-row k-" + kind;
      row.lastChild.textContent = LBL[kind];
      c.say(kind === "good" ? "Nice. That’s exactly what a pro would do." : (kind === "bad" ? "Oof. Let’s see how that plays out…" : "Hmm, not ideal. Here’s why."));
      c.face(kind === "good" ? "correct" : (kind === "bad" ? "wrong" : "think"));
      ui.progress((scene + 1) / scenes.length * 100);
      var last = res.next_scene === null || res.next_scene === undefined;
      var chip = function (label, n) { return h("span", { class: "cqs-delta" + (n > 0 ? " is-up" : (n < 0 ? " is-down" : "")) }, [label + " " + delta(n)]); };
      var next = h("button", { type: "button", class: "btn3d " + (kind === "good" ? "btn3d--good" : (kind === "bad" ? "btn3d--bad" : "")) }, [last ? "See ending" : "Next scene"]);
      next.addEventListener("click", function () {
        busy = false;
        if (last) ending(res.ending);
        else { scene = res.next_scene; showScene(); }
      });
      list.replaceWith(h("div", { class: "cqs-outcome sheet cqs-outcome--" + kind, role: "status" }, [
        h("span", { class: "cqs-outcome-label" }, ["WHAT HAPPENED"]),
        h("span", { class: "cqs-outcome-text" }, [res.outcome_text]),
        h("div", { style: { display: "flex", flexWrap: "wrap", gap: "8px" } }, [chip(SEC, res.effects.sec), chip(TRUST, res.effects.trust)]),
        h("div", { style: { display: "flex", justifyContent: "flex-end" } }, [next])
      ]));
      setTimeout(function () { next.focus({ preventScroll: true }); }, 60);
    }).catch(function (err) {
      busy = false;
      buttons.forEach(function (b) { b.disabled = false; });
      list.appendChild(h("p", { role: "alert", class: "cqs-footer-note", style: { color: "#9A3412" } }, [err.message || "Couldn’t reach the server."]));
    });
  }

  function ending(end) {
    end = end || { key: "mid", tag: "ENDING", title: "The end", text: "", face: "think" };
    ui.scene("Ending");
    ui.progress(100);
    story.innerHTML = "";
    var again = h("button", { type: "button", class: "btn3d btn3d--ghost" }, ["Try another path"]);
    var results = h("button", { type: "button", class: "btn3d" }, ["See results"]);
    again.addEventListener("click", function () {
      again.disabled = true;
      ui.restart().catch(function () { again.disabled = false; });
    });
    results.addEventListener("click", function () { results.disabled = true; ui.next(); });
    story.appendChild(h("div", { class: "cqs-card cqs-ending rise" }, [
      ui.avatar(170, end.face || "think"),
      h("span", { class: "cqs-tag cqs-ending-tag--" + end.key, style: { alignSelf: "center" } }, ["ENDING · " + end.tag]),
      h("h1", null, [end.title]),
      h("p", null, [end.text]),
      h("div", { class: "cqs-btn-row" }, [again, results])
    ]));
  }

  var impact = h("aside", { class: "cqs-card cqs-impact rise" }, [
    h("span", { class: "cqs-label" }, ["YOUR IMPACT"]),
    h("div", null, [h("div", { class: "cqs-meter-head" }, [h("span", null, [SEC]), secVal]), h("div", { class: "cqs-meter-track" }, [secBar])]),
    h("div", null, [h("div", { class: "cqs-meter-head" }, [h("span", null, [TRUST]), trustVal]), h("div", { class: "cqs-meter-track" }, [trustBar])]),
    h("div", { class: "cqs-path" }, [h("span", { class: "cqs-label" }, ["YOUR PATH"])].concat(pathRows))
  ]);

  showScene();
  paintMeters();

  return {
    el: h("div", { class: "cqs-split", style: { gap: "24px" } }, [story, impact]),
    footer: "none",
    ready: function () { return false; }
  };
});
