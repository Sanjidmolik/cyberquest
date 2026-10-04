/*
  Course reader page turning.

  react-pageflip 2.0.3 does not run by itself in this Django page: its
  build is a React wrapper whose effect is:

      pageFlip = new PageFlip(element, props);
      pageFlip.loadFromHTML(pageElements);

  That PageFlip class is the page-flip build (courses/js/vendor), exposed in
  the browser as St.PageFlip. This file uses that same constructor and
  loadFromHTML call.

  Course text and PDF pages still come from the existing course record.
*/
(function () {
    "use strict";

    /* Every visit opens on the first page. Set this to false if you ever want
       readers to resume where they stopped (uses the saved page from the server). */
    const START_AT_FIRST_PAGE = true;

    /* The template declares `const READER_CONFIG = {...}`. A top-level `const`
       is visible by name but is NOT a property of `window`, so it must be read
       by name (falling back to window for a `var`/window assignment). */
    const cfg = (typeof READER_CONFIG !== "undefined") ? READER_CONFIG : window.READER_CONFIG;
    if (!cfg) {
        console.error("CyberQuest reader: READER_CONFIG is missing, so the book cannot start.");
        return;
    }

    const bookEl = document.getElementById("book");
    const prevBtn = document.getElementById("prev-btn");
    const nextBtn = document.getElementById("next-btn");
    const pageIndicator = document.getElementById("page-indicator");
    const progressFill = document.getElementById("reader-progress-fill");
    const completeBtn = document.getElementById("complete-btn");
    const loadingEl = document.getElementById("reader-loading");
    const errorEl = document.getElementById("reader-error");
    const stageEl = document.getElementById("reader-stage");
    const fullBtn = document.getElementById("fullscreen-btn");
    const fontBtns = [document.getElementById("font-decrease"), document.getElementById("font-increase")];
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* localStorage can throw (private mode, blocked cookies): never let that break the reader. */
    const store = {
        get: function (key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } },
        set: function (key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* ignore */ } },
    };

    const TEXT_RATIO = 460 / 640;   // width / height of one text page
    const MIN_PAGE_W = 340;         // narrower than this and a two-page spread becomes one page

    let pageRatio = TEXT_RATIO;
    let pageFlip = null;
    let totalPages = 1;
    let reachedEnd = cfg.alreadyDone;
    let paginationKey = "";

    function showError() {
        if (loadingEl) loadingEl.hidden = true;
        if (stageEl) stageEl.hidden = true;
        if (errorEl) errorEl.hidden = false;
    }

    /* ---------------------------------------------------------------
       Sizing: make the book as large as the screen allows
       --------------------------------------------------------------- */
    function computeLayout() {
        const narrow = window.matchMedia("(max-width: 700px)").matches;
        const gutter = narrow ? 34 : 64;              // room for the arrow buttons
        const styles = window.getComputedStyle(stageEl);
        const padY = (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0);
        const availW = Math.max(200, stageEl.clientWidth - gutter * 2);
        const availH = Math.max(200, stageEl.clientHeight - padY);

        let pageH = Math.min(availH, availW / 2 / pageRatio);
        let pageW = pageH * pageRatio;
        const spread = availW >= MIN_PAGE_W * 2 && pageW >= MIN_PAGE_W;
        if (!spread) {
            pageH = Math.min(availH, availW / pageRatio);
            pageW = pageH * pageRatio;
        }
        pageW = Math.floor(pageW);
        pageH = Math.floor(pageH);
        return { spread: spread, pageW: pageW, pageH: pageH, bookW: spread ? pageW * 2 : pageW };
    }

    function applyLayout() {
        const layout = computeLayout();
        bookEl.style.width = layout.bookW + "px";
        bookEl.style.height = layout.pageH + "px";
        bookEl.style.minWidth = "0";
        bookEl.style.minHeight = "0";
        bookEl.style.maxWidth = "none";
        return layout;
    }

    function pageShell(inner, number, total, extra) {
        const page = document.createElement("div");
        page.className = "cq-sheet";
        if (extra) page.dataset.density = extra;
        page.innerHTML =
            '<header class="cq-sheet-label">' + cfg.chapterLabel + "</header>" +
            inner +
            '<footer class="cq-sheet-foot">Page ' + number + " of " + total + "</footer>";
        return page;
    }

    function pdfSheet(inner) {
        const page = document.createElement("div");
        page.className = "cq-sheet cq-pdf-sheet";
        page.innerHTML = inner;
        return page;
    }

    /* ---------------------------------------------------------------
       Text courses
       --------------------------------------------------------------- */
    function paginateText(pageW, pageH) {
        const source = document.getElementById("raw-course-content");
        const blocks = source ? Array.from(source.children) : [];
        const measurer = document.createElement("div");
        measurer.className = "cq-sheet cq-measurer";
        measurer.style.width = pageW + "px";
        measurer.style.height = pageH + "px";
        document.body.appendChild(measurer);

        /* Measure with the same label and footer a real page has, so the text
           that "fits" really fits and pages never need a scrollbar. */
        const head = '<header class="cq-sheet-label">' + cfg.chapterLabel + "</header>";
        const foot = '<footer class="cq-sheet-foot">Page 000 of 000</footer>';
        const max = measurer.clientHeight;
        const pages = [];
        let current = "";

        function fits(html) {
            measurer.innerHTML = head + html + foot;
            return measurer.scrollHeight <= max + 1;
        }

        blocks.forEach(function (block) {
            const candidate = current + block.outerHTML;
            if (fits(candidate)) {
                current = candidate;
            } else if (!current) {
                const words = block.textContent.split(/\s+/);
                let chunk = "";
                words.forEach(function (word) {
                    const next = (chunk + " " + word).trim();
                    if (fits("<p>" + next + "</p>")) chunk = next;
                    else {
                        if (chunk) pages.push("<p>" + chunk + "</p>");
                        chunk = word;
                    }
                });
                current = chunk ? "<p>" + chunk + "</p>" : "";
            } else {
                pages.push(current);
                current = block.outerHTML;
            }
        });
        if (current) pages.push(current);
        measurer.remove();
        return pages.length ? pages : ["<p>No content available yet.</p>"];
    }

    function currentKey(layout) {
        const size = window.getComputedStyle(document.documentElement).getPropertyValue("--reader-font-size");
        return layout.pageW + "x" + layout.pageH + "@" + (size || "").trim();
    }

    /* Text pages are cut to fit the page size and font size, so they must be
       cut again when either changes (window resize, full screen, A+ / A-). */
    function repaginate() {
        if (!pageFlip || cfg.usesPdf) return;
        const layout = computeLayout();
        const key = currentKey(layout);
        if (key === paginationKey) return;
        paginationKey = key;

        const oldTotal = totalPages;
        const current = pageFlip.getCurrentPageIndex();
        const nodes = buildNodes(paginateText(layout.pageW, layout.pageH));
        pageFlip.updateFromHtml(nodes);
        totalPages = pageFlip.getPageCount();
        const target = oldTotal > 1 ? Math.round(current / (oldTotal - 1) * (totalPages - 1)) : 0;
        applyLayout();
        pageFlip.update();
        if (target !== pageFlip.getCurrentPageIndex()) pageFlip.turnToPage(target);
        updateUi(pageFlip.getCurrentPageIndex());
    }

    /* ---------------------------------------------------------------
       PDF courses: sharp pages, shown as soon as the first spread is ready
       --------------------------------------------------------------- */
    async function openPdf() {
        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        const doc = await pdfjsLib.getDocument({
            url: cfg.pdfUrl,
            standardFontDataUrl: "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/standard_fonts/",
        }).promise;
        const first = await doc.getPage(1);
        const base = first.getViewport({ scale: 1 });
        return { doc: doc, ratio: base.width / base.height };
    }

    /* Render big enough for full screen on this display, so text stays crisp. */
    function renderTargetWidth(layout) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const biggest = Math.max(layout.pageW, Math.round(window.screen.height * pageRatio));
        return Math.max(700, Math.min(1500, Math.round(biggest * dpr)));
    }

    async function renderPdfPage(doc, n, width) {
        const page = await doc.getPage(n);
        const base = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: width / base.width });
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        await page.render({ canvasContext: ctx, viewport: viewport }).promise;
        const blob = await new Promise(function (resolve) { canvas.toBlob(resolve, "image/jpeg", 0.92); });
        canvas.width = 0;
        canvas.height = 0;
        page.cleanup();
        return URL.createObjectURL(blob);
    }

    async function fillPdfPage(doc, n, width, img) {
        try {
            img.src = await renderPdfPage(doc, n, width);
            img.parentNode.classList.add("is-ready");
        } catch (err) {
            console.warn("CyberQuest reader: could not draw PDF page " + n, err);
        }
    }

    /* ---------------------------------------------------------------
       Book building
       --------------------------------------------------------------- */
    function buildNodes(parts) {
        const total = parts.length + 1;
        const cover = pageShell(
            "<h1>" + cfg.courseTitle + "</h1><p>" + (cfg.shortDescription || "") + "</p>",
            1,
            total,
            "hard"
        );
        const body = parts.map(function (html, index) {
            const last = index === parts.length - 1;
            if (cfg.usesPdf) {
                const sheet = pdfSheet(html);
                if (last && cfg.practiceUrl) {
                    sheet.insertAdjacentHTML(
                        "beforeend",
                        '<p class="cq-practice cq-practice-float"><a class="reader-complete-btn" href="' + cfg.practiceUrl + '">Start Practice</a></p>'
                    );
                }
                return sheet;
            }
            let bodyHtml = html;
            if (last && cfg.practiceUrl) {
                bodyHtml += '<p class="cq-practice"><a class="reader-complete-btn" href="' + cfg.practiceUrl + '">Start Practice</a></p>';
            }
            return pageShell(bodyHtml, index + 2, total, "");
        });
        return [cover].concat(body);
    }

    /* In two-page (landscape) mode page-flip reports the LEFT page of the spread,
       but the right page (index + 1) is on screen too. The last page counts as
       reached as soon as it is visible, otherwise a book with an even number of
       body pages could never be completed on desktop. */
    function lastVisibleIndex(index) {
        const spread = pageFlip && pageFlip.getOrientation() === "landscape";
        return spread && index > 0 ? Math.min(index + 1, totalPages - 1) : index;
    }

    function updateUi(index) {
        totalPages = pageFlip ? pageFlip.getPageCount() : totalPages;
        const current = Math.min(index, totalPages - 1);
        const seen = lastVisibleIndex(current);
        pageIndicator.textContent = seen > current
            ? "Pages " + (current + 1) + "\u2013" + (seen + 1) + " of " + totalPages
            : "Page " + (current + 1) + " of " + totalPages;
        progressFill.style.width = ((seen + 1) / totalPages) * 100 + "%";
        prevBtn.disabled = current <= 0;
        nextBtn.disabled = seen >= totalPages - 1;
        if (seen >= totalPages - 1) reachedEnd = true;
        if (reachedEnd && !cfg.alreadyDone) {
            completeBtn.disabled = false;
            completeBtn.textContent = "Mark Course Complete";
        }
    }

    let saveTimer = null;
    function saveProgress(index) {
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(function () {
            fetch(cfg.saveProgressUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrfToken },
                body: JSON.stringify({ page_index: index }),
            }).catch(function () {});
        }, 400);
    }

    function relayout() {
        if (!pageFlip) return;
        applyLayout();
        pageFlip.update();
        repaginate();
    }

    function mount(nodes) {
        bookEl.style.visibility = "hidden";
        nodes.forEach(function (node) { bookEl.appendChild(node); });
        if (typeof St === "undefined" || !St.PageFlip) {
            throw new Error("page flip engine missing");
        }
        pageFlip = new St.PageFlip(bookEl, {
            /* With size "stretch" these two numbers only set the page shape;
               applyLayout() below sets the real, screen-filling size. */
            width: Math.round(pageRatio * 1000),
            height: 1000,
            size: "stretch",
            minWidth: MIN_PAGE_W,
            maxWidth: 4000,
            minHeight: 200,
            maxHeight: 4000,
            showCover: true,
            usePortrait: true,
            mobileScrollSupport: true,
            flippingTime: reduced ? 1 : 700,
            useMouseEvents: true,
            drawShadow: !reduced,
            maxShadowOpacity: 0.35,
            swipeDistance: 30,
            clickEventForward: true,
            startPage: START_AT_FIRST_PAGE ? 0 : Math.min(cfg.resumePageIndex || 0, nodes.length - 1),
        });
        pageFlip.loadFromHTML(nodes);
        applyLayout();
        pageFlip.update();
        bookEl.style.visibility = "";

        pageFlip.on("flip", function (event) {
            updateUi(event.data);
            saveProgress(event.data);
        });
        pageFlip.on("changeOrientation", function () {
            updateUi(pageFlip.getCurrentPageIndex());
        });
        updateUi(pageFlip.getCurrentPageIndex());
        prevBtn.addEventListener("click", function () { pageFlip.flipPrev(); });
        nextBtn.addEventListener("click", function () { pageFlip.flipNext(); });
        document.addEventListener("keydown", function (event) {
            if (event.ctrlKey || event.metaKey || event.altKey) return;
            if (event.key === "ArrowRight") pageFlip.flipNext();
            else if (event.key === "ArrowLeft") pageFlip.flipPrev();
            else if (event.key === "f" || event.key === "F") toggleFullscreen();
        });

        let resizeTimer = null;
        window.addEventListener("resize", function () {
            if (!pageFlip) return;
            applyLayout();
            pageFlip.update();
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(relayout, 200);
        });
    }

    /* ---------------------------------------------------------------
       Full screen
       --------------------------------------------------------------- */
    function fullscreenSupported() {
        return !!(document.fullscreenEnabled && document.documentElement.requestFullscreen);
    }

    function toggleFullscreen() {
        if (!fullscreenSupported()) return;
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            document.documentElement.requestFullscreen().catch(function () {});
        }
    }

    function syncFullscreenBtn() {
        if (!fullBtn) return;
        const on = !!document.fullscreenElement;
        fullBtn.textContent = on ? "Exit full screen" : "Full screen";
        fullBtn.setAttribute("aria-pressed", on ? "true" : "false");
    }

    if (fullBtn) {
        if (fullscreenSupported()) {
            fullBtn.addEventListener("click", toggleFullscreen);
            document.addEventListener("fullscreenchange", function () {
                syncFullscreenBtn();
                window.setTimeout(relayout, 150);
            });
            syncFullscreenBtn();
        } else {
            fullBtn.hidden = true;
        }
    }

    /* ---------------------------------------------------------------
       Controls
       --------------------------------------------------------------- */
    completeBtn.addEventListener("click", async function () {
        if (completeBtn.disabled) return;
        try {
            const res = await fetch(cfg.completeUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrfToken },
                body: JSON.stringify({
                    pages_reached: pageFlip ? lastVisibleIndex(pageFlip.getCurrentPageIndex()) : 0,
                    total_pages: pageFlip ? pageFlip.getPageCount() : 1,
                }),
            });
            const data = await res.json();
            if (res.ok) {
                completeBtn.textContent = "✔ Course Complete!";
                completeBtn.disabled = true;
                if (data.new_badges && data.new_badges.length) {
                    window.alert("New badge unlocked: " + data.new_badges.join(", "));
                }
            } else {
                window.alert(data.error || "Could not mark complete yet.");
            }
        } catch (err) {
            window.alert("Something went wrong saving your progress. Please try again.");
        }
    });

    document.getElementById("try-again").addEventListener("click", function () {
        window.location.reload();
    });

    /* A- / A+ resize the text of text courses. PDF pages are pictures, so the
       buttons would do nothing there: hide them instead of leaving dead buttons. */
    if (cfg.usesPdf) {
        fontBtns.forEach(function (btn) { if (btn) btn.hidden = true; });
    } else {
        document.getElementById("font-increase").addEventListener("click", function () { changeFont(2); });
        document.getElementById("font-decrease").addEventListener("click", function () { changeFont(-2); });
    }

    function changeFont(delta) {
        const current = parseInt(window.getComputedStyle(document.documentElement).getPropertyValue("--reader-font-size"), 10) || 18;
        const next = Math.max(14, Math.min(28, current + delta));
        if (next === current) return;
        document.documentElement.style.setProperty("--reader-font-size", next + "px");
        store.set("cq_reader_font_size", String(next));
        repaginate();
    }

    const themeBtns = Array.from(document.querySelectorAll(".theme-btn"));
    themeBtns.forEach(function (btn) {
        btn.addEventListener("click", function () { setTheme(btn.dataset.theme); });
    });

    function setTheme(theme) {
        if (["light", "sepia", "dark"].indexOf(theme) === -1) theme = "light";
        document.body.className = "theme-" + theme;
        themeBtns.forEach(function (btn) {
            const on = btn.dataset.theme === theme;
            btn.classList.toggle("active", on);
            btn.setAttribute("aria-pressed", on ? "true" : "false");
        });
        store.set("cq_reader_theme", theme);
    }

    /* ---------------------------------------------------------------
       Start
       --------------------------------------------------------------- */
    async function init() {
        setTheme(store.get("cq_reader_theme") || "light");
        const savedSize = store.get("cq_reader_font_size");
        if (savedSize) document.documentElement.style.setProperty("--reader-font-size", savedSize + "px");
        try {
            if (cfg.usesPdf) {
                const pdf = await openPdf();
                pageRatio = pdf.ratio;
                const layout = computeLayout();
                const width = renderTargetWidth(layout);
                const parts = Array.from({ length: pdf.doc.numPages }, function (_, i) {
                    return '<img class="cq-pdf-page-img" alt="Course page ' + (i + 1) + '" draggable="false">';
                });
                const nodes = buildNodes(parts);
                const imgs = nodes.slice(1).map(function (node) { return node.querySelector("img"); });
                const firstBatch = Math.min(2, imgs.length);
                for (let n = 1; n <= firstBatch; n += 1) await fillPdfPage(pdf.doc, n, width, imgs[n - 1]);
                mount(nodes);
                if (loadingEl) loadingEl.hidden = true;
                /* The rest of the pages draw quietly while the reader starts. */
                for (let n = firstBatch + 1; n <= imgs.length; n += 1) await fillPdfPage(pdf.doc, n, width, imgs[n - 1]);
            } else {
                pageRatio = TEXT_RATIO;
                const layout = computeLayout();
                paginationKey = currentKey(layout);
                mount(buildNodes(paginateText(layout.pageW, layout.pageH)));
                if (loadingEl) loadingEl.hidden = true;
            }
        } catch (err) {
            console.error("CyberQuest reader failed to start:", err);
            showError();
        }
    }

    init();
})();
