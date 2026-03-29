"""Regression tests for orchestrator failure handling."""

import pytest

from atlas.core.exceptions import DatabaseError, PipelineError
from atlas.pipeline.orchestrator import PipelineOrchestrator


class _BrokenDatabase:
    """Database stub that fails before run record creation."""

    def create_tables(self) -> None:
        return None

    class _BrokenSessionContext:
        def __enter__(self):
            raise DatabaseError("simulated db outage during run creation")

        def __exit__(self, exc_type, exc, tb):
            return False

    def session(self):
        return self._BrokenSessionContext()


@pytest.mark.asyncio
async def test_run_failure_before_run_creation_raises_pipeline_error_without_unboundlocalerror():
    """A DB failure before create_run should not crash with UnboundLocalError."""
    orchestrator = PipelineOrchestrator()
    orchestrator._db = _BrokenDatabase()
    orchestrator._initialized = True

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run()

    message = str(exc_info.value)
    assert "Pipeline execution failed" in message
    assert "UnboundLocalError" not in message
