/* Practice Studio wizard: Basics autosave and the Steps editor.

   - Forms are built from the server's schema; values go in with .value / textContent only.
   - Autosave every 30 s while there are unsaved changes (draft only; the server doesn't audit
     autosaves). "Save" saves now and is audited.
   - Every save names the draft revision it started from. If someone else saved in between,
     the server refuses (409): we say who, keep everything typed on the page, and stop
     autosaving until the page is reloaded.
   - If the sign-in expired or the security token failed, we say so and keep the typed data.
   - Steps: Up / Down buttons and drag-and-drop; the briefing (and a choice session's branch)
     stay locked in place. */
(function () {
  "use strict";

  var AUTOSAVE_MS = 30000;
  var statusEl = document.getElementById("st-save-status");
  var alertEl = document.getElementById("st-alert");
  var state = { revision: null, edits: 0, savedEdits: 0, saving: false, blocked: false, url: "" };
  var collect = null;                     // returns the payload for the page being edited

  function el(tag, cls, txt) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (txt !== undefined && txt !== null) node.textContent = txt;
    return node;
  }

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function dirty() { return state.edits !== state.savedEdits; }
  function changed() { state.edits += 1; if (!state.blocked) setStatus("Unsaved changes"); }
  function setStatus(text) { if (statusEl) statusEl.textContent = text; }

  function showAlert(message, withReload) {
    if (!alertEl) return;
    alertEl.textContent = message;
    if (withReload) {
      var reload = el("button", "ops-btn-quiet", "Reload");
      reload.type = "button";
      reload.addEventListener("click", function () {
        if (!dirty() || window.confirm("Reload and lose the changes on this page?")) {
          state.savedEdits = state.edits;
          window.location.reload();
        }
      });
      alertEl.appendChild(document.createTextNode(" "));
      alertEl.appendChild(reload);
    }
    alertEl.hidden = !message;
  }

  /** Resolves true when the draft was saved, false otherwise (the reason is shown). */
  function save(autosave) {
    if (state.saving || state.blocked || !collect) return Promise.resolve(false);
    state.saving = true;
    var sentAt = state.edits;
    var payload = collect();
    payload.revision = state.revision;
    payload.autosave = !!autosave;
    setStatus(autosave ? "Autosaving…" : "Saving…");
    return fetch(state.url, {
      method: "POST", credentials: "same-origin", redirect: "follow",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(payload)
    }).then(function (res) {
      var json = (res.headers.get("Content-Type") || "").indexOf("application/json") !== -1;
      if (res.redirected || !json) {
        // Signed out (redirected to the sign-in page) or the security token was refused.
        throw { auth: true };
      }
      return res.json().then(function (data) { return { status: res.status, data: data }; });
    }).then(function (result) {
      if (result.status === 200) {
        state.revision = result.data.revision;
        state.savedEdits = sentAt;
        var revisionInput = document.querySelector("#st-basics input[name=revision]");
        if (revisionInput) revisionInput.value = state.revision;
        showAlert("");
        setStatus((dirty() ? "Unsaved changes · " : "") + (autosave ? "Autosaved at " : "Saved at ") + result.data.saved_at);
        return true;
      }
      setStatus("Not saved");
      if (result.status === 409) {
        state.blocked = true;
        showAlert(result.data.error, true);
      } else {
        showAlert(result.data.error || "Couldn't save. Try again.");
      }
      return false;
    }).catch(function (err) {
      setStatus("Not saved");
      showAlert(err && err.auth
        ? "You've been signed out, or this page's security token expired. Everything you typed is still here: sign in again in a new tab, then press Save on this page."
        : "Couldn't reach the server. Your changes are still here; try Save again in a moment.");
      return false;
    }).then(function (ok) { state.saving = false; return ok; });
  }

  // "Preview" always shows the latest SAVED draft: save first, and only go on if it worked.
  document.querySelectorAll("a[data-save-first]").forEach(function (link) {
    link.addEventListener("click", function (e) {
      if (!collect || !dirty()) return;
      e.preventDefault();
      save(false).then(function (ok) { if (ok) window.location.href = link.href; });
    });
  });

  window.addEventListener("beforeunload", function (e) {
    if (dirty()) { e.preventDefault(); e.returnValue = ""; }
  });
  setInterval(function () { if (dirty()) save(true); }, AUTOSAVE_MS);

  // ---------- counters and "Insert example" for plain form fields ----------

  function wireCounter(input, max, counter) {
    function update() {
      var n = input.value.length;
      counter.textContent = n + " / " + max + (n > max ? " · longer than recommended" : "");
      counter.classList.toggle("is-over", n > max);
    }
    input.addEventListener("input", update);
    update();
  }

  function insertExample(input, example) {
    if (input.value.trim() && !window.confirm("Replace the current text with the example?")) return;
    input.value = example;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
  }

  // ---------- Basics page ----------

  var basics = document.getElementById("st-basics");
  if (basics) {
    state.url = basics.getAttribute("data-save-url");
    state.revision = parseInt(basics.querySelector("input[name=revision]").value, 10);
    basics.querySelectorAll("[data-max]").forEach(function (input) {
      var counter = input.parentNode.querySelector(".st-counter");
      if (counter) wireCounter(input, parseInt(input.getAttribute("data-max"), 10), counter);
    });
    basics.querySelectorAll(".st-example").forEach(function (button) {
      button.addEventListener("click", function () {
        var input = document.getElementById(button.getAttribute("data-for"));
        insertExample(input, input.getAttribute("data-example"));
      });
    });
    basics.addEventListener("input", changed);
    basics.addEventListener("change", changed);
    basics.addEventListener("submit", function () { state.savedEdits = state.edits; });   // normal form post
    collect = function () {
      var data = {};
      ["title", "topic", "difficulty", "est_minutes", "badge", "description"].forEach(function (name) {
        data[name] = basics.elements[name].value;
      });
      return { basics: data };
    };
    return;
  }

  // ---------- Steps editor ----------

  var root = document.getElementById("st-editor");
  var configNode = document.getElementById("st-editor-config");
  if (!root || !configNode) return;
  var cfg = JSON.parse(configNode.textContent);
  var data = cfg.data;
  state.url = root.getAttribute("data-save-url");
  state.revision = cfg.revision;
  var uid = 0;
  function nextId() { uid += 1; return "st-f" + uid; }

  collect = function () {
    var session = clone(data);
    delete session.meta;                  // badge and description are edited on Basics
    return { session: session };
  };
  document.getElementById("st-save").addEventListener("click", function () { save(false); });

  function fieldWrap(def, control, id) {
    var wrap = el("div", "st-field");
    var label = el("label", null, def.label);
    label.htmlFor = id;
    wrap.appendChild(label);
    wrap.appendChild(control);
    var foot = el("small");
    if (def.help) foot.appendChild(el("span", null, def.help + " "));
    wrap.appendChild(foot);
    return { wrap: wrap, foot: foot };
  }

  function textField(def, obj) {
    var id = nextId();
    var input = el(def.kind === "textarea" ? "textarea" : "input");
    input.id = id;
    if (def.kind === "textarea") input.rows = def.rows || 3;
    input.maxLength = 4000;
    input.value = obj[def.key] == null ? "" : String(obj[def.key]);
    var parts = fieldWrap(def, input, id);
    var counter = el("span", "st-counter");
    parts.foot.appendChild(counter);
    var need = el("span", "st-need", def.required ? " Needed before publishing." : "");
    function check() { need.hidden = !def.required || input.value.trim() !== ""; }
    input.addEventListener("input", function () { obj[def.key] = input.value; changed(); check(); });
    if (def.max) wireCounter(input, def.max, counter);
    parts.foot.appendChild(need);
    check();
    if (def.example) {
      var ex = el("button", "st-example", "Insert example");
      ex.type = "button";
      ex.addEventListener("click", function () { insertExample(input, def.example); });
      parts.foot.appendChild(document.createTextNode(" "));
      parts.foot.appendChild(ex);
    }
    return parts.wrap;
  }

  function selectField(def, obj, options) {
    var id = nextId();
    var select = el("select");
    select.id = id;
    options.forEach(function (pair) {
      var option = el("option", null, pair[1]);
      option.value = pair[0];
      select.appendChild(option);
    });
    var current = obj[def.key] == null ? "" : String(obj[def.key]);
    select.value = current;
    if (select.value !== current && options.length) select.value = String(options[0][0]);
    select.addEventListener("change", function () {
      obj[def.key] = def.kind === "level" ? (select.value === "" ? null : parseInt(select.value, 10)) : select.value;
      changed();
    });
    return fieldWrap(def, select, id).wrap;
  }

  function boolField(def, obj) {
    var id = nextId();
    var wrap = el("div", "st-field st-check");
    var box = el("input");
    box.type = "checkbox";
    box.id = id;
    box.checked = !!obj[def.key];
    box.addEventListener("change", function () { obj[def.key] = box.checked; changed(); });
    var label = el("label", null, " " + def.label);
    label.htmlFor = id;
    wrap.appendChild(box);
    wrap.appendChild(label);
    return wrap;
  }

  function choiceField(def, obj) {
    var box = el("fieldset", "st-choice");
    box.appendChild(el("legend", null, def.label));
    if (!Array.isArray(obj[def.key])) obj[def.key] = [];
    while (obj[def.key].length < def.count) obj[def.key].push("");
    var name = nextId();
    obj[def.key].slice(0, def.count).forEach(function (value, i) {
      var row = el("div", "st-choice-row");
      var radio = el("input");
      radio.type = "radio";
      radio.name = name;
      radio.checked = obj[def.secure_key] === i;
      radio.setAttribute("aria-label", "Option " + (i + 1) + " is the secure one");
      radio.addEventListener("change", function () { obj[def.secure_key] = i; changed(); });
      var input = el("input");
      input.value = value || "";
      input.maxLength = 4000;
      input.setAttribute("aria-label", "Option " + (i + 1) + (i === 0 ? " (weakest)" : i === def.count - 1 ? " (strongest)" : ""));
      input.addEventListener("input", function () { obj[def.key][i] = input.value; changed(); });
      row.appendChild(radio);
      row.appendChild(input);
      box.appendChild(row);
    });
    if (def.help) box.appendChild(el("small", null, def.help));
    return box;
  }

  function stringsField(def, obj) {
    var box = el("fieldset", "st-rows");
    box.appendChild(el("legend", null, def.label));
    if (!Array.isArray(obj[def.key])) obj[def.key] = [];
    var list = el("div");
    box.appendChild(list);
    function draw() {
      list.textContent = "";
      obj[def.key].forEach(function (value, i) {
        var row = el("div", "st-choice-row");
        var input = el("input");
        input.value = value;
        input.maxLength = 4000;
        input.setAttribute("aria-label", def.label + " " + (i + 1));
        input.addEventListener("input", function () { obj[def.key][i] = input.value; changed(); });
        var remove = el("button", "ops-btn-quiet", "Remove");
        remove.type = "button";
        remove.addEventListener("click", function () { obj[def.key].splice(i, 1); changed(); draw(); });
        row.appendChild(input);
        row.appendChild(remove);
        list.appendChild(row);
      });
      add.disabled = obj[def.key].length >= (def.max_items || 10);
    }
    var add = el("button", "ops-btn-quiet", "Add line");
    add.type = "button";
    add.addEventListener("click", function () { obj[def.key].push(""); changed(); draw(); });
    box.appendChild(add);
    draw();
    return box;
  }

  function moveItem(list, from, to) {
    var item = list.splice(from, 1)[0];
    list.splice(to, 0, item);
  }

  function rowsField(def, obj) {
    var box = el("fieldset", "st-rows");
    box.appendChild(el("legend", null, def.label));
    if (def.help) box.appendChild(el("small", "st-rows-help", def.help));
    if (!Array.isArray(obj[def.key])) obj[def.key] = [];
    var list = el("div", "st-rows-list");
    box.appendChild(list);
    var add = el("button", "ops-btn-quiet", def.add || "Add");
    add.type = "button";
    add.addEventListener("click", function () {
      var row = clone(def.new || {});
      row.uid = null;
      obj[def.key].push(row);
      changed();
      draw();
    });
    box.appendChild(add);
    function draw() {
      list.textContent = "";
      var rows = obj[def.key];
      rows.forEach(function (row, i) {
        var item = el("div", "st-row");
        var head = el("div", "st-row-head");
        head.appendChild(el("strong", null, (i + 1) + "."));
        var controls = el("div", "st-row-controls");
        function button(text, label, disabled, action) {
          var b = el("button", "ops-btn-quiet", text);
          b.type = "button";
          b.setAttribute("aria-label", label);
          b.disabled = disabled;
          b.addEventListener("click", function () { action(); changed(); draw(); });
          controls.appendChild(b);
        }
        if (def.reorder !== false) {
          button("↑", "Move up", i === 0, function () { moveItem(rows, i, i - 1); });
          button("↓", "Move down", i === rows.length - 1, function () { moveItem(rows, i, i + 1); });
        }
        button("Remove", "Remove " + (i + 1), rows.length <= (def.min || 0), function () { rows.splice(i, 1); });
        head.appendChild(controls);
        item.appendChild(head);
        item.appendChild(fields(def.row, row));
        list.appendChild(item);
      });
      add.disabled = rows.length >= (def.max || 60);
      var count = rows.length;
      box.classList.toggle("is-short", def.min && count < def.min);
    }
    draw();
    return box;
  }

  function groupField(def, obj) {
    if (!obj[def.key] || typeof obj[def.key] !== "object") obj[def.key] = {};
    var box = el("details", "st-group");
    box.open = !!def.open;
    box.appendChild(el("summary", null, def.label));
    box.appendChild(fields(def.fields, obj[def.key]));
    return box;
  }

  function levelOptions(obj, def) {
    var labels = Array.isArray(obj[def.options_from]) ? obj[def.options_from] : [];
    if (!labels.length) labels = ["Low", "Medium", "High", "Critical"];
    return [["", "Choose…"]].concat(labels.map(function (label, i) { return [String(i), label]; }));
  }

  function fields(schema, obj) {
    var frag = document.createDocumentFragment();
    schema.forEach(function (def) {
      if (def.kind === "text" || def.kind === "textarea") frag.appendChild(textField(def, obj));
      else if (def.kind === "select") frag.appendChild(selectField(def, obj, def.options));
      else if (def.kind === "level") frag.appendChild(selectField(def, obj, levelOptions(obj, def)));
      else if (def.kind === "bool") frag.appendChild(boolField(def, obj));
      else if (def.kind === "group") frag.appendChild(groupField(def, obj));
      else if (def.kind === "rows") frag.appendChild(rowsField(def, obj));
      else if (def.kind === "choice") frag.appendChild(choiceField(def, obj));
      else if (def.kind === "strings") frag.appendChild(stringsField(def, obj));
    });
    return frag;
  }

  // ---------- step cards ----------

  function isRequired(step) { return cfg.required.indexOf(step.type) !== -1; }
  var dragFrom = null;

  function stepCard(step, index) {
    var steps = data.steps;
    var locked = isRequired(step);
    var card = el("section", "ops-panel st-step" + (locked ? " is-locked" : ""));
    card.setAttribute("aria-labelledby", "st-step-" + index);
    var head = el("div", "st-step-head");
    var title = el("h2", null, "Step " + (index + 1) + " · " + (cfg.names[step.type] || step.type));
    title.id = "st-step-" + index;
    head.appendChild(title);
    var controls = el("div", "st-row-controls");
    if (locked) {
      controls.appendChild(el("span", "st-lock", "Required · stays in place"));
    } else {
      card.draggable = true;
      var firstMovable = 1;
      function button(text, label, disabled, action) {
        var b = el("button", "ops-btn-quiet", text);
        b.type = "button";
        b.setAttribute("aria-label", label);
        b.disabled = disabled;
        b.addEventListener("click", function () { action(); changed(); renderAll(); });
        controls.appendChild(b);
      }
      button("↑", "Move step up", index <= firstMovable || isRequired(steps[index - 1]), function () { moveItem(steps, index, index - 1); });
      button("↓", "Move step down", index === steps.length - 1 || isRequired(steps[index + 1]), function () { moveItem(steps, index, index + 1); });
      button("Remove step", "Remove step " + (index + 1), false, function () {
        if (window.confirm("Remove this step? Its text will be lost when you save.")) steps.splice(index, 1);
      });
      card.addEventListener("dragstart", function (e) { dragFrom = index; e.dataTransfer.effectAllowed = "move"; card.classList.add("is-dragging"); });
      card.addEventListener("dragend", function () { card.classList.remove("is-dragging"); });
    }
    card.addEventListener("dragover", function (e) { if (dragFrom !== null && !locked) e.preventDefault(); });
    card.addEventListener("drop", function (e) {
      e.preventDefault();
      if (dragFrom === null || locked || dragFrom === index) return;
      moveItem(steps, dragFrom, index);
      dragFrom = null;
      changed();
      renderAll();
    });
    head.appendChild(controls);
    card.appendChild(head);
    var schema = cfg.schema[step.type];
    if (schema) card.appendChild(fields(schema, step.data));
    return card;
  }

  function addStepControl() {
    var box = el("div", "ops-panel st-add-step");
    var id = nextId();
    var label = el("label", null, "Add a step");
    label.htmlFor = id;
    var select = el("select");
    select.id = id;
    cfg.allowed.forEach(function (type) {
      var option = el("option", null, cfg.names[type] || type);
      option.value = type;
      select.appendChild(option);
    });
    var add = el("button", null, "Add step");
    add.type = "button";
    add.addEventListener("click", function () {
      data.steps.push({ uid: null, type: select.value, data: clone(cfg.blanks[select.value]) });
      changed();
      renderAll();
      var cards = root.querySelectorAll(".st-step");
      if (cards.length) cards[cards.length - 1].scrollIntoView({ behavior: "smooth", block: "start" });
    });
    box.appendChild(label);
    box.appendChild(select);
    box.appendChild(add);
    return box;
  }

  function debriefCard() {
    var card = el("section", "ops-panel st-step is-locked");
    var head = el("div", "st-step-head");
    head.appendChild(el("h2", null, "Results screen"));
    head.appendChild(el("span", "st-lock", "Always last"));
    card.appendChild(head);
    if (!data.debrief) data.debrief = { headline: "", sub: "", learned: [] };
    card.appendChild(fields(cfg.debrief_schema, data.debrief));
    return card;
  }

  function renderAll() {
    var scroll = window.scrollY;
    root.textContent = "";
    data.steps.forEach(function (step, i) { root.appendChild(stepCard(step, i)); });
    root.appendChild(addStepControl());
    root.appendChild(debriefCard());
    window.scrollTo(0, scroll);
  }

  renderAll();
})();
