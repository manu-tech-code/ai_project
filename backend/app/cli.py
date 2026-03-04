"""
ALM Command-Line Interface.

Provides commands for submitting analysis jobs, retrieving results,
and generating reports directly from the terminal without going through
the REST API.

Usage:
    alm analyze --repo /path/to/repo [--label "My Project"]
    alm status --job-id <uuid>
    alm plan --job-id <uuid>
    alm report --job-id <uuid> [--format markdown|json]
    alm api-keys create --label "CI Key" --scopes read write
    alm api-keys list
    alm db upgrade
    alm db downgrade [--revision <rev>]
    alm serve [--host 0.0.0.0] [--port 8000]
"""

import asyncio
import json
import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="alm",
    help="AI Legacy Modernization Platform — CLI",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True)

# Sub-command groups.
api_keys_app = typer.Typer(help="Manage API keys")
db_app = typer.Typer(help="Database migration commands")
app.add_typer(api_keys_app, name="api-keys")
app.add_typer(db_app, name="db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_settings():
    from app.core.config import get_settings  # noqa: PLC0415
    return get_settings()


def _get_db_session():
    """Return an async context manager for a DB session."""
    from app.core.database import AsyncSessionLocal  # noqa: PLC0415
    return AsyncSessionLocal()


def _run(coro):
    """Run a coroutine in the event loop and return its result."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# analyze — submit a new analysis job
# ---------------------------------------------------------------------------


@app.command()
def analyze(
    repo: str = typer.Option(..., "--repo", "-r", help="Path to the repository or archive to analyze"),
    label: str | None = typer.Option(None, "--label", "-l", help="Human-readable job label"),
    languages: str | None = typer.Option(
        None, "--languages",
        help="Comma-separated language filter (e.g. java,python)",
    ),
    severity: str = typer.Option("low", "--severity", help="Minimum smell severity: critical|high|medium|low"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate inputs without creating a job"),
) -> None:
    """
    Submit a new analysis job for a local repository.

    The repo path can be either a directory (will be zipped automatically)
    or an existing .zip/.tar.gz archive.
    """
    repo_path = Path(repo)
    if not repo_path.exists():
        err_console.print(f"[red]Error:[/red] Path does not exist: {repo}")
        raise typer.Exit(code=1)

    settings = _get_settings()
    console.print(f"[bold]ALM Platform[/bold] v{settings.app_version}")
    console.print(f"Analyzing: [cyan]{repo_path.resolve()}[/cyan]")
    if label:
        console.print(f"Label: {label}")

    if dry_run:
        console.print("[yellow]Dry run — no job created.[/yellow]")
        raise typer.Exit(code=0)

    config = {"smell_severity_threshold": severity}
    if languages:
        config["languages"] = [l.strip() for l in languages.split(",")]  # noqa: E741

    async def _submit():
        async with _get_db_session() as db:
            from app.services.analysis import AnalysisService  # noqa: PLC0415

            # Auto-zip directory if a plain directory was provided.
            archive_path = repo_path
            if repo_path.is_dir():
                import shutil  # noqa: E401
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                shutil.make_archive(str(tmp_path.with_suffix("")), "zip", str(repo_path))
                archive_path = tmp_path.with_suffix(".zip")
                console.print(f"Zipped directory to: {archive_path}")

            service = AnalysisService(db)
            job_id = await service.create_job(
                archive_path=archive_path,
                label=label,
                config=config,
            )
            return job_id

    try:
        job_id = _run(_submit())
        console.print("\n[green]Job created successfully![/green]")
        console.print(f"Job ID: [bold]{job_id}[/bold]")
        console.print("\nMonitor progress with:")
        console.print(f"  alm status --job-id {job_id}")
    except Exception as exc:
        err_console.print(f"[red]Failed to create job:[/red] {exc}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# status — get job status
# ---------------------------------------------------------------------------


@app.command()
def status(
    job_id: str = typer.Option(..., "--job-id", "-j", help="Job UUID to query"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Poll status every 5 seconds"),
) -> None:
    """Get the current status and metadata for an analysis job."""

    async def _get_status(jid: uuid.UUID) -> dict:
        async with _get_db_session() as db:
            from app.services.analysis import AnalysisService  # noqa: PLC0415
            service = AnalysisService(db)
            return await service.get_job(jid)

    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        err_console.print(f"[red]Invalid UUID:[/red] {job_id}")
        raise typer.Exit(code=1)

    def _print_status(job_data: dict) -> None:
        status_color = {
            "pending": "yellow", "detecting": "cyan", "mapping": "cyan",
            "analyzing": "cyan", "planning": "cyan", "transforming": "cyan",
            "validating": "cyan", "complete": "green", "failed": "red",
            "cancelled": "dim",
        }.get(job_data.get("status", ""), "white")

        table = Table(title=f"Job {job_id}", show_header=False, box=None)
        table.add_column("Field", style="bold", width=20)
        table.add_column("Value")
        table.add_row("Status", f"[{status_color}]{job_data.get('status')}[/{status_color}]")
        table.add_row("Label", job_data.get("label") or "—")
        table.add_row("Stage", job_data.get("current_stage") or "—")
        table.add_row("Languages", ", ".join(job_data.get("languages") or []) or "—")
        table.add_row("Files", str(job_data.get("file_count") or "—"))
        table.add_row("Created", job_data.get("created_at", ""))
        if job_data.get("error_message"):
            table.add_row("Error", f"[red]{job_data['error_message']}[/red]")
        console.print(table)

    if watch:
        import time
        while True:
            try:
                job_data = _run(_get_status(jid))
                console.clear()
                _print_status(job_data)
                if job_data.get("status") in ("complete", "failed", "cancelled"):
                    break
                console.print("[dim]Refreshing in 5s... (Ctrl+C to stop)[/dim]")
                time.sleep(5)
            except KeyboardInterrupt:
                break
    else:
        try:
            job_data = _run(_get_status(jid))
            _print_status(job_data)
        except Exception as exc:
            err_console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# plan — display the refactor plan for a job
# ---------------------------------------------------------------------------


@app.command()
def plan(
    job_id: str = typer.Option(..., "--job-id", "-j", help="Job UUID to query"),
) -> None:
    """Display the refactor plan for a completed analysis job."""

    async def _get_plan(jid: uuid.UUID) -> tuple[dict | None, list]:
        async with _get_db_session() as db:
            from sqlalchemy import select  # noqa: PLC0415

            from app.models.plan import Plan, PlanTask  # noqa: PLC0415
            plan_result = await db.execute(
                select(Plan).where(Plan.job_id == jid).order_by(Plan.version.desc()).limit(1)
            )
            plan_obj = plan_result.scalar_one_or_none()
            if plan_obj is None:
                return None, []
            tasks_result = await db.execute(
                select(PlanTask).where(PlanTask.plan_id == plan_obj.id)
            )
            tasks = tasks_result.scalars().all()
            plan_data = {
                "plan_id": str(plan_obj.id),
                "estimated_effort_hours": plan_obj.estimated_effort_hours,
                "risk_level": plan_obj.risk_level,
                "version": plan_obj.version,
            }
            tasks_data = [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "pattern": t.refactor_pattern,
                    "status": t.status,
                    "automated": "yes" if t.automated else "no",
                    "hours": t.estimated_hours,
                }
                for t in tasks
            ]
            return plan_data, tasks_data

    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        err_console.print(f"[red]Invalid UUID:[/red] {job_id}")
        raise typer.Exit(code=1)

    plan_data, tasks_data = _run(_get_plan(jid))
    if plan_data is None:
        console.print("[yellow]No plan found for this job.[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"\n[bold]Refactor Plan[/bold] (v{plan_data['version']})")
    console.print(f"Estimated effort: {plan_data.get('estimated_effort_hours') or '?'} hours")
    console.print(f"Risk level: {plan_data.get('risk_level') or '?'}\n")

    table = Table(title="Plan Tasks", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", min_width=30)
    table.add_column("Pattern", width=30)
    table.add_column("Status", width=10)
    table.add_column("Auto?", width=6)
    table.add_column("Hours", width=6)

    for i, task in enumerate(tasks_data, 1):
        status_style = {"pending": "yellow", "approved": "green", "rejected": "red", "applied": "dim"}.get(
            task["status"], "white"
        )
        table.add_row(
            str(i),
            task["title"],
            task["pattern"],
            f"[{status_style}]{task['status']}[/{status_style}]",
            task["automated"],
            str(task["hours"] or "—"),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# report — generate and display a report
# ---------------------------------------------------------------------------


@app.command()
def report(
    job_id: str = typer.Option(..., "--job-id", "-j", help="Job UUID to query"),
    fmt: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown|json"),
    output: str | None = typer.Option(None, "--output", "-o", help="Write output to file"),
) -> None:
    """Generate and display the modernization report for a completed job."""

    async def _get_report(jid: uuid.UUID) -> str:
        async with _get_db_session() as db:
            from sqlalchemy import select  # noqa: PLC0415

            from app.models.job import Job, Report  # noqa: PLC0415
            job_result = await db.execute(select(Job).where(Job.id == jid))
            job = job_result.scalar_one_or_none()
            if job is None:
                raise ValueError(f"Job {jid} not found")

            # Check cache.
            report_result = await db.execute(select(Report).where(Report.job_id == jid))
            cached = report_result.scalar_one_or_none()

            if fmt == "json":
                if cached and cached.report_json:
                    return json.dumps(cached.report_json, indent=2)
                from app.api.v1.report import _build_report_json  # noqa: PLC0415
                data = await _build_report_json(job, db)
                return json.dumps(data, indent=2)
            else:
                if cached and cached.report_markdown:
                    return cached.report_markdown
                from app.api.v1.report import (  # noqa: PLC0415
                    _build_report_json,
                    _report_json_to_markdown,
                )
                data = await _build_report_json(job, db)
                return _report_json_to_markdown(data, job)

    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        err_console.print(f"[red]Invalid UUID:[/red] {job_id}")
        raise typer.Exit(code=1)

    try:
        content = _run(_get_report(jid))
    except Exception as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if output:
        Path(output).write_text(content, encoding="utf-8")
        console.print(f"[green]Report written to:[/green] {output}")
    else:
        if fmt == "markdown":
            # Use rich Markdown rendering if available.
            try:
                from rich.markdown import Markdown  # noqa: PLC0415
                console.print(Markdown(content))
            except Exception:
                print(content)
        else:
            print(content)


# ---------------------------------------------------------------------------
# API key management sub-commands
# ---------------------------------------------------------------------------


@api_keys_app.command("create")
def api_keys_create(
    label: str = typer.Option(..., "--label", "-l", help="Key label"),
    scopes: list[str] = typer.Option(["read", "write"], "--scopes", "-s", help="Authorization scopes"),
    expires: str | None = typer.Option(None, "--expires", help="Expiry date (ISO8601)"),
    rate_limit: int = typer.Option(100, "--rate-limit", help="Requests per minute"),
) -> None:
    """Create a new API key."""
    from datetime import datetime  # noqa: PLC0415

    expires_at = None
    if expires:
        try:
            expires_at = datetime.fromisoformat(expires)
        except ValueError:
            err_console.print(f"[red]Invalid expires date:[/red] {expires}")
            raise typer.Exit(code=1)

    async def _create():
        async with _get_db_session() as db:
            import uuid as _uuid  # noqa: PLC0415
            from datetime import UTC  # noqa: PLC0415

            from app.core.security import generate_api_key, hash_api_key  # noqa: PLC0415
            from app.models.api_key import APIKey  # noqa: PLC0415

            raw_key = generate_api_key()
            key_hash = hash_api_key(raw_key)
            api_key = APIKey(
                id=_uuid.uuid4(),
                label=label,
                key_hash=key_hash,
                key_prefix=raw_key[:12],
                scopes=scopes,
                rate_limit_per_minute=rate_limit,
                expires_at=expires_at,
                created_at=datetime.now(UTC),
            )
            db.add(api_key)
            await db.flush()
            return raw_key, str(api_key.id)

    try:
        raw_key, key_id = _run(_create())
        console.print("\n[green]API key created![/green]")
        console.print(f"Key ID:   [bold]{key_id}[/bold]")
        console.print(f"Key:      [bold yellow]{raw_key}[/bold yellow]")
        console.print(f"Scopes:   {', '.join(scopes)}")
        console.print("\n[red]Store this key now — it will not be shown again.[/red]")
    except Exception as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)


@api_keys_app.command("list")
def api_keys_list() -> None:
    """List all API keys (without raw values)."""

    async def _list():
        async with _get_db_session() as db:
            from sqlalchemy import select  # noqa: PLC0415

            from app.models.api_key import APIKey  # noqa: PLC0415
            result = await db.execute(select(APIKey).order_by(APIKey.created_at.desc()))
            return result.scalars().all()

    try:
        keys = _run(_list())
    except Exception as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if not keys:
        console.print("[yellow]No API keys found.[/yellow]")
        return

    table = Table(title="API Keys", show_lines=True)
    table.add_column("ID", style="dim", width=36)
    table.add_column("Label", min_width=20)
    table.add_column("Prefix", width=14)
    table.add_column("Scopes", width=20)
    table.add_column("Revoked", width=8)
    table.add_column("Created", width=20)

    for k in keys:
        revoked_str = "[red]yes[/red]" if k.revoked else "[green]no[/green]"
        table.add_row(
            str(k.id),
            k.label,
            k.key_prefix,
            ", ".join(k.scopes or []),
            revoked_str,
            k.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Database migration sub-commands
# ---------------------------------------------------------------------------


@db_app.command("upgrade")
def db_upgrade(
    revision: str = typer.Option("head", "--revision", "-r", help="Alembic revision target"),
) -> None:
    """Run Alembic database migrations forward to the target revision."""
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    alembic_cfg = Config("alembic.ini")
    try:
        command.upgrade(alembic_cfg, revision)
        console.print(f"[green]Database upgraded to revision:[/green] {revision}")
    except Exception as exc:
        err_console.print(f"[red]Migration failed:[/red] {exc}")
        raise typer.Exit(code=1)


@db_app.command("downgrade")
def db_downgrade(
    revision: str = typer.Option("-1", "--revision", "-r", help="Alembic revision target (default: -1)"),
) -> None:
    """Run Alembic database migrations backward to the target revision."""
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    alembic_cfg = Config("alembic.ini")
    try:
        command.downgrade(alembic_cfg, revision)
        console.print(f"[green]Database downgraded to revision:[/green] {revision}")
    except Exception as exc:
        err_console.print(f"[red]Migration failed:[/red] {exc}")
        raise typer.Exit(code=1)


@db_app.command("current")
def db_current() -> None:
    """Show the current Alembic revision applied to the database."""
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    alembic_cfg = Config("alembic.ini")
    command.current(alembic_cfg)


@db_app.command("history")
def db_history() -> None:
    """Show the Alembic migration history."""
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    alembic_cfg = Config("alembic.ini")
    command.history(alembic_cfg)


# ---------------------------------------------------------------------------
# serve — start the uvicorn development server
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable hot reload (development)"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of worker processes"),
) -> None:
    """Start the ALM Backend API server using uvicorn."""
    import uvicorn  # noqa: PLC0415

    console.print(f"[bold]Starting ALM Backend[/bold] on {host}:{port}")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
