/* One threshold for every blocking load. Change it here only. */
var CQ_LOADING_DELAY_MS = 1500;

(function () {
  var pending = 0;
  var visible = false;
  var timers = [];
  var bar = null;
  var seq = 0;

  function delay() {
    var configured = window.CQ_LOADING && window.CQ_LOADING.delayMs;
    return typeof configured === "number" ? configured : CQ_LOADING_DELAY_MS;
  }

  function ensureBar() {
    if (bar && bar.isConnected) return bar;
    bar = document.createElement("div");
    bar.className = "cq-loadbar";
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-label", "Loading");
    bar.setAttribute("aria-hidden", "true");
    bar.innerHTML = '<span class="cq-loadbar-fill"></span>';
    document.documentElement.appendChild(bar);
    return bar;
  }

  function show() {
    if (pending < 1 || visible) return;
    visible = true;
    var el = ensureBar();
    el.classList.add("is-on");
    el.setAttribute("aria-hidden", "false");
  }

  function hide() {
    if (pending > 0) return;
    visible = false;
    if (!bar) return;
    bar.classList.remove("is-on");
    bar.setAttribute("aria-hidden", "true");
  }

  function start() {
    var id = ++seq;
    pending += 1;
    var timer = window.setTimeout(function () {
      timer.done = true;
      show();
    }, delay());
    timer.cqId = id;
    timers.push(timer);
    return id;
  }

  function finish(id) {
    for (var i = 0; i < timers.length; i += 1) {
      if (timers[i].cqId === id) {
        window.clearTimeout(timers[i]);
        timers.splice(i, 1);
        break;
      }
    }
    if (pending > 0) pending -= 1;
    hide();
  }

  function reset() {
    timers.forEach(function (timer) { window.clearTimeout(timer); });
    timers = [];
    pending = 0;
    hide();
  }

  window.CQ_LOADING = {
    delayMs: CQ_LOADING_DELAY_MS,
    start: start,
    finish: finish,
    reset: reset,
    pending: function () { return pending; },
    visible: function () { return visible; },
  };

  function sameDocument(url) {
    return url.origin === location.origin && url.pathname === location.pathname && url.search === location.search;
  }

  function trackNavigation(event) {
    if (event.hashChange || event.downloadRequest) return;
    if (event.destination && event.destination.sameDocument) return;
    var id = start();
    var done = function () { finish(id); };
    if (typeof event.intercept === "function") {
      /* Do not intercept. The browser still navigates; we only observe. */
    }
    navigation.addEventListener("navigatesuccess", done, { once: true });
    navigation.addEventListener("navigateerror", done, { once: true });
  }

  if (window.navigation && typeof navigation.addEventListener === "function") {
    navigation.addEventListener("navigate", trackNavigation);
  } else {
    document.addEventListener("click", function (event) {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      var link = event.target && event.target.closest ? event.target.closest("a[href]") : null;
      if (!link || link.target && link.target !== "_self" || link.hasAttribute("download")) return;
      var url;
      try { url = new URL(link.href, location.href); } catch (error) { return; }
      if (url.origin !== location.origin || sameDocument(url)) return;
      start();
    });
    document.addEventListener("submit", function (event) {
      if (event.defaultPrevented) return;
      var form = event.target;
      if (!form || (form.target && form.target !== "_self")) return;
      start();
    });
    window.addEventListener("pagehide", reset);
  }

  window.addEventListener("pageshow", function (event) {
    if (event.persisted) reset();
  });

  function watch(root) {
    var nodes = (root || document).querySelectorAll("[data-cq-blocking]");
    nodes.forEach(function (el) {
      if (el.dataset.cqLoadingWatched) return;
      el.dataset.cqLoadingWatched = "1";
      if (el.tagName === "IMG" && el.complete) return;
      var id = start();
      var done = function () { finish(id); };
      el.addEventListener("load", done, { once: true });
      el.addEventListener("error", done, { once: true });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { watch(document); });
  } else {
    watch(document);
  }

  var nativeFetch = window.fetch;
  if (typeof nativeFetch === "function") {
    window.fetch = function (input, init) {
      var blocking = init && init.cqBlocking === true;
      if (!blocking) return nativeFetch.apply(this, arguments);
      var next = Object.assign({}, init);
      delete next.cqBlocking;
      var id = start();
      return nativeFetch.call(this, input, next).then(function (response) {
        finish(id);
        return response;
      }, function (error) {
        finish(id);
        throw error;
      });
    };
  }
})();
