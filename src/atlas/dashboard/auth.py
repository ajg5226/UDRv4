"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os

import streamlit as st

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.core.secrets import get_secret


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test", "testing"}


def _is_development_environment(environment: str) -> bool:
    """Return whether dashboard defaults are acceptable for this environment."""
    return environment.lower() in DEVELOPMENT_ENVIRONMENTS


def _parse_users_json(users_json: str, source: str) -> dict[str, str]:
    """Parse and validate username -> password-hash JSON."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            "Dashboard user credentials must be valid JSON",
            details={"source": source},
            cause=exc,
        ) from exc

    if not isinstance(users, dict) or not users:
        raise ConfigurationError(
            "Dashboard user credentials must be a non-empty JSON object of strings",
            details={"source": source},
        )

    has_invalid_entry = any(
        not isinstance(username, str) or not isinstance(password_hash, str)
        for username, password_hash in users.items()
    )
    if has_invalid_entry:
        raise ConfigurationError(
            "Dashboard user credentials must be a non-empty JSON object of strings",
            details={"source": source},
        )

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
    is_development = _is_development_environment(settings.environment)

    # Try environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json:
        return _parse_users_json(users_json, "ATLAS_DASHBOARD_USERS")

    # In deployed environments, credentials should come from Key Vault.
    should_check_keyvault = (
        bool(settings.dashboard.auth.users_secret)
        and (not is_development or bool(os.getenv(settings.keyvault.vault_url_env)))
    )
    if should_check_keyvault:
        secret_users_json = get_secret(settings.dashboard.auth.users_secret)
        if secret_users_json:
            return _parse_users_json(
                secret_users_json,
                settings.dashboard.auth.users_secret,
            )

    if not is_development:
        raise ConfigurationError(
            "Dashboard user credentials are required outside development environments",
            details={
                "environment": settings.environment,
                "env_var": "ATLAS_DASHBOARD_USERS",
                "users_secret": settings.dashboard.auth.users_secret,
            },
        )
    
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
            try:
                is_valid = verify_password(username, password)
            except ConfigurationError:
                st.error("Dashboard authentication is not configured correctly.")
                return

            if is_valid:
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    # Development hint
    if _is_development_environment(get_settings().environment):
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
