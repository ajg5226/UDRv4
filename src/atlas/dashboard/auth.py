"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os
from typing import Optional

import streamlit as st

from atlas.core.config import get_settings


def _is_development_environment() -> bool:
    """Return True for environments where local default credentials are allowed."""
    environment = get_settings().environment.lower()
    return environment in {"development", "dev", "local", "test", "testing"}


def _parse_users_json(users_json: str) -> dict[str, str]:
    """Parse and validate ATLAS_DASHBOARD_USERS JSON payload."""
    users = json.loads(users_json)
    if not isinstance(users, dict):
        raise ValueError("ATLAS_DASHBOARD_USERS must be a JSON object of username->password hash")
    if not users:
        raise ValueError("ATLAS_DASHBOARD_USERS cannot be empty")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in users.items()):
        raise ValueError("ATLAS_DASHBOARD_USERS entries must be string username->hash pairs")
    return users


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, this would load from Key Vault.
    For development, uses environment variable or defaults.
    
    Returns:
        Dict of username -> password_hash
    """
    # Try environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json:
        try:
            return _parse_users_json(users_json)
        except ValueError:
            if not _is_development_environment():
                raise ValueError(
                    "Dashboard authentication is misconfigured. "
                    "Set ATLAS_DASHBOARD_USERS to valid JSON username->SHA256 hashes."
                )
    
    # Default users for development (password: atlas123)
    # In production, set ATLAS_DASHBOARD_USERS or use Key Vault
    if not _is_development_environment():
        raise ValueError(
            "Dashboard authentication is not configured for this environment. "
            "Set ATLAS_DASHBOARD_USERS to valid JSON username->SHA256 hashes."
        )

    default_password_hash = hashlib.sha256("atlas123".encode()).hexdigest()
    
    return {
        "admin": default_password_hash,
        "analyst": default_password_hash,
    }


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(
    username: str,
    password: str,
    users: Optional[dict[str, str]] = None,
) -> bool:
    """
    Verify a username/password combination.
    
    Args:
        username: Username to verify
        password: Plain text password
        
    Returns:
        True if credentials are valid
    """
    users = users or get_users()
    
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

    try:
        users = get_users()
    except ValueError as exc:
        st.error(str(exc))
        return
    
    # Login form
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            if verify_password(username, password, users):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    # Development hint
    if _is_development_environment():
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
