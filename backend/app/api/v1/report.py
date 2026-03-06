"""
Report endpoints — JSON report, PDF export, Markdown export, and list.

GET /report                   — list all completed reports (paginated)
GET /report/{job_id}          — full JSON modernization report
GET /report/{job_id}/pdf      — PDF export (streamed)
GET /report/{job_id}/markdown — Markdown export
"""

import io
from datetime import UTC, datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.core.cache import cache_get, cache_set
from app.models.job import Job, Report
from app.models.patch import Patch, ValidationResult
from app.models.plan import Plan, PlanTask
from app.models.smell import Smell

router = APIRouter()


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


def _compute_modernization_score(
    total_smells: int,
    critical_smells: int,
    high_smells: int,
    patches_generated: int,
    patches_passed: int,
) -> int:
    """
    Compute the modernization score (0-100).

    100 = no smells detected and all patches pass validation.
    Score is penalised by smell count weighted by severity and validation failures.
    """
    score = 100
    score -= critical_smells * 10
    score -= high_smells * 4
    score -= max(0, (total_smells - critical_smells - high_smells)) * 1

    if patches_generated > 0:
        pass_rate = patches_passed / patches_generated
        validation_penalty = int((1 - pass_rate) * 20)
        score -= validation_penalty

    return max(0, min(100, score))


async def _build_report_json(job: Job, db: AsyncSession) -> dict:
    """Assemble the full report JSON from the database for a completed job."""
    # Smell statistics.
    smells_result = await db.execute(
        select(Smell).where(Smell.job_id == job.id, Smell.dismissed.is_(False))
    )
    smells = smells_result.scalars().all()

    by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_type: dict[str, int] = {}
    for s in smells:
        by_severity[s.severity] = by_severity.get(s.severity, 0) + 1
        by_type[s.smell_type] = by_type.get(s.smell_type, 0) + 1

    # Plan statistics.
    plan_result = await db.execute(
        select(Plan).where(Plan.job_id == job.id).order_by(Plan.version.desc()).limit(1)
    )
    plan = plan_result.scalar_one_or_none()

    task_count = 0
    automated_task_count = 0
    estimated_effort = 0.0
    risk_level = "low"

    if plan:
        tasks_result = await db.execute(
            select(PlanTask).where(PlanTask.plan_id == plan.id)
        )
        tasks = tasks_result.scalars().all()
        task_count = len(tasks)
        automated_task_count = sum(1 for t in tasks if t.automated)
        estimated_effort = plan.estimated_effort_hours or 0.0
        risk_level = plan.risk_level or "low"

    # Patch statistics.
    patches_result = await db.execute(
        select(Patch).where(Patch.job_id == job.id)
    )
    patches = patches_result.scalars().all()
    patches_generated = len(patches)

    patches_passed = 0
    by_language: dict[str, int] = {}
    by_patch_type: dict[str, int] = {}
    for patch in patches:
        by_language[patch.language] = by_language.get(patch.language, 0) + 1
        by_patch_type[patch.patch_type] = by_patch_type.get(patch.patch_type, 0) + 1

    if patches_generated > 0:
        # Batch-fetch the latest validation result per patch in 2 queries (no N+1).
        patch_ids = [p.id for p in patches]
        latest_vr_subq = (
            select(
                ValidationResult.patch_id,
                func.max(ValidationResult.created_at).label("max_created_at"),
            )
            .where(ValidationResult.patch_id.in_(patch_ids))
            .group_by(ValidationResult.patch_id)
            .subquery()
        )
        vr_rows = await db.execute(
            select(ValidationResult.patch_id, ValidationResult.passed)
            .join(
                latest_vr_subq,
                (ValidationResult.patch_id == latest_vr_subq.c.patch_id)
                & (ValidationResult.created_at == latest_vr_subq.c.max_created_at),
            )
        )
        patches_passed = sum(1 for row in vr_rows.all() if row.passed is True)

    validation_pass_rate = (
        round(patches_passed / patches_generated, 3) if patches_generated > 0 else 0.0
    )

    total_smells = len(smells)
    critical_smells = by_severity.get("critical", 0)
    high_smells = by_severity.get("high", 0)
    score = _compute_modernization_score(
        total_smells, critical_smells, high_smells, patches_generated, patches_passed
    )

    # Build recommendations from top critical smells.
    recommendations = []
    critical_smell_list = sorted(
        [s for s in smells if s.severity == "critical"],
        key=lambda s: s.confidence,
        reverse=True,
    )
    for i, smell in enumerate(critical_smell_list[:5], start=1):
        recommendations.append({
            "priority": i,
            "title": f"Address {smell.smell_type.replace('_', ' ').title()} smell",
            "impact": smell.description[:200] if smell.description else "",
            "effort_hours": 4.0 * (smell.confidence or 0.5),
        })

    return {
        "report_id": None,  # filled in by caller
        "job_id": str(job.id),
        "generated_at": datetime.now(UTC).isoformat(),
        "job_label": job.label,
        "executive_summary": {
            "total_files_analyzed": job.file_count or 0,
            "total_lines_analyzed": job.total_lines or 0,
            "languages": job.languages or [],
            "smells_found": total_smells,
            "smells_critical": critical_smells,
            "patches_generated": patches_generated,
            "patches_validated": patches_generated,
            "patches_passed_validation": patches_passed,
            "estimated_tech_debt_hours": round(estimated_effort, 1),
            "modernization_score": score,
        },
        "smell_breakdown": {
            "by_severity": by_severity,
            "by_type": by_type,
        },
        "plan_summary": {
            "total_tasks": task_count,
            "automated_tasks": automated_task_count,
            "estimated_effort_hours": round(estimated_effort, 1),
            "risk_level": risk_level,
        },
        "patch_summary": {
            "total_patches": patches_generated,
            "by_language": by_language,
            "by_type": by_patch_type,
            "validation_pass_rate": validation_pass_rate,
        },
        "recommendations": recommendations,
        "similar_jobs": [],
    }


