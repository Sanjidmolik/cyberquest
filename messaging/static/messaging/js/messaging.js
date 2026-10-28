/* Inbox and conversation: send, poll, read markers, live updates.

   Polling always runs (it is the fallback when WebSockets aren't available):
   - every 4 s while a conversation is open and the user was active in the last 2 minutes,
   - every 15 s otherwise (inbox only, or idle for 2 minutes),
   - paused while the tab is hidden; resumes (and polls at once) when it comes back.
   The WebSocket, when it connects, only says "this conversation changed"; we then poll at once.
   Message text is only ever inserted with textContent. */
(function () {
  "use strict";

  var node = document.getElementById("msg-config");
  if (!node) return;
  var cfg = JSON.parse(node.textContent);
  var FAST = 4000, SLOW = 15000, IDLE_AFTER = 120000;
  var lastActivity = Date.now();
  var timer = null;
  var lastId = 0, firstId = 0, readUpto = 0;
  var thread = document.getElementById("msg-thread");

  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function api(url, body) {
    var opts = { credentials: "same-origin", headers: { "Accept": "application/json" } };
    if (body !== undefined) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.headers["X-CSRFToken"] = csrf();
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) { data._status = res.status; return data; });
    });
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function timeLabel(iso) {
    var d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleString([], { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" });
  }

  // ---------- conversation ----------

  function bubble(m) {
    var li = el("li", "msg-bubble " + (m.mine ? "is-mine" : "is-theirs"));
    li.dataset.id = m.id;
    if (!m.mine) li.appendChild(el("span", "msg-bubble-who", m.sender || "Deleted user"));
    li.appendChild(el("p", "msg-bubble-text" + (m.removed ? " is-removed" : ""), m.removed ? "Message removed" : m.text));
    var t = el("time", "msg-bubble-time", timeLabel(m.at));
    t.setAttribute("datetime", m.at);
    li.appendChild(t);
    return li;
  }

  function addMessages(list, atTop) {
    if (!thread || !list.length) return;
    var nearBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
    var frag = document.createDocumentFragment();
    list.forEach(function (m) {
      if (thread.querySelector('[data-id="' + m.id + '"]')) return;
      frag.appendChild(bubble(m));
      lastId = Math.max(lastId, m.id);
      firstId = firstId ? Math.min(firstId, m.id) : m.id;
    });
    if (atTop) {
      var before = thread.scrollHeight;
      thread.insertBefore(frag, thread.firstChild);
      thread.scrollTop += thread.scrollHeight - before;
    } else {
      thread.appendChild(frag);
      if (nearBottom || list.some(function (m) { return m.mine; })) thread.scrollTop = thread.scrollHeight;
    }
    markRead();
  }

  function markRead() {
    if (!cfg.conversation || document.hidden || lastId <= readUpto) return;
    readUpto = lastId;
    api(cfg.urls.read, { upto: lastId });
  }

  function applyStatus(status) {
    if (!status) return;
    var form = document.getElementById("msg-compose");
    var cannot = document.getElementById("msg-cannot");
    if (form) form.hidden = !status.can_send;
    if (cannot) { cannot.hidden = status.can_send; cannot.textContent = status.reason || ""; }
  }

  function pollConversation() {
    return api(cfg.urls.poll + "?after=" + lastId).then(function (data) {
      if (data._status !== 200) return;
      addMessages(data.messages || []);
      applyStatus(data.status);
    });
  }

  function setupConversation() {
    addMessages(cfg.messages || []);
    if (thread) thread.scrollTop = thread.scrollHeight;
    var older = document.getElementById("msg-older");
    if (older && (cfg.messages || []).length >= 50) {
      older.hidden = false;
      older.addEventListener("click", function () {
        api(cfg.urls.poll + "?before=" + firstId).then(function (data) {
          var rows = data.messages || [];
          addMessages(rows, true);
          if (rows.length < 50) older.hidden = true;
        });
      });
    }
    var form = document.getElementById("msg-compose");
    var box = document.getElementById("msg-text");
    var counter = document.getElementById("msg-counter");
    var error = document.getElementById("msg-error");
    var send = document.getElementById("msg-send");
    if (!form || !box) return;
    box.addEventListener("input", function () {
      counter.textContent = box.value.length + " / " + cfg.max;
      counter.classList.toggle("is-near", box.value.length > cfg.max * 0.9);
    });
    box.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = box.value.trim();
      if (!text) return;
      send.disabled = true;
      error.textContent = "";
      api(cfg.urls.send, { text: text }).then(function (data) {
        if (data._status === 201) {
          box.value = "";
          counter.textContent = "0 / " + cfg.max;
          addMessages([data.message]);
        } else {
          error.textContent = data.error || "Couldn't send. Try again.";
        }
      }).catch(function () {
        error.textContent = "Couldn't send: check your connection.";
      }).then(function () { send.disabled = false; box.focus(); });
    });
  }

  // ---------- inbox list ----------

  function refreshInbox() {
    return api(cfg.urls.inbox + (cfg.tab === "requests" ? "?tab=requests" : "")).then(function (data) {
      if (data._status !== 200) return;
      var counts = {};
      (data.rows || []).forEach(function (r) { counts[r.id] = r; });
      document.querySelectorAll(".msg-conv[data-id]").forEach(function (a) {
        var row = counts[a.dataset.id];
        if (!row) return;
        a.classList.toggle("is-unread", row.unread > 0 && a.dataset.id !== cfg.conversation);
        var preview = a.querySelector(".msg-conv-preview");
        if (preview) preview.textContent = (row.mine_last ? "You: " : "") + row.preview;
        var side = a.querySelector(".msg-conv-side time");
        if (side) side.textContent = row.when;
      });
      var badge = document.getElementById("msg-request-count");
      if (badge) badge.textContent = data.requests || "";
    });
  }

  // ---------- scheduling ----------

  function interval() {
    if (!cfg.conversation) return SLOW;
    return Date.now() - lastActivity > IDLE_AFTER ? SLOW : FAST;
  }

  function tick() {
    timer = null;
    if (document.hidden) return;                    // resumes on visibilitychange
    var work = cfg.conversation ? pollConversation() : refreshInbox();
    work.catch(function () {}).then(schedule);
  }

  function schedule() {
    clearTimeout(timer);
    if (!document.hidden) timer = setTimeout(tick, interval());
  }

  function pollNow() { clearTimeout(timer); tick(); }

  ["keydown", "pointerdown", "scroll", "focus"].forEach(function (type) {
    window.addEventListener(type, function () {
      var wasIdle = Date.now() - lastActivity > IDLE_AFTER;
      lastActivity = Date.now();
      if (wasIdle && cfg.conversation) pollNow();
    }, { passive: true, capture: true });
  });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { clearTimeout(timer); timer = null; }
    else { lastActivity = Date.now(); pollNow(); markRead(); }
  });

  // ---------- live updates (optional) ----------

  function connect(delay) {
    if (!("WebSocket" in window) || !cfg.socket) return;
    var url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + cfg.socket;
    var ws;
    try { ws = new WebSocket(url); } catch (e) { return; }
    ws.onmessage = function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (e) { return; }
      if (data.type !== "changed") return;
      if (cfg.conversation && data.conversation === cfg.conversation) pollNow();
      else refreshInbox();
    };
    ws.onclose = function () {            // retry with back-off; polling keeps working meanwhile
      var next = Math.min((delay || 2000) * 2, 60000);
      setTimeout(function () { connect(next); }, next);
    };
  }

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  if (cfg.conversation) setupConversation();
  schedule();
  connect();
})();
