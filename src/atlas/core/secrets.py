"""Secrets management for ATLAS."""

import os
from functools import lru_cache
from typing import Optional

from atlas.core.config import get_settings
from atlas.core.logging import get_logger

logger = get_logger(__name__)


class SecretsManager:
    """
    Secrets manager with support for multiple backends.
    
    Supports:
    - Environment variables (development)
    - Azure Key Vault (production)
    """
    
    def __init__(self) -> None:
        self._client = None
        self._vault_url: Optional[str] = None
    
    def _get_vault_url(self) -> Optional[str]:
        """Get the Key Vault URL from environment."""
        if self._vault_url is None:
            settings = get_settings()
            env_var = settings.keyvault.vault_url_env
            self._vault_url = os.getenv(env_var)
        return self._vault_url
    
    def _get_keyvault_client(self):
        """Get Azure Key Vault client (lazy initialization)."""
        if self._client is None:
            vault_url = self._get_vault_url()
            
            if not vault_url:
                logger.debug("Key Vault URL not configured, using environment variables only")
                return None
            
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient
                
                credential = DefaultAzureCredential()
                self._client = SecretClient(vault_url=vault_url, credential=credential)
                logger.info(f"Connected to Key Vault: {vault_url}")
                
            except ImportError:
                logger.warning("Azure SDK not installed, Key Vault unavailable")
                return None
            except Exception as e:
                logger.warning(f"Failed to connect to Key Vault: {e}")
                return None
        
        return self._client
    
    def get_secret(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a secret by name.
        
        Checks in order:
        1. Environment variable (name uppercased with underscores)
        2. Azure Key Vault
        3. Default value
        
        Args:
            name: Secret name (e.g., "tiingo-api-key")
            default: Default value if not found
            
        Returns:
            Secret value or default
        """
        # Convert name to environment variable format
        # tiingo-api-key -> TIINGO_API_KEY
        env_name = name.upper().replace("-", "_")
        
        # Try environment variable first
        value = os.getenv(env_name)
        if value:
            logger.debug(f"Secret '{name}' loaded from environment")
            return value
        
        # Try Key Vault
        client = self._get_keyvault_client()
        if client:
            try:
                secret = client.get_secret(name)
                logger.debug(f"Secret '{name}' loaded from Key Vault")
                return secret.value
            except Exception as e:
                logger.debug(f"Secret '{name}' not found in Key Vault: {e}")
        
        # Return default
        if default is not None:
            logger.debug(f"Using default value for secret '{name}'")
            return default
        
        logger.warning(f"Secret '{name}' not found")
        return None
    
    def set_secret(self, name: str, value: str) -> bool:
        """
        Set a secret in Key Vault.
        
        Args:
            name: Secret name
            value: Secret value
            
        Returns:
            True if successful
        """
        client = self._get_keyvault_client()
        if not client:
            logger.error("Cannot set secret: Key Vault not available")
            return False
        
        try:
            client.set_secret(name, value)
            logger.info(f"Secret '{name}' set in Key Vault")
            return True
        except Exception as e:
            logger.error(f"Failed to set secret '{name}': {e}")
            return False
    
    def list_secrets(self) -> list[str]:
        """
        List all secret names in Key Vault.
        
        Returns:
            List of secret names
        """
        client = self._get_keyvault_client()
        if not client:
            return []
        
        try:
            secrets = client.list_properties_of_secrets()
            return [s.name for s in secrets]
        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            return []


# Global secrets manager instance
_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get the global secrets manager instance."""
    global _manager
    if _manager is None:
        _manager = SecretsManager()
    return _manager


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Convenience function to get a secret.
    
    Args:
        name: Secret name
        default: Default value if not found
        
    Returns:
        Secret value or default
    """
    return get_secrets_manager().get_secret(name, default)
