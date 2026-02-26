"""Tests for atlas.core.config."""

import os
from pathlib import Path

import pytest

from atlas.core.config import (
    Settings,
    deep_merge,
    get_settings,
    reload_settings,
    PipelineConfig,
    DatabaseConfig,
)


class TestDeepMerge:
    def test_flat_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        assert deep_merge(base, override) == {"a": 1, "b": 3}

    def test_nested_override(self):
        base = {"top": {"a": 1, "b": 2}}
        override = {"top": {"b": 3}}
        result = deep_merge(base, override)
        assert result["top"]["a"] == 1
        assert result["top"]["b"] == 3

    def test_new_key_added(self):
        base = {"a": 1}
        override = {"b": 2}
        assert deep_merge(base, override) == {"a": 1, "b": 2}

    def test_empty_override(self):
        base = {"a": 1}
        assert deep_merge(base, {}) == {"a": 1}

    def test_deeply_nested(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 99}}}
        result = deep_merge(base, override)
        assert result["a"]["b"]["c"] == 99
        assert result["a"]["b"]["d"] == 2


class TestSettings:
    def test_loads_from_yaml(self):
        settings = get_settings()
        assert settings.pipeline.schedule == "0 5 * * *"
        assert settings.pipeline.timezone == "America/New_York"

    def test_development_environment_overrides(self, monkeypatch):
        monkeypatch.setenv("ATLAS_ENV", "development")
        settings = reload_settings()
        assert settings.database.driver == "sqlite"
        assert settings.logging.level == "DEBUG"
        assert settings.logging.format == "text"
        assert settings.storage.raw_archive.enabled is False

    def test_defaults_when_no_yaml(self):
        settings = Settings()
        assert isinstance(settings.pipeline, PipelineConfig)
        assert isinstance(settings.database, DatabaseConfig)
        assert settings.pipeline.batch_size_days == 30

    def test_default_providers(self):
        settings = get_settings()
        assert "tiingo" in settings.pipeline.default_providers
        assert "fred" in settings.pipeline.default_providers

    def test_reload_clears_cache(self, monkeypatch):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        s3 = reload_settings()
        assert s3 is not s1
