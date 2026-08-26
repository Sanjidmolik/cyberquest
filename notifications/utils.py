"""
notifications/utils.py
--------------------------
ONE JOB: create a notification. Other apps call notify(user, message)
instead of importing the Notification model directly everywhere --
keeps the notification-creation logic (and any future rules, like
capping how many are kept) in one place.
"""

from .models import Notification


def notify(user, message: str, link_url: str = "") -> Notification:
    return Notification.objects.create(user=user, message=message, link_url=link_url)
