"""Liveness and database check for the hosting platform's health probe."""

import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@never_cache
@require_GET
def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check could not reach the database")
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
