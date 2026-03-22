"""Regression tests for pipeline orchestrator error handling."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from atlas.core.exceptions import PipelineError
from atlas.pipeline import orchestrator as orchestrator_module
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig


class _DummyDatabase:
    @contextmanager
    def session(self):  # type: ignore[no-untyped-def]
        yield object()


class _FailingPipelineRunRepository:
    def __init__(self, _session) -> None:
        pass

    def create_run(self, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("create_run failed")

    def complete_run(self, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("complete_run should not be called when run_id is unavailable")


@pytest.mark.asyncio
async def test_run_preserves_original_error_when_run_record_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure before run_id assignment should still raise PipelineError with original cause."""
    monkeypatch.setattr(
        orchestrator_module,
        "get_settings",
        lambda: SimpleNamespace(
            pipeline=SimpleNamespace(default_providers=[]),
            features=SimpleNamespace(enabled=False),
        ),
    )
    monkeypatch.setattr(orchestrator_module, "get_database", lambda: _DummyDatabase())
    monkeypatch.setattr(orchestrator_module, "get_provider_registry", lambda: SimpleNamespace())
    monkeypatch.setattr(
        orchestrator_module,
        "PipelineRunRepository",
        _FailingPipelineRunRepository,
    )

    orchestrator = PipelineOrchestrator()
    orchestrator._initialized = True

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig(providers=[]))

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert str(exc_info.value.cause) == "create_run failed"
