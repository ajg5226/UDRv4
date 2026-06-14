"""Simple authentication for ATLAS dashboard."""

import hashlib
import json

import streamlit as st

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.core.secrets import get_secret


def _is_development() -> bool:
    """Return whether development-only auth defaults may be used."""
    return get_settings().environment.lower() == "development"


def _parse_users(users_json: str) -> dict[str, str]:
    """Parse and validate dashboard users JSON."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as e:
        raise ConfigurationError("Dashboard users secret is not valid JSON", cause=e) from e

    if not isinstance(users, dict) or not users:
        raise ConfigurationError("Dashboard users must be a non-empty JSON object")

    for username, password_hash in users.items():
        if not isinstance(username, str) or not isinstance(password_hash, str) or not password_hash:
            raise ConfigurationError("Dashboard users must map usernames to password hashes")

    return users


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, load from environment or Key Vault and fail closed if
    credentials are not configured. Development may use local defaults.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()
    users_json = get_secret(settings.dashboard.auth.users_secret)
    if users_json:
        return _parse_users(users_json)

    if not _is_development():
        raise ConfigurationError("Dashboard users must be configured outside development")

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
    
    if _is_development():
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
