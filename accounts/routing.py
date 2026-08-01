"""
accounts/routing.py
----------------------
ONE JOB: decide which URL name a user should land on next, based on
where they are in the required learning path:

    login/signup -> course intro (if not read yet) -> dashboard -> games

Keeping this in one function means the "what's the next step" rule is
never duplicated across login_view, signup_view, and the course view.
"""


def next_step_url_name(user):
    """Return the url name (not the path) the user should be sent to next."""
    from courses.progress import has_completed_all_courses  # local import avoids a
                                                              # circular import between
                                                              # accounts <-> courses
    if not has_completed_all_courses(user):
        return "courses:intro"
    return "dashboard:home"
