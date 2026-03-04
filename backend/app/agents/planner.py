"""
Agent 4: Planner

Generates a prioritized, dependency-ordered refactor plan using LLM.

The Planner receives the list of confirmed smells and produces a RefactorPlan
with ordered tasks, effort estimates, and risk assessment.

LLM: claude-3-5-sonnet-20241022

Output:
  - Inserts into plans, plan_tasks tables
  - Returns RefactorPlan
"""

import json
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select, update

from app.agents.base import BaseAgent, JobContext
from app.models.plan import Plan, PlanTask
from app.models.smell import Smell

# Severity ordering (lower = higher priority)
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Smell type -> (refactor_pattern, base_effort_hours, automated)
SMELL_TASK_MAP: dict[str, tuple[str, float, bool]] = {
    "god_class":            ("extract_class", 8.0, True),
    "large_class":          ("extract_class", 6.0, True),
    "long_method":          ("extract_method", 2.0, True),
    "feature_envy":         ("move_method", 4.0, True),
    "tight_coupling":       ("introduce_interface", 5.0, True),  # also covers JDBC
    "circular_dependency":  ("break_circular_dependency", 8.0, False),
    "dead_code":            ("remove_dead_code", 1.0, True),
    "anemic_domain_model":  ("introduce_interface", 4.0, False),
    "data_clumps":          ("introduce_parameter_object", 3.0, True),
    "shotgun_surgery":      ("introduce_facade", 6.0, False),
    "divergent_change":     ("extract_class", 5.0, False),
    "primitive_obsession":  ("replace_magic_numbers", 2.0, True),
    "long_parameter_list":  ("introduce_parameter_object", 2.0, True),
    "spaghetti_code":       ("decompose_conditional", 6.0, False),
    "lava_flow":            ("remove_dead_code", 4.0, False),
    "missing_abstraction":  ("introduce_interface", 5.0, False),
    "singleton_abuse":      ("introduce_facade", 3.0, False),
}


