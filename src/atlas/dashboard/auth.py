"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os
from typing import Optional

import streamlit as st

from atlas.core.config import get_settings


def _parse_users_json(users_json: str) -> Optional[dict[str, str]]:
    """Parse dashboard users JSON into a username -> password_hash map."""
    try:
        parsed = json.loads(users_json)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    users: dict[str, str] = {}
    for username, password_hash in parsed.items():
        if not isinstance(username, str) or not isinstance(password_hash, str):
            return None
        users[username] = password_hash

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

    # Try environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json:
        parsed = _parse_users_json(users_json)
        if parsed is not None:
            return parsed
        # Fail closed in non-development environments if provided credentials are malformed.
        if settings.environment != "development":
            return {}

    # Try secret manager (environment variable or Key Vault backend)
    users_secret_name = settings.dashboard.auth.users_secret
    if users_secret_name:
        from atlas.core.secrets import get_secret

        users_secret = get_secret(users_secret_name)
        if users_secret:
            parsed = _parse_users_json(users_secret)
            if parsed is not None:
                return parsed
            if settings.environment != "development":
                return {}

    # Development-only fallback credentials (password: atlas123)
    if settings.environment != "development":
        return {}

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
    
    # Development hint
    settings = get_settings()
    if settings.environment == "development":
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
