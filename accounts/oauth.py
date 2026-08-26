"""
accounts/oauth.py
--------------------
ONE JOB: talk to Google's OAuth2 endpoints. Kept separate from views.py
so these HTTP calls can be mocked out in tests (we don't want tests
depending on a real network call to Google every time).

This is the standard OAuth2 "Authorization Code" flow:
  1. Send the user to Google's consent screen (build_google_auth_url)
  2. Google redirects back to us with a one-time `code`
  3. We exchange that code for an access token (exchange_code_for_token)
  4. We use the access token to ask Google who the user is (fetch_google_userinfo)
"""

from urllib.parse import urlencode
import requests
from django.conf import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_google_auth_url(state: str, redirect_uri: str) -> str:
    """Build the URL that sends the user to Google's own sign-in/consent screen."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,          # CSRF protection -- checked again in the callback
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    """Trade the one-time authorization code for a real access token."""
    response = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=10)
    response.raise_for_status()
    return response.json()  # contains "access_token"


def fetch_google_userinfo(access_token: str) -> dict:
    """Use the access token to ask Google for the signed-in user's profile."""
    response = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()  # contains "email", "email_verified", "name", "picture"
