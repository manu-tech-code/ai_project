"""
Agent 5: Transformer (Patch Generator)

Generates concrete code patches for all automated plan tasks using LLM.

For complex refactors, uses Claude's structured output for higher accuracy.
Output patches are stored as unified diffs in the patches table.

Output:
  - Inserts into patches table
  - patch_count is updated by the calling endpoint, not this agent
  - Returns list[CodePatch]
"""

import asyncio
import difflib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import insert, select, update

from app.agents.base import BaseAgent, JobContext
from app.models.job import Job
from app.models.patch import Patch
from app.models.plan import PlanTask

# Prompt templates for each refactor pattern
PROMPT_TEMPLATES: dict[str, str] = {
    "extract_class": """
<task>Refactor the following class by extracting focused service classes.</task>
<context>
File: {file_path}
Class: {class_name}
Current Description: {description}
Evidence: {evidence}
</context>
<constraints>
- Preserve all public method signatures (no breaking changes)
- Keep the original class thin; delegate to extracted service(s)
- Use constructor injection for dependencies
- Follow the existing code style and naming conventions
- Do not change package/module structure unless necessary
</constraints>
<output_format>
Output a unified diff patch in this exact format:
--- a/{file_path}
+++ b/{file_path}
@@ ... @@
[patch lines]

If new files are needed, add them as additional diff sections.
Output only the diff. No explanations.
</output_format>
""",

    "extract_method": """
<task>Decompose the following long method into smaller, focused methods.</task>
<context>
File: {file_path}
Method: {class_name}
Description: {description}
Evidence: {evidence}
</context>
<constraints>
- Each extracted method must have a single, clear responsibility
- Preserve all existing behavior (no logic changes)
- Name extracted methods descriptively
- Extracted methods should be private unless reuse is expected
</constraints>
<output_format>
Output a unified diff patch. Output only the diff. No explanations.
--- a/{file_path}
+++ b/{file_path}
@@ ... @@
</output_format>
""",

    "introduce_interface": """
<task>Replace direct JDBC usage with Spring Data JPA Repository pattern.</task>
<context>
File: {file_path}
Class: {class_name}
Description: {description}
Evidence: {evidence}
</context>
<constraints>
- Create a JPA Entity class if not already present
- Create a Spring Data JPA Repository interface
- Refactor the class to use the Repository
- Use @Autowired or constructor injection
- Preserve all existing business logic behavior
</constraints>
<output_format>
Output unified diff patches for all affected files.
Output only the diffs. No explanations.
</output_format>
""",

    "break_circular_dependency": """
<task>Break the circular dependency by introducing an abstraction.</task>
<context>
Files: {file_path}
Description: {description}
Evidence: {evidence}
</context>
<constraints>
- Introduce an interface or event to break the cycle
- Apply Dependency Inversion Principle
- Minimize changes to existing public APIs
</constraints>
<output_format>
Output unified diff patches. Output only the diffs. No explanations.
</output_format>
""",

    "remove_dead_code": """
<task>Remove the identified dead code safely.</task>
<context>
File: {file_path}
Entity: {class_name}
Description: {description}
</context>
<constraints>
- Only remove code that has no callers (verify there are no dynamic/reflection-based calls)
- Add a deprecation comment if unsure, rather than deleting
- Preserve any related tests
</constraints>
<output_format>
Output a unified diff patch. Output only the diff. No explanations.
</output_format>
""",

    "move_method": """
<task>Move the feature-envious method to its target class.</task>
<context>
File: {file_path}
Method: {class_name}
Description: {description}
Evidence: {evidence}
</context>
<constraints>
- Move method to the class it interacts with most
- Update all call sites
- Keep a deprecated delegation method in the original class if needed for compatibility
</constraints>
<output_format>
Output unified diff patches. Output only the diffs. No explanations.
</output_format>
""",

    "default": """
<task>Apply the following refactoring to improve code quality.</task>
<context>
File: {file_path}
Entity: {class_name}
Refactoring Pattern: {pattern}
Description: {description}
Evidence: {evidence}
</context>
<constraints>
- Preserve all existing behavior
- Follow existing code style
- Minimize scope of changes
</constraints>
<output_format>
Output a unified diff patch. Output only the diff, no explanations.
--- a/{file_path}
+++ b/{file_path}
</output_format>
""",
}


