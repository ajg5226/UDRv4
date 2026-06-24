"""Simple authentication for ATLAS dashboard."""

import hashlib
import json

import streamlit as st

from atlas.core.config import get_settings
from atlas.core.logging import get_logger
from atlas.core.secrets import get_secret

logger = get_logger(__name__)

DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test"}
DEFAULT_DASHBOARD_PASSWORD = "atlas123"


def get_users() -> dict[str, str]:
    """
    Get user credentials.

    Loads credentials from the configured dashboard users secret. Development
    defaults are only available for local/dev environments when no secret is set.

    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()
    configured_users, has_configured_secret = _get_configured_users(
        settings.dashboard.auth.users_secret
    )

    if has_configured_secret:
        return configured_users

    if _allow_development_defaults():
        return _default_users()

    logger.error("Dashboard authentication is enabled, but no dashboard users secret is configured")
    return {}


def _get_configured_users(secret_name: str) -> tuple[dict[str, str], bool]:
    """Load and validate dashboard users from environment or Key Vault."""
    users_json = get_secret(secret_name)
    if not users_json:
        return {}, False

    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON in dashboard users secret '{secret_name}': {exc}")
        return {}, True

    if not isinstance(users, dict) or not all(
        isinstance(username, str) and isinstance(password_hash, str)
        for username, password_hash in users.items()
    ):
        logger.error(
            f"Dashboard users secret '{secret_name}' must be a JSON object of string password hashes"
        )
        return {}, True

    return users, True


def _allow_development_defaults() -> bool:
    """Return whether built-in development users are allowed."""
    environment = get_settings().environment.lower()
    return environment in DEVELOPMENT_ENVIRONMENTS


def _default_users() -> dict[str, str]:
    """Return built-in local development users."""
    default_password_hash = hash_password(DEFAULT_DASHBOARD_PASSWORD)
    return {
        "admin": default_password_hash,
        "analyst": default_password_hash,
    }


def using_development_default_users() -> bool:
    """Return true only when the login form is using built-in development users."""
    settings = get_settings()
    _, has_configured_secret = _get_configured_users(settings.dashboard.auth.users_secret)
    return not has_configured_secret and _allow_development_defaults()


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

    st.markdown("Welcome to ATLAS Dashboard. Please log in to continue.\n\n---")

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

    # Development hint
    if using_development_default_users():
        st.markdown(
            f"---\n\n"
            f"**Development Mode**\n\n"
            f"Default credentials:\n"
            f"- Username: `admin` or `analyst`\n"
            f"- Password: `{DEFAULT_DASHBOARD_PASSWORD}`\n\n"
            f"*Set `ATLAS_DASHBOARD_USERS` environment variable with JSON credentials for production.*"
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
