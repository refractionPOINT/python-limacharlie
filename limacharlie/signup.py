"""Account signup for new LimaCharlie users.

Calls the Firebase Cloud Function to create a user profile in LimaCharlie.
This is idempotent -- safe to call for users who already have an account.
"""

import requests

from .constants import SIGNUP_URL, INTERNAL_EMAIL_DOMAINS


class SignupError(Exception):
    """Raised when the signup call fails in a non-recoverable way."""
    pass


def signup_user(id_token, email):
    """Create a user profile in LimaCharlie.

    This calls the signUp Firebase Cloud Function. The call is idempotent:
    if the user already exists the endpoint returns success.

    Args:
        id_token: Firebase ID token from OAuth.
        email: User email address.

    Raises:
        SignupError: If the signup request fails unexpectedly.
    """
    is_internal = any(email.lower().endswith(f"@{d}") for d in INTERNAL_EMAIL_DOMAINS)

    payload = {
        "data": {
            "email": email,
            "metadata": {
                "is_custom_domain": False,
                "is_custom_domain_client": False,
                "is_internal_user": is_internal,
            },
        }
    }

    try:
        resp = requests.post(
            SIGNUP_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {id_token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        raise SignupError(f"Signup request failed: {exc}")

    if resp.status_code == 200:
        return  # New user created (or function returned success)

    # 400 with "already signed up" / "already exists" is fine -- user exists.
    if resp.status_code == 400:
        body = resp.text.lower()
        if "already signed up" in body or "already exists" in body:
            return

    # Any other error is unexpected but not necessarily fatal -- the JWT
    # endpoint will give a clearer error if the user truly doesn't exist.
    raise SignupError(
        f"Signup returned HTTP {resp.status_code}: {resp.text}"
    )
