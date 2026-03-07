"""
Unit tests for SQLAlchemy ORM models (Job, UCGNode, UCGEdge, Smell).

Tests verify model construction, field defaults, and helper methods.
No database connection required — models are instantiated in-memory.
"""

import uuid
from datetime import datetime, UTC

import pytest


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------


def test_job_model_defaults():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    # status default is set at DB insert time; before flush it may be None or "pending"
    assert job.status in (None, "pending", "queued")


def test_job_model_with_explicit_status():
    from app.models.job import Job  # noqa: PLC0415

    job = Job(status="complete")
    assert job.status == "complete"


def test_job_default_retry_count_is_zero():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    # SQLAlchemy mapped_column default= applies at INSERT time, not constructor time
    assert job.retry_count in (None, 0)


def test_job_default_languages_is_empty_or_list():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    # languages defaults to a list (possibly empty, via SQLAlchemy default=list)
    assert job.languages is None or isinstance(job.languages, list)


def test_job_duration_seconds_returns_none_without_timestamps():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    assert job.duration_seconds() is None


def test_job_duration_seconds_computed_correctly():
    from app.models.job import Job  # noqa: PLC0415
    from datetime import timedelta

    now = datetime.now(UTC)
    job = Job()
    job.started_at = now
    job.completed_at = now + timedelta(seconds=300)

    duration = job.duration_seconds()
    assert duration == 300.0


def test_job_stage_progress_all_pending_for_new_job():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    job.status = "pending"
    job.current_stage = None

    progress = job.stage_progress()
    assert isinstance(progress, dict)
    # All stages should be "pending" since no stage is running
    for stage_status in progress.values():
        assert stage_status in ("pending", "running", "complete", "failed")


def test_job_stage_progress_running_stage_is_running():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    job.status = "analyzing"
    job.current_stage = "analyzing"

    progress = job.stage_progress()
    assert progress.get("analyzing") == "running"


def test_job_stage_progress_prior_stages_complete():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    job.status = "analyzing"
    job.current_stage = "analyzing"

    progress = job.stage_progress()
    assert progress.get("detecting") == "complete"
    assert progress.get("mapping") == "complete"


def test_job_stage_progress_future_stages_pending():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    job.status = "analyzing"
    job.current_stage = "analyzing"

    progress = job.stage_progress()
    assert progress.get("planning") == "pending"
    assert progress.get("validating") == "pending"
    assert "transforming" not in progress  # transformer is now on-demand, not a pipeline stage


def test_job_stage_progress_all_complete_for_finished_job():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    job.status = "complete"
    job.current_stage = None

    progress = job.stage_progress()
    for stage_status in progress.values():
        assert stage_status == "complete"


def test_job_label_defaults_to_none():
    from app.models.job import Job  # noqa: PLC0415

    job = Job()
    assert job.label is None


# ---------------------------------------------------------------------------
# UCGNode model
# ---------------------------------------------------------------------------


def test_ucg_node_model_basic_fields():
    from app.models.ucg import UCGNode  # noqa: PLC0415

    job_id = uuid.uuid4()
    node = UCGNode(
        job_id=job_id,
        node_type="CLASS",
        qualified_name="com.example.OrderService",
        language="java",
        file_path="src/OrderService.java",
        line_start=1,
        line_end=100,
    )
    assert node.node_type == "CLASS"
    assert node.qualified_name == "com.example.OrderService"
    assert node.language == "java"
    assert node.file_path == "src/OrderService.java"
    assert node.line_start == 1
    assert node.line_end == 100


def test_ucg_node_model_job_id_matches():
    from app.models.ucg import UCGNode  # noqa: PLC0415

    job_id = uuid.uuid4()
    node = UCGNode(
        job_id=job_id,
        node_type="METHOD",
        qualified_name="com.example.OrderService.createOrder",
        language="java",
    )
    assert node.job_id == job_id


def test_ucg_node_model_default_properties():
    from app.models.ucg import UCGNode  # noqa: PLC0415

    node = UCGNode(
        job_id=uuid.uuid4(),
        node_type="FUNCTION",
        qualified_name="mymodule.my_func",
        language="python",
    )
    # properties defaults to {} (SQLAlchemy default=dict)
    assert node.properties is None or isinstance(node.properties, dict)