class TransformerAgent(BaseAgent):
    """
    Generates code patches for automated refactor tasks via LLM.

    Only processes plan tasks with automated=True.
    Uses structured prompts for code generation.
    Generates unified diffs with Python difflib.
    """

    stage_name = "on_demand"

    async def run(self, context: JobContext, task_ids: list[UUID] | None = None) -> dict:  # type: ignore[override]
        """
        Load approved plan tasks from DB, invoke LLM to generate patches,
        produce unified diffs, and insert into patches table.

        Args:
            context: Job execution context with db session and LLM provider.
            task_ids: Optional subset of task UUIDs to generate patches for.
                      When None, all pending/approved automated tasks are processed.
        """
        job_id = context.job_id
        db = context.db_session

        # Load automated plan tasks for this job
        query = (
            select(PlanTask)
            .where(PlanTask.job_id == job_id)
            .where(PlanTask.automated.is_(True))
            .where(PlanTask.status.in_(["pending", "approved"]))
        )
        if task_ids:
            query = query.where(PlanTask.id.in_(task_ids))
        task_result = await db.execute(query)
        tasks: list[PlanTask] = list(task_result.scalars().all())

        if not tasks:
            self.logger.info("[%s] No automated tasks to transform.", job_id)
            return {"patches_created": 0}

        self.logger.info(
            "[%s] Generating patches for %d automated tasks...", job_id, len(tasks)
        )

        patches_created = 0
        patch_rows = []

        # Process tasks with controlled concurrency (up to 3 concurrent LLM calls)
        concurrency = min(3, len(tasks))
        semaphore = asyncio.Semaphore(concurrency)

        async def _limited_generate(idx: int, task: PlanTask) -> dict | None:
            async with semaphore:
                await self.emit_progress(
                    context,
                    f"Generating patch {idx+1}/{len(tasks)}: {task.title}",
                    percent=int(20 + (idx / len(tasks)) * 60),
                )
                return await self._generate_patch(context, task)

        results = await asyncio.gather(
            *(_limited_generate(i, t) for i, t in enumerate(tasks)),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(
                    "[%s] Failed to generate patch for task '%s': %s",
                    job_id, tasks[i].title, result,
                )
            elif result is not None:
                patch_rows.append(result)
                patches_created += 1

        await self.emit_progress(context, "Persisting patches to database", percent=85)

        # Persist patches
        if patch_rows:
            await self._persist_patches(context, patch_rows)

        self.logger.info("[%s] Transformer complete: %d patches created.", job_id, patches_created)

        return {
            "patches_created": patches_created,
            "patch_ids": [str(p["id"]) for p in patch_rows],
        }

    async def _generate_patch(self, context: JobContext, task: PlanTask) -> dict | None:
        """Generate a patch for a single plan task."""
        # Determine file path and entity name from task
        file_path = task.affected_files[0] if task.affected_files else "unknown"
        full_path = context.repo_path / file_path if file_path != "unknown" else None

        # Read original content
        original_content = ""
        if full_path and full_path.exists():
            try:
                original_content = full_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                original_content = ""

        # Determine language from file extension
        language = _detect_language(file_path)

        # Select prompt template
        template = PROMPT_TEMPLATES.get(task.refactor_pattern, PROMPT_TEMPLATES["default"])

        # Extract entity name from task title
        entity_name = _extract_entity_name(task.title)

        # Format prompt
        prompt = template.format(
            file_path=file_path,
            class_name=entity_name,
            description=task.description,
            evidence=json.dumps({
                "title": task.title,
                "refactor_pattern": task.refactor_pattern,
                "estimated_hours": task.estimated_hours,
            }),
            pattern=task.refactor_pattern,
        )

        # Add source code context if available (truncated to avoid token limits)
        if original_content:
            truncated_src = original_content[:6000]
            prompt = (
                f"<source_code>\n{truncated_src}\n</source_code>\n\n" + prompt
            )

        patched_content = original_content
        diff_text = ""
        tokens_used = 0
        model_used = "stub"

        if context.llm is not None:
            try:
                result = await context.llm.complete(
                    system=(
                        "You are a senior software architect specializing in legacy code modernization. "
                        "You generate precise, minimal unified diff patches. "
                        "Output only the diff content, nothing else."
                    ),
                    user=prompt,
                    temperature=0.2,
                    max_tokens=4096,
                )
                llm_output = result.content.strip()
                tokens_used = result.input_tokens + result.output_tokens
                model_used = result.model

                # Try to extract patched content from the diff
                patched_content, diff_text = _apply_diff_to_get_patched(
                    original_content, llm_output, file_path
                )
            except Exception as exc:
                self.logger.warning(
                    "[%s] LLM patch generation failed for task '%s': %s",
                    context.job_id, task.title, exc,
                )
                await self.emit_progress(
                    context,
                    f"LLM unavailable for {file_path}: {exc}. Generated stub patch.",
                )
                # Generate a stub patch explaining what should be done
                diff_text = _make_stub_diff(file_path, task)
                patched_content = original_content  # unchanged
        else:
            # No LLM configured: generate stub patch
            diff_text = _make_stub_diff(file_path, task)
            model_used = "stub"

        if not diff_text:
            # Generate minimal stub diff
            diff_text = _make_stub_diff(file_path, task)

        return {
            "id": uuid.uuid4(),
            "job_id": context.job_id,
            "task_id": task.id,
            "file_path": file_path,
            "patch_type": "modify",
            "language": language,
            "status": "pending",
            "original_content": original_content,
            "patched_content": patched_content,
            "diff": diff_text,
            "tokens_used": tokens_used,
            "model_used": model_used,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    async def _persist_patches(self, context: JobContext, patch_rows: list[dict]) -> None:
        """Insert patch records into the patches table."""
        try:
            await context.db_session.execute(insert(Patch), patch_rows)
            await context.db_session.commit()
        except Exception as exc:
            await context.db_session.rollback()
            self.logger.error("[%s] Failed to bulk-insert patches: %s", context.job_id, exc)
            for row in patch_rows:
                try:
                    await context.db_session.execute(insert(Patch), [row])
                    await context.db_session.commit()
                except Exception as row_exc:
                    await context.db_session.rollback()
                    self.logger.warning(
                        "[%s] Skipping patch for task '%s': %s",
                        context.job_id, row.get("task_id"), row_exc,
                    )

    async def _update_job_patch_count(self, context: JobContext, count: int) -> None:
        try:
            stmt = (
                update(Job)
                .where(Job.id == context.job_id)
                .values(patch_count=count, updated_at=datetime.now(UTC))
            )
            await context.db_session.execute(stmt)
            await context.db_session.commit()
        except Exception as exc:
            self.logger.error(
                "[%s] Failed to update job patch_count: %s", context.job_id, exc
            )


# ── Helper utilities ──────────────────────────────────────────────────────────

_EXT_TO_LANG = {
    ".java": "java",
    ".py": "python",
    ".php": "php",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def _detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(ext, "java")


def _extract_entity_name(title: str) -> str:
    """Extract entity name from task title like 'Extract service from MyClass'."""
    match = re.search(r"'([^']+)'", title)
    return match.group(1) if match else "UnknownEntity"


def _apply_diff_to_get_patched(
    original: str, llm_output: str, file_path: str
) -> tuple[str, str]:
    """
    Attempt to extract a unified diff from LLM output.
    If the output looks like a diff, use it as-is.
    Otherwise, treat the output as the complete new file content.
    """
    # Check if the LLM output looks like a unified diff
    if llm_output.startswith("---") or "@@" in llm_output[:500]:
        # Looks like a diff; return it directly (cannot safely apply without patching tool)
        return original, llm_output

    # LLM returned new file content directly
    if llm_output and len(llm_output) > 50:
        diff_lines = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            llm_output.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        ))
        diff_text = "\n".join(diff_lines) if diff_lines else ""
        return llm_output, diff_text

    return original, ""


def _make_stub_diff(file_path: str, task: PlanTask) -> str:
    """Generate a stub diff explaining what changes should be made."""
    return (
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -1,1 +1,1 @@\n"
        f"-# TODO: Apply refactoring manually\n"
        f"+# REFACTORING TASK: {task.title}\n"
        f"+# Pattern: {task.refactor_pattern}\n"
        f"+# Description: {task.description[:200]}\n"
        f"+# Estimated effort: {task.estimated_hours}h\n"
        f"+# This patch was generated as a stub because LLM was not available\n"
        f"+# or the source file could not be located.\n"
    )
