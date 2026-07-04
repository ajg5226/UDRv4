"""Simple authentication for ATLAS dashboard."""

import hashlib
import json

import streamlit as st

from atlas.core.config import get_settings, is_development_environment
from atlas.core.exceptions import ConfigurationError
from atlas.core.secrets import get_secret


def _parse_users(users_json: str, *, source: str) -> dict[str, str]:
    """Parse and validate simple-auth users from a configured secret."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            "Dashboard users secret must be valid JSON",
            details={"source": source},
            cause=exc,
        ) from exc

    if not isinstance(users, dict) or not users:
        raise ConfigurationError(
            "Dashboard users secret must be a non-empty JSON object",
            details={"source": source},
        )

    for username, password_hash in users.items():
        if not isinstance(username, str) or not username:
            raise ConfigurationError(
                "Dashboard usernames must be non-empty strings",
                details={"source": source},
            )
        if not isinstance(password_hash, str) or not password_hash:
            raise ConfigurationError(
                "Dashboard password hashes must be non-empty strings",
                details={"source": source, "username": username},
            )

    return users


def get_users() -> dict[str, str]:
    """
    Get user credentials.

    In production, this would load from Key Vault.
    For development, uses environment variable or defaults.

    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()
    users_secret = settings.dashboard.auth.users_secret
    users_json = get_secret(users_secret)
    if users_json:
        return _parse_users(users_json, source=users_secret)

    if not is_development_environment(settings.environment):
        raise ConfigurationError(
            "Dashboard users must be configured outside development environments",
            details={"users_secret": users_secret, "environment": settings.environment},
        )

    # Default users for development (password: atlas123).
    default_password_hash = hashlib.sha256(b"atlas123").hexdigest()

    return {
        "admin": default_password_hash,
        "analyst": default_password_hash,
    }


def should_show_development_hint() -> bool:
    """Return True when the login page may show local development credentials."""
    return is_development_environment(get_settings().environment)


def validate_dashboard_auth_config() -> None:
    """Fail closed before serving the dashboard with unsafe production auth."""
    settings = get_settings()
    if not settings.dashboard.auth.enabled and not is_development_environment(settings.environment):
        raise ConfigurationError(
            "Dashboard authentication cannot be disabled outside development environments",
            details={"environment": settings.environment},
        )

    if settings.dashboard.auth.enabled and settings.dashboard.auth.method == "simple":
        get_users()


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

    if should_show_development_hint():
        st.markdown("""
        ---

        **Development Mode**

        Default credentials:
        - Username: `admin` or `analyst`
        - Password: `atlas123`

        *Set `ATLAS_DASHBOARD_USERS` environment variable with JSON credentials for production.*
        """)


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
