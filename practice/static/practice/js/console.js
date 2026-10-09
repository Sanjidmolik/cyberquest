(function () {
    document.querySelectorAll(".tool-list form").forEach(function (form) {
        form.addEventListener("submit", function () {
            var button = form.querySelector("button");
            if (!button) return;
            button.classList.add("is-busy");
            if (button.classList.contains("decision-btn")) button.classList.add("is-selected");
            button.setAttribute("aria-busy", "true");
            window.setTimeout(function () { button.disabled = true; }, 0);
        });
    });
})();
