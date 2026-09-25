from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import ContactMessage


def home_view(request):
    """Public marketing homepage (CyberShield Academy design)."""
    return render(request, "pages/home.html")


def about_view(request):
    return render(request, "pages/about.html")


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
    Searches both admin-managed Courses and the static games registry
    by keyword. Two different data sources, one combined results page.
    """
    from courses.models import Course
    from games.registry import GAMES_REGISTRY

    query = request.GET.get("q", "").strip()
    course_results = []
    game_results = []

    if query:
        course_results = Course.objects.filter(
            Q(title__icontains=query) | Q(short_description__icontains=query),
            is_published=True,
        )
        game_results = [
            g for g in GAMES_REGISTRY
            if query.lower() in g["name"].lower() or query.lower() in g["description"].lower()
        ]

    return render(request, "pages/search.html", {
        "query": query,
        "course_results": course_results,
        "game_results": game_results,
        "has_results": bool(course_results or game_results),
    })
