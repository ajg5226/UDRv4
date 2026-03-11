"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os

import streamlit as st

from atlas.core.logging import get_logger

logger = get_logger(__name__)

_INSECURE_DEFAULT_USERS = ("admin", "analyst")
_INSECURE_DEFAULT_PASSWORD = "atlas123"
_INSECURE_DEFAULTS_ENV = "ATLAS_ALLOW_INSECURE_DASHBOARD_DEFAULTS"


def get_users() -> dict[str, str]:
    """
    Get user credentials.

    In production, users must be configured via environment/secret.
    Optional insecure defaults are available only via explicit opt-in.

    Returns:
        Dict of username -> password_hash
    """
    # Try environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json:
        try:
            users = json.loads(users_json)
            if not isinstance(users, dict):
                logger.error("ATLAS_DASHBOARD_USERS must be a JSON object")
                return {}
            return {
                username: password_hash
                for username, password_hash in users.items()
                if isinstance(username, str) and isinstance(password_hash, str)
            }
        except json.JSONDecodeError:
            logger.error("Invalid JSON in ATLAS_DASHBOARD_USERS")
            return {}

    # Insecure fallback is opt-in only and intended for local development.
    if os.getenv(_INSECURE_DEFAULTS_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        logger.warning("Using insecure default dashboard credentials")
        default_password_hash = hashlib.sha256(_INSECURE_DEFAULT_PASSWORD.encode()).hexdigest()
        return {username: default_password_hash for username in _INSECURE_DEFAULT_USERS}

    logger.error(
        "Dashboard users are not configured; set ATLAS_DASHBOARD_USERS or explicitly enable "
        "ATLAS_ALLOW_INSECURE_DASHBOARD_DEFAULTS for local development only"
    )
    return {}


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(username: str, password: str) -> bool:
    """
    Verify a username/password combination.

    Args:
        username: Username to verify
        password: Plain text password

    Returns:
        True if credentials are valid
    """
    users = get_users()

    if username not in users:
        return False

    password_hash = hash_password(password)
    return password_hash == users[username]


def check_authentication() -> bool:
    """
    Check if the current session is authenticated.

    Returns:
        True if authenticated
    """
    return st.session_state.get("authenticated", False)


def show_login() -> None:
    """Display the login form."""
    st.title("🔐 ATLAS Login")

    st.markdown("""
    Welcome to ATLAS Dashboard. Please log in to continue.

    ---
    """)

    # Login form
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if verify_password(username, password):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password")

    if os.getenv(_INSECURE_DEFAULTS_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        st.warning(
            "Insecure default dashboard credentials are enabled via "
            "`ATLAS_ALLOW_INSECURE_DASHBOARD_DEFAULTS`."
        )


def logout() -> None:
    """Log out the current user."""
    if "authenticated" in st.session_state:
        del st.session_state["authenticated"]
    if "username" in st.session_state:
        del st.session_state["username"]


def require_role(allowed_roles: list[str]) -> bool:
    """
    Check if current user has one of the allowed roles.

    Note: This is a simplified implementation. In production,
    use proper RBAC with Azure AD or similar.

    Args:
        allowed_roles: List of allowed role names

    Returns:
        True if user has required role
    """
    if not check_authentication():
        return False

    username = st.session_state.get("username", "")

    # Simple role mapping for development
    # In production, this would query a proper role system
    role_mapping = {
        "admin": ["admin", "engineer", "analyst"],
        "analyst": ["analyst"],
    }

    user_roles = role_mapping.get(username, [])

    return any(role in allowed_roles for role in user_roles)
