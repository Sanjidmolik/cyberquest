/* CyberQuest interactive practice: the step engine.
   Loads the (answer-free) content, runs one step renderer at a time, posts answers to the
   server for grading and shows the feedback sheet. No page reloads between steps.
   Practice is self-paced: there is no countdown anywhere in this file. */
(function () {
  "use strict";

  var cfg, root, attemptId = null, content = null, hearts = 3, stepIndex = 0, stepStarted = 0, progress = 0;
  var registry = {};
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- tiny DOM helpers ----------
  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k === "html") el.innerHTML = v;
        else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
        else if (k === "style" && typeof v === "object") {
          Object.keys(v).forEach(function (prop) {
            if (prop.slice(0, 2) === "--") el.style.setProperty(prop, v[prop]);  // custom properties need setProperty
            else el.style[prop] = v[prop];
          });
        }
        else el.setAttribute(k, v === true ? "" : v);
      });
    }
    (children || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return el;
  }

  var ICONS = {
    x: '<path d="M6 6l12 12"></path><path d="M18 6L6 18"></path>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"></path>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path>',
    key: '<circle cx="8" cy="15" r="4"></circle><path d="m10.8 12.2 8.7-8.7"></path><path d="m16 7 2.5 2.5"></path><path d="m18.5 4.5 2 2"></path>',
    users: '<circle cx="9" cy="8" r="3.5"></circle><path d="M2.5 20a6.5 6.5 0 0 1 13 0"></path><circle cx="17" cy="9" r="2.8"></circle><path d="M16.5 14.2A5.5 5.5 0 0 1 22 20"></path>',
    user: '<circle cx="12" cy="8" r="4"></circle><path d="M4 21a8 8 0 0 1 16 0"></path>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"></path><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"></path>',
    building: '<rect x="4" y="3" width="16" height="18" rx="2"></rect><path d="M9 7h1M14 7h1M9 11h1M14 11h1M9 15h1M14 15h1"></path><path d="M10 21v-3h4v3"></path>',
    clock: '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>',
    target: '<circle cx="12" cy="12" r="9"></circle><circle cx="12" cy="12" r="5"></circle><circle cx="12" cy="12" r="1"></circle>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"></path><path d="M8.5 12.5l2.5 2.5 4.5-5"></path>',
    warn: '<path d="M12 3 2 21h20z"></path><path d="M12 10v4"></path><path d="M12 17.5v.5"></path>'
  };
  function icon(name, size, stroke) {
    var span = document.createElement("span");
    span.style.display = "inline-flex";
    span.innerHTML = '<svg aria-hidden="true" width="' + (size || 24) + '" height="' + (size || 24) +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + (stroke || 2.4) +
      '" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || ICONS.shield) + "</svg>";
    return span.firstChild;
  }
  function heartIcon() {
    var s = document.createElement("span");
    s.innerHTML = '<svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="#F25F7A" stroke="#C81E45" stroke-width="1.5"><path d="M12 21s-7.5-4.6-9.6-9.2C.9 8.4 3 4.5 6.8 4.5c2.1 0 3.6 1.1 5.2 3 1.6-1.9 3.1-3 5.2-3 3.8 0 5.9 3.9 4.4 7.3C19.5 16.4 12 21 12 21z"></path></svg>';
    return s.firstChild;
  }
  function boltIcon(size) {
    var s = document.createElement("span");
    s.innerHTML = '<svg aria-hidden="true" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="#FFB020" stroke="#8A5A00" stroke-width="1.5" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"></path></svg>';
    return s.firstChild;
  }

  /** Hana + speech bubble. size in px. */
  function coach(size, text, face) {
    var box = h("div", { class: "cqs-avatar", style: { "--size": size + "px" } });
    var bubble = h("div", { class: "cqs-bubble rise", "aria-live": "polite" }, [text || ""]);
    var el = h("div", { class: "cqs-coach" }, [box, bubble]);
    var hana = window.CQHana.mount(box);
    window.CQHana.setExpression(hana, face || "neutral");
    var last = face || "neutral";
    return {
      el: el, box: box, bubble: bubble,
      say: function (t) { if (bubble.textContent !== t) bubble.textContent = t; },
      face: function (f) { if (f !== last) { last = f; window.CQHana.setExpression(hana, f); } }
    };
  }

  function avatar(size, face) {
    var box = h("div", { class: "cqs-avatar", style: { "--size": size + "px" } });
    window.CQHana.setExpression(window.CQHana.mount(box), face || "neutral");
    return box;
  }

  function tile(cls, attrs, children) {
    attrs = attrs || {};
    attrs.type = "button";
    attrs.class = "opt cqs-tile " + (cls || "");
    return h("button", attrs, children);
  }

  /** Swap a tile's state class: sel | right | wrong | missed | dim | "". */
  function setState(el, state, extra) {
    ["is-sel", "is-right", "is-wrong", "is-missed", "is-dim", "shake", "pop-in"].forEach(function (c) { el.classList.remove(c); });
    if (state) el.classList.add("is-" + state);
    if (extra) { void el.offsetWidth; el.classList.add(extra); }
  }

  // ---------- server ----------
  function post(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrf, "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body || {})
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) { var err = new Error(data.error || "Something went wrong."); err.status = res.status; throw err; }
        return data;
      });
    });
  }
  function attemptUrl(kind) { return cfg.urls[kind].replace("/0/", "/" + attemptId + "/"); }

  function sendAnswer(answer) {
    return post(attemptUrl("answer"), { step: stepIndex, answer: answer, time_ms: Date.now() - stepStarted }).then(function (res) {
      if (typeof res.hearts === "number") setHearts(res.hearts);
      return res;
    });
  }

  // ---------- shell ----------
  var shell = {};

  function topBar() {
    var quit = h("a", { href: cfg.urls.center, class: "cqs-quit", "aria-label": "Quit mission" }, [icon("x", 24, 3)]);
    var fill = h("div", { class: "cqs-progress-fill fill shine", style: { width: progress + "%" } });
    var bar = h("div", {
      class: "cqs-progress" + (cfg.kind === "choice" ? " cqs-progress--choice" : ""), role: "progressbar",
      "aria-label": cfg.kind === "choice" ? "Story progress" : "Mission progress",
      "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(progress)
    }, [fill]);
    var kids = [quit, bar];
    if (cfg.kind === "incident") {
      // The design's countdown clock is replaced: Practice never runs against the clock.
      kids.push(h("span", { class: "cqs-pace" }, [icon("clock", 18, 2.6), "Self-paced"]));
    }
    if (cfg.kind === "choice") {
      shell.scene = h("span", { class: "cqs-scene-label" }, ["Scene 1 of 3"]);
      kids.push(shell.scene);
    } else {
      shell.hearts = h("span", { "data-hearts": "" }, [String(hearts)]);
      kids.push(h("div", { class: "cqs-hearts", "aria-label": hearts + " lives left" }, [heartIcon(), shell.hearts]));
    }
    shell.bar = bar; shell.fill = fill;
    return h("div", { class: "cqs-top" }, kids);
  }

  function setProgress(pct) {
    progress = Math.max(0, Math.min(100, Math.round(pct)));
    if (!shell.fill) return;
    shell.fill.style.width = progress + "%";
    shell.bar.setAttribute("aria-valuenow", String(progress));
  }
  function setHearts(n) {
    hearts = n;
    if (shell.hearts) {
      shell.hearts.textContent = String(n);
      shell.hearts.parentNode.setAttribute("aria-label", n + " lives left");
    }
  }

  function screen(parts) {
    root.innerHTML = "";
    parts.forEach(function (p) { if (p) root.appendChild(p); });
    window.scrollTo(0, 0);
  }

  function gradedSteps() { return content.steps.filter(function (s) { return s.type !== "story"; }).length; }

  // ---------- footers ----------
  function footerWrap(children, cls) {
    return h("footer", { class: "cqs-footer " + (cls || "") }, [h("div", { class: "cqs-footer-in" }, children)]);
  }

  function errorNote(err) {
    return h("span", { class: "cqs-footer-note", role: "alert", style: { color: "#9A3412" } },
      [err && err.message ? err.message : "Couldn’t reach the server. Check your connection and try again."]);
  }

  function sheet(res, onContinue) {
    var ok = !!res.correct;
    var btn = h("button", { type: "button", class: "btn3d " + (ok ? "btn3d--good" : "btn3d--bad"), onclick: onContinue }, ["Continue"]);
    var foot = h("footer", { class: "cqs-footer cqs-sheet sheet " + (ok ? "cqs-sheet--good" : "cqs-sheet--bad"), role: "status" }, [
      h("div", { class: "cqs-footer-in" }, [
        h("div", { class: "cqs-sheet-msg" }, [
          h("div", { class: "cqs-sheet-icon pop-in" }, [icon(ok ? "check" : "x", ok ? 36 : 34, 3.5)]),
          h("div", null, [
            h("span", { class: "cqs-sheet-title" }, [res.title || (ok ? "Correct!" : "Not quite")]),
            res.text ? h("span", { class: "cqs-sheet-text" }, [res.text]) : null
          ])
        ]),
        btn
      ])
    ]);
    setTimeout(function () { btn.focus({ preventScroll: true }); }, 60);
    return foot;
  }

  // ---------- step flow ----------
  function runStep(i) {
    stepIndex = i;
    stepStarted = Date.now();
    if (i >= content.steps.length) return complete();
    var step = content.steps[i];
    var make = registry[step.type];
    if (!make) { root.appendChild(h("p", { class: "cqs-error" }, ["Unknown step type: " + step.type])); return; }

    var total = gradedSteps();
    var done = content.steps.slice(0, i).filter(function (s) { return s.type !== "story"; }).length;
    var footer = null;
    var ctrl;
    var ui = {
      h: h, icon: icon, coach: coach, avatar: avatar, tile: tile, setState: setState,
      answer: sendAnswer,
      changed: function () { if (footer && footer.refresh) footer.refresh(); },
      progress: setProgress,
      scene: function (t) { if (shell.scene) shell.scene.textContent = t; },
      next: function () { runStep(i + 1); },
      restart: restart
    };
    ctrl = make(step, ui);

    var main = h("main", { class: "cqs-main" }, [
      h("div", { class: "cqs-wrap" + (ctrl.width ? " cqs-wrap--" + ctrl.width : "") }, [ctrl.el])
    ]);
    footer = buildFooter(ctrl, i);
    screen([topBar(), main, footer ? footer.el : null]);
    // Animate the bar from where it was to the share of steps already done.
    setTimeout(function () { setProgress(total ? done / total * 100 : 0); }, 250);
    if (ctrl.mounted) ctrl.mounted();
  }

  function buildFooter(ctrl, i) {
    var total = gradedSteps();
    var doneAfter = content.steps.slice(0, i + 1).filter(function (s) { return s.type !== "story"; }).length;
    if (ctrl.footer === "none") return null;

    var holder = {};
    var note = h("span", { class: "cqs-footer-note" });
    var main = h("button", { type: "button", class: "btn3d", disabled: true }, [ctrl.checkLabel || (ctrl.footer === "continue" ? "Continue" : "Check")]);
    var left = ctrl.footer === "continue" ? note
      : h("button", { type: "button", class: "btn3d btn3d--ghost" }, ["Skip"]);
    var el = footerWrap([left, main]);
    holder.el = el;
    holder.refresh = function () {
      var ready = !!ctrl.ready();
      main.disabled = !ready;
      if (ctrl.footer === "continue" && ctrl.note) note.textContent = ctrl.note();
    };
    holder.refresh();

    function fail(err) {
      main.disabled = false; main.textContent = ctrl.checkLabel || "Check";
      var old = el.querySelector("[role=alert]"); if (old) old.remove();
      el.firstChild.insertBefore(errorNote(err), main);
    }

    if (ctrl.footer === "continue") {
      main.addEventListener("click", function () {
        if (!ctrl.ready()) return;
        main.disabled = true;
        var p = ctrl.answer ? sendAnswer(ctrl.answer()) : Promise.resolve();
        p.then(function () { setProgress(doneAfter / total * 100); runStep(i + 1); }).catch(fail);
      });
      return holder;
    }

    left.addEventListener("click", function () {
      left.disabled = true;
      sendAnswer({ skipped: true }).then(function () { runStep(i + 1); }).catch(function (err) { left.disabled = false; fail(err); });
    });
    main.addEventListener("click", function () {
      if (!ctrl.ready()) return;
      main.disabled = true; left.disabled = true;
      sendAnswer(ctrl.answer()).then(function (res) {
        ctrl.onResult(res);
        setProgress(doneAfter / total * 100);
        var sh = sheet(res, function () { runStep(i + 1); });
        el.replaceWith(sh);
      }).catch(function (err) { left.disabled = false; fail(err); });
    });
    return holder;
  }

  function start() {
    var btn = root.querySelector("[data-cq-start]");
    btn.disabled = true;
    btn.textContent = "Loading…";
    post(cfg.urls.start, { scenario: cfg.slug }).then(function (data) {
      attemptId = data.attempt_id;
      content = data.content;
      setHearts(data.hearts);
      progress = 0;
      runStep(1);
    }).catch(function (err) {
      btn.disabled = false;
      btn.textContent = "Start mission";
      var old = root.querySelector("footer [role=alert]"); if (old) old.remove();
      btn.parentNode.insertBefore(errorNote(err), btn);
    });
  }

  /** Branch "Try another path": a fresh attempt, straight back to the first scene. */
  function restart() {
    return post(cfg.urls.start, { scenario: cfg.slug }).then(function (data) {
      attemptId = data.attempt_id;
      content = data.content;
      setHearts(data.hearts);
      progress = 0;
      runStep(1);
    });
  }

  function complete() {
    screen([topBar(), h("main", { class: "cqs-main" }, [h("p", { class: "cqs-footer-note", style: { textAlign: "center" } }, ["Saving your results…"])])]);
    setProgress(100);
    post(attemptUrl("complete")).then(function (res) {
      cfg.xp = res.level ? res.level.xp : cfg.xp;
      debrief(res);
    }).catch(function (err) {
      screen([topBar(), h("main", { class: "cqs-main" }, [
        h("div", { class: "cqs-error", role: "alert" }, [err.message || "Couldn’t save your results."]),
        h("div", { style: { textAlign: "center" } }, [h("button", { type: "button", class: "btn3d", onclick: complete }, ["Try again"])])
      ])]);
    });
  }

  // ---------- results (Debrief) ----------
  var KIND_TAG = { simulation: "SIMULATION", incident: "INCIDENT", choice: "CHOICE" };

  function countUp(el, to, suffix, prefix) {
    if (reduceMotion) { el.textContent = (prefix || "") + to + (suffix || ""); return; }
    var k = 0;
    var t = setInterval(function () {
      k += 1;
      el.textContent = (prefix || "") + Math.round(to * k / 30) + (suffix || "");
      if (k >= 30) clearInterval(t);
    }, 30);
  }

  function statBox(mod, label, iconEl, valueEl) {
    return h("div", { class: "cqs-stat rise cqs-stat--" + mod }, [
      h("div", { class: "cqs-stat-label" }, [label]),
      h("div", { class: "cqs-stat-val" }, [iconEl, valueEl])
    ]);
  }

  function debrief(res) {
    var d = res.debrief || {};
    var isChoice = res.kind === "choice";
    var ending = res.ending || {};
    var colors = ["#7C4DFF", "#FFB020", "#0B8A5F", "#F25F7A", "#5EC8F2"];
    var confetti = h("div", { class: "cqs-confetti", "aria-hidden": "true" });
    for (var i = 0; i < 22; i++) {
      confetti.appendChild(h("span", { class: "confetti", style: {
        left: ((i * 47) % 100) + "%", background: colors[i % colors.length], animationDuration: (3.2 + (i % 5) * 0.55) + "s",
        animationDelay: ((i * 0.31) % 3) + "s", borderRadius: i % 3 === 0 ? "50%" : "3px"
      } }));
    }
    var xpVal = h("span", null, ["+0"]);
    var s2Val = h("span", null, ["0"]);
    var stats = h("div", { class: "cqs-stats" }, [
      statBox("xp", "TOTAL XP", boltIcon(30), xpVal),
      statBox("good", isChoice ? "GOOD CALLS" : "ACCURACY", icon("target", 30, 2.6), s2Val),
      statBox("brand", res.kind === "incident" ? "RESPONSE TIME" : "TIME TAKEN", icon("clock", 30, 2.6), h("span", null, [res.time || "–"]))
    ]);
    stats.children[1].style.animationDelay = ".3s";
    stats.children[2].style.animationDelay = ".4s";
    var learned = h("div", { class: "cqs-learned" }, (d.learned || []).map(function (t) { return h("span", null, [icon("check", 18, 3.2), t]); }));

    var main = h("main", { class: "cqs-debrief-main" }, [h("div", { class: "cqs-debrief" }, [
      avatar(190, isChoice ? (ending.face || "happy") : "happy"),
      h("div", { class: "rise" }, [
        h("span", { class: "cqs-tag cqs-tag--" + res.kind, style: { alignSelf: "center", display: "inline-block" } }, [(KIND_TAG[res.kind] || "PRACTICE") + " SESSION"]),
        h("h1", null, [isChoice && ending.title ? ending.title : (d.headline || "Mission complete!")]),
        h("p", { class: "cqs-debrief-sub" }, [isChoice && ending.text ? ending.text : (d.sub || "")])
      ]),
      stats,
      h("div", { class: "rise", style: { animationDelay: ".5s" } }, [h("span", { class: "cqs-label" }, ["WHAT YOU LEARNED"]), learned])
    ])]);
    var foot = footerWrap([
      h("a", { href: cfg.urls.replay, class: "btn3d btn3d--ghost" }, ["Replay mission"]),
      h("button", { type: "button", class: "btn3d", onclick: function () { rewards(res); } }, ["Continue"])
    ]);
    screen([confetti, main, foot]);
    countUp(xpVal, res.xp || 0, "", "+");
    if (isChoice) countUp(s2Val, res.good_calls || 0, " / " + (res.total_calls || 3));
    else countUp(s2Val, res.accuracy || 0, "%");
  }

  // ---------- rewards ----------
  function rewards(res) {
    var badge = (res.badges || [])[0];
    var lvl = res.level || { level: 1, xp: 0, into: 0, to_next: 100 };
    var comp = res.competency || { course: "", done: 0, total: 0, percent: 0 };
    var medal = h("div", { class: "cqs-medal badge-in" }, badge ? [h("span", { "aria-hidden": "true" }, [badge.icon])] : [icon("shield", 76, 2.4)]);
    var hanaLine = "+" + (res.xp || 0) + " XP earned." + (lvl.leveled_up ? " You reached level " + lvl.level + "!" : " Keep it up!");
    var c = coach(96, hanaLine, "happy");
    var copy = h("div", { class: "cqs-reward-copy" }, [
      h("span", { class: "cqs-reward-kicker rise" }, [badge ? "NEW BADGE UNLOCKED" : "MISSION COMPLETE"]),
      h("h1", { class: "rise" }, [badge ? badge.name : cfg.title]),
      h("p", { class: "rise" }, [badge ? badge.description : "No new badge this time. Badges unlock as you finish more practice."]),
      c.el
    ]);
    c.el.classList.add("rise");
    var lvlFill = h("div", { class: "fill shine", style: { background: "#FFB020" } });
    var compFill = h("div", { class: "fill shine", style: { background: "#0B8A5F" } });
    var pad = function (n) { return n < 10 ? "0" + n : String(n); };
    var cards = [
      h("section", { class: "cqs-card cqs-reward-card rise", style: { animationDelay: ".35s" } }, [
        h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center" } }, [
          h("span", { class: "cqs-label" }, ["LEVEL " + pad(lvl.level)]),
          h("span", { class: "cqs-xp-float float-up" }, [boltIcon(18), "+" + (res.xp || 0) + " XP"])
        ]),
        h("div", { class: "cqs-bar" }, [lvlFill]),
        h("span", { class: "cqs-reward-note" }, [lvl.xp + " XP · " + lvl.to_next + " to Level " + pad(lvl.level + 1)])
      ]),
      h("section", { class: "cqs-card cqs-reward-card rise", style: { animationDelay: ".45s" } }, [
        h("span", { class: "cqs-label" }, [String(comp.course || "").toUpperCase() + " SKILL"]),
        h("div", { class: "cqs-bar" }, [compFill]),
        h("span", { class: "cqs-reward-note" }, [comp.done + " of " + comp.total + " interactive scenario" + (comp.total === 1 ? "" : "s") + " done"])
      ])
    ];
    if (res.next) {
      cards.push(h("a", { href: res.next.url, class: "cqs-next-card rise opt", style: { animationDelay: ".55s" } }, [
        h("div", { class: "cqs-next-ic" }, [icon("shield", 30, 2.4)]),
        h("div", null, [
          h("span", { class: "cqs-next-kicker" }, ["UP NEXT · " + String(res.next.kind).toUpperCase()]),
          h("span", { class: "cqs-next-title" }, [res.next.title]),
          h("span", { class: "cqs-next-meta" }, [res.next.difficulty + " · ~" + res.next.minutes + " min"])
        ])
      ]));
    }
    var main = h("main", { class: "cqs-rewards-main" }, [h("div", { class: "cqs-rewards" }, [
      h("div", { class: "cqs-reward-hero" }, [
        h("div", { class: "cqs-medal-wrap" }, [h("div", { class: "burst spin", "aria-hidden": "true" }), medal]),
        copy
      ]),
      h("div", { class: "cqs-reward-cards" }, cards)
    ])]);
    var foot = footerWrap([
      h("a", { href: cfg.urls.center, class: "btn3d btn3d--ghost" }, ["Practice Center"]),
      h("a", { href: res.next ? res.next.url : cfg.urls.center, class: "btn3d" }, [res.next ? "Next mission" : "Done"])
    ]);
    screen([main, foot]);
    setTimeout(function () {
      lvlFill.style.width = lvl.into + "%";
      compFill.style.width = comp.percent + "%";
    }, 300);
  }

  // ---------- briefing (story step, server-rendered) ----------
  function typewriter() {
    var el = root.querySelector("[data-typewriter]");
    var box = root.querySelector("[data-hana]");
    var hana = window.CQHana.mount(box);
    var end = box.getAttribute("data-expression") || "smile";
    if (!el) return;
    var text = el.textContent;
    if (reduceMotion) { window.CQHana.setExpression(hana, end); return; }
    var n = 0, face = "";
    el.textContent = "";
    el.classList.add("caret");
    var t = setInterval(function () {
      n += 1;
      el.textContent = text.slice(0, n);
      var f = n % 6 < 3 ? "talk" : "smile";
      if (f !== face) { face = f; window.CQHana.setExpression(hana, f); }
      if (n >= text.length) {
        clearInterval(t);
        el.classList.remove("caret");
        window.CQHana.setExpression(hana, end);
      }
    }, 28);
  }

  function boot() {
    root = document.getElementById("cq-session");
    cfg = JSON.parse(document.getElementById("cq-session-config").textContent);
    hearts = cfg.hearts;
    typewriter();
    var agree = root.querySelector("[data-cq-agree]");
    var startBtn = root.querySelector("[data-cq-start]");
    if (cfg.locked || !agree || !startBtn) return;
    agree.addEventListener("change", function () { startBtn.disabled = !agree.checked; });
    startBtn.addEventListener("click", function () { if (agree.checked) start(); });
  }

  window.CQSteps = { register: function (type, make) { registry[type] = make; } };
  window.CQEngine = { boot: boot };
})();
