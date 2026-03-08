"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os

import streamlit as st

from atlas.core.config import get_settings
from atlas.core.logging import get_logger

logger = get_logger(__name__)


def _parse_users_json(users_json: str, source: str) -> dict[str, str] | None:
    """Parse and validate a JSON username -> password_hash mapping."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as exc:
        logger.error("Invalid dashboard users JSON", source=source, error=str(exc))
        return None

    if not isinstance(users, dict):
        logger.error("Dashboard users payload must be a JSON object", source=source)
        return None

    validated_users: dict[str, str] = {}
    for username, password_hash in users.items():
        if isinstance(username, str) and isinstance(password_hash, str):
            validated_users[username] = password_hash
        else:
            logger.warning(
                "Ignoring invalid dashboard credential entry",
                source=source,
                username_type=type(username).__name__,
                password_hash_type=type(password_hash).__name__,
            )

    if not validated_users:
        logger.error("No valid dashboard credentials found", source=source)
        return None

    return validated_users


def get_users() -> dict[str, str]:
    """
    Get user credentials.

    In production, this would load from Key Vault.
    For development, uses environment variable or defaults.

    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()

    # Try environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json:
        parsed_users = _parse_users_json(users_json, "ATLAS_DASHBOARD_USERS")
        if parsed_users:
            return parsed_users

    # Then try configured secret backend.
    try:
        from atlas.core.secrets import get_secret

        secret_name = settings.dashboard.auth.users_secret
        users_secret = get_secret(secret_name)
        if users_secret:
            parsed_users = _parse_users_json(users_secret, f"secret:{secret_name}")
            if parsed_users:
                return parsed_users
    except Exception as exc:
        logger.warning(
            "Could not load dashboard users from secret backend",
            error=str(exc),
        )

    # Fail closed in non-development environments.
    environment = settings.environment.lower()
    if environment not in {"development", "dev", "local", "test"}:
        logger.error(
            "Dashboard authentication misconfigured: refusing default credentials",
            environment=environment,
        )
        return {}

    # Development fallback users (password: atlas123)
    default_password_hash = hashlib.sha256(b"atlas123").hexdigest()

    return {
        "admin": default_password_hash,
        "analyst": default_password_hash,
    }


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

    settings = get_settings()
    if settings.environment.lower() in {"development", "dev", "local", "test"}:
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
