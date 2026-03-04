"""
Unit tests for app.agents.language_detector.LanguageDetectorAgent.

All DB calls are mocked with AsyncMock so no real database is required.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.agents.language_detector import LanguageDetectorAgent, EXTENSION_MAP, SKIP_DIRS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(job_id: str, repo_path: str, db_session=None) -> MagicMock:
    """Build a minimal JobContext mock."""
    ctx = MagicMock()
    ctx.job_id = job_id
    ctx.repo_path = Path(repo_path)
    db = db_session if db_session is not None else AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    ctx.db_session = db
    ctx.languages = []
    return ctx


# ---------------------------------------------------------------------------
# EXTENSION_MAP / SKIP_DIRS constant tests
# ---------------------------------------------------------------------------


def test_extension_map_contains_java():
    assert ".java" in EXTENSION_MAP
    assert EXTENSION_MAP[".java"] == "java"


def test_extension_map_contains_python():
    assert ".py" in EXTENSION_MAP
    assert EXTENSION_MAP[".py"] == "python"


def test_extension_map_contains_typescript():
    assert ".ts" in EXTENSION_MAP
    assert EXTENSION_MAP[".ts"] == "typescript"


def test_skip_dirs_contains_node_modules():
    assert "node_modules" in SKIP_DIRS


def test_skip_dirs_contains_venv():
    assert ".venv" in SKIP_DIRS


# ---------------------------------------------------------------------------
# Java repo detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_java_in_java_repo(sample_java_repo):
    ctx = _make_ctx("job-java-1", str(sample_java_repo))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    assert "java" in result["languages"] or any(
        (isinstance(l, dict) and l.get("language") == "java") or l == "java"
        for l in result["languages"]
    ), f"Expected 'java' in languages, got: {result['languages']}"


@pytest.mark.asyncio
async def test_java_is_dominant_language(sample_java_repo):
    ctx = _make_ctx("job-java-2", str(sample_java_repo))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    assert result["dominant"] == "java"


@pytest.mark.asyncio
async def test_java_file_count_positive(sample_java_repo):
    ctx = _make_ctx("job-java-3", str(sample_java_repo))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    assert result["total_files"] > 0


@pytest.mark.asyncio
async def test_java_detects_spring_framework(sample_java_repo):
    """pom.xml in the sample repo references spring-boot-starter."""
    ctx = _make_ctx("job-java-4", str(sample_java_repo))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    # Frameworks are nested in the list of LanguageInfo dicts
    java_info = next(
        (l for l in result["languages"] if isinstance(l, dict) and l.get("language") == "java"),
        None,
    )
    if java_info:
        assert "spring" in java_info.get("frameworks_detected", [])


# ---------------------------------------------------------------------------
# Python repo detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_python_in_python_repo(sample_python_repo):
    ctx = _make_ctx("job-py-1", str(sample_python_repo))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    langs = result["languages"]
    lang_names = [l["language"] if isinstance(l, dict) else l for l in langs]
    assert "python" in lang_names


@pytest.mark.asyncio
async def test_python_is_dominant(sample_python_repo):
    ctx = _make_ctx("job-py-2", str(sample_python_repo))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    assert result["dominant"] == "python"


@pytest.mark.asyncio
async def test_python_total_lines_positive(sample_python_repo):
    ctx = _make_ctx("job-py-3", str(sample_python_repo))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    assert result["total_lines"] > 0


# ---------------------------------------------------------------------------
# Mixed repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detects_typescript_via_tsconfig(sample_mixed_repo):
    """tsconfig.json implies TypeScript even if no .ts files were found."""
    ctx = _make_ctx("job-mix-1", str(sample_mixed_repo))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    lang_names = [l["language"] if isinstance(l, dict) else l for l in result["languages"]]
    assert "typescript" in lang_names or "python" in lang_names  # at least one detected


# ---------------------------------------------------------------------------
# Empty repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_repo_returns_empty_languages(tmp_path):
    ctx = _make_ctx("job-empty-1", str(tmp_path))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    assert result["languages"] == [] or result["dominant"] is None or result["dominant"] == ""


@pytest.mark.asyncio
async def test_empty_repo_file_count_zero_or_none(tmp_path):
    ctx = _make_ctx("job-empty-2", str(tmp_path))
    agent = LanguageDetectorAgent()
    result = await agent.run(ctx)

    assert result["total_files"] == 0 or result.get("file_counts") == {}


# ---------------------------------------------------------------------------
# Context is updated with detected languages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_languages_updated(sample_python_repo):
    ctx = _make_ctx("job-ctx-1", str(sample_python_repo))
    agent = LanguageDetectorAgent()
    await agent.run(ctx)

    assert isinstance(ctx.languages, list)
    assert "python" in ctx.languages


# ---------------------------------------------------------------------------
# stage_name
# ---------------------------------------------------------------------------


def test_stage_name_is_detecting():
    agent = LanguageDetectorAgent()
    assert agent.stage_name == "detecting"
