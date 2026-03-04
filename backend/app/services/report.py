"""
Report service — assembles modernization reports from job data,
generates Markdown exports.
"""

import uuid as _uuid_mod
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, Report
from app.models.patch import Patch, ValidationResult
from app.models.plan import Plan, PlanTask
from app.models.smell import Smell

# Severity penalty weights for modernization score computation
SEVERITY_PENALTY = {
    "critical": 15,
    "high": 8,
    "medium": 3,
    "low": 1,
}


class ReportService:
    """
    Assembles and exports modernization reports for completed jobs.
    Reads from jobs, smells, plans, patches, and validation_results tables.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def generate_report(self, job_id: UUID) -> dict:
        """
        Build the full report JSON for a completed job.
        Computes modernization_score = max(0, 100 - weighted smell penalty).
        Persists the report to the reports table (upsert by job_id).
        """
        db = self._db

        # Load job
        job_result = await db.execute(select(Job).where(Job.id == job_id))
        job = job_result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Load smells
        smell_result = await db.execute(
            select(Smell).where(Smell.job_id == job_id)
        )
        smells = list(smell_result.scalars().all())

        # Load plan
        plan_result = await db.execute(
            select(Plan).where(Plan.job_id == job_id).order_by(Plan.version.desc())
        )
        plan = plan_result.scalar_one_or_none()

        # Load plan tasks
        tasks: list[PlanTask] = []
        if plan:
            task_result = await db.execute(
                select(PlanTask).where(PlanTask.plan_id == plan.id)
            )
            tasks = list(task_result.scalars().all())

        # Load patches
        patch_result = await db.execute(
            select(Patch).where(Patch.job_id == job_id)
        )
        patches = list(patch_result.scalars().all())

        # Load validation results
        val_result = await db.execute(
            select(ValidationResult).where(ValidationResult.job_id == job_id)
        )
        validations = list(val_result.scalars().all())

        # --- Compute statistics ---
        total_smells = len(smells)
        smells_by_severity: dict[str, int] = {}
        smells_by_type: dict[str, int] = {}
        for s in smells:
            smells_by_severity[s.severity] = smells_by_severity.get(s.severity, 0) + 1
            smells_by_type[s.smell_type] = smells_by_type.get(s.smell_type, 0) + 1

        critical_smells = smells_by_severity.get("critical", 0)
        high_smells = smells_by_severity.get("high", 0)

        # Modernization score: start at 100, subtract penalties for each smell
        penalty = sum(
            SEVERITY_PENALTY.get(s.severity, 1) for s in smells
        )
        modernization_score = max(0, min(100, 100 - penalty))

        # Patch statistics
        patches_generated = len(patches)
        patch_val_map: dict[UUID, ValidationResult] = {v.patch_id: v for v in validations}
        patches_passed = sum(
            1 for p in patches
            if patch_val_map.get(p.id) and patch_val_map[p.id].passed
        )

        # Effort estimate
        estimated_hours = plan.estimated_effort_hours if plan else 0.0

        # --- Build report JSON ---
        report_json = {
            "job_id": str(job_id),
            "generated_at": datetime.now(UTC).isoformat(),
            "job_label": job.label or str(job_id),
            "languages": job.languages or [],
            "file_count": job.file_count,
            "total_lines": job.total_lines,
            "modernization_score": modernization_score,
            "ucg": {
                "node_count": job.ucg_node_count or 0,
                "edge_count": job.ucg_edge_count or 0,
            },
            "smells": {
                "total": total_smells,
                "by_severity": smells_by_severity,
                "by_type": smells_by_type,
                "critical": critical_smells,
                "high": high_smells,
                "items": [
                    {
                        "id": str(s.id),
                        "type": s.smell_type,
                        "severity": s.severity,
                        "description": s.description,
                        "confidence": s.confidence,
                        "llm_rationale": s.llm_rationale,
                        "dismissed": s.dismissed,
                    }
                    for s in smells
                ],
            },
            "plan": {
                "id": str(plan.id) if plan else None,
                "version": plan.version if plan else None,
                "estimated_effort_hours": estimated_hours,
                "risk_level": plan.risk_level if plan else None,
                "task_count": len(tasks),
                "tasks": [
                    {
                        "id": str(t.id),
                        "title": t.title,
                        "pattern": t.refactor_pattern,
                        "estimated_hours": t.estimated_hours,
                        "automated": t.automated,
                        "status": t.status,
                    }
                    for t in tasks
                ],
            },
            "patches": {
                "generated": patches_generated,
                "passed_validation": patches_passed,
                "items": [
                    {
                        "id": str(p.id),
                        "file_path": p.file_path,
                        "language": p.language,
                        "patch_type": p.patch_type,
                        "status": p.status,
                        "validation_passed": (
                            patch_val_map[p.id].passed if p.id in patch_val_map else None
                        ),
                    }
                    for p in patches
                ],
            },
            "validation": {
                "total": len(validations),
                "passed": sum(1 for v in validations if v.passed),
                "failed": sum(1 for v in validations if not v.passed),
            },
        }

        # --- Persist report ---
        now = datetime.now(UTC)
        report_data = {
            "job_id": job_id,
            "generated_at": now,
            "report_json": report_json,
            "report_markdown": None,  # generated on demand
            "modernization_score": modernization_score,
            "total_smells": total_smells,
            "critical_smells": critical_smells,
            "patches_generated": patches_generated,
            "patches_passed": patches_passed,
            "estimated_hours": estimated_hours,
        }

        # Upsert: check if report already exists
        existing_result = await db.execute(
            select(Report).where(Report.job_id == job_id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            stmt = (
                update(Report)
                .where(Report.job_id == job_id)
                .values(**{k: v for k, v in report_data.items() if k != "job_id"})
            )
            await db.execute(stmt)
        else:
            report_data["id"] = _uuid_mod.uuid4()
            await db.execute(insert(Report), [report_data])

        await db.commit()

        return report_json

    async def export_markdown(self, job_id: UUID) -> str:
        """Convert the report JSON to a Markdown document."""
        report_json = await self.generate_report(job_id)
        return _render_markdown(report_json)

    async def export_pdf(self, job_id: UUID) -> bytes:
        """Render the report as a PDF binary using markdown -> HTML -> PDF."""
        markdown_text = await self.export_markdown(job_id)
        return _render_pdf(markdown_text)


# ── Rendering helpers ─────────────────────────────────────────────────────────

def _render_markdown(report: dict) -> str:
    """Render a report dict as a Markdown document."""
    now_str = datetime.now(UTC).strftime("%Y-%m-%d")
    job_id = report.get("job_id", "")
    label = report.get("job_label", job_id)
    score = report.get("modernization_score", 0)
    languages = ", ".join(report.get("languages", [])) or "unknown"
    file_count = report.get("file_count") or "unknown"
    total_lines = report.get("total_lines") or "unknown"

    ucg = report.get("ucg", {})
    smells_data = report.get("smells", {})
    plan_data = report.get("plan", {})
    patches_data = report.get("patches", {})
    validation_data = report.get("validation", {})

    lines = [
        "---",
        f"title: \"ALM Modernization Report — {label}\"",
        f"job_id: \"{job_id}\"",
        f"generated_at: \"{now_str}\"",
        f"modernization_score: {score}",
        "---",
        "",
        "# ALM Modernization Report",
        f"**Job:** `{label}`  ",
        f"**Generated:** {now_str}  ",
        f"**Modernization Score:** {score}/100",
        "",
        "## Executive Summary",
        "",
        f"This report covers the analysis of a **{languages}** codebase comprising "
        f"**{file_count} files** and **{total_lines} lines** of code.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Modernization Score | **{score}/100** |",
        f"| Languages Detected | {languages} |",
        f"| Files Analyzed | {file_count} |",
        f"| Total Lines | {total_lines} |",
        f"| UCG Nodes | {ucg.get('node_count', 0)} |",
        f"| UCG Edges | {ucg.get('edge_count', 0)} |",
        f"| Smells Detected | {smells_data.get('total', 0)} |",
        f"| Patches Generated | {patches_data.get('generated', 0)} |",
        f"| Patches Passed | {patches_data.get('passed_validation', 0)} |",
        "",
        "## UCG Statistics",
        "",
        f"The Universal Code Graph contains **{ucg.get('node_count', 0)} nodes** "
        f"and **{ucg.get('edge_count', 0)} edges**.",
        "",
        "## Smell Report",
        "",
    ]

    by_severity = smells_data.get("by_severity", {})
    lines += [
        "| Severity | Count |",
        "|---|---|",
    ]
    for sev in ("critical", "high", "medium", "low"):
        cnt = by_severity.get(sev, 0)
        if cnt:
            lines.append(f"| {sev.title()} | {cnt} |")

    lines += ["", "### Smell Details", "", "| Type | Severity | Description |", "|---|---|---|"]
    for smell in smells_data.get("items", [])[:20]:  # cap at 20 in report
        desc_short = (smell.get("description") or "")[:80].replace("|", "\\|")
        lines.append(
            f"| {smell.get('type', '')} | {smell.get('severity', '')} | {desc_short} |"
        )

    lines += [
        "",
        "## Refactor Roadmap",
        "",
        f"**Risk Level:** {plan_data.get('risk_level', 'unknown').title()}  ",
        f"**Estimated Effort:** {plan_data.get('estimated_effort_hours', 0):.1f} hours  ",
        f"**Total Tasks:** {plan_data.get('task_count', 0)}",
        "",
        "| # | Title | Pattern | Effort (h) | Automated |",
        "|---|---|---|---|---|",
    ]
    for i, task in enumerate(plan_data.get("tasks", [])[:15], 1):
        automated = "Yes" if task.get("automated") else "No"
        title = (task.get("title") or "")[:60].replace("|", "\\|")
        lines.append(
            f"| {i} | {title} | {task.get('pattern', '')} "
            f"| {task.get('estimated_hours', 0):.1f} | {automated} |"
        )

    lines += [
        "",
        "## Patch Summary",
        "",
        f"- Patches generated: **{patches_data.get('generated', 0)}**",
        f"- Patches passed validation: **{patches_data.get('passed_validation', 0)}**",
        f"- Validation runs: {validation_data.get('total', 0)} "
        f"({validation_data.get('passed', 0)} passed, {validation_data.get('failed', 0)} failed)",
        "",
        "## Validation Results",
        "",
        "| File | Language | Type | Validation |",
        "|---|---|---|---|",
    ]
    for p in patches_data.get("items", [])[:10]:
        val = "PASS" if p.get("validation_passed") else (
            "FAIL" if p.get("validation_passed") is False else "N/A"
        )
        lines.append(
            f"| {p.get('file_path', '')[:50]} | {p.get('language', '')} "
            f"| {p.get('patch_type', '')} | {val} |"
        )

    lines += [
        "",
        "---",
        f"*Generated by ALM Platform v0.2.0 on {now_str}*",
    ]

    return "\n".join(lines)


def _render_pdf(markdown_text: str) -> bytes:
    """
    Render Markdown as PDF bytes.
    Tries weasyprint -> reportlab -> returns UTF-8 bytes as fallback.
    """
    try:
        import markdown as md_lib
        from weasyprint import HTML
        html_content = f"""
        <html><head><style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        td, th {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        code {{ background: #f4f4f4; padding: 2px 4px; }}
        </style></head><body>
        {md_lib.markdown(markdown_text, extensions=['tables'])}
        </body></html>
        """
        return HTML(string=html_content).write_pdf()
    except ImportError:
        pass

    # Fallback: return the markdown as UTF-8 bytes
    return markdown_text.encode("utf-8")
