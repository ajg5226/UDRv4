"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import logging
import os

import streamlit as st

logger = logging.getLogger(__name__)

_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_DEFAULT_PASSWORD_HASH = hashlib.sha256("atlas123".encode()).hexdigest()
_DEFAULT_USERS = {
    "admin": _DEFAULT_PASSWORD_HASH,
    "analyst": _DEFAULT_PASSWORD_HASH,
}


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
            loaded_users = json.loads(users_json)
        except json.JSONDecodeError:
            logger.error("Invalid ATLAS_DASHBOARD_USERS JSON; disabling logins")
            return {}

        if not isinstance(loaded_users, dict):
            logger.error("ATLAS_DASHBOARD_USERS must be a JSON object; disabling logins")
            return {}

        users: dict[str, str] = {}
        for username, password_hash in loaded_users.items():
            if not isinstance(username, str) or not isinstance(password_hash, str):
                logger.error("ATLAS_DASHBOARD_USERS entries must be string:string pairs")
                return {}
            users[username] = password_hash

        return users

    # Optional development fallback for local demos.
    # This is intentionally opt-in so production does not silently expose defaults.
    allow_default_users = (
        os.getenv("ATLAS_DASHBOARD_ALLOW_DEFAULT_USERS", "").strip().lower() in _TRUTHY_ENV_VALUES
    )
    if allow_default_users:
        return _DEFAULT_USERS.copy()

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
    
    allow_default_users = (
        os.getenv("ATLAS_DASHBOARD_ALLOW_DEFAULT_USERS", "").strip().lower() in _TRUTHY_ENV_VALUES
    )
    if allow_default_users:
        st.markdown("""
        ---
        
        **Development Mode**
        
        Default credentials:
        - Username: `admin` or `analyst`
        - Password: `atlas123`
        
        *Set `ATLAS_DASHBOARD_USERS` to disable development credentials.*
        """)
    else:
        st.caption("Configure `ATLAS_DASHBOARD_USERS` with dashboard credentials.")


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
