(function () {
  var dataNode = document.getElementById("pc-catalog");
  if (!dataNode) return;
  var catalog = JSON.parse(dataNode.textContent);
  var byDomain = {};
  catalog.forEach(function (domain) { byDomain[domain.slug] = domain; });

  var floor = document.getElementById("pc-floor");
  var stage = document.getElementById("pc-stage");
  var form = document.getElementById("pc-start");
  var keyInput = document.getElementById("pc-key");

  function text(id, value) {
    var node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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
    var packet = document.createElement("span");
    packet.className = "pc-packet";
    packet.setAttribute("aria-hidden", "true");
    floor.appendChild(packet);
  }

  function renderScene(scene) {
    if (!floor) return;
    if (reducedMotion || !floor.childElementCount) {
      drawScene(scene);
      return;
    }
    floor.classList.add("is-out");
    window.setTimeout(function () {
      drawScene(scene);
      floor.classList.remove("is-out");
    }, 160);
  }

  function selectScenario(domainSlug, scenarioKey) {
    var domain = byDomain[domainSlug];
    if (!domain) return;
    var scenario = domain.scenarios.filter(function (row) { return row.key === scenarioKey; })[0] || domain.scenarios[0];
    document.querySelectorAll(".pc-topic").forEach(function (tab) {
      var on = tab.getAttribute("data-domain") === domainSlug;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".pc-card-list").forEach(function (list) {
      list.hidden = list.getAttribute("data-domain") !== domainSlug;
    });
    document.querySelectorAll(".pc-card").forEach(function (card) {
      var on = card.getAttribute("data-key") === scenario.key && card.getAttribute("data-domain") === domainSlug;
      card.classList.toggle("is-active", on);
      card.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (stage) stage.setAttribute("data-domain", domainSlug);
    renderScene(scenario.scene);
    text("pc-type", scenario.activity_label);
    text("pc-title", scenario.title);
    text("pc-summary", scenario.summary);
    text("pc-activity", scenario.activity_label);
    text("pc-difficulty", scenario.difficulty_label);
    text("pc-time", "~" + scenario.minutes + " min");
    text("pc-skill", scenario.objective);
    text("pc-state", scenario.completed ? ("COMPLETED · BEST " + scenario.best + "%") : "Not completed yet");
    text("pc-domain-status", domain.full_label + " · " + domain.percent + "% · " + domain.level + " · " + domain.activity_label);
    if (keyInput) keyInput.value = scenario.key;
    if (form) form.action = domain.start_url;
  }

  document.querySelectorAll(".pc-topic").forEach(function (tab) {
    tab.addEventListener("click", function () {
      var domain = byDomain[tab.getAttribute("data-domain")];
      var preferred = domain.scenarios.filter(function (row) { return row.preferred; })[0] || domain.scenarios[0];
      selectScenario(domain.slug, preferred.key);
    });
  });
  document.querySelectorAll(".pc-card").forEach(function (card) {
    card.addEventListener("click", function () {
      selectScenario(card.getAttribute("data-domain"), card.getAttribute("data-key"));
    });
  });
})();
