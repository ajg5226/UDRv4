"""Simple authentication for ATLAS dashboard."""

import hashlib
import json
import os

import streamlit as st

from atlas.core.config import get_settings


class AuthConfigurationError(RuntimeError):
    """Raised when dashboard authentication cannot be configured safely."""


def _parse_users_json(users_json: str, source: str) -> dict[str, str]:
    """Parse username -> password-hash JSON from a trusted config source."""
    try:
        users = json.loads(users_json)
    except json.JSONDecodeError as exc:
        raise AuthConfigurationError(f"Invalid dashboard users JSON in {source}") from exc

    if not isinstance(users, dict) or not users:
        raise AuthConfigurationError(f"Dashboard users in {source} must be a non-empty object")

    for username, password_hash in users.items():
        if not isinstance(username, str) or not username:
            raise AuthConfigurationError(f"Dashboard users in {source} contain an invalid username")
        if not isinstance(password_hash, str) or not password_hash:
            raise AuthConfigurationError(
                f"Dashboard user '{username}' in {source} has an invalid password hash"
            )

    return users


def _is_development_environment() -> bool:
    """Return True only for environments where default credentials are acceptable."""
    settings = get_settings()
    return settings.environment.lower() in {"development", "dev", "local", "test", "testing"}


def get_users() -> dict[str, str]:
    """
    Get user credentials.
    
    In production, users must be configured through an environment variable or
    the configured Key Vault secret. Development may fall back to defaults.
    
    Returns:
        Dict of username -> password_hash
    """
    # Try environment variable first (JSON format)
    users_json = os.getenv("ATLAS_DASHBOARD_USERS")
    if users_json:
        return _parse_users_json(users_json, "ATLAS_DASHBOARD_USERS")

    settings = get_settings()

    # Try the configured secret before considering development defaults.
    try:
        from atlas.core.secrets import get_secret

        secret_json = get_secret(settings.dashboard.auth.users_secret)
    except Exception as exc:
        if not _is_development_environment():
            raise AuthConfigurationError(
                "Dashboard users secret could not be loaded in a non-development environment"
            ) from exc
        secret_json = None

    if secret_json:
        return _parse_users_json(secret_json, settings.dashboard.auth.users_secret)

    if not _is_development_environment():
        raise AuthConfigurationError(
            "Dashboard users are not configured. Set ATLAS_DASHBOARD_USERS or "
            f"the '{settings.dashboard.auth.users_secret}' secret."
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
    
    auth_configured = True
    auth_error = ""
    if not _is_development_environment():
        try:
            get_users()
        except AuthConfigurationError as exc:
            auth_configured = False
            auth_error = str(exc)

    if not auth_configured:
        st.error("Dashboard authentication is not configured.")
        st.info(auth_error)
        st.stop()

    # Login form
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            try:
                valid_credentials = verify_password(username, password)
            except AuthConfigurationError as exc:
                st.error("Dashboard authentication is not configured.")
                st.info(str(exc))
                st.stop()

            if valid_credentials:
                st.session_state["authenticated"] = True
                st.session_state["username"] = username
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    if _is_development_environment():
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
