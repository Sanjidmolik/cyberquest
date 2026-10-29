from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from cyberquest.ratelimit import rate_limit

from .models import ContactMessage


def home_view(request):
    """Public marketing homepage (CyberShield Academy design)."""
    from pages.visits import homepage_visit_totals, record_homepage_visit

    record_homepage_visit(request)
    return render(request, "home.html", homepage_visit_totals())


def about_view(request):
    return render(request, "pages/about.html")


POLICY_UPDATED = "13 October 2026"


def _legal_context():
    from django.conf import settings

    source_url = settings.SOURCE_CODE_URL
    revision = settings.SOURCE_CODE_REVISION
    revision_url = f"{source_url}/tree/{revision}" if source_url and revision else ""
    return {
        "operator_name": settings.LEGAL_OPERATOR_NAME,
        "contact_email": settings.LEGAL_CONTACT_EMAIL,
        "source_url": source_url,
        "source_revision": revision[:12],
        "source_revision_url": revision_url,
        "policy_updated": POLICY_UPDATED,
        "session_days": settings.SESSION_COOKIE_AGE // 86400,
    }


def privacy_view(request):
    from accounts.codes import CODE_VALID_MINUTES
    from accounts.retention import RETENTION

    ctx = _legal_context()
    ctx.update({"code_minutes": CODE_VALID_MINUTES, "retention": RETENTION})
    return render(request, "pages/privacy.html", ctx)


def terms_view(request):
    return render(request, "pages/terms.html", _legal_context())


def notices_view(request):
    return render(request, "pages/notices.html", _legal_context())


@rate_limit(key_prefix="contact", limit=8, window_seconds=3600)
def contact_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        message = request.POST.get("message", "").strip()

        if name and email and message:
            ContactMessage.objects.create(name=name, email=email, message=message)
            messages.success(request, "Thanks for reaching out! We'll get back to you soon.")
            return redirect("pages:contact")
        else:
            messages.error(request, "Please fill in every field.")

    return render(request, "pages/contact.html")


@login_required(login_url="/accounts/login/")
def search_view(request):
    """
    Searches admin-managed Courses, the static games registry and published blog posts
    (never drafts) by keyword, on one combined results page.
    """
    from blog.models import Post
    from courses.models import Course
    from games.registry import active_games

    query = request.GET.get("q", "").strip()
    course_results = []
    game_results = []
    post_results = []

    if query:
        course_results = Course.objects.active().filter(
            Q(title__icontains=query) | Q(short_description__icontains=query),
        )
        game_results = [
            g for g in active_games()
            if query.lower() in g["name"].lower() or query.lower() in g["description"].lower()
        ]
        post_results = Post.objects.published().filter(
            Q(title__icontains=query) | Q(excerpt__icontains=query),
        ).order_by("-published_at")[:10]

    return render(request, "pages/search.html", {
        "query": query,
        "course_results": course_results,
        "game_results": game_results,
        "post_results": post_results,
        "has_results": bool(course_results or game_results or post_results),
    })
