/*
  practice/static/practice/js/center.js
  Practice Center: course selection (left), scenario selection (center) and
  the detail panel (right). Everything shown comes from the server-rendered
  catalog (#pc-catalog); this file only switches what is visible and fills
  the detail panel. Every card and the Start button link to the scenario's
  interactive session (/practice/<slug>/); hovering or focusing a card previews it.
*/
(function () {
  "use strict";
  var dataNode = document.getElementById("pc-catalog");
  if (!dataNode) return;
  var catalog = JSON.parse(dataNode.textContent);
  var byDomain = {};
  catalog.forEach(function (topic) { byDomain[topic.slug] = topic; });

  var tabs = Array.prototype.slice.call(document.querySelectorAll(".pc-topic[data-panel]"));
  var panels = Array.prototype.slice.call(document.querySelectorAll(".pc-panel"));
  var detailBody = document.getElementById("pc-detail-body");
  var detailEmpty = document.getElementById("pc-detail-empty");
  var floor = document.getElementById("pc-floor");
  var startLink = document.getElementById("pc-start");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var SEARCH = '<svg class="pc-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/></svg>';

  function text(id, value) {
    var node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function drawScene(scene) {
    if (!floor) return;
    floor.replaceChildren();
    var nodes = (scene && scene.nodes) || [];
    var suspicious = (scene && scene.suspicious) || [];
    nodes.forEach(function (node, index) {
      if (index > 0) {
        var link = document.createElement("span");
        link.className = "pc-link";
        link.setAttribute("aria-hidden", "true");
        floor.appendChild(link);
      }
      var el = document.createElement("div");
      el.className = "pc-node" + (suspicious.indexOf(node.id) >= 0 ? " is-alert" : "");
      var label = document.createElement("span");
      label.textContent = node.label;
      el.appendChild(label);
      floor.appendChild(el);
    });
  }

  function renderTools(tools) {
    var list = document.getElementById("pc-tools");
    if (!list) return;
    list.replaceChildren();
    (tools || []).forEach(function (name) {
      var li = document.createElement("li");
      li.innerHTML = SEARCH;
      var label = document.createElement("span");
      label.textContent = name;
      li.appendChild(label);
      list.appendChild(li);
    });
  }

  function showDetail(on) {
    if (detailBody) detailBody.hidden = !on;
    if (detailEmpty) detailEmpty.hidden = on;
  }

  function selectScenario(domainSlug, scenarioKey) {
    var topic = byDomain[domainSlug];
    if (!topic || !topic.scenarios.length) { showDetail(false); return; }
    var scenario = topic.scenarios.filter(function (row) { return row.key === scenarioKey; })[0] || topic.scenarios[0];
    showDetail(true);

    document.querySelectorAll(".pc-card").forEach(function (card) {
      var on = card.getAttribute("data-key") === scenario.key;
      card.classList.toggle("is-active", on);
      card.setAttribute("aria-pressed", on ? "true" : "false");
    });

    text("pc-num", scenario.number);
    text("pc-ref", topic.full_label);
    text("pc-time", "~" + scenario.minutes + " min");
    text("pc-title", scenario.title);
    text("pc-type", scenario.activity_label);
    text("pc-stage-type", scenario.activity_label);
    text("pc-summary", scenario.summary);
    text("pc-obj-text", scenario.objective);
    text("pc-workspace", scenario.workspace);
    text("pc-severity", scenario.severity ? "Severity: " + scenario.severity.charAt(0) + scenario.severity.slice(1).toLowerCase() : "");
    text("pc-state", scenario.completed ? "✓ COMPLETED · BEST " + scenario.best + "%" : "Not completed yet");
    text("pc-xp-domain", topic.full_label);

    var diff = document.getElementById("pc-diff-chip");
    if (diff) {
      diff.className = "pc-chip pc-chip--" + (scenario.difficulty || "beginner");
      diff.textContent = scenario.difficulty_label;
    }
    drawScene(scenario.scene);
    renderTools(scenario.tools);

    if (startLink) startLink.href = scenario.url;
  }

  function selectPanel(panelId, focusTab) {
    var panel = null;
    panels.forEach(function (p) {
      var on = p.getAttribute("data-panel") === panelId;
      p.hidden = !on;
      if (on) panel = p;
    });
    tabs.forEach(function (tab) {
      var on = tab.getAttribute("data-panel") === panelId;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.tabIndex = on ? 0 : -1;
      if (on && focusTab) tab.focus();
    });
    if (!panel) return;
    var domain = panel.getAttribute("data-domain");
    var topic = byDomain[domain];
    if (!topic || !topic.scenarios.length) { showDetail(false); return; }
    var preferred = topic.scenarios.filter(function (row) { return row.preferred; })[0] || topic.scenarios[0];
    selectScenario(domain, preferred.key);
    // On narrow screens the panels stack: bring the chosen course into view.
    if (window.matchMedia("(max-width: 1100px)").matches) {
      panel.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    }
  }

  tabs.forEach(function (tab, index) {
    tab.addEventListener("click", function () { selectPanel(tab.getAttribute("data-panel"), false); });
    tab.addEventListener("keydown", function (event) {
      var next = null;
      if (event.key === "ArrowDown" || event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
      else if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (event.key === "Home") next = tabs[0];
      else if (event.key === "End") next = tabs[tabs.length - 1];
      if (!next) return;
      event.preventDefault();
      selectPanel(next.getAttribute("data-panel"), true);
    });
  });

  // Clicking a card opens it (it is a link); pointing at it or tabbing to it previews it.
  document.querySelectorAll(".pc-card").forEach(function (card) {
    function preview() { selectScenario(card.getAttribute("data-domain"), card.getAttribute("data-key")); }
    card.addEventListener("mouseenter", preview);
    card.addEventListener("focus", preview);
  });

  // The server opens on the recommended course; an empty course hides the detail.
  var open = panels.filter(function (p) { return !p.hidden; })[0];
  if (open && !byDomain[open.getAttribute("data-domain")]) showDetail(false);
})();
