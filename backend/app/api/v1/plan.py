"""
Plan endpoints — refactor plan management.

GET   /plan/{job_id}                   — get refactor plan with all tasks
GET   /plan/{job_id}/tasks             — list plan tasks (paginated)
GET   /plan/{job_id}/tasks/{task_id}   — single task detail
PATCH /plan/{job_id}/tasks/{task_id}   — update task status or notes
POST  /plan/{job_id}/regenerate        — trigger LLM plan regeneration
"""

import uuid
from datetime import UTC, datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.models.job import Job
from app.models.plan import Plan, PlanTask
from app.schemas.job import PaginationMeta
from app.schemas.plan import (
    PlanResponse,
    PlanTaskListResponse,
    PlanTaskResponse,
    PlanTaskSummaryResponse,
    PlanTaskUpdateRequest,
    RegeneratePlanRequest,
    RegeneratePlanResponse,
)

router = APIRouter()

_VALID_STATUS_TRANSITIONS = {
    "pending": {"approved", "rejected"},
    "approved": {"rejected"},
    "rejected": {"approved"},
    "applied": set(),  # Cannot transition out of applied
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_job_or_404(job_id: UUID, db: AsyncSession) -> Job:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "message": f"No job found with ID {job_id}"},
        )
    return job


async def _get_latest_plan(job_id: UUID, db: AsyncSession) -> Plan | None:
    """Return the latest plan version for a job, or None if no plan exists."""
    result = await db.execute(
        select(Plan)
        .where(Plan.job_id == job_id)
        .order_by(Plan.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _task_to_response(task: PlanTask) -> PlanTaskResponse:
    return PlanTaskResponse(
        task_id=task.id,
        title=task.title,
        description=task.description,
        smell_ids=list(task.smell_ids or []),
        affected_files=list(task.affected_files or []),
        refactor_pattern=task.refactor_pattern,
        dependencies=list(task.dependencies or []),
        estimated_hours=task.estimated_hours,
        automated=task.automated,
        status=task.status,
        priority_override=task.priority_override,
        notes=task.notes,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _task_to_summary(task: PlanTask) -> PlanTaskSummaryResponse:
    return PlanTaskSummaryResponse(
        task_id=task.id,
        title=task.title,
        description=task.description,
        smell_ids=list(task.smell_ids or []),
        affected_files=list(task.affected_files or []),
        refactor_pattern=task.refactor_pattern,
        dependencies=list(task.dependencies or []),
        estimated_hours=task.estimated_hours,
        automated=task.automated,
        status=task.status,
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get("/{job_id}", response_model=PlanResponse)
async def get_plan(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> PlanResponse:
    """Get the latest refactor plan for a job including all tasks."""
    await _get_job_or_404(job_id, db)

    plan = await _get_latest_plan(job_id, db)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "plan_not_found", "message": f"No plan found for job {job_id}"},
        )

    tasks_result = await db.execute(
        select(PlanTask)
        .where(PlanTask.plan_id == plan.id)
        .order_by(PlanTask.created_at)
    )
    tasks = tasks_result.scalars().all()
    automated_count = sum(1 for t in tasks if t.automated)

    return PlanResponse(
        plan_id=plan.id,
        job_id=plan.job_id,
        status="draft",
        estimated_effort_hours=plan.estimated_effort_hours,
        risk_level=plan.risk_level,
        task_count=len(tasks),
        automated_task_count=automated_count,
        priority_order=list(plan.priority_order or []),
        created_at=plan.created_at,
        tasks=[_task_to_summary(t) for t in tasks],
    )


@router.get("/{job_id}/tasks", response_model=PlanTaskListResponse)
async def list_tasks(
    job_id: UUID,
    task_status: str | None = None,
    automated: bool | None = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> PlanTaskListResponse:
    """List all tasks for the latest plan with optional status and automation filters."""
    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    offset = (page - 1) * page_size

    await _get_job_or_404(job_id, db)

    plan = await _get_latest_plan(job_id, db)
    if plan is None:
        return PlanTaskListResponse(
            data=[],
            pagination=PaginationMeta(
                page=page, page_size=page_size, total_items=0, total_pages=1,
                has_next=False, has_prev=False,
            ),
        )

    query = select(PlanTask).where(PlanTask.plan_id == plan.id)
    count_query = select(func.count()).select_from(PlanTask).where(PlanTask.plan_id == plan.id)

    if task_status:
        query = query.where(PlanTask.status == task_status.lower())
        count_query = count_query.where(PlanTask.status == task_status.lower())
    if automated is not None:
        query = query.where(PlanTask.automated.is_(automated))
        count_query = count_query.where(PlanTask.automated.is_(automated))

    total_items = (await db.execute(count_query)).scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    tasks_result = await db.execute(
        query.order_by(PlanTask.created_at).offset(offset).limit(page_size)
    )
    tasks = tasks_result.scalars().all()

    return PlanTaskListResponse(
        data=[_task_to_response(t) for t in tasks],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get("/{job_id}/tasks/{task_id}", response_model=PlanTaskResponse)
async def get_task(
    job_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> PlanTaskResponse:
    """Get full detail for a single plan task."""
    await _get_job_or_404(job_id, db)

    result = await db.execute(
        select(PlanTask).where(PlanTask.id == task_id, PlanTask.job_id == job_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "task_not_found", "message": f"No task {task_id} in job {job_id}"},
        )
    return _task_to_response(task)


@router.patch("/{job_id}/tasks/{task_id}", response_model=PlanTaskResponse)
async def update_task(
    job_id: UUID,
    task_id: UUID,
    body: PlanTaskUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> PlanTaskResponse:
    """Update a plan task status (approve/reject) or add reviewer notes."""
    await _get_job_or_404(job_id, db)

    result = await db.execute(
        select(PlanTask).where(PlanTask.id == task_id, PlanTask.job_id == job_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "task_not_found", "message": f"No task {task_id} in job {job_id}"},
        )

    if body.status is not None:
        new_status = body.status.lower()
        allowed_transitions = _VALID_STATUS_TRANSITIONS.get(task.status, set())
        if new_status not in allowed_transitions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_status_transition",
                    "message": (
                        f"Cannot transition task from '{task.status}' to '{new_status}'. "
                        f"Allowed transitions: {sorted(allowed_transitions) or 'none'}"
                    ),
                },
            )
        task.status = new_status

    if body.priority_override is not None:
        task.priority_override = body.priority_override
    if body.notes is not None:
        task.notes = body.notes

    task.updated_at = datetime.now(UTC)
    await db.flush()

    return _task_to_response(task)


@router.post("/{job_id}/regenerate", status_code=status.HTTP_202_ACCEPTED, response_model=RegeneratePlanResponse)
async def regenerate_plan(
    job_id: UUID,
    body: RegeneratePlanRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> RegeneratePlanResponse:
    """
    Queue LLM plan regeneration for a job.

    Creates a new Plan record with an incremented version number and schedules
    the Planner agent to populate it. Requires that smells have been detected.
    """
    from app.models.smell import Smell  # noqa: PLC0415

    await _get_job_or_404(job_id, db)

    # Ensure smells exist before attempting regeneration.
    smell_count = (
        await db.execute(
            select(func.count()).select_from(Smell).where(Smell.job_id == job_id)
        )
    ).scalar_one()
    if smell_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "no_smells",
                "message": "Cannot regenerate plan: no smells have been detected for this job.",
            },
        )

    # Determine the next version number.
    latest_plan = await _get_latest_plan(job_id, db)
    next_version = (latest_plan.version + 1) if latest_plan else 1

    new_plan = Plan(
        id=uuid.uuid4(),
        job_id=job_id,
        version=next_version,
        priority_order=[],
        created_at=datetime.now(UTC),
    )
    db.add(new_plan)
    await db.flush()

    return RegeneratePlanResponse(
        message="Plan regeneration queued",
        job_id=job_id,
        new_plan_id=new_plan.id,
    )
