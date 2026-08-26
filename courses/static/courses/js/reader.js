/*
  courses/static/courses/js/reader.js
  ---------------------------------------
  Powers the book-style course reader for BOTH content types:
    - Plain text courses: this file paginates the content into
      screen-sized "pages" on the fly (re-paginates on font size change).
    - PDF e-book courses: this file renders each PDF page onto a canvas
      via PDF.js, on demand, and treats each rendered canvas as a page.

  Either way, from here down everything (flipping, progress bar, page
  counter, resuming, marking complete) works identically -- the two
  content types are unified behind one `getPageContent(index)` function.
*/

(function () {
    "use strict";

    const cfg = READER_CONFIG;

    // ---- DOM references ----
    const pageCurrentEl = document.getElementById("page-current");
    const pageIncomingEl = document.getElementById("page-incoming");
    const prevBtn = document.getElementById("prev-btn");
    const nextBtn = document.getElementById("next-btn");
    const pageIndicator = document.getElementById("page-indicator");
    const progressFill = document.getElementById("reader-progress-fill");
    const completeBtn = document.getElementById("complete-btn");

    let currentIndex = 0;
    let totalPages = 1;
    let textPages = [];       // used when !cfg.usesPdf
    let pdfDoc = null;        // used when cfg.usesPdf
    let pdfPageCache = {};    // pageIndex -> rendered canvas (cloned on use)
    let hasReachedEnd = cfg.alreadyDone;

    // ============================================================
    // TEXT PAGINATION (only used for plain-text courses)
    // ============================================================
    function paginateText() {
        const source = document.getElementById("raw-course-content");
        if (!source) { textPages = ["<p>No content available yet.</p>"]; return; }

        // A hidden measuring box with the SAME size/padding/font as a real
        // page, so we can find exactly how much content fits per page.
        const measurer = document.createElement("div");
        measurer.style.cssText = window.getComputedStyle(pageCurrentEl).cssText;
        measurer.style.position = "absolute";
        measurer.style.visibility = "hidden";
        measurer.style.height = pageCurrentEl.clientHeight + "px";
        measurer.style.width = pageCurrentEl.clientWidth + "px";
        measurer.style.overflow = "hidden";
        document.body.appendChild(measurer);

        const maxHeight = pageCurrentEl.clientHeight;
        const blocks = Array.from(source.children).length ? Array.from(source.children) : [source];

        const pages = [];
        let currentPageHTML = "";

        function fits(html) {
            measurer.innerHTML = html;
            return measurer.scrollHeight <= maxHeight;
        }

        blocks.forEach((block) => {
            const candidate = currentPageHTML + block.outerHTML;
            if (fits(candidate)) {
                currentPageHTML = candidate;
            } else if (currentPageHTML === "") {
                // A single block alone is too tall (long paragraph) --
                // split it word by word so nothing gets lost.
                const words = block.textContent.split(" ");
                let chunk = "";
                words.forEach((word) => {
                    const testChunk = chunk + word + " ";
                    if (fits(`<p>${testChunk}</p>`)) {
                        chunk = testChunk;
                    } else {
                        pages.push(`<p>${chunk}</p>`);
                        chunk = word + " ";
                    }
                });
                currentPageHTML = `<p>${chunk}</p>`;
            } else {
                pages.push(currentPageHTML);
                currentPageHTML = block.outerHTML;
            }
        });
        if (currentPageHTML) pages.push(currentPageHTML);

        document.body.removeChild(measurer);
        textPages = pages.length ? pages : ["<p>No content available yet.</p>"];
    }

    // ============================================================
    // PDF RENDERING (only used for PDF e-book courses)
    // ============================================================
    async function loadPdf() {
        pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        pdfDoc = await pdfjsLib.getDocument({
             url: cfg.pdfUrl,
            standardFontDataUrl: "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/standard_fonts/",
        }).promise;
        totalPages = pdfDoc.numPages;
    }

       async function renderPdfPage(index) {
        // IMPORTANT: we cache a data URL (not the canvas element itself).
        // Cloning or re-serializing a <canvas> node does NOT preserve its
        // drawn pixel content -- only the empty tag/dimensions survive.
        // An <img> built from a cached data URL has no such problem.
        if (pdfPageCache[index]) {
            const img = document.createElement("img");
            img.src = pdfPageCache[index];
            img.className = "cq-pdf-page-img";
            return img;
        }

        const pageNumber = index + 1; // PDF.js pages are 1-indexed
        const page = await pdfDoc.getPage(pageNumber);
        const containerWidth = pageCurrentEl.clientWidth - 92; // minus page padding
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = containerWidth / baseViewport.width;
        const viewport = page.getViewport({ scale });

        const canvas = document.createElement("canvas");
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;

        pdfPageCache[index] = canvas.toDataURL();

        const img = document.createElement("img");
        img.src = pdfPageCache[index];
        img.className = "cq-pdf-page-img";
        return img;
    }

    // ============================================================
    // UNIFIED PAGE ACCESS
    // ============================================================
    async function getPageContent(index) {
        if (cfg.usesPdf) {
            return await renderPdfPage(index);
        }
        return textPages[index] || "";
    }

    // ============================================================
    // UNIFIED PAGE ACCESS
    // ============================================================
    async function getPageContent(index) {
        if (cfg.usesPdf) {
            const canvas = await renderPdfPage(index);
            const wrapper = document.createElement("div");
            wrapper.appendChild(canvas);
            return wrapper.innerHTML === "" ? "" : wrapper;
        }
        return textPages[index] || "";
    }

    function setElementContent(el, content) {
        if (content instanceof HTMLElement) {
            el.innerHTML = "";
            el.appendChild(content);
        } else {
            el.innerHTML = content;
        }
    }

    // ============================================================
    // NAVIGATION + FLIP ANIMATION
    // ============================================================
    async function renderCurrentPage() {
        const content = await getPageContent(currentIndex);
        setElementContent(pageCurrentEl, content);
        updateUI();
        saveProgress();
    }

    function updateUI() {
        pageIndicator.textContent = `Page ${currentIndex + 1} of ${totalPages}`;
        progressFill.style.width = `${((currentIndex + 1) / totalPages) * 100}%`;
        prevBtn.disabled = currentIndex === 0;
        nextBtn.disabled = currentIndex === totalPages - 1;

        if (currentIndex === totalPages - 1) {
            hasReachedEnd = true;
        }
        if (hasReachedEnd) {
            completeBtn.disabled = cfg.alreadyDone; // stays enabled unless already done
            if (!cfg.alreadyDone) completeBtn.textContent = "Mark Course Complete";
        }
    }

    async function goToPage(newIndex, direction) {
        if (newIndex < 0 || newIndex >= totalPages || newIndex === currentIndex) return;

        // Pre-render the incoming page's content BEFORE animating, so it's
        // ready and waiting underneath the moment it's revealed.
        const incomingContent = await getPageContent(newIndex);
        setElementContent(pageIncomingEl, incomingContent);

        pageCurrentEl.classList.add(direction === "next" ? "flipping-next" : "flipping-prev");

        function handler(e) {
            // transform AND opacity transition together -- only act once,
            // on whichever fires, but ignore the first if a second is coming.
            if (e.propertyName !== "transform") return;
            pageCurrentEl.removeEventListener("transitionend", handler);

            currentIndex = newIndex;

            // Reuse the content we already rendered above instead of
            // re-fetching it -- and reset the flip rotation WITHOUT
            // animating the reset itself (only the deliberate turn should
            // ever animate; otherwise removing the class plays the flip
            // backwards first, which is the "flash" you were seeing).
            pageCurrentEl.style.transition = "none";
            setElementContent(pageCurrentEl, incomingContent);
            pageCurrentEl.classList.remove("flipping-next", "flipping-prev");
            pageCurrentEl.offsetHeight; // force a reflow so the transition:none actually takes effect
            pageCurrentEl.style.transition = "";

            updateUI();
            saveProgress();
        }

        pageCurrentEl.addEventListener("transitionend", handler);
    }

    nextBtn.addEventListener("click", () => goToPage(currentIndex + 1, "next"));
    prevBtn.addEventListener("click", () => goToPage(currentIndex - 1, "prev"));

    document.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight") goToPage(currentIndex + 1, "next");
        if (e.key === "ArrowLeft") goToPage(currentIndex - 1, "prev");
    });

    // Simple swipe support for touch devices
    let touchStartX = null;
    document.getElementById("book").addEventListener("touchstart", (e) => {
        touchStartX = e.touches[0].clientX;
    });
    document.getElementById("book").addEventListener("touchend", (e) => {
        if (touchStartX === null) return;
        const deltaX = e.changedTouches[0].clientX - touchStartX;
        if (Math.abs(deltaX) > 50) {
            if (deltaX < 0) goToPage(currentIndex + 1, "next");
            else goToPage(currentIndex - 1, "prev");
        }
        touchStartX = null;
    });

    // ============================================================
    // FONT SIZE + THEME CONTROLS
    // ============================================================
    document.getElementById("font-increase").addEventListener("click", () => {
        changeFontSize(2);
    });
    document.getElementById("font-decrease").addEventListener("click", () => {
        changeFontSize(-2);
    });

    function changeFontSize(delta) {
        const current = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--reader-font-size"));
        const next = Math.max(14, Math.min(28, current + delta));
        document.documentElement.style.setProperty("--reader-font-size", next + "px");
        localStorage.setItem("cq_reader_font_size", next);
        if (!cfg.usesPdf) {
            // Font size change means page capacity changed -- must re-paginate.
            const progressRatio = currentIndex / totalPages;
            paginateText();
            totalPages = textPages.length;
            currentIndex = Math.min(Math.round(progressRatio * totalPages), totalPages - 1);
            renderCurrentPage();
        }
    }

    document.querySelectorAll(".theme-btn").forEach((btn) => {
        btn.addEventListener("click", () => setTheme(btn.dataset.theme));
    });

    function setTheme(theme) {
        document.body.className = `theme-${theme}`;
        localStorage.setItem("cq_reader_theme", theme);
        document.querySelectorAll(".theme-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.theme === theme);
        });
    }

    // ============================================================
    // SAVE PROGRESS + MARK COMPLETE (server calls)
    // ============================================================
    let saveTimer = null;
    function saveProgress() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            fetch(cfg.saveProgressUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrfToken },
                body: JSON.stringify({ page_index: currentIndex }),
            }).catch(() => {}); // best-effort, never blocks reading
        }, 400);
    }

    completeBtn.addEventListener("click", async () => {
        if (completeBtn.disabled) return;
        try {
            const res = await fetch(cfg.completeUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": cfg.csrfToken },
                body: JSON.stringify({ pages_reached: currentIndex, total_pages: totalPages }),
            });
            const data = await res.json();
            if (res.ok) {
                completeBtn.textContent = "✔ Course Complete!";
                completeBtn.disabled = true;
                if (data.new_badges && data.new_badges.length) {
                    alert("🏆 New badge unlocked: " + data.new_badges.join(", "));
                }
            } else {
                alert(data.error || "Could not mark complete yet.");
            }
        } catch (err) {
            alert("Something went wrong saving your progress. Please try again.");
        }
    });

    // ============================================================
    // INIT
    // ============================================================
    async function init() {
        const savedTheme = localStorage.getItem("cq_reader_theme") || "light";
        setTheme(savedTheme);
        const savedFontSize = localStorage.getItem("cq_reader_font_size");
        if (savedFontSize) document.documentElement.style.setProperty("--reader-font-size", savedFontSize + "px");

        if (cfg.usesPdf) {
            await loadPdf();
        } else {
            paginateText();
            totalPages = textPages.length;
        }

        currentIndex = Math.min(cfg.resumePageIndex || 0, totalPages - 1);
        renderCurrentPage();
    }

    init();
})();
