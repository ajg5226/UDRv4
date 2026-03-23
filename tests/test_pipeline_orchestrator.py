from contextlib import contextmanager

import pytest

from atlas.core.exceptions import PipelineError
from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig
from atlas.storage.repository import PipelineRunRepository


class _DummyDatabase:
    @contextmanager
    def session(self):
        yield object()


@pytest.mark.asyncio
async def test_run_preserves_original_error_when_run_id_not_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = PipelineOrchestrator()
    orchestrator._initialized = True
    orchestrator._db = _DummyDatabase()

    def _raise_create_error(self, **kwargs):  # noqa: ANN001
        raise RuntimeError("failed to create run record")

    complete_run_called = False

    def _track_complete_run(self, **kwargs):  # noqa: ANN001
        nonlocal complete_run_called
        complete_run_called = True

    monkeypatch.setattr(PipelineRunRepository, "create_run", _raise_create_error)
    monkeypatch.setattr(PipelineRunRepository, "complete_run", _track_complete_run)

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(RunConfig())

    assert isinstance(exc_info.value.cause, RuntimeError)
    assert exc_info.value.run_id is None
    assert complete_run_called is False
