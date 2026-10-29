/* Blog editor: "Insert image". Uploads through the same checks as the Images panel
   (blog_panel:image_insert) and puts the returned Markdown line at the cursor in the body.
   The Images panel's own upload form keeps working without JavaScript. */
(function () {
  "use strict";

  var dialog = document.getElementById("bp-insert");
  var open = document.getElementById("bp-insert-open");
  var body = document.getElementById("id_body");
  if (!dialog || !open || !body || typeof dialog.showModal !== "function") {
    if (open) open.hidden = true;           // old browsers: use the Images panel instead
    return;
  }
  var form = document.getElementById("bp-insert-form");
  var error = document.getElementById("bp-insert-error");
  var submit = document.getElementById("bp-insert-submit");
  var cursor = { start: body.value.length, end: body.value.length };

  function showError(text) { error.textContent = text; error.hidden = !text; }

  open.addEventListener("click", function () {
    cursor = { start: body.selectionStart, end: body.selectionEnd };
    form.reset();
    showError("");
    dialog.showModal();
    document.getElementById("bp-insert-file").focus();
  });
  document.getElementById("bp-insert-cancel").addEventListener("click", function () { dialog.close(); });
  dialog.addEventListener("close", function () { open.focus(); });

  function insert(line) {
    var before = body.value.slice(0, cursor.start);
    var after = body.value.slice(cursor.end);
    // An image is its own paragraph: blank lines around it unless already there.
    var lead = before === "" || /\n\n$/.test(before) ? "" : (/\n$/.test(before) ? "\n" : "\n\n");
    var tail = after === "" || /^\n\n/.test(after) ? "" : (/^\n/.test(after) ? "\n" : "\n\n");
    body.value = before + lead + line + tail + after;
    var at = (before + lead + line).length;
    body.focus();
    body.setSelectionRange(at, at);
    body.dispatchEvent(new Event("input", { bubbles: true }));
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!form.elements.alt.value.trim()) {
      showError("Add alt text: describe the image for people who can't see it.");
      form.elements.alt.focus();
      return;
    }
    submit.disabled = true;
    showError("");
    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-CSRFToken": form.elements.csrfmiddlewaretoken.value, "Accept": "application/json" }
    }).then(function (res) {
      var type = res.headers.get("Content-Type") || "";
      if (type.indexOf("application/json") === -1) {
        throw new Error(res.status === 403 ? "Your session has ended or the page is out of date. Copy your text, then reload."
                                           : "The upload didn't go through. Try again.");
      }
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
      if (!result.ok) throw new Error((result.data.errors || ["The upload didn't go through."]).join(" "));
      dialog.close();
      insert(result.data.markdown);
    }).catch(function (err) {
      showError(err.message || "The upload didn't go through. Try again.");
    }).then(function () { submit.disabled = false; });
  });
})();
