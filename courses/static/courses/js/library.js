(function () {
  var root = document.getElementById("lib");
  if (!root) return;

  function el(id) { return document.getElementById(id); }
  function setText(id, value) { var node = el(id); if (node) node.textContent = value; }

  /* ---------- Filter tabs ---------- */
  var tabs = Array.prototype.slice.call(root.querySelectorAll(".lib-tab"));
  var shelf = el("lib-shelf");

  function applyFilter(tab) {
    var filter = tab.getAttribute("data-filter");
    tabs.forEach(function (other) {
      var on = other === tab;
      other.setAttribute("aria-selected", on ? "true" : "false");
      other.tabIndex = on ? 0 : -1;
    });
    if (shelf) shelf.setAttribute("aria-labelledby", tab.id);

    var shown = 0;
    root.querySelectorAll(".lib-row").forEach(function (row) {
      var rowShown = 0;
      row.querySelectorAll(".lib-slot").forEach(function (slot) {
        var match = filter === "all" || slot.getAttribute("data-status") === filter;
        slot.hidden = !match;
        if (match) rowShown += 1;
      });
      row.hidden = rowShown === 0;
      shown += rowShown;
    });
    var empty = el("lib-empty");
    if (empty) empty.hidden = shown > 0;
  }

  tabs.forEach(function (tab, index) {
    tab.addEventListener("click", function () { applyFilter(tab); });
    tab.addEventListener("keydown", function (event) {
      var next = null;
      if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
      else if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (event.key === "Home") next = tabs[0];
      else if (event.key === "End") next = tabs[tabs.length - 1];
      if (!next) return;
      event.preventDefault();
      next.focus();
      applyFilter(next);
    });
  });

  /* ---------- Book selection + reading stand ---------- */
  var books = Array.prototype.slice.call(root.querySelectorAll(".lib-shelf .book"));

  function updateStand(button) {
    var d = button.dataset;
    var done = d.done === "1";
    var standBook = el("stand-book");
    if (standBook) standBook.className = "book book--lg tone-" + d.tone;
    var cover = el("stand-cover");
    if (cover) cover.src = d.cover;
    setText("stand-vol", d.vol + " · " + d.code);
    setText("stand-cover-title", d.title);
    setText("stand-meta", d.code + " · " + d.format);
    setText("stand-title", d.title);
    setText("stand-summary", d.summary);
    setText("stand-status", done ? "Completed" : "Not started");
    setText("stand-percent", done ? "100%" : "0%");
    var bar = el("stand-bar");
    if (bar) bar.style.width = done ? "100%" : "0%";
    var open = el("stand-open");
    if (open) open.href = d.url;
    setText("stand-open-label", done ? "Read again" : "Open book");
    setText("stand-unlock-text", d.unlocks
      ? "Finish the book to unlock the " + d.unlocks + " mission"
      : "Finish the book to complete this course");
  }

  function select(button) {
    books.forEach(function (other) {
      var on = other === button;
      other.classList.toggle("is-selected", on);
      other.setAttribute("aria-pressed", on ? "true" : "false");
    });
    updateStand(button);
  }

  books.forEach(function (button) {
    button.addEventListener("click", function () { select(button); });
    // Double click opens the book straight away.
    button.addEventListener("dblclick", function () { window.location.href = button.dataset.url; });
  });

  // Start on the first unread book, or the first book if all are done.
  var first = books.filter(function (b) { return b.dataset.done !== "1"; })[0] || books[0];
  if (first) select(first);
})();
