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

_DEV_ENVIRONMENTS = {"development", "dev", "local", "test"}


def _parse_users_json(users_json: str, source: str) -> Optional[dict[str, str]]:
    """Parse and validate dashboard user credentials from JSON."""
    try:
        payload = json.loads(users_json)
    except json.JSONDecodeError:
        logger.warning("Failed to parse dashboard users JSON", source=source)
        return None

    if not isinstance(payload, dict):
        logger.warning("Dashboard users payload must be a JSON object", source=source)
        return None

    if not all(isinstance(user, str) and isinstance(pw_hash, str) for user, pw_hash in payload.items()):
        logger.warning("Dashboard users payload contains invalid key/value types", source=source)
        return None

    return payload


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, this would load from Key Vault.
    For development, uses environment variable or defaults.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()

    # Try explicit environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json:
        users = _parse_users_json(users_json, source="ATLAS_DASHBOARD_USERS")
        if users is not None:
            return users

    # Then try configured secret (Key Vault or env-backed secret)
    secret_name = settings.dashboard.auth.users_secret
    users_secret = get_secret(secret_name)
    if users_secret:
        users = _parse_users_json(users_secret, source=secret_name)
        if users is not None:
            return users

    # Development-only fallback credentials
    environment = settings.environment.lower()
    if environment in _DEV_ENVIRONMENTS:
        default_password_hash = hashlib.sha256("atlas123".encode()).hexdigest()
        return {
            "admin": default_password_hash,
            "analyst": default_password_hash,
        }

    # Fail closed outside development if credentials are missing/invalid.
    logger.error(
        "Dashboard credentials missing; login is disabled until configured",
        environment=settings.environment,
        users_secret=secret_name,
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
    if settings.environment.lower() in _DEV_ENVIRONMENTS:
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
