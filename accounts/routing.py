"""
accounts/routing.py
----------------------
ONE JOB: decide which URL name a user should land on next.

    login/signup -> [profile incomplete?] -> complete_profile
                  -> [courses unread?]     -> courses:intro
                  -> otherwise             -> dashboard:home

The ethical-agreement check comes FIRST because it's a hard requirement
for using ANY part of the platform (including reading courses) -- most
users satisfy it at signup, but Google sign-in creates accounts where
it hasn't been confirmed yet.
"""


def next_step_url_name(user):
    if not user.ethical_agreement:
        return "accounts:complete_profile"

    from courses.progress import has_completed_all_courses
    if not has_completed_all_courses(user):
        return "courses:intro"

    return "dashboard:home"
