"""
accounts/routing.py
----------------------
ONE JOB: decide which URL name a user should land on next.

    login/signup -> [profile incomplete?] -> complete_profile
                  -> otherwise             -> dashboard:home

Course completion still gates games and certificates. It does not
force a new account into the course reader.
"""


def next_step_url_name(user):
    if not user.ethical_agreement:
        return "accounts:complete_profile"
    return "dashboard:home"
