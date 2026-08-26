(() => {
  "use strict";

  // ---------- Content bank ----------
  // Each entry has a `reason` used for the learning-reinforcement toast —
  // shown whether the player catches it, wrongly whacks it, or misses it.
  const EMAILS = [
    // ---- phishing ----
    { type: "phishing", sender: "IT Support <it-helpdesk@corp-secure-mail.com>", subject: "Your password expires in 1 hour", preview: "Click below to keep access to your account. Failure to act will result in permanent lockout.", reason: "Sender domain isn't your company's — it's a lookalike." },
    { type: "phishing", sender: "PayPa1 Security <service@paypa1-verify.com>", subject: "Unusual sign-in attempt detected", preview: "We noticed a login from a new device. Verify your identity now to avoid suspension.", reason: "Domain uses a '1' instead of 'l' — classic lookalike." },
    { type: "phishing", sender: "Amazon Deliveries <tracking@amaz0n-shipping.net>", subject: "Delivery failed — action required", preview: "Your package couldn't be delivered. Confirm your address within 24 hours or it will be returned.", reason: "'Amazon' misspelled with a zero, plus false urgency." },
    { type: "phishing", sender: "Michael Chen (CEO) <m.chen@corp-outreach.com>", subject: "Quick favor, are you at your desk?", preview: "I'm in meetings all day. Need you to purchase gift cards for a client — I'll explain later.", reason: "CEO-fraud pattern: urgency, secrecy, and an off-company domain." },
    { type: "phishing", sender: "HR Payroll <payroll-update@hr-systems-portal.com>", subject: "Update your direct deposit info", preview: "Our system flagged an issue with your bank details. Log in immediately to avoid a delayed paycheck.", reason: "Real payroll changes don't go through a random third-party domain." },
    { type: "phishing", sender: "Netflix Billing <billing@netflix-account-check.com>", subject: "Your payment method was declined", preview: "Update your billing details now or your membership will be cancelled today.", reason: "Not netflix.com — a domain that just mentions Netflix." },
    { type: "phishing", sender: "Apple Support <noreply@apple-id-locked.com>", subject: "Your Apple ID has been locked", preview: "We detected suspicious activity. Verify your identity within 24 hours to restore access.", reason: "Apple doesn't send account alerts from a non-apple.com domain." },
    { type: "phishing", sender: "DocuSign <no-reply@docusign-secure-files.net>", subject: "You have a document awaiting signature", preview: "Click to review and sign. This link expires in 3 hours.", reason: "Real DocuSign mail comes from docusign.net — this is a decoy domain." },
    { type: "phishing", sender: "Bank Alert <alerts@chase-secure-verify.com>", subject: "Suspicious transaction on your account", preview: "A charge of $842.00 was flagged. If this wasn't you, confirm your login to reverse it.", reason: "Banks don't use side-domains like chase-secure-verify.com." },
    { type: "phishing", sender: "Windows Defender <alert@microsft-support.com>", subject: "Threat detected on your device", preview: "3 viruses found. Call the number below immediately or click to run a free removal tool.", reason: "'Microsoft' is misspelled, and real alerts don't ask you to call a number." },
    { type: "phishing", sender: "Prize Center <winner@sweepstakes-rewards.info>", subject: "You've won a $1,000 gift card!", preview: "Congratulations! Claim your prize within 48 hours by confirming your shipping details.", reason: "Unsolicited prize you never entered — a classic lure." },
    { type: "phishing", sender: "Zoom Meetings <meeting-noreply@zoom-invite-link.com>", subject: "You missed a meeting", preview: "A recording is ready. View it before it's deleted in 24 hours.", reason: "Not zoom.us — and the fake urgency pushes a fast click." },

    // ---- legit ----
    { type: "legit", sender: "GitHub <notifications@github.com>", subject: "[your-org/repo] New pull request opened", preview: "alex-dev opened #482: Fix pagination bug on the reports page.", reason: "Real github.com domain, plain factual subject, no urgency." },
    { type: "legit", sender: "Priya Nair <priya.nair@yourcompany.com>", subject: "Notes from today's standup", preview: "Recapping what we covered — action items are in the doc, due Friday.", reason: "Internal colleague on your real company domain." },
    { type: "legit", sender: "Google Calendar <calendar-notification@google.com>", subject: "Reminder: Design Review at 2:00 PM", preview: "This event starts in 30 minutes. Join with Google Meet.", reason: "Standard calendar reminder from google.com, nothing requested." },
    { type: "legit", sender: "Chase <no.reply.alerts@chase.com>", subject: "Your March statement is ready", preview: "Log in to chase.com anytime to view your latest statement.", reason: "Correct chase.com domain, tells you to go to the site yourself." },
    { type: "legit", sender: "Spotify <no-reply@spotify.com>", subject: "Your 2026 Wrapped is here", preview: "See your top artists and songs from this year.", reason: "Real spotify.com sender, low-stakes content, no action demanded." },
    { type: "legit", sender: "Delta Air Lines <no-reply@delta.com>", subject: "Check-in now open for flight DL 1421", preview: "Your flight departs tomorrow at 7:45 AM from Gate B12.", reason: "Matches a trip you'd recognize, sent from the real delta.com." },
    { type: "legit", sender: "Slack <feedback@slack.com>", subject: "Your weekly workspace summary", preview: "142 messages, 6 new channel invites this week.", reason: "Routine digest from the real slack.com domain." },
    { type: "legit", sender: "Jordan Lee <jordan.lee@yourcompany.com>", subject: "Shared: Q3 budget draft.xlsx", preview: "Left comments on the marketing line items — take a look when you can.", reason: "Coworker, internal domain, describes exactly what's attached." },
    { type: "legit", sender: "Amazon <auto-confirm@amazon.com>", subject: "Your order has shipped", preview: "Arriving Thursday. Track your package anytime in Your Orders.", reason: "Real amazon.com domain, matches an order you actually placed." },
    { type: "legit", sender: "LinkedIn <messages-noreply@linkedin.com>", subject: "You have 3 new profile views", preview: "See who's been checking out your profile this week.", reason: "Low-stakes notification from the genuine linkedin.com." },
  ];

  const PHISHING = EMAILS.filter(e => e.type === "phishing");
  const LEGIT = EMAILS.filter(e => e.type === "legit");

  // ---------- Config ----------
  const HOLE_COUNT = 9;
  const ROUND_SECONDS = 45;
  const STARTING_LIVES = 3;
  const PHISH_SPAWN_BIAS = 0.6; // ~60% of spawns are phishing

  // Difficulty ramps as the round progresses (t: 0 -> 1)
  const SPAWN_DELAY = { start: [650, 1000], end: [350, 600] };  // [min,max] ms between spawns
  const VISIBLE_MS   = { start: 2200, end: 1200 };              // how long a card stays up

  // ---------- State ----------
  let holes = [];
  let usedEmails = [];
  let score = 0, streak = 0, lives = STARTING_LIVES;
  let totalPhishSpawned = 0, correctCatches = 0, wrongClicks = 0, missedPhish = 0;
  let timeLeft = ROUND_SECONDS;
  let roundActive = false;
  let spawnTimeoutId = null, tickIntervalId = null;

  // ---------- DOM ----------
  const gridEl = document.getElementById("grid");
  const scoreEl = document.getElementById("hud-score");
  const streakEl = document.getElementById("hud-streak");
  const timerEl = document.getElementById("hud-timer");
  const livesEl = document.getElementById("hud-lives");
  const overlayStart = document.getElementById("overlay-start");
  const overlayEnd = document.getElementById("overlay-end");
  const endHeading = document.getElementById("end-heading");
  const endRating = document.getElementById("end-rating");
  const endBreakdown = document.getElementById("end-breakdown");
  const endUnlock = document.getElementById("end-unlock");

  function buildGrid() {
    gridEl.innerHTML = "";
    holes = [];
    for (let i = 0; i < HOLE_COUNT; i++) {
      const hole = document.createElement("div");
      hole.className = "hole";
      hole.setAttribute("tabindex", "0");
      hole.setAttribute("role", "button");
      hole.setAttribute("aria-label", "Empty inbox slot");
      const card = document.createElement("div");
      card.className = "card";
      hole.appendChild(card);
      hole.addEventListener("click", () => handleWhack(i));
      hole.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleWhack(i); }
      });
      gridEl.appendChild(hole);
      holes.push({ el: hole, card, occupant: null, expireId: null });
    }
  }

  function lerp(a, b, t) { return a + (b - a) * t; }

  function pickEmail() {
    const wantPhish = Math.random() < PHISH_SPAWN_BIAS;
    const pool = wantPhish ? PHISHING : LEGIT;
    // avoid immediate repeats when possible
    const options = pool.filter(e => !usedEmails.includes(e) || usedEmails.length >= pool.length);
    const choice = options[Math.floor(Math.random() * options.length)] || pool[Math.floor(Math.random() * pool.length)];
    usedEmails.push(choice);
    if (usedEmails.length > 6) usedEmails.shift();
    return choice;
  }

  function emptyHoleIndex() {
    const empties = holes.map((h, i) => h.occupant ? -1 : i).filter(i => i !== -1);
    if (!empties.length) return -1;
    return empties[Math.floor(Math.random() * empties.length)];
  }

  function spawn() {
    if (!roundActive) return;
    const t = 1 - timeLeft / ROUND_SECONDS;
    const idx = emptyHoleIndex();
    if (idx !== -1) {
      const email = pickEmail();
      const hole = holes[idx];
      hole.occupant = email;
      hole.card.innerHTML = `
        <div class="from">${escapeHtml(email.sender)}</div>
        <div class="subject">${escapeHtml(email.subject)}</div>
        <div class="preview">${escapeHtml(email.preview)}</div>`;
      hole.card.className = "card";
      hole.el.setAttribute("aria-label", `Email: ${email.subject}`);
      requestAnimationFrame(() => hole.card.classList.add("up"));

      if (email.type === "phishing") totalPhishSpawned++;

      const visible = lerp(VISIBLE_MS.start, VISIBLE_MS.end, t);
      hole.expireId = setTimeout(() => expire(idx), visible);
    }

    const [dMin, dMax] = [
      lerp(SPAWN_DELAY.start[0], SPAWN_DELAY.end[0], t),
      lerp(SPAWN_DELAY.start[1], SPAWN_DELAY.end[1], t),
    ];
    spawnTimeoutId = setTimeout(spawn, dMin + Math.random() * (dMax - dMin));
  }

  function expire(idx) {
    const hole = holes[idx];
    const email = hole.occupant;
    if (!email) return;
    if (email.type === "phishing") {
      missedPhish++;
      streak = 0;
      showToast(hole, "miss", "MISSED", email.reason);
    }
    clearHole(hole);
  }

  function clearHole(hole) {
    hole.card.classList.remove("up");
    hole.occupant = null;
    hole.el.setAttribute("aria-label", "Empty inbox slot");
    if (hole.expireId) { clearTimeout(hole.expireId); hole.expireId = null; }
  }

  function handleWhack(idx) {
    if (!roundActive) return;
    const hole = holes[idx];
    const email = hole.occupant;
    if (!email) return;

    if (hole.expireId) { clearTimeout(hole.expireId); hole.expireId = null; }

    if (email.type === "phishing") {
      correctCatches++;
      streak++;
      const bonus = Math.min(streak * 2, 20);
      score += 10 + bonus;
      hole.card.classList.add("ring-alert");
      showToast(hole, "alert", "PHISH CAUGHT", email.reason);
    } else {
      wrongClicks++;
      streak = 0;
      lives = Math.max(0, lives - 1);
      score = Math.max(0, score - 15);
      hole.card.classList.add("ring-safe");
      showToast(hole, "safe", "THAT'S LEGIT", email.reason);
    }

    hole.card.classList.add("whacked");
    setTimeout(() => { hole.card.classList.remove("ring-alert", "ring-safe", "whacked"); }, 200);
    clearHole(hole);
    updateHud();

    if (lives <= 0) endRound();
  }

  function showToast(hole, kind, label, reason) {
    const toast = document.createElement("div");
    toast.className = `toast ${kind}`;
    toast.innerHTML = `<strong>${label}</strong>${escapeHtml(reason)}`;
    hole.el.appendChild(toast);
    setTimeout(() => toast.remove(), 1550);
  }

  function updateHud() {
    scoreEl.textContent = score;
    streakEl.textContent = streak;
    timerEl.textContent = timeLeft;
    livesEl.textContent = "\u2665".repeat(lives) + "\u2661".repeat(STARTING_LIVES - lives);
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function startRound() {
    score = 0; streak = 0; lives = STARTING_LIVES;
    totalPhishSpawned = 0; correctCatches = 0; wrongClicks = 0; missedPhish = 0;
    timeLeft = ROUND_SECONDS;
    usedEmails = [];
    buildGrid();
    updateHud();
    overlayStart.classList.add("hidden");
    overlayEnd.classList.add("hidden");
    roundActive = true;

    tickIntervalId = setInterval(() => {
      timeLeft--;
      updateHud();
      if (timeLeft <= 0) endRound();
    }, 1000);

    spawn();
  }

  function endRound() {
    if (!roundActive) return;
    roundActive = false;
    clearTimeout(spawnTimeoutId);
    clearInterval(tickIntervalId);
    holes.forEach(h => { if (h.expireId) clearTimeout(h.expireId); });

    const rating = computeRating();
    renderEndScreen(rating, { pending: true });
    submitScore(rating).then(res => renderEndScreen(rating, res));
  }

  function computeRating() {
    if (totalPhishSpawned === 0) return 0;
    const accuracy = Math.round((correctCatches / totalPhishSpawned) * 100);
    return Math.max(0, Math.min(100, accuracy - wrongClicks * 10));
  }

  function renderEndScreen(rating, result) {
    overlayEnd.classList.remove("hidden");
    endHeading.textContent = lives <= 0 ? "INBOX COMPROMISED" : "ROUND OVER";
    endRating.textContent = rating;
    endRating.className = "rating " + (rating >= 80 ? "pass" : "fail");
    endBreakdown.textContent =
      `${correctCatches}/${totalPhishSpawned} phishing emails caught \u2022 ` +
      `${wrongClicks} legit email(s) wrongly whacked \u2022 ${missedPhish} missed`;

    if (result.pending) {
      endUnlock.textContent = "Submitting score\u2026";
      endUnlock.className = "unlock-msg";
      return;
    }

    if (result.already_completed) {
      endUnlock.textContent = "Already played before \u2014 no additional XP awarded, but great practice!";
      endUnlock.className = "unlock-msg";
    } else if (result.xp_awarded) {
      let msg = `\u2713 +${result.xp_awarded} XP earned!`;
      if (result.leveled_up) msg += ` Level up \u2014 you're now Level ${result.new_level}!`;
      endUnlock.textContent = msg;
      endUnlock.className = "unlock-msg pass";
    } else {
      endUnlock.textContent = "No XP this round \u2014 catch more phishing emails to earn XP!";
      endUnlock.className = "unlock-msg fail";
    }
  }

  function getCsrfToken() {
    // Django renders a hidden {% csrf_token %} input on the page (see
    // whack_a_phish.html) -- grab its value to include in the POST below.
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  async function submitScore(score) {
    try {
      const res = await fetch("/games/whack-a-phish/submit-score/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        body: JSON.stringify({ score }),
      });
      if (!res.ok) throw new Error("bad response");
      return await res.json();
    } catch (err) {
      // Fall back to a client-only check if the backend call fails
      return { unlocked_level_2: score >= 80 };
    }
  }

  document.getElementById("btn-start").addEventListener("click", startRound);
  document.getElementById("btn-retry").addEventListener("click", startRound);

  buildGrid();
})();
