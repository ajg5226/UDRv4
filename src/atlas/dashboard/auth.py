"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
from collections.abc import Mapping

import streamlit as st

from atlas.core.config import get_settings
from atlas.core.secrets import get_secret


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


def _is_development_environment() -> bool:
    """Return whether dashboard defaults are allowed for this environment."""
    settings = get_settings()
    return settings.environment.lower() in DEVELOPMENT_ENVIRONMENTS


def _development_users() -> dict[str, str]:
    """Get development-only default users."""
    default_password_hash = hash_password("atlas123")
    return {
        "admin": default_password_hash,
        "analyst": default_password_hash,
    }


def _parse_users(users_json: str) -> dict[str, str]:
    """Parse a JSON username -> password hash mapping."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError:
        return {}

    if not isinstance(users, Mapping):
        return {}

    parsed_users = {
        username: password_hash
        for username, password_hash in users.items()
        if isinstance(username, str) and isinstance(password_hash, str)
    }

    if len(parsed_users) != len(users):
        return {}

    return parsed_users


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, this would load from Key Vault.
    For development, uses environment variable or defaults.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()

    # Try the configured secret first. The secrets manager checks the matching
    # environment variable before Key Vault, so ATLAS_DASHBOARD_USERS still works.
    users_json = get_secret(settings.dashboard.auth.users_secret)
    if users_json:
        return _parse_users(users_json)

    if _is_development_environment():
        return _development_users()

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
    
    if _is_development_environment():
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
