"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os
from typing import Optional

import streamlit as st

from atlas.core.config import Settings, get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.core.secrets import get_secret


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


def is_development_environment(environment: Optional[str] = None) -> bool:
    """Return whether the configured environment may use development auth defaults."""
    env = environment if environment is not None else get_settings().environment
    return env.lower() in DEVELOPMENT_ENVIRONMENTS


def _parse_users_json(users_json: str, *, source: str, fail_closed: bool) -> dict[str, str]:
    """Parse and validate dashboard user credentials from JSON."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as e:
        if fail_closed:
            raise ConfigurationError(
                "Invalid dashboard user credentials JSON",
                details={"source": source},
                cause=e,
            ) from e
        return {}

    if (
        not isinstance(users, dict)
        or not users
        or any(not isinstance(username, str) or not username for username in users)
        or any(
            not isinstance(password_hash, str) or not password_hash
            for password_hash in users.values()
        )
    ):
        if fail_closed:
            raise ConfigurationError(
                "Dashboard user credentials must be a non-empty JSON object",
                details={"source": source},
            )
        return {}

    return users


def get_users(settings: Optional[Settings] = None) -> dict[str, str]:
    """
    Get user credentials.
    
    In production, credentials must come from the environment or Key Vault.
    Development-like environments may use local default users.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = settings or get_settings()
    fail_closed = not is_development_environment(settings.environment)

    # Try environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json:
        users = _parse_users_json(
            users_json,
            source="ATLAS_DASHBOARD_USERS",
            fail_closed=fail_closed,
        )
        if users:
            return users

    users_secret = get_secret(settings.dashboard.auth.users_secret)
    if users_secret:
        return _parse_users_json(
            users_secret,
            source=settings.dashboard.auth.users_secret,
            fail_closed=fail_closed,
        )

    if fail_closed:
        raise ConfigurationError(
            "Dashboard user credentials are required outside development environments",
            details={"environment": settings.environment},
        )
    
    # Default users for development (password: atlas123)
    default_password_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    
    return {
        "admin": default_password_hash,
        "analyst": default_password_hash,
    }


def ensure_dashboard_auth_configured(settings: Optional[Settings] = None) -> None:
    """Fail closed for unsafe dashboard authentication settings."""
    settings = settings or get_settings()
    if not settings.dashboard.auth.enabled:
        if not is_development_environment(settings.environment):
            raise ConfigurationError(
                "Dashboard authentication cannot be disabled outside development environments",
                details={"environment": settings.environment},
            )
        return

    if not is_development_environment(settings.environment):
        get_users(settings)


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
    
    if is_development_environment():
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