class PlannerAgent(BaseAgent):
    """
    Generates a refactor plan from detected smells using rule templates + optional LLM.
    """

    stage_name = "planning"

    async def run(self, context: JobContext) -> dict:
        """
        Load smells from DB, invoke LLM to produce a structured RefactorPlan,
        and insert the plan and tasks into the database.
        """
        job_id = context.job_id
        db = context.db_session

        # Load smells from DB
        smell_result = await db.execute(
            select(Smell)
            .where(Smell.job_id == job_id)
            .where(Smell.dismissed.is_(False))
        )
        smells: list[Smell] = list(smell_result.scalars().all())

        if not smells:
            self.logger.info("[%s] No smells to plan for.", job_id)
            return {"tasks_created": 0, "plan_id": None}

        self.logger.info("[%s] Planning refactor for %d smells...", job_id, len(smells))
        await self.emit_progress(context, "Generating refactor plan", percent=20)

        # Sort smells by severity (critical first)
        smells.sort(key=lambda s: SEVERITY_RANK.get(s.severity, 9))

        # Generate plan tasks from smells
        tasks: list[dict] = []
        for smell in smells:
            task_data = self._smell_to_task(smell)
            if task_data:
                tasks.append(task_data)

        if not tasks:
            self.logger.warning("[%s] No tasks generated from smells.", job_id)
            return {"tasks_created": 0, "plan_id": None}

        await self.emit_progress(context, "Enriching tasks with LLM", percent=40)

        # Optionally enrich tasks with LLM
        if context.llm is not None:
            tasks = await self._enrich_tasks_with_llm(context, tasks, smells)

        # Compute dependency order (topological sort heuristic)
        tasks = self._assign_dependencies(tasks)

        # Compute effort and risk
        total_effort = sum(t.get("estimated_hours", 0.0) for t in tasks)
        risk_level = self._compute_risk_level(smells)

        await self.emit_progress(context, "Persisting plan to database", percent=70)

        # Persist Plan record
        plan_id = uuid.uuid4()
        now = datetime.now(UTC)

        plan_row = {
            "id": plan_id,
            "job_id": job_id,
            "version": 1,
            "estimated_effort_hours": total_effort,
            "risk_level": risk_level,
            "priority_order": [],  # updated after tasks are inserted
            "llm_model": getattr(context.llm, "_model", None) if context.llm else None,
            "tokens_used": None,
            "created_at": now,
        }

        try:
            await db.execute(insert(Plan), [plan_row])
            await db.commit()
        except Exception as exc:
            await db.rollback()
            self.logger.error("[%s] Failed to insert plan: %s", job_id, exc)
            raise

        # Persist PlanTask records
        task_ids: list[UUID] = []
        task_rows = []
        for task in tasks:
            task_id = uuid.uuid4()
            task["_id"] = task_id
            task_ids.append(task_id)
            task_rows.append({
                "id": task_id,
                "plan_id": plan_id,
                "job_id": job_id,
                "title": task["title"],
                "description": task["description"],
                "smell_ids": task.get("smell_ids", []),
                "affected_files": task.get("affected_files", []),
                "refactor_pattern": task["refactor_pattern"],
                "dependencies": task.get("dependencies", []),
                "estimated_hours": task.get("estimated_hours", 1.0),
                "automated": task.get("automated", True),
                "status": "pending",
                "priority_override": None,
                "notes": task.get("notes"),
                "created_at": now,
                "updated_at": now,
            })

        try:
            await db.execute(insert(PlanTask), task_rows)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            self.logger.error("[%s] Failed to insert plan tasks: %s", job_id, exc)
            # Try row-by-row
            for row in task_rows:
                try:
                    await db.execute(insert(PlanTask), [row])
                    await db.commit()
                except Exception as row_exc:
                    await db.rollback()
                    self.logger.warning("[%s] Skipping task '%s': %s", job_id, row["title"], row_exc)

        # Update plan with priority order (task IDs in order)
        try:
            stmt = (
                update(Plan)
                .where(Plan.id == plan_id)
                .values(priority_order=task_ids)
            )
            await db.execute(stmt)
            await db.commit()
        except Exception as exc:
            self.logger.error("[%s] Failed to update plan priority_order: %s", job_id, exc)

        self.logger.info(
            "[%s] Planner complete: %d tasks created (effort: %.1fh, risk: %s).",
            job_id, len(task_rows), total_effort, risk_level,
        )

        return {
            "plan_id": str(plan_id),
            "tasks_created": len(task_rows),
            "total_effort_hours": total_effort,
            "risk_level": risk_level,
        }

    def _smell_to_task(self, smell: Smell) -> dict | None:
        """Convert a smell record into a task dictionary."""
        mapping = SMELL_TASK_MAP.get(smell.smell_type)
        if not mapping:
            mapping = ("introduce_interface", 3.0, False)

        pattern, base_effort, automated = mapping
        evidence = smell.evidence or {}

        # Compute effort based on evidence metrics
        effort = base_effort
        if smell.smell_type == "god_class":
            method_count = evidence.get("method_count", 10)
            effort = max(base_effort, method_count / 5.0)
        elif smell.smell_type == "large_class":
            loc = evidence.get("loc", 300)
            effort = max(base_effort, loc / 60.0)
        elif smell.smell_type == "long_method":
            loc = evidence.get("loc", 50)
            effort = max(1.0, loc / 25.0)

        # Derive affected files from the description
        affected_files: list[str] = []

        # Extract node file info from evidence if available
        node_file = evidence.get("file_path") or evidence.get("filePath")
        if node_file:
            affected_files.append(node_file)

        # Generate task title and description
        name_parts = smell.description.split("'")
        entity_name = name_parts[1] if len(name_parts) > 1 else "unknown"

        title, description = self._generate_task_text(smell, entity_name, pattern, evidence)

        return {
            "title": title,
            "description": description,
            "smell_ids": [smell.id],
            "affected_files": affected_files,
            "refactor_pattern": pattern,
            "estimated_hours": round(effort, 1),
            "automated": automated,
            "notes": smell.llm_rationale,
            "severity": smell.severity,
        }

    def _generate_task_text(
        self,
        smell: Smell,
        entity_name: str,
        pattern: str,
        evidence: dict,
    ) -> tuple[str, str]:
        """Generate title and description for a task."""
        smell_type = smell.smell_type

        if smell_type == "god_class":
            method_count = evidence.get("method_count", "many")
            title = f"Extract service from '{entity_name}'"
            description = (
                f"'{entity_name}' has {method_count} methods and violates Single Responsibility. "
                f"Extract business logic into focused service classes. "
                f"Apply Extract Class pattern: identify cohesive method groups and move them "
                f"to new dedicated classes with clear boundaries."
            )
        elif smell_type == "large_class":
            loc = evidence.get("loc", "many")
            title = f"Split '{entity_name}' into focused classes"
            description = (
                f"'{entity_name}' has {loc} LOC and is too large. "
                f"Decompose it into smaller, focused classes following SRP. "
                f"Identify distinct responsibilities and extract each into its own class."
            )
        elif smell_type == "tight_coupling":
            title = f"Replace JDBC in '{entity_name}' with Repository pattern"
            description = (
                f"'{entity_name}' uses direct JDBC which tightly couples it to the database. "
                f"Replace with a JPA Entity + Spring Data JPA Repository. "
                f"This decouples data access from business logic and improves testability."
            )
        elif smell_type == "long_method":
            loc = evidence.get("loc", "many")
            title = f"Decompose '{entity_name}' into smaller methods"
            description = (
                f"'{entity_name}' has {loc} LOC and is too long. "
                f"Apply Extract Method: identify distinct steps and extract each into "
                f"a well-named helper method with a clear single responsibility."
            )
        elif smell_type == "circular_dependency":
            cycle_len = evidence.get("cycle_length", 2)
            title = f"Break circular dependency ({cycle_len}-node cycle)"
            description = (
                f"A {cycle_len}-node circular dependency was detected. "
                f"Introduce an abstraction layer (interface or event bus) to break the cycle. "
                f"Apply Dependency Inversion: depend on abstractions, not concretions."
            )
        elif smell_type == "dead_code":
            title = f"Remove dead code: '{entity_name}'"
            description = (
                f"'{entity_name}' has no callers and appears to be dead code. "
                f"Verify it is truly unused (search for dynamic invocations), then remove it "
                f"to reduce maintenance burden."
            )
        elif smell_type == "feature_envy":
            title = f"Move '{entity_name}' to its target class"
            description = (
                f"'{entity_name}' is envious of other classes. "
                f"Apply Move Method: relocate it to the class it interacts with most, "
                f"reducing coupling and improving cohesion."
            )
        elif smell_type == "anemic_domain_model":
            title = f"Enrich '{entity_name}' with domain logic"
            description = (
                f"'{entity_name}' is an anemic domain object with mostly accessors. "
                f"Move relevant business logic from service classes into this entity "
                f"following Domain-Driven Design principles."
            )
        else:
            title = f"Refactor '{entity_name}' ({smell_type.replace('_', ' ').title()})"
            description = (
                f"Address {smell_type.replace('_', ' ')} in '{entity_name}'. "
                f"Apply {pattern.replace('_', ' ')} refactoring pattern."
            )

        return title, description

    def _assign_dependencies(self, tasks: list[dict]) -> list[dict]:
        """
        Assign task dependencies using a heuristic:
        - Break cycle tasks must come before other tasks in the same affected files.
        - Extract class tasks must come before extract method tasks on the same class.
        """
        # For simplicity, critical tasks have no dependencies; others depend on critical ones.
        critical_task_indices = [
            i for i, t in enumerate(tasks)
            if t.get("severity") == "critical"
        ]

        for i, task in enumerate(tasks):
            if i in critical_task_indices:
                task["dependencies"] = []
            else:
                # Non-critical tasks nominally depend on all critical tasks
                task["dependencies"] = []  # Keep empty for now; real dep graph needs symbol resolution

        return tasks

    def _compute_risk_level(self, smells: list[Smell]) -> str:
        """Compute overall risk level from smell severities."""
        if any(s.severity == "critical" for s in smells):
            return "critical"
        if any(s.severity == "high" for s in smells):
            return "high"
        if any(s.severity == "medium" for s in smells):
            return "medium"
        return "low"

    async def _enrich_tasks_with_llm(
        self,
        context: JobContext,
        tasks: list[dict],
        smells: list[Smell],
    ) -> list[dict]:
        """Use LLM to enrich high-priority task descriptions."""
        smell_by_id: dict[UUID, Smell] = {s.id: s for s in smells}

        # Only enrich first 5 tasks to control token usage
        for task in tasks[:5]:
            smell_ids = task.get("smell_ids", [])
            related_smells = [smell_by_id[sid] for sid in smell_ids if sid in smell_by_id]
            if not related_smells:
                continue
            smell = related_smells[0]
            try:
                prompt = (
                    f"<task>Generate a detailed, actionable refactoring task description.</task>\n"
                    f"<smell_type>{smell.smell_type}</smell_type>\n"
                    f"<pattern>{task['refactor_pattern']}</pattern>\n"
                    f"<current_description>{task['description']}</current_description>\n"
                    f"<evidence>{json.dumps(smell.evidence)}</evidence>\n"
                    f"<output_format>Provide a single improved task description (3-5 sentences) "
                    f"that includes specific steps for the developer. Focus on actionability.</output_format>"
                )
                result = await context.llm.complete(
                    system="You are a senior software architect specializing in refactoring legacy code.",
                    user=prompt,
                    temperature=0.4,
                    max_tokens=512,
                )
                improved = result.content.strip()
                if improved and len(improved) > 20:
                    task["description"] = improved
            except Exception as exc:
                self.logger.warning(
                    "[%s] LLM task enrichment failed: %s", context.job_id, exc
                )

        return tasks
