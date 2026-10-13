"""Gunicorn settings for production. Start with:

    gunicorn cyberquest.wsgi:application -c deploy/gunicorn.conf.py

Every value can be overridden with an environment variable.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# Two sync workers fit Render's smaller instances. Raise WEB_CONCURRENCY on larger ones.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))

# Longer than EMAIL_TIMEOUT (at most 20 s), so a slow mail provider produces a
# handled error instead of a killed worker.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5

# No max_requests: admin question generation runs on a background thread
# inside the worker, and recycling the worker would abort it.

# Access log to stdout. Paths only; codes and passwords travel in POST bodies.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Render terminates TLS at its proxy and forwards X-Forwarded-Proto.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "*")
