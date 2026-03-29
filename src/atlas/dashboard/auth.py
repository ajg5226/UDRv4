"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os
from typing import Optional

import streamlit as st

from atlas.core.config import get_settings
from atlas.core.logging import get_logger
from atlas.core.secrets import get_secret

logger = get_logger(__name__)


def _parse_users_json(users_json: Optional[str]) -> Optional[dict[str, str]]:
    """Parse and validate dashboard users JSON payload."""
    if not users_json:
        return None

    try:
        parsed = json.loads(users_json)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    users: dict[str, str] = {}
    for username, password_hash in parsed.items():
        if isinstance(username, str) and isinstance(password_hash, str):
            users[username] = password_hash

    return users if users else None


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, this would load from Key Vault.
    For development, uses environment variable or defaults.
    
    Returns:
        Dict of username -> password_hash
    """
    # 1) Explicit environment override (JSON format)
    env_users = _parse_users_json(os.getenv("ATLAS_DASHBOARD_USERS"))
    if env_users:
        return env_users

    settings = get_settings()

    # 2) Key Vault secret for non-local deployments
    secret_name = settings.dashboard.auth.users_secret
    if secret_name:
        keyvault_users = _parse_users_json(get_secret(secret_name))
        if keyvault_users:
            return keyvault_users

    # 3) Development fallback only
    environment = (settings.environment or "").lower()
    if environment in {"development", "dev", "local", "test"}:
        default_password_hash = hashlib.sha256("atlas123".encode()).hexdigest()
        return {
            "admin": default_password_hash,
            "analyst": default_password_hash,
        }

    # Fail closed in non-development environments.
    logger.error(
        "Dashboard credentials not configured; refusing development fallback",
        environment=environment,
    )
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
    
    settings = get_settings()
    environment = (settings.environment or "").lower()
    if environment in {"development", "dev", "local", "test"}:
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
