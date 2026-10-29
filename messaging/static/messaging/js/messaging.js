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
  var seen = cfg.receipts || { delivered_upto: 0, read_upto: 0 };
  var TICKS = { sent: ["✓", "Sent"], delivered: ["✓✓", "Delivered"], read: ["✓✓", "Read"] };
  var socket = null, typingSentAt = 0, typingHide = null;

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
    if (m.kind === "system") {                          // "X set disappearing messages to 1 hour"
      var note = el("li", "msg-system", m.text);
      note.setAttribute("data-id", m.id);
      return note;
    }
    var li = el("li", "msg-bubble " + (m.mine ? "is-mine" : "is-theirs"));
    li.dataset.id = m.id;
    if (!m.mine) li.appendChild(el("span", "msg-bubble-who", m.sender || "Deleted user"));
    li.appendChild(el("p", "msg-bubble-text" + (m.removed ? " is-removed" : ""), m.removed ? "Message removed" : m.text));
    var t = el("time", "msg-bubble-time", timeLabel(m.at));
    t.setAttribute("datetime", m.at);
    li.appendChild(t);
    if (m.status) {
      var tick = el("span", "msg-tick");
      tick.dataset.mine = "1";
      li.appendChild(tick);
      setTick(tick, m.status);
    }
    if (m.can_report && cfg.urls.report) {
      var report = el("button", "msg-report-btn", m.reported ? "Reported" : "Report");
      report.type = "button";
      report.disabled = !!m.reported;
      report.setAttribute("aria-label", "Report this message");
      report.addEventListener("click", function () { openReport(m.id, report); });
      li.appendChild(report);
    }
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

  function setTick(tick, status) {
    tick.textContent = TICKS[status][0];
    tick.setAttribute("aria-label", TICKS[status][1]);
    tick.setAttribute("role", "img");
    tick.classList.toggle("is-read", status === "read");
  }

  function applyReceipts(r) {
    if (!r || !thread) return;
    seen = r;
    thread.querySelectorAll(".msg-bubble.is-mine").forEach(function (li) {
      var tick = li.querySelector(".msg-tick");
      var id = +li.dataset.id;
      if (!tick) return;
      setTick(tick, id <= r.read_upto ? "read" : id <= r.delivered_upto ? "delivered" : "sent");
    });
  }

  function applyPresence(online) {
    var p = document.getElementById("msg-presence");
    if (p) p.hidden = !online;
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
      applyReceipts(data.receipts);
      applyPresence(data.online);
      var select = document.getElementById("msg-timer");
      if (select && data.timer && document.activeElement !== select) select.value = data.timer;
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
    var timerSelect = document.getElementById("msg-timer");
    if (timerSelect) timerSelect.addEventListener("change", function () {
      api(cfg.urls.timer, { timer: timerSelect.value }).then(function (data) {
        if (data._status === 200) { if (data.message) addMessages([data.message]); }
        else { error.textContent = data.error || "Couldn't change it. Try again."; timerSelect.value = cfg.timer; }
      });
    });
    box.addEventListener("input", function () {
      // Typing indicator: WebSocket only, at most every 3 s (the server throttles too).
      if (socket && socket.readyState === 1 && Date.now() - typingSentAt > 3000) {
        typingSentAt = Date.now();
        socket.send(JSON.stringify({ type: "typing", conversation: cfg.conversation }));
      }
      counter.textContent = box.value.length + " / " + cfg.max;
      counter.classList.toggle("is-near", box.value.length > cfg.max * 0.9);
    });
    box.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
    });
    var warn = document.getElementById("msg-warn");

    function submit(confirm) {
      var text = box.value.trim();
      if (!text) return;
      send.disabled = true;
      error.textContent = "";
      if (warn) warn.hidden = true;
      api(cfg.urls.send, { text: text, confirm: confirm }).then(function (data) {
        if (data._status === 201) {
          box.value = "";
          counter.textContent = "0 / " + cfg.max;
          addMessages([data.message]);
        } else if (data._status === 409 && data.needs_confirmation && warn) {
          // "May be offensive": the sender decides. Nothing is sent until they confirm.
          warn.hidden = false;
          document.getElementById("msg-warn-send").focus();
        } else {
          error.textContent = data.error || "Couldn't send. Try again.";
        }
      }).catch(function () {
        error.textContent = "Couldn't send: check your connection.";
      }).then(function () { send.disabled = false; if (!warn || warn.hidden) box.focus(); });
    }

    form.addEventListener("submit", function (e) { e.preventDefault(); submit(false); });
    if (warn) {
      document.getElementById("msg-warn-send").addEventListener("click", function () { submit(true); });
      document.getElementById("msg-warn-edit").addEventListener("click", function () { warn.hidden = true; box.focus(); });
    }
  }

  // ---------- reporting ----------

  var reportDialog = document.getElementById("msg-report");
  var reportTarget = null;

  function openReport(messageId, button) {
    if (!reportDialog) return;
    reportTarget = { id: messageId, button: button };
    document.getElementById("msg-report-form").reset();
    document.getElementById("msg-report-error").textContent = "";
    reportDialog.showModal();
  }

  if (reportDialog) {
    document.getElementById("msg-report-cancel").addEventListener("click", function () { reportDialog.close(); });
    document.getElementById("msg-report-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var form = e.target;
      var reason = form.querySelector("input[name=reason]:checked");
      var errorBox = document.getElementById("msg-report-error");
      if (!reason) { errorBox.textContent = "Choose a reason."; return; }
      api(cfg.urls.report, {
        message: reportTarget.id, reason: reason.value,
        note: form.note.value, block: form.block.checked
      }).then(function (data) {
        if (data._status === 201 || data._status === 200) {
          reportDialog.close();
          reportTarget.button.textContent = "Reported";
          reportTarget.button.disabled = true;
          if (form.block.checked) window.location.reload();
        } else {
          errorBox.textContent = data.error || "Couldn't send the report. Try again.";
        }
      });
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
        var dot = a.querySelector("[data-online]");
        if (dot) dot.hidden = !row.online;
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
    socket = ws;
    ws.onmessage = function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (e) { return; }
      if (data.type === "typing" && data.conversation === cfg.conversation) {
        var note = document.getElementById("msg-typing");
        if (!note) return;
        note.textContent = (cfg.other || "They") + " is typing…";
        note.hidden = false;
        clearTimeout(typingHide);
        typingHide = setTimeout(function () { note.hidden = true; }, 5000);
        return;
      }
      if (data.type !== "changed") return;
      if (cfg.conversation && data.conversation === cfg.conversation) pollNow();
      else refreshInbox();
    };
    ws.onclose = function () {            // retry with back-off; polling keeps working meanwhile
      socket = null;
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
