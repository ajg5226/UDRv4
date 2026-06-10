"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os

import streamlit as st

from atlas.core.config import Settings, get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.core.secrets import get_secret


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


def is_development_environment(environment: str) -> bool:
    """Return whether an environment may use development-only auth behavior."""
    return environment.lower() in DEVELOPMENT_ENVIRONMENTS


def _parse_users_json(users_json: str, source: str) -> dict[str, str]:
    """Parse and validate dashboard user credentials."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            "Invalid dashboard user credentials JSON",
            details={"source": source},
            cause=exc,
        ) from exc

    if not isinstance(users, dict) or not users:
        raise ConfigurationError(
            "Dashboard user credentials must be a non-empty JSON object",
            details={"source": source},
        )

    for username, password_hash in users.items():
        if not isinstance(username, str) or not username.strip():
            raise ConfigurationError(
                "Dashboard usernames must be non-empty strings",
                details={"source": source},
            )

        if (
            not isinstance(password_hash, str)
            or len(password_hash) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in password_hash)
        ):
            raise ConfigurationError(
                "Dashboard password hashes must be SHA-256 hex digests",
                details={"source": source, "username": username},
            )

    return users


def dashboard_auth_enabled(settings: Settings | None = None) -> bool:
    """Return whether dashboard auth is enabled, failing closed in production."""
    settings = settings or get_settings()

    if settings.dashboard.auth.enabled:
        return True

    if is_development_environment(settings.environment):
        return False

    raise ConfigurationError(
        "Dashboard authentication cannot be disabled outside development",
        details={"environment": settings.environment},
    )


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, loads from an environment variable or configured secret.
    Development-like environments may fall back to default local credentials.
    
    Returns:
        Dict of username -> password_hash
    """
    settings = get_settings()
    
    # Try environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json is not None:
        if not users_json.strip():
            raise ConfigurationError(
                "ATLAS_DASHBOARD_USERS cannot be empty",
                details={"source": "ATLAS_DASHBOARD_USERS"},
            )
        return _parse_users_json(users_json, "ATLAS_DASHBOARD_USERS")
    
    # Try configured secret (Key Vault in production, env-compatible in local runs)
    users_secret = get_secret(settings.dashboard.auth.users_secret)
    if users_secret:
        return _parse_users_json(users_secret, settings.dashboard.auth.users_secret)
    
    if not is_development_environment(settings.environment):
        raise ConfigurationError(
            "Dashboard users must be configured outside development",
            details={
                "environment": settings.environment,
                "env_var": "ATLAS_DASHBOARD_USERS",
                "secret": settings.dashboard.auth.users_secret,
            },
        )
    
    # Default users for development-like environments only (password: atlas123)
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
    
    settings = get_settings()
    if is_development_environment(settings.environment):
        st.markdown("""
        ---
        
        **Development Mode**
        
        Default credentials:
        - Username: `admin` or `analyst`
        - Password: `atlas123`
        
        *Set `ATLAS_DASHBOARD_USERS` environment variable with JSON credentials for production.*
        """)
    else:
        st.caption("Contact your administrator if you need dashboard access.")


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
