"""The public face of an account: what other members may see.

Only the avatar, username, completed-course count and XP are public. Avatar URLs use the
user's random `avatar_token`, never the numeric id. If the owner has blocked the viewer,
the viewer gets neither their card nor their photo.
"""

from django.urls import reverse

# Shown for users without a photo, for unknown tokens and when the owner blocked the viewer:
# the same bytes every time, so the response never tells these cases apart.
DEFAULT_AVATAR_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Avatar">'
    '<rect width="64" height="64" rx="32" fill="#2c1766"/>'
    '<circle cx="32" cy="25" r="11" fill="#a78bfa"/>'
    '<path d="M12 54c3-11 11-17 20-17s17 6 20 17" fill="#a78bfa"/>'
    "</svg>"
).encode("utf-8")


def avatar_url(user):
    return reverse("accounts:avatar", args=[user.avatar_token])


def default_avatar_url():
    """The default image, tied to nobody (real tokens are 24 characters, never "default")."""
    return reverse("accounts:avatar", args=["default"])


def completed_courses(user):
    from courses.models import CourseProgress
    return CourseProgress.objects.filter(user=user).values("course").distinct().count()


def hidden_from(owner, viewer):
    """True when `owner` has blocked `viewer`: then the viewer sees no card and no photo."""
    if viewer is None or not viewer.is_authenticated or owner.pk == viewer.pk:
        return False
    from messaging.models import Block
    return Block.objects.filter(blocker=owner, blocked=viewer).exists()


def public_card(user, viewer=None):
    """{'username', 'avatar_url', 'courses', 'xp'} or None if the owner blocked the viewer."""
    if hidden_from(user, viewer):
        return None
    return {
        "username": user.username,
        "avatar_url": avatar_url(user),
        "courses": completed_courses(user),
        "xp": user.xp,
    }
