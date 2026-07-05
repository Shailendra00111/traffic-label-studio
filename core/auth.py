"""
core/auth.py
====================
Cloud authentication via Supabase — shared between this desktop app and
the AnnotateX website. Registering or logging in here uses the exact
same account as the website: same username, same password, same account.

Requires the supabase python package:
    pip install supabase --break-system-packages
    (on Windows, usually just: pip install supabase)
"""

from supabase import create_client, Client

# Public project URL + publishable key (safe to keep in client code —
# access to data is controlled by Row Level Security policies on the
# "profiles" table in Supabase, not by hiding this key).
SUPABASE_URL = "https://fczzurqvafiiabafwecc.supabase.co"
SUPABASE_KEY = "sb_publishable_yv7Dj-Ds9L_L4jQJFq-yww_A5_jgxS_"

_supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class AuthResult:
    def __init__(self, success: bool, message: str):
        self.success = success
        self.message = message


def register_user(username: str, email: str, password: str) -> AuthResult:
    """Create a new account. Requires username + email + password because
    Supabase authenticates by email under the hood; the username is stored
    alongside it in the 'profiles' table so people can still log in with
    just a username (see login_user below)."""
    username = (username or "").strip()
    email = (email or "").strip()

    if len(username) < 3:
        return AuthResult(False, "Username must be at least 3 characters")
    if not email or "@" not in email:
        return AuthResult(False, "Please enter a valid email address")
    if len(password) < 4:
        return AuthResult(False, "Password must be at least 4 characters")

    try:
        existing = (
            _supabase.table("profiles")
            .select("username")
            .eq("username", username)
            .execute()
        )
        if existing.data:
            return AuthResult(False, "Username is already taken")

        result = _supabase.auth.sign_up({"email": email, "password": password})
        user = result.user
        if user is None:
            return AuthResult(False, "Registration failed. Please try again.")

        _supabase.table("profiles").insert(
            {"id": user.id, "username": username, "email": email}
        ).execute()

        return AuthResult(True, "Account created successfully!")
    except Exception as e:
        msg = str(e)
        if "already registered" in msg.lower() or "duplicate" in msg.lower():
            return AuthResult(False, "This email is already registered")
        return AuthResult(False, f"Registration failed: {msg}")


def login_user(username: str, password: str) -> AuthResult:
    """Look up the email tied to this username, then authenticate with
    Supabase using that email + password."""
    username = (username or "").strip()

    try:
        lookup = (
            _supabase.table("profiles")
            .select("email")
            .eq("username", username)
            .execute()
        )
        if not lookup.data:
            return AuthResult(False, "User not found")

        email = lookup.data[0]["email"]
        result = _supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        if result.user is None:
            return AuthResult(False, "Incorrect password")

        return AuthResult(True, "Login successful")
    except Exception:
        return AuthResult(False, "Incorrect username or password")