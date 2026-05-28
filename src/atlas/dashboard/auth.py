"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os

import streamlit as st

from atlas.core.config import get_settings
from atlas.core.secrets import get_secret


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


class AuthConfigurationError(RuntimeError):
    """Raised when dashboard authentication is unsafe or misconfigured."""


def _is_development_environment(environment: str) -> bool:
    """Return whether development-only authentication defaults are allowed."""
    return environment.lower() in DEVELOPMENT_ENVIRONMENTS


def _parse_users_json(users_json: str, source: str) -> dict[str, str]:
    """Parse and validate username-to-password-hash credentials."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as exc:
        raise AuthConfigurationError(f"Invalid dashboard user JSON in {source}") from exc
    
    if not isinstance(users, dict) or not users:
        raise AuthConfigurationError(f"Dashboard users in {source} must be a non-empty object")
    
    if not all(isinstance(username, str) and username for username in users):
        raise AuthConfigurationError(f"Dashboard usernames in {source} must be non-empty strings")
    
    if not all(isinstance(password_hash, str) and password_hash for password_hash in users.values()):
        raise AuthConfigurationError(
            f"Dashboard password hashes in {source} must be non-empty strings"
        )
    
    return users


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    Outside development, users must be configured explicitly by environment
    variable or the configured Key Vault secret. Development defaults are never
    accepted in production-like environments.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()
    
    # Try the documented environment variable first (JSON format).
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    source = "ATLAS_DASHBOARD_USERS"
    
    if not users_json:
        users_json = get_secret(settings.dashboard.auth.users_secret)
        source = f"secret '{settings.dashboard.auth.users_secret}'"
    
    if users_json:
        return _parse_users_json(users_json, source)
    
    if not _is_development_environment(settings.environment):
        raise AuthConfigurationError(
            "Dashboard users must be configured outside development; set "
            "ATLAS_DASHBOARD_USERS or the configured dashboard users secret"
        )
    
    # Default users for development (password: atlas123)
    default_password_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    
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


def validate_auth_settings() -> None:
    """Ensure production-like dashboard deployments cannot bypass authentication."""
    settings = get_settings()
    
    if _is_development_environment(settings.environment):
        return
    
    if not settings.dashboard.auth.enabled:
        raise AuthConfigurationError("Dashboard authentication cannot be disabled outside development")
    
    if settings.dashboard.auth.method != "simple":
        raise AuthConfigurationError(
            f"Unsupported dashboard auth method: {settings.dashboard.auth.method!r}"
        )
    
    get_users()


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
    
    if not _is_development_environment(get_settings().environment):
        return
    
    # Development hint
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
