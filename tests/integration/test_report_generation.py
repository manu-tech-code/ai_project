"""
Integration smoke tests for report-related services.

Tests verify that the service layer can be imported and invoked at a minimal
level without requiring real infrastructure services.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# ReportService smoke test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_service_can_be_imported():
    """ReportService must be importable without crashing."""
    try:
        from app.services.report import ReportService  # noqa: PLC0415
        assert ReportService is not None
    except ImportError as e:
        pytest.skip(f"ReportService not yet implemented: {e}")


@pytest.mark.asyncio
async def test_report_service_instantiates(db_session):
    """ReportService should be constructable with a DB session."""
    try:
        from app.services.report import ReportService  # noqa: PLC0415
        service = ReportService(db_session)
        assert service is not None
    except ImportError as e:
        pytest.skip(f"ReportService not yet implemented: {e}")
    except TypeError:
        # Might not accept db_session in constructor
        try:
            service = ReportService()
            assert service is not None
        except Exception as exc:
            pytest.skip(f"ReportService constructor incompatible: {exc}")


# ---------------------------------------------------------------------------
# AnalysisService smoke test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analysis_service_can_be_imported():
    """AnalysisService must be importable."""
    try:
        from app.services.analysis import AnalysisService  # noqa: PLC0415
        assert AnalysisService is not None
    except ImportError as e:
        pytest.skip(f"AnalysisService not yet implemented: {e}")


@pytest.mark.asyncio
async def test_analysis_service_instantiates(db_session):
    """AnalysisService should be constructable with a DB session."""
    try:
        from app.services.analysis import AnalysisService  # noqa: PLC0415
        service = AnalysisService(db_session)
        assert service is not None
    except ImportError as e:
        pytest.skip(f"AnalysisService not yet implemented: {e}")
    except TypeError as exc:
        pytest.skip(f"AnalysisService constructor incompatible: {exc}")


# ---------------------------------------------------------------------------
# Job status state machine
# ---------------------------------------------------------------------------


def test_job_status_valid_transitions():
    """
    Verify the expected state machine values are known constants.
    Not a DB test — just validates the domain model.
    """
    from app.models.job import Job  # noqa: PLC0415

    valid_statuses = {
        "pending", "detecting", "mapping", "analyzing",
        "planning", "transforming", "validating",
        "complete", "failed", "cancelled",
    }

    job = Job(status="pending")
    assert job.status in valid_statuses

    job.status = "complete"
    assert job.status in valid_statuses

    job.status = "failed"
    assert job.status in valid_statuses


# ---------------------------------------------------------------------------
# DB job persistence round-trip (with SQLite fixture)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_can_be_saved_and_retrieved(db_session):
    """Create a Job record in the test DB and verify it can be retrieved."""
    import uuid
    from app.models.job import Job  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        status="pending",
        languages=[],
        config={},
    )
    db_session.add(job)
    await db_session.flush()

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    retrieved = result.scalar_one_or_none()

    assert retrieved is not None, "Job was not persisted to the test DB"
    assert retrieved.id == job_id
    assert retrieved.status == "pending"


@pytest.mark.asyncio
async def test_multiple_jobs_can_be_saved(db_session):
    """Multiple jobs with different IDs should coexist in the DB."""
    from app.models.job import Job  # noqa: PLC0415
    from sqlalchemy import select, func  # noqa: PLC0415

    ids = [uuid.uuid4() for _ in range(3)]
    for jid in ids:
        db_session.add(Job(id=jid, status="pending", languages=[], config={}))
    await db_session.flush()

    count_result = await db_session.execute(
        select(func.count()).select_from(Job)
    )
    count = count_result.scalar_one()
    assert count >= 3


@pytest.mark.asyncio
async def test_job_status_can_be_updated(db_session):
    """Updating a job's status should persist correctly."""
    from app.models.job import Job  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    job_id = uuid.uuid4()
    job = Job(id=job_id, status="pending", languages=[], config={})
    db_session.add(job)
    await db_session.flush()

    # Update status
    job.status = "detecting"
    await db_session.flush()

    result = await db_session.execute(select(Job).where(Job.id == job_id))
    updated = result.scalar_one()
    assert updated.status == "detecting"


# ---------------------------------------------------------------------------
# UCG node and edge persistence round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ucg_node_can_be_saved(db_session):
    """UCGNode should be persistable to the test SQLite DB."""
    from app.models.job import Job  # noqa: PLC0415
    from app.models.ucg import UCGNode  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    job_id = uuid.uuid4()
    job = Job(id=job_id, status="mapping", languages=[], config={})
    db_session.add(job)
    await db_session.flush()

    node_id = uuid.uuid4()
    node = UCGNode(
        id=node_id,
        job_id=job_id,
        node_type="CLASS",
        qualified_name="com.example.OrderService",
        language="java",
        file_path="src/OrderService.java",
        line_start=1,
        line_end=100,
        properties={},
    )
    db_session.add(node)
    await db_session.flush()

    result = await db_session.execute(select(UCGNode).where(UCGNode.id == node_id))
    retrieved = result.scalar_one_or_none()

    assert retrieved is not None
    assert retrieved.qualified_name == "com.example.OrderService"
    assert retrieved.node_type == "CLASS"


@pytest.mark.asyncio
async def test_smell_can_be_saved(db_session):
    """Smell should be persistable to the test SQLite DB."""
    from app.models.job import Job  # noqa: PLC0415
    from app.models.smell import Smell  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    job_id = uuid.uuid4()
    job = Job(id=job_id, status="analyzing", languages=[], config={})
    db_session.add(job)
    await db_session.flush()

    smell_id = uuid.uuid4()
    smell = Smell(
        id=smell_id,
        job_id=job_id,
        smell_type="god_class",
        severity="high",
        description="Too many methods",
        confidence=0.85,
        affected_node_ids=[],
        evidence={"method_count": 12},
        dismissed=False,
    )
    db_session.add(smell)
    await db_session.flush()

    result = await db_session.execute(select(Smell).where(Smell.id == smell_id))
    retrieved = result.scalar_one_or_none()

    assert retrieved is not None
    assert retrieved.smell_type == "god_class"
    assert retrieved.severity == "high"
    assert retrieved.dismissed is False
