"""Session-deduped homepage visit counts. Does not store IP addresses."""

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from pages.models import HomepageVisitDay


def record_homepage_visit(request) -> None:
    """Count one homepage visit per browser session per calendar day."""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and (user.is_staff or user.is_superuser):
        return
    today = timezone.localdate()
    marker = str(today)
    if request.session.get("homepage_visit_day") == marker:
        return
    request.session["homepage_visit_day"] = marker
    with transaction.atomic():
        row, created = HomepageVisitDay.objects.select_for_update().get_or_create(
            day=today,
            defaults={"visits": 1},
        )
        if not created:
            HomepageVisitDay.objects.filter(pk=row.pk).update(visits=F("visits") + 1)


def homepage_visit_totals() -> dict:
    today = timezone.localdate()
    total = HomepageVisitDay.objects.aggregate(n=Sum("visits"))["n"] or 0
    today_row = HomepageVisitDay.objects.filter(day=today).first()
    return {
        "homepage_visits": total,
        "homepage_visits_today": today_row.visits if today_row else 0,
        "homepage_counts_since": HomepageVisitDay.objects.order_by("day").values_list("day", flat=True).first(),
    }
