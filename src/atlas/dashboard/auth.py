"""Simple authentication for ATLAS dashboard."""

import hashlib
import hmac
import json

import streamlit as st

from atlas.core.config import get_settings, is_development_environment
from atlas.core.exceptions import ConfigurationError
from atlas.core.secrets import get_secret

_SHA256_HEX_LENGTH = 64


def _default_users() -> dict[str, str]:
    """Return development-only default users."""
    default_password_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    return {
        "admin": default_password_hash,
        "analyst": default_password_hash,
    }


def _validate_users(users: object) -> dict[str, str]:
    """Validate the username -> SHA-256 password hash mapping."""
    if not isinstance(users, dict) or not users:
        raise ConfigurationError("Dashboard users must be a non-empty JSON object")

    validated: dict[str, str] = {}
    for username, password_hash in users.items():
        if not isinstance(username, str) or not username.strip():
            raise ConfigurationError("Dashboard usernames must be non-empty strings")
        if (
            not isinstance(password_hash, str)
            or len(password_hash) != _SHA256_HEX_LENGTH
            or any(char not in "0123456789abcdefABCDEF" for char in password_hash)
        ):
            raise ConfigurationError(
                f"Dashboard password hash for user '{username}' must be a SHA-256 hex digest"
            )
        validated[username] = password_hash.lower()

    return validated


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, this would load from Key Vault.
    For development, uses environment variable or defaults.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()

    # Load through the configured secret name. In development this still supports
    # ATLAS_DASHBOARD_USERS via the secrets manager's env-var lookup.
    users_json = get_secret(settings.dashboard.auth.users_secret)
    if users_json:
        try:
            return _validate_users(json.loads(users_json))
        except json.JSONDecodeError as exc:
            raise ConfigurationError("Dashboard users secret must contain valid JSON") from exc

    if is_development_environment(settings.environment):
        return _default_users()

    raise ConfigurationError(
        "Dashboard users secret is required outside development environments"
    )


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
    return hmac.compare_digest(password_hash, users[username])


def check_authentication() -> bool:
    """
    Check if the current session is authenticated.
    
    Returns:
        True if authenticated
    """
    return st.session_state.get("authenticated", False)


def show_login() -> None:
    """Display the login form."""
    settings = get_settings()

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
    
    if is_development_environment(settings.environment):
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
