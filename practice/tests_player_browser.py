"""The real student player in a real browser (headless Microsoft Edge or Chrome).

Deferred from Studio phase 1: content with keys the player doesn't know (`meta`, future
top-level, step and row keys) must play without JavaScript errors. Skipped when no
Chromium-based browser is installed (e.g. a minimal CI image).

How it works: a test-only URL signs a student in and serves the real session page with a
small script added at the top that records any JavaScript error, then ticks the agreement
and presses "Start mission" the way a student would. The script reports what happened to a
second test-only URL (Edge on Windows doesn't print --dump-dom output to a console).
"""

import copy
import os
import shutil
import subprocess
import tempfile

from django.contrib.auth import get_user_model, login
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import path

from cyberquest.urls import urlpatterns as site_urls
from practice.models import Scenario
from practice.session_views import session_page
from practice.testing import convert_all

PROBE = """<script>
(function () {
  var root = document.documentElement;
  var error = "";
  function fail(message) { error = error || String(message || "error"); }
  window.addEventListener("error", function (e) { fail(e.message); });
  window.addEventListener("unhandledrejection", function (e) { fail("promise: " + (e.reason && e.reason.message)); });
  document.addEventListener("DOMContentLoaded", function () {
    var agree = document.querySelector("[data-cq-agree]");
    agree.checked = true;
    agree.dispatchEvent(new Event("change"));
    document.querySelector("[data-cq-start]").click();
    setTimeout(function () {
      var step = document.querySelector(".cqs-main");
      var rendered = step && !document.querySelector(".cqs-error") ? "yes" : "no";
      fetch("/__probe_result/?slug=" + encodeURIComponent(root.getAttribute("data-slug") || "") +
            "&rendered=" + rendered + "&error=" + encodeURIComponent(error));
    }, 2500);
  });
})();
</script>"""


def _browser():
    candidates = [
        os.environ.get("CQ_TEST_BROWSER", ""),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("msedge") or "", shutil.which("microsoft-edge") or "",
        shutil.which("google-chrome") or "", shutil.which("chromium") or "",
    ]
    return next((c for c in candidates if c and os.path.exists(c)), None)


RESULTS = {}


def probe_result(request):
    from django.http import HttpResponse
    RESULTS[request.GET.get("slug", "")] = {"rendered": request.GET.get("rendered"), "error": request.GET.get("error", "")}
    return HttpResponse("ok")


def probe_session(request, slug):
    """Test-only: sign the probe student in and serve the real player with the probe script."""
    user = get_user_model().objects.get(username="browserprobe")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    response = session_page(request, slug)
    probe = PROBE.replace("<script>", f'<script>document.documentElement.setAttribute("data-slug", "{slug}");', 1)
    response.content = response.content.replace(b"<head>", b"<head>" + probe.encode(), 1)
    return response


urlpatterns = [path("__probe/<slug:slug>/", probe_session), path("__probe_result/", probe_result)] + site_urls


@override_settings(ROOT_URLCONF=__name__, ALLOWED_HOSTS=["*"])
class PlayerIgnoresUnknownKeysTests(StaticLiveServerTestCase):
    def setUp(self):
        self.browser = _browser()
        if not self.browser:
            self.skipTest("No headless Edge/Chrome installed")
        convert_all()
        get_user_model().objects.create_user(email="probe@example.com", password="x-probe-123", username="browserprobe")

    def _play(self, slug):
        """Open the probe page in the headless browser; return what the page reported."""
        RESULTS.pop(slug, None)
        for _ in range(3):                         # headless Edge sometimes fails its first launch
            profile = tempfile.mkdtemp()
            try:
                subprocess.run(
                    [self.browser, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                     "--virtual-time-budget=9000", f"--screenshot={os.path.join(profile, 'shot.png')}",
                     f"{self.live_server_url}/__probe/{slug}/"],
                    capture_output=True, timeout=90,
                )
            finally:
                shutil.rmtree(profile, ignore_errors=True)
            if slug in RESULTS:
                return RESULTS[slug]
        return None

    def _with_unknown_keys(self, slug):
        scenario = Scenario.objects.get(slug=slug)
        content = copy.deepcopy(scenario.content)
        content["meta"] = {"badge": "Probe Badge", "description": "Probe description"}
        content["future_top_level"] = {"anything": [1, 2, 3]}
        for step in content["steps"]:
            step["future_step_key"] = {"nested": True}
            for value in list(step.values()):
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    value[0]["future_row_key"] = "kept"
        Scenario.objects.filter(pk=scenario.pk).update(content=content)

    def test_the_player_ignores_unknown_keys_without_errors(self):
        for slug in ("phish-01-choice", "phishing-microsoft-disable"):      # a branch and a hotspot/mcq session
            self._with_unknown_keys(slug)
            result = self._play(slug)
            self.assertIsNotNone(result, f"{slug}: the browser never reported back")
            self.assertEqual(result["error"], "", slug)
            self.assertEqual(result["rendered"], "yes", slug)
