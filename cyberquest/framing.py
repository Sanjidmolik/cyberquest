"""No other page may frame CyberQuest: X-Frame-Options DENY (Django) plus the modern
equivalent, CSP `frame-ancestors 'none'`, on every response.

The single exception is the Practice Studio preview player, which the Studio shows in an
iframe on the same site: that view sets SAMEORIGIN and `frame-ancestors 'self'` itself
(practice/studio/preview_views.py), and this middleware leaves an existing CSP alone.
"""


class FrameAncestorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response
