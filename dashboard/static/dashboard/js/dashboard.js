/*
  dashboard/static/dashboard/js/dashboard.js
  -----------------------------------------------
  Only job: toggle the sidebar open/closed on small screens, where it's
  hidden off-canvas by default (see the @media rule in dashboard.css).
*/

document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("sidebar-toggle");
    const sidebar = document.getElementById("sidebar");

    if (!toggleBtn || !sidebar) return;

    toggleBtn.addEventListener("click", function () {
        sidebar.classList.toggle("open");
    });

    // Clicking outside the open sidebar (on mobile) closes it again.
    document.addEventListener("click", function (e) {
        const clickedInsideSidebar = sidebar.contains(e.target);
        const clickedToggle = toggleBtn.contains(e.target);
        if (sidebar.classList.contains("open") && !clickedInsideSidebar && !clickedToggle) {
            sidebar.classList.remove("open");
        }
    });
});
