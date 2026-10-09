/*
  dashboard/static/dashboard/js/dashboard.js
  -----------------------------------------------
  - Mobile sidebar toggle
  - Homepage-compatible dark/light theme (cq_home_theme)
  - Sidebar active state for hash links + press feedback
  - Mission card pointer glow (homepage-style)
*/

document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("sidebar");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", function () {
            sidebar.classList.toggle("open");
            sidebar.style.transform = sidebar.classList.contains("open") ? "translateX(0)" : "";
        });

        document.addEventListener("click", function (e) {
            const clickedInsideSidebar = sidebar.contains(e.target);
            const clickedToggle = toggleBtn.contains(e.target);
            if (sidebar.classList.contains("open") && !clickedInsideSidebar && !clickedToggle) {
                sidebar.classList.remove("open");
                sidebar.style.transform = "";
            }
        });
    }

    /* ---------- Theme (same key + behaviour as homepage) ---------- */
    const KEY = "cq_home_theme";
    const COLORS = { dark: "#701fd3", light: "#f7f1ff" };
    const root = document.documentElement;
    const themeBtn = document.getElementById("themeToggle");
    const meta = document.querySelector('meta[name="theme-color"]');

    function current() {
        return root.getAttribute("data-theme") === "light" ? "light" : "dark";
    }

    function sync() {
        const t = current();
        root.setAttribute("data-theme", t);
        if (meta) meta.setAttribute("content", COLORS[t]);
        if (themeBtn) {
            const label = t === "dark" ? "Switch to day mode" : "Switch to dark mode";
            themeBtn.setAttribute("aria-label", label);
            themeBtn.title = label;
        }
    }

    function apply(t) {
        root.setAttribute("data-theme", t === "light" ? "light" : "dark");
        try { localStorage.setItem(KEY, t === "light" ? "light" : "dark"); } catch (e) {}
        sync();
    }

    function switchTo(next, x, y) {
        if (reduced) {
            apply(next);
            return;
        }
        if (document.startViewTransition) {
            const radius = Math.hypot(
                Math.max(x, window.innerWidth - x),
                Math.max(y, window.innerHeight - y)
            );
            const vt = document.startViewTransition(function () { apply(next); });
            vt.ready.then(function () {
                root.animate(
                    {
                        clipPath: [
                            "circle(0px at " + x + "px " + y + "px)",
                            "circle(" + radius + "px at " + x + "px " + y + "px)",
                        ],
                    },
                    {
                        duration: 700,
                        easing: "cubic-bezier(.2,.8,.2,1)",
                        pseudoElement: "::view-transition-new(root)",
                    }
                );
            }).catch(function () {});
            return;
        }
        root.classList.add("theme-fade");
        apply(next);
        window.setTimeout(function () { root.classList.remove("theme-fade"); }, 500);
    }

    if (themeBtn) {
        themeBtn.addEventListener("click", function () {
            const r = themeBtn.getBoundingClientRect();
            switchTo(
                current() === "dark" ? "light" : "dark",
                r.left + r.width / 2,
                r.top + r.height / 2
            );
        });
    }
    window.addEventListener("storage", function (e) {
        if (e.key === KEY && (e.newValue === "light" || e.newValue === "dark")) {
            root.setAttribute("data-theme", e.newValue);
            sync();
        }
    });
    sync();

    /* ---------- Sidebar press + in-dashboard section focus ---------- */
    const navItems = document.querySelectorAll(".sidebar-nav .nav-item[data-nav]");
    const sectionOrder = [
        { id: "overview", nav: "overview" },
        { id: "active-missions", nav: "missions" },
        { id: "skill-matrix", nav: "progress" },
    ];
    const onDashboardHome = !!document.getElementById("overview") && !!document.getElementById("active-missions");
    let lockObserver = false;

    function setDashActive(nav) {
        sectionOrder.forEach(function (entry) {
            const item = document.querySelector('.sidebar-nav .nav-item[data-nav="' + entry.nav + '"]');
            if (!item) return;
            const on = entry.nav === nav;
            item.classList.toggle("active", on);
            if (on) item.setAttribute("aria-current", "true");
            else item.removeAttribute("aria-current");
        });
    }

    function pulseSection(el, revealMissions) {
        if (!el) return;
        el.classList.remove("is-focused");
        if (!reduced) {
            void el.offsetWidth;
            el.classList.add("is-focused");
            window.setTimeout(function () { el.classList.remove("is-focused"); }, 1200);
        }
        if (revealMissions && !reduced) {
            const row = el.querySelector(".missions-row");
            if (row && !row.dataset.revealed) {
                row.dataset.revealed = "1";
                row.classList.add("is-revealing");
            }
        }
    }

    function focusSection(id, updateHash) {
        const entry = sectionOrder.filter(function (item) { return item.id === id; })[0];
        const el = document.getElementById(id);
        if (!entry || !el) return;
        setDashActive(entry.nav);
        const top = id === "overview" ? 0 : Math.max(0, el.getBoundingClientRect().top + window.scrollY - 84);
        lockObserver = true;
        window.scrollTo({ top: top, behavior: reduced ? "auto" : "smooth" });
        if (updateHash) {
            const next = "#" + id;
            if (window.location.hash !== next) {
                history.pushState(null, "", next);
            }
        }
        pulseSection(el, id === "active-missions");
        window.setTimeout(function () { lockObserver = false; }, reduced ? 0 : 700);
        if (sidebar && sidebar.classList.contains("open")) {
            sidebar.classList.remove("open");
            sidebar.style.transform = "";
        }
    }

    navItems.forEach(function (item) {
        item.addEventListener("click", function () {
            item.classList.add("nav-item-press");
            window.setTimeout(function () {
                item.classList.remove("nav-item-press");
            }, reduced ? 0 : 280);
        });
    });

    if (onDashboardHome) {
        document.querySelectorAll(".sidebar-nav .nav-item[data-section]").forEach(function (link) {
            link.addEventListener("click", function (event) {
                const id = link.getAttribute("data-section");
                if (!document.getElementById(id)) return;
                event.preventDefault();
                focusSection(id, true);
            });
        });

        if ("IntersectionObserver" in window) {
            const seen = new Map();
            const observer = new IntersectionObserver(function (entries) {
                if (lockObserver) return;
                entries.forEach(function (entry) {
                    seen.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0);
                });
                let best = "overview";
                let bestRatio = 0;
                sectionOrder.forEach(function (item) {
                    const ratio = seen.get(item.id) || 0;
                    if (ratio > bestRatio) {
                        bestRatio = ratio;
                        best = item.nav;
                    }
                });
                if (bestRatio > 0) setDashActive(best);
            }, { rootMargin: "-20% 0px -45% 0px", threshold: [0.15, 0.35, 0.6] });
            sectionOrder.forEach(function (item) {
                const el = document.getElementById(item.id);
                if (el) observer.observe(el);
            });
        }

        const initial = (window.location.hash || "").replace("#", "");
        if (initial && document.getElementById(initial)) {
            window.setTimeout(function () { focusSection(initial, false); }, 60);
        }
        window.addEventListener("hashchange", function () {
            const id = (window.location.hash || "").replace("#", "");
            if (document.getElementById(id)) focusSection(id, false);
        });
    }

    const commandReturn = document.querySelector(".cc-return");
    if (commandReturn) {
        commandReturn.addEventListener("pointerdown", function () {
            commandReturn.classList.add("is-pressed");
        });
    }

    /* ---------- Mission cards: homepage-style pointer glow ---------- */
    document.querySelectorAll(".mission-card").forEach(function (card) {
        if (card.classList.contains("mission-soon")) return;
        card.addEventListener("pointermove", function (e) {
            if (reduced) return;
            const r = card.getBoundingClientRect();
            card.style.setProperty("--mx", (e.clientX - r.left) + "px");
            card.style.setProperty("--my", (e.clientY - r.top) + "px");
        });
        card.addEventListener("click", function () {
            if (card.classList.contains("mission-locked") || card.classList.contains("mission-soon")) return;
            card.classList.add("mission-card-press");
        });
    });
});
