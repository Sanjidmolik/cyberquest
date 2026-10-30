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
  var scroller = document.getElementById("msg-scroll") || thread;
  var TICKS = { sent: "Sent", delivered: "Delivered", read: "Read" };
  var TIMER_BADGE = { view: "After viewing", "1h": "1h", "24h": "24h", "7d": "7d" };
  var SVG = "http://www.w3.org/2000/svg";

  // Icons are built with DOM methods, never from HTML strings.
  function svg(width, height, viewBox, paths, filled) {
    var s = document.createElementNS(SVG, "svg");
    s.setAttribute("width", width); s.setAttribute("height", height); s.setAttribute("viewBox", viewBox);
    s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false");
    s.setAttribute("fill", filled ? "currentColor" : "none");
    if (!filled) {
      s.setAttribute("stroke", "currentColor"); s.setAttribute("stroke-width", "2.6");
      s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
    }
    paths.forEach(function (spec) {
      var node = document.createElementNS(SVG, spec[0]);
      Object.keys(spec[1]).forEach(function (k) { node.setAttribute(k, spec[1][k]); });
      s.appendChild(node);
    });
    return s;
  }
  function clockIcon(size) { return svg(size, size, "0 0 24 24", [["circle", { cx: 12, cy: 13, r: 8 }], ["path", { d: "M12 9v4" }]]); }
  function photoIcon() {
    return svg(18, 18, "0 0 24 24", [["rect", { x: 3, y: 5, width: 18, height: 14, rx: 3 }], ["circle", { cx: 9, cy: 11, r: 2 }],
      ["path", { d: "m21 17-5-5-8 8" }]]);
  }
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
    if (m.photo) li.appendChild(photoBody(m));
    else li.appendChild(el("p", "msg-bubble-text" + (m.removed ? " is-removed" : ""), m.removed ? "Message removed" : m.text));
    var meta = el("span", "mx-meta");
    if (m.timer && m.timer !== "off" && TIMER_BADGE[m.timer]) {
      var badge = el("span", "mx-badge");
      badge.appendChild(clockIcon(11));
      badge.appendChild(document.createTextNode(TIMER_BADGE[m.timer]));
      badge.setAttribute("title", "Disappearing message");
      meta.appendChild(badge);
    }
    var t = el("time", "msg-bubble-time", timeLabel(m.at));
    t.setAttribute("datetime", m.at);
    meta.appendChild(t);
    if (m.status) {
      var tick = el("span", "msg-tick");
      tick.dataset.mine = "1";
      meta.appendChild(tick);
      setTick(tick, m.status);
    }
    li.appendChild(meta);
    if (m.can_report && cfg.urls.report) {
      var report = el("button", "msg-report-btn", m.reported ? "Reported" : "Report");
      report.type = "button";
      report.disabled = !!m.reported;
      report.setAttribute("aria-label", "Report this message");
      report.addEventListener("click", function () { openReport(m.id, report); });
      li.appendChild(report);
      latestReportable = { id: m.id, button: report };
      var headerReport = document.getElementById("msg-report-chat");
      if (headerReport && !m.reported) headerReport.hidden = false;
    }
    return li;
  }

  var latestReportable = null;

  function addMessages(list, atTop) {
    if (!thread || !list.length) return;
    var nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
    var frag = document.createDocumentFragment();
    list.forEach(function (m) {
      if (thread.querySelector('[data-id="' + m.id + '"]')) return;
      frag.appendChild(bubble(m));
      lastId = Math.max(lastId, m.id);
      firstId = firstId ? Math.min(firstId, m.id) : m.id;
    });
    if (atTop) {
      var before = scroller.scrollHeight;
      thread.insertBefore(frag, thread.firstChild);
      scroller.scrollTop += scroller.scrollHeight - before;
    } else {
      thread.appendChild(frag);
      if (nearBottom || list.some(function (m) { return m.mine; })) scroller.scrollTop = scroller.scrollHeight;
    }
    markRead();
  }

  // ---------- view-once photos ----------

  function photoLabel(m) {
    if (m.photo.state === "opened") return "Photo · opened";
    return m.mine ? "Photo · sent" : "Photo · view once";
  }

  function photoBody(m) {
    var b = el("button", "mx-photo msg-photo-open");
    b.type = "button";
    b.appendChild(photoIcon());
    b.appendChild(el("span", null, m.photo.can_open ? "Photo · view once · tap to open" : photoLabel(m)));
    if (m.photo.can_open) b.addEventListener("click", function () { openPhoto(m, b); });
    else b.disabled = true;
    return b;
  }

  function photoDone(button, text) {
    button.disabled = true;
    button.lastChild.textContent = text;
  }

  var viewer = document.getElementById("msg-viewer");
  var viewerUrl = null, viewerTimer = null;

  function closeViewer() {
    clearInterval(viewerTimer);
    var img = document.getElementById("msg-viewer-img");
    img.removeAttribute("src");
    if (viewerUrl) { URL.revokeObjectURL(viewerUrl); viewerUrl = null; }
    if (viewer.open) viewer.close();
  }

  function openPhoto(m, button) {
    if (!viewer) return;
    button.disabled = true;
    fetch(cfg.urls.photo_open.replace("/0/open/", "/" + m.id + "/open/"), {
      method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf() }
    }).then(function (res) {
      if (!res.ok) return res.json().catch(function () { return {}; }).then(function (d) { throw new Error(d.error || "This photo isn't available."); });
      return res.blob();
    }).then(function (blob) {
      photoDone(button, "Photo · opened");
      viewerUrl = URL.createObjectURL(blob);
      document.getElementById("msg-viewer-img").src = viewerUrl;
      // Deterrent only: who is looking, and when, tiled across the photo.
      var marks = document.getElementById("msg-viewer-mark"), label = cfg.me + " · " + new Date().toLocaleString();
      marks.textContent = "";
      for (var i = 0; i < 9; i++) marks.appendChild(el("span", null, label));
      var total = cfg.view_seconds || 10, left = total;
      var count = document.getElementById("msg-viewer-count"), ring = document.getElementById("msg-viewer-ring");
      var secs = document.getElementById("msg-viewer-secs");
      function show() {
        count.textContent = "View once · closes in " + left + " s";
        secs.textContent = left;
        ring.setAttribute("stroke-dashoffset", String(138.2 * (1 - left / total)));
      }
      show();
      viewer.showModal();
      document.getElementById("msg-viewer-close").focus();
      viewerTimer = setInterval(function () {
        left -= 1;
        show();
        if (left <= 0) closeViewer();
      }, 1000);
    }).catch(function (err) {
      photoDone(button, err.message);
    });
  }

  if (viewer) {
    document.getElementById("msg-viewer-close").addEventListener("click", closeViewer);
    viewer.addEventListener("close", closeViewer);
    viewer.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    viewer.addEventListener("dragstart", function (e) { e.preventDefault(); });
    var stage = document.getElementById("msg-viewer-stage");
    function blurIt(on) { stage.classList.toggle("is-blurred", on); }
    window.addEventListener("blur", function () { blurIt(true); });
    window.addEventListener("focus", function () { blurIt(false); });
    document.addEventListener("visibilitychange", function () { blurIt(document.hidden); });
  }

  function setTick(tick, status) {
    if (tick.dataset.status === status) return;
    tick.dataset.status = status;
    tick.textContent = "";
    tick.appendChild(status === "sent"
      ? svg(15, 15, "0 0 24 24", [["path", { d: "M5 12.5l4.5 4.5L19 7.5" }]])
      : svg(20, 15, "0 0 30 24", [["path", { d: "M2 12.5l4.5 4.5L16 7.5" }], ["path", { d: "M11 15l2 2L22.5 7.5" }]]));
    tick.setAttribute("aria-label", TICKS[status]);
    tick.setAttribute("role", "img");
    tick.setAttribute("title", TICKS[status]);
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

  // Deterrent only: no text selection while disappearing messages are on (screen readers still
  // read everything; nothing is hidden from assistive technology).
  function applyTimer(value) {
    cfg.timer = value;
    if (thread) thread.classList.toggle("is-nocopy", value !== "off");
    var note = document.getElementById("msg-nocopy");
    if (note) note.hidden = value === "off";
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
      if (data.timer) applyTimer(data.timer);
    });
  }

  function setupConversation() {
    addMessages(cfg.messages || []);
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
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
        if (data._status === 200) { if (data.message) addMessages([data.message]); applyTimer(timerSelect.value); }
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
    var photoInput = document.getElementById("msg-photo");
    if (photoInput) photoInput.addEventListener("change", function () {
      var file = photoInput.files[0];
      if (!file) return;
      var body = new FormData();
      body.append("photo", file);
      error.textContent = "Sending photo…";
      fetch(cfg.urls.photo, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf() }, body: body })
        .then(function (res) { return res.json().then(function (d) { d._status = res.status; return d; }); })
        .then(function (data) {
          error.textContent = data._status === 201 ? "" : (data.error || "Couldn't send the photo.");
          if (data._status === 201) addMessages([data.message]);
        }).catch(function () { error.textContent = "Couldn't send the photo: check your connection."; })
        .then(function () { photoInput.value = ""; });
    });
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

  var headerReport = document.getElementById("msg-report-chat");
  if (headerReport) headerReport.addEventListener("click", function () {
    if (latestReportable) openReport(latestReportable.id, latestReportable.button);
  });

  var grow = document.getElementById("msg-text");
  if (grow) grow.addEventListener("input", function () {
    grow.style.height = "auto";
    grow.style.height = Math.min(grow.scrollHeight, 120) + "px";
  });

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
          if (headerReport && latestReportable && reportTarget.id === latestReportable.id) headerReport.hidden = true;
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
        var side = a.querySelector("time");
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
        document.getElementById("msg-typing-text").textContent = (cfg.other || "They") + " is typing…";
        note.hidden = false;
        scroller.scrollTop = scroller.scrollHeight;
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
