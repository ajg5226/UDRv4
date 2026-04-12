"""Simple authentication for ATLAS dashboard."""

import hashlib
import hmac
import json
import os
from typing import Optional

import streamlit as st

from atlas.core.config import get_settings


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, this would load from Key Vault.
    For development, uses environment variable or defaults.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()

    def _parse_users(raw_users: Optional[str]) -> Optional[dict[str, str]]:
        if not raw_users:
            return None
        try:
            parsed = json.loads(raw_users)
            if isinstance(parsed, dict) and all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in parsed.items()
            ):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    # Try environment variable first (JSON format)
    users = _parse_users(os.getenv("ATLAS_DASHBOARD_USERS"))
    if users:
        return users

    # Fallback to secret store for non-development deployments
    if settings.environment != "development":
        try:
            from atlas.core.secrets import get_secret

            users_secret = get_secret(settings.dashboard.auth.users_secret)
            users = _parse_users(users_secret)
            if users:
                return users
        except Exception:
            pass

        # Fail closed when credentials are missing in non-development environments.
        return {}

    # Development-only defaults (password: atlas123)
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
    st.title("🔐 ATLAS Login")
    
    st.markdown("""
    Welcome to ATLAS Dashboard. Please log in to continue.
    
    ---
    """)
    
    users = get_users()
    if not users:
        st.error(
            "Dashboard authentication is not configured. "
            "Set dashboard users via secret configuration."
        )
        return

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
