"""Simple authentication for ATLAS dashboard."""

import hashlib
import hmac
import json
import re

import streamlit as st

from atlas.core.config import get_settings, is_development_environment
from atlas.core.exceptions import ConfigurationError
from atlas.core.secrets import get_secret

_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _parse_users_json(users_json: str) -> dict[str, str]:
    """Parse and validate dashboard users JSON."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("Dashboard users secret must be valid JSON", cause=exc) from exc

    if not isinstance(users, dict) or not users:
        raise ConfigurationError("Dashboard users secret must be a non-empty JSON object")

    parsed_users: dict[str, str] = {}
    for username, password_hash in users.items():
        if not isinstance(username, str) or not username.strip():
            raise ConfigurationError("Dashboard users secret contains an invalid username")
        if not isinstance(password_hash, str) or not _SHA256_HEX_RE.fullmatch(password_hash):
            raise ConfigurationError(
                "Dashboard users secret must map usernames to SHA-256 password hashes",
                details={"username": username},
            )
        parsed_users[username] = password_hash.lower()

    return parsed_users


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    Production-like environments must provide a configured users secret.
    Development-like environments may use local default users.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()

    users_json = get_secret(settings.dashboard.auth.users_secret)
    if users_json:
        return _parse_users_json(users_json)

    if not is_development_environment(settings.environment):
        raise ConfigurationError(
            "Dashboard users secret is required outside development",
            details={"users_secret": settings.dashboard.auth.users_secret},
        )

    # Default users for development (password: atlas123)
    default_password_hash = hashlib.sha256(b"atlas123").hexdigest()
    
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


def validate_auth_configuration() -> None:
    """Reject dashboard auth settings that would expose production data."""
    settings = get_settings()
    if not settings.dashboard.auth.enabled and not is_development_environment(settings.environment):
        raise ConfigurationError("Dashboard authentication cannot be disabled outside development")


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
    
    if is_development_environment(get_settings().environment):
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
