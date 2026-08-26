"""
certificates/eligibility.py
--------------------------------
ONE JOB: decide whether a user has earned the CyberQuest completion
certificate. Kept separate so the rule (currently: all courses done +
earned the 'course_complete' badge) can change in one place without
touching the PDF-generation code.
"""

def is_eligible_for_certificate(user) -> bool:
    from achievements.models import UserBadge
    return UserBadge.objects.filter(user=user, badge__code="course_complete").exists()
