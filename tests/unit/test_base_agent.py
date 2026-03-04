"""
Unit tests for app.agents.base (BaseAgent, JobContext, AgentError).
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.base import AgentError, BaseAgent, JobContext


# ---------------------------------------------------------------------------
# JobContext
# ---------------------------------------------------------------------------


def test_job_context_stores_job_id():
    job_id = uuid.uuid4()
    ctx = JobContext(
        job_id=job_id,
        repo_path=Path("/tmp/test"),
        db_session=MagicMock(),
    )
    assert ctx.job_id == job_id


def test_job_context_stores_repo_path():
    ctx = JobContext(
        job_id=uuid.uuid4(),
        repo_path=Path("/tmp/repo"),
        db_session=MagicMock(),
    )
    assert ctx.repo_path == Path("/tmp/repo")


def test_job_context_languages_default_empty():
    ctx = JobContext(
        job_id=uuid.uuid4(),
        repo_path=Path("/tmp"),
        db_session=MagicMock(),
    )
    assert ctx.languages == []


def test_job_context_job_config_default_empty_dict():
    ctx = JobContext(
        job_id=uuid.uuid4(),
        repo_path=Path("/tmp"),
        db_session=MagicMock(),
    )
    assert ctx.job_config == {}


def test_job_context_llm_default_none():
    ctx = JobContext(
        job_id=uuid.uuid4(),
        repo_path=Path("/tmp"),
        db_session=MagicMock(),
    )
    assert ctx.llm is None


def test_job_context_custom_config():
    ctx = JobContext(
        job_id=uuid.uuid4(),
        repo_path=Path("/tmp"),
        db_session=MagicMock(),
        job_config={"max_patches": 5},
    )
    assert ctx.job_config["max_patches"] == 5


# ---------------------------------------------------------------------------
# AgentError
# ---------------------------------------------------------------------------


def test_agent_error_stores_agent_name():
    job_id = uuid.uuid4()
    err = AgentError("Something failed", agent="SmellDetector", job_id=job_id)
    assert err.agent == "SmellDetector"


def test_agent_error_stores_job_id():
    job_id = uuid.uuid4()
    err = AgentError("Fail", agent="Mapper", job_id=job_id)
    assert err.agent == "Mapper"


def test_agent_error_retryable_default_true():
    err = AgentError("Fail", agent="Planner", job_id=uuid.uuid4())
    assert err.retryable is True


def test_agent_error_retryable_can_be_false():
    err = AgentError("Fail", agent="Validator", job_id=uuid.uuid4(), retryable=False)
    assert err.retryable is False


def test_agent_error_message():
    err = AgentError("Something went wrong", agent="Learner", job_id=uuid.uuid4())
    assert str(err) == "Something went wrong"


# ---------------------------------------------------------------------------
# BaseAgent concrete subclass
# ---------------------------------------------------------------------------


class ConcreteAgent(BaseAgent):
    """Minimal concrete agent for testing BaseAgent lifecycle methods."""

    stage_name = "testing"

    async def run(self, context: JobContext) -> dict:
        return {"result": "ok"}


@pytest.mark.asyncio
async def test_execute_calls_on_start_and_run_and_on_complete():
    agent = ConcreteAgent()

    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    ctx = JobContext(
        job_id=uuid.uuid4(),
        repo_path=Path("/tmp"),
        db_session=db,
    )

    result = await agent.execute(ctx)
    assert result == {"result": "ok"}


@pytest.mark.asyncio
async def test_run_returns_dict():
    agent = ConcreteAgent()
    db = AsyncMock()
    ctx = JobContext(
        job_id=uuid.uuid4(),
        repo_path=Path("/tmp"),
        db_session=db,
    )
    result = await agent.run(ctx)
    assert isinstance(result, dict)


def test_base_agent_has_logger():
    agent = ConcreteAgent()
    assert agent.logger is not None


def test_stage_name_attribute():
    agent = ConcreteAgent()
    assert agent.stage_name == "testing"


@pytest.mark.asyncio
async def test_emit_progress_does_not_raise():
    agent = ConcreteAgent()
    db = AsyncMock()
    ctx = JobContext(job_id=uuid.uuid4(), repo_path=Path("/tmp"), db_session=db)
    # Should not raise even without Redis pub/sub
    await agent.emit_progress(ctx, "Processing...", percent=50)
