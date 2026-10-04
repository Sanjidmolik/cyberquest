(function () {
  const params = new URLSearchParams(location.search);
  const raw = params.get("generating");
  if (!raw) return;
  const ids = raw.split(",").map(s => s.trim()).filter(Boolean);
  if (!ids.length) return;

  const root = document.createElement("div");
  root.className = "cq-loader on";
  root.innerHTML = `
    <div class="cq-loader-card" role="status" aria-live="polite">
      <div class="cq-cube" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span><span></span></div>
      <h2>Building the question bank</h2>
      <p class="cq-stage">Analyzing source material...</p>
      <p class="cq-count"></p>
      <p class="cq-error" hidden></p>
    </div>`;
  document.body.appendChild(root);
  const stage = root.querySelector(".cq-stage");
  const count = root.querySelector(".cq-count");
  const error = root.querySelector(".cq-error");

  const terminal = new Set(["REVIEW", "PARTIAL", "FAILED", "APPROVED", "ARCHIVED", "DRAFT"]);

  async function poll() {
    let still = false;
    for (const id of ids) {
      const res = await fetch(`/api/question-banks/${id}/`, { credentials: "same-origin" });
      if (!res.ok) {
        error.hidden = false;
        error.textContent = "Could not read generation status.";
        return;
      }
      const data = await res.json();
      if (data.generation_stage) stage.textContent = data.generation_stage;
      if (data.generation_requested) {
        count.textContent = `${data.generation_completed} of ${data.generation_requested} questions accepted`;
      } else {
        count.textContent = "";
      }
      if (data.status === "FAILED" || data.status === "PARTIAL") {
        error.hidden = false;
        error.textContent = data.last_error || "Generation needs attention.";
      }
      if (!terminal.has(data.status)) still = true;
    }
    if (still) {
      setTimeout(poll, 2000);
    } else {
      stage.textContent = stage.textContent || "Preparing your question bank...";
      setTimeout(() => location.href = location.pathname, 900);
    }
  }
  poll().catch(() => {
    error.hidden = false;
    error.textContent = "Status check failed. Refresh the page to try again.";
  });
})();