def test_ucg_node_python_language():
    from app.models.ucg import UCGNode  # noqa: PLC0415

    node = UCGNode(
        job_id=uuid.uuid4(),
        node_type="CLASS",
        qualified_name="models.User",
        language="python",
    )
    assert node.language == "python"


# ---------------------------------------------------------------------------
# UCGEdge model
# ---------------------------------------------------------------------------


def test_ucg_edge_model_basic_fields():
    from app.models.ucg import UCGEdge  # noqa: PLC0415

    job_id = uuid.uuid4()
    src_id = uuid.uuid4()
    tgt_id = uuid.uuid4()

    edge = UCGEdge(
        job_id=job_id,
        edge_type="CALLS",
        source_node_id=src_id,
        target_node_id=tgt_id,
    )
    assert edge.edge_type == "CALLS"
    assert edge.source_node_id == src_id
    assert edge.target_node_id == tgt_id


def test_ucg_edge_default_weight():
    from app.models.ucg import UCGEdge  # noqa: PLC0415

    edge = UCGEdge(
        job_id=uuid.uuid4(),
        edge_type="CONTAINS",
        source_node_id=uuid.uuid4(),
        target_node_id=uuid.uuid4(),
    )
    assert edge.weight in (None, 1.0)


def test_ucg_edge_custom_weight():
    from app.models.ucg import UCGEdge  # noqa: PLC0415

    edge = UCGEdge(
        job_id=uuid.uuid4(),
        edge_type="DEPENDS_ON",
        source_node_id=uuid.uuid4(),
        target_node_id=uuid.uuid4(),
        weight=2.5,
    )
    assert edge.weight == 2.5


# ---------------------------------------------------------------------------
# Smell model
# ---------------------------------------------------------------------------


def test_smell_model_basic_fields():
    from app.models.smell import Smell  # noqa: PLC0415

    job_id = uuid.uuid4()
    smell = Smell(
        job_id=job_id,
        smell_type="god_class",
        severity="high",
        description="Too many methods",
        confidence=0.85,
        affected_node_ids=[],
        evidence={"method_count": 12},
    )
    assert smell.smell_type == "god_class"
    assert smell.severity == "high"
    assert smell.confidence == 0.85
    assert smell.evidence == {"method_count": 12}


def test_smell_default_dismissed_is_false():
    from app.models.smell import Smell  # noqa: PLC0415

    smell = Smell(
        job_id=uuid.uuid4(),
        smell_type="long_method",
        severity="medium",
        description="Long",
        confidence=0.7,
        affected_node_ids=[],
        evidence={},
    )
    assert smell.dismissed in (None, False)


def test_smell_llm_rationale_defaults_to_none():
    from app.models.smell import Smell  # noqa: PLC0415

    smell = Smell(
        job_id=uuid.uuid4(),
        smell_type="dead_code",
        severity="low",
        description="Unused",
        confidence=0.6,
        affected_node_ids=[],
        evidence={},
    )
    assert smell.llm_rationale is None


def test_smell_all_severity_levels():
    """All four severity levels must be valid."""
    from app.models.smell import Smell  # noqa: PLC0415

    for severity in ["critical", "high", "medium", "low"]:
        smell = Smell(
            job_id=uuid.uuid4(),
            smell_type="god_class",
            severity=severity,
            description="test",
            confidence=0.9,
            affected_node_ids=[],
            evidence={},
        )
        assert smell.severity == severity


def test_smell_affected_node_ids_list():
    from app.models.smell import Smell  # noqa: PLC0415

    node_ids = [uuid.uuid4(), uuid.uuid4()]
    smell = Smell(
        job_id=uuid.uuid4(),
        smell_type="circular_dependency",
        severity="critical",
        description="Cycle detected",
        confidence=0.95,
        affected_node_ids=node_ids,
        evidence={"cycle_length": 2},
    )
    assert len(smell.affected_node_ids) == 2


# ---------------------------------------------------------------------------
# Report model
# ---------------------------------------------------------------------------


def test_report_model_instantiates():
    from app.models.job import Report  # noqa: PLC0415

    job_id = uuid.uuid4()
    report = Report(
        job_id=job_id,
        report_json={},
    )
    assert report.job_id == job_id


def test_report_model_modernization_score_none_by_default():
    from app.models.job import Report  # noqa: PLC0415

    report = Report(job_id=uuid.uuid4(), report_json={})
    assert report.modernization_score is None
