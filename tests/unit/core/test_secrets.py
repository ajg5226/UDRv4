"""Tests for atlas.core.secrets."""

import pytest

from atlas.core.secrets import SecretsManager, get_secret


class TestSecretsManager:
    def test_reads_from_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "env_value")
        mgr = SecretsManager()
        assert mgr.get_secret("my-secret") == "env_value"

    def test_env_var_name_conversion(self, monkeypatch):
        monkeypatch.setenv("TIINGO_API_KEY", "key123")
        mgr = SecretsManager()
        assert mgr.get_secret("tiingo-api-key") == "key123"

    def test_returns_default_when_missing(self):
        mgr = SecretsManager()
        assert mgr.get_secret("nonexistent-secret", default="fallback") == "fallback"

    def test_returns_none_when_missing_no_default(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_SECRET", raising=False)
        mgr = SecretsManager()
        assert mgr.get_secret("nonexistent-secret") is None

    def test_env_takes_precedence_over_keyvault(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "from_env")
        mgr = SecretsManager()
        assert mgr.get_secret("test-key") == "from_env"

    def test_keyvault_client_none_without_url(self, monkeypatch):
        monkeypatch.delenv("ATLAS_KEYVAULT_URL", raising=False)
        mgr = SecretsManager()
        assert mgr._get_keyvault_client() is None

    def test_set_secret_fails_without_keyvault(self):
        mgr = SecretsManager()
        assert mgr.set_secret("test", "value") is False

    def test_list_secrets_empty_without_keyvault(self):
        mgr = SecretsManager()
        assert mgr.list_secrets() == []


class TestGetSecretConvenience:
    def test_convenience_function(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "fred_key_123")
        import atlas.core.secrets as sm
        sm._manager = None
        assert get_secret("fred-api-key") == "fred_key_123"
        sm._manager = None