def _report_json_to_markdown(report_data: dict, job: Job) -> str:
    """Convert the report JSON to a readable Markdown document."""
    summary = report_data.get("executive_summary", {})
    smell_breakdown = report_data.get("smell_breakdown", {})
    plan_summary = report_data.get("plan_summary", {})
    patch_summary = report_data.get("patch_summary", {})

    lines = [
        "# ALM Modernization Report",
        "",
        f"**Job:** {job.label or str(job.id)}",
        f"**Generated:** {report_data.get('generated_at', '')}",
        f"**Modernization Score:** {summary.get('modernization_score', 'N/A')} / 100",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Files Analyzed | {summary.get('total_files_analyzed', 0)} |",
        f"| Lines Analyzed | {summary.get('total_lines_analyzed', 0):,} |",
        f"| Languages | {', '.join(summary.get('languages', []))} |",
        f"| Smells Found | {summary.get('smells_found', 0)} |",
        f"| Critical Smells | {summary.get('smells_critical', 0)} |",
        f"| Patches Generated | {summary.get('patches_generated', 0)} |",
        f"| Patches Passed Validation | {summary.get('patches_passed_validation', 0)} |",
        f"| Estimated Tech Debt | {summary.get('estimated_tech_debt_hours', 0)} hours |",
        "",
        "---",
        "",
        "## Smell Breakdown",
        "",
        "### By Severity",
        "",
    ]
    for sev, count in smell_breakdown.get("by_severity", {}).items():
        lines.append(f"- **{sev.capitalize()}**: {count}")

    lines.extend([
        "",
        "### By Type",
        "",
    ])
    for smell_type, count in smell_breakdown.get("by_type", {}).items():
        lines.append(f"- `{smell_type}`: {count}")

    lines.extend([
        "",
        "---",
        "",
        "## Refactor Plan",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Tasks | {plan_summary.get('total_tasks', 0)} |",
        f"| Automated Tasks | {plan_summary.get('automated_tasks', 0)} |",
        f"| Estimated Effort | {plan_summary.get('estimated_effort_hours', 0)} hours |",
        f"| Risk Level | {plan_summary.get('risk_level', 'unknown').capitalize()} |",
        "",
        "---",
        "",
        "## Patch Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Patches | {patch_summary.get('total_patches', 0)} |",
        f"| Validation Pass Rate | {patch_summary.get('validation_pass_rate', 0) * 100:.1f}% |",
        "",
        "---",
        "",
        "## Recommendations",
        "",
    ])

    for rec in report_data.get("recommendations", []):
        lines.extend([
            f"### {rec.get('priority', '')}. {rec.get('title', '')}",
            "",
            f"{rec.get('impact', '')}",
            "",
            f"**Estimated effort:** {rec.get('effort_hours', 0):.1f} hours",
            "",
        ])

    lines.extend([
        "---",
        "",
        "*Generated by ALM Platform v0.2.0*",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get("", response_model=dict)
async def list_reports(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> dict:
    """List all completed modernization reports (paginated)."""
    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    offset = (page - 1) * page_size

    # Reports are immutable once generated — cache the list for 5 minutes.
    cache_key = f"alm:report:list:p{page}:ps{page_size}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    count_result = await db.execute(select(func.count()).select_from(Report))
    total_items = count_result.scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    reports_result = await db.execute(
        select(Report)
        .order_by(Report.generated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    reports = reports_result.scalars().all()

    # Load job labels for the list.
    job_ids = [r.job_id for r in reports]
    jobs_by_id: dict[UUID, Job] = {}
    if job_ids:
        jobs_result = await db.execute(select(Job).where(Job.id.in_(job_ids)))
        jobs_by_id = {j.id: j for j in jobs_result.scalars().all()}

    data = []
    for report in reports:
        job = jobs_by_id.get(report.job_id)
        data.append({
            "report_id": str(report.id),
            "job_id": str(report.job_id),
            "job_label": job.label if job else None,
            "generated_at": report.generated_at.isoformat(),
            "modernization_score": report.modernization_score,
            "total_smells": report.total_smells,
            "critical_smells": report.critical_smells,
            "patches_generated": report.patches_generated,
            "patches_passed": report.patches_passed,
            "estimated_hours": report.estimated_hours,
        })

    result = {
        "data": data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }
    await cache_set(cache_key, result, ttl=300)
    return result


@router.get("/{job_id}", response_model=dict)
async def get_report(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> dict:
    """
    Get the complete modernization report for a job as JSON.

    If a cached report exists in the reports table, it is returned directly.
    Otherwise the report is computed on-the-fly from the current DB state
    and cached for future requests.

    An additional Redis layer caches the final JSON for 5 minutes so that
    repeated GETs don't even touch PostgreSQL.
    """
    job = await _get_job_or_404(job_id, db)

    # Redis fast path — avoids DB hit entirely for hot reports.
    redis_key = f"alm:report:{job_id}"
    redis_cached = await cache_get(redis_key)
    if redis_cached:
        return redis_cached

    # Check for cached report in the reports table.
    cached_result = await db.execute(
        select(Report).where(Report.job_id == job_id)
    )
    cached_report = cached_result.scalar_one_or_none()

    if cached_report and cached_report.report_json:
        report_data = dict(cached_report.report_json)
        report_data["report_id"] = str(cached_report.id)
        await cache_set(redis_key, report_data, ttl=300)
        return report_data

    # Compute report on-the-fly.
    report_data = await _build_report_json(job, db)

    # Cache it.
    import uuid as _uuid  # noqa: PLC0415
    summary = report_data.get("executive_summary", {})
    new_report = Report(
        id=_uuid.uuid4(),
        job_id=job_id,
        generated_at=datetime.now(UTC),
        report_json=report_data,
        report_markdown=_report_json_to_markdown(report_data, job),
        modernization_score=summary.get("modernization_score"),
        total_smells=summary.get("smells_found"),
        critical_smells=summary.get("smells_critical"),
        patches_generated=summary.get("patches_generated"),
        patches_passed=summary.get("patches_passed_validation"),
        estimated_hours=summary.get("estimated_tech_debt_hours"),
    )
    db.add(new_report)
    try:
        await db.flush()
    except Exception:
        # Report may already exist due to race condition — ignore.
        await db.rollback()

    report_data["report_id"] = str(new_report.id)
    await cache_set(redis_key, report_data, ttl=300)
    return report_data


@router.get("/{job_id}/pdf")
async def export_report_pdf(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> StreamingResponse:
    """
    Export the modernization report as a PDF document (streamed binary).

    Generates a simple PDF from the Markdown report. Requires the ``markdown``
    and ``weasyprint`` packages; falls back to plain text if unavailable.
    """
    job = await _get_job_or_404(job_id, db)

    # Get or generate the markdown content.
    cached_result = await db.execute(select(Report).where(Report.job_id == job_id))
    cached_report = cached_result.scalar_one_or_none()

    if cached_report and cached_report.report_markdown:
        md_content = cached_report.report_markdown
    else:
        report_data = await _build_report_json(job, db)
        md_content = _report_json_to_markdown(report_data, job)

    # Attempt PDF generation with weasyprint; fall back to HTML response.
    try:
        import markdown  # type: ignore[import]
        import weasyprint  # type: ignore[import]

        html_content = markdown.markdown(
            md_content,
            extensions=["tables", "fenced_code"],
        )
        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
  h1 {{ color: #2c3e50; }} h2 {{ color: #34495e; }} h3 {{ color: #555; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background-color: #f2f2f2; }}
  code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; }}
</style></head><body>{html_content}</body></html>"""

        pdf_bytes = weasyprint.HTML(string=full_html).write_pdf()
        return StreamingResponse(
            content=io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="alm-report-{job_id}.pdf"'
            },
        )
    except ImportError:
        # weasyprint not available — return the Markdown as plain text.
        return StreamingResponse(
            content=io.BytesIO(md_content.encode("utf-8")),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="alm-report-{job_id}.md"',
                "X-Fallback": "weasyprint-not-installed",
            },
        )


@router.get("/{job_id}/markdown")
async def export_report_markdown(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> Response:
    """Export the modernization report as a Markdown document."""
    job = await _get_job_or_404(job_id, db)

    cached_result = await db.execute(select(Report).where(Report.job_id == job_id))
    cached_report = cached_result.scalar_one_or_none()

    if cached_report and cached_report.report_markdown:
        md_content = cached_report.report_markdown
    else:
        report_data = await _build_report_json(job, db)
        md_content = _report_json_to_markdown(report_data, job)

    return Response(
        content=md_content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="alm-report-{job_id}.md"'
        },
    )
