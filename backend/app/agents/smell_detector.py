"""
Agent 3: SmellDetector

Detects architectural smells using rule-based heuristics and optional LLM confirmation.

Detection pipeline:
  1. Run rule-based detectors against UCG metrics (no LLM cost).
  2. For each candidate, optionally invoke LLM to confirm and rate severity.
  3. Merge scores and insert confirmed smells into the smells table.

Output:
  - Inserts into smells table
  - Updates jobs.smell_count
  - Returns list[SmellResult]
"""

import asyncio
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select, update

from app.agents.base import BaseAgent, JobContext
from app.models.job import Job
from app.models.smell import Smell
from app.models.ucg import UCGEdge, UCGNode


@dataclass
class SmellResult:
    smell_type: str
    severity: str
    affected_node_ids: list[UUID]
    description: str
    evidence: dict
    confidence: float
    llm_rationale: str | None = None


class SmellDetectorAgent(BaseAgent):
    """
    Detects architectural smells via rule engines + optional LLM confirmation.
    """

    stage_name = "analyzing"

    # Severity ordering for sorting
    SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    async def run(self, context: JobContext) -> dict:
        """
        Load UCG from DB, apply rule-based detectors, then optionally confirm with LLM.
        Insert confirmed smells into the smells table.
        """
        job_id = context.job_id
        db = context.db_session

        self.logger.info("[%s] Loading UCG nodes and edges from DB...", job_id)

        # Load all nodes for this job
        node_result = await db.execute(
            select(UCGNode).where(UCGNode.job_id == job_id)
        )
        nodes: list[UCGNode] = list(node_result.scalars().all())

        # Load all edges for this job
        edge_result = await db.execute(
            select(UCGEdge).where(UCGEdge.job_id == job_id)
        )
        edges: list[UCGEdge] = list(edge_result.scalars().all())

        self.logger.info(
            "[%s] Loaded %d nodes and %d edges. Running smell detectors...",
            job_id, len(nodes), len(edges),
        )

        await self.emit_progress(context, "Running rule-based smell detectors", percent=20)

        candidates: list[SmellResult] = []

        # Build lookup structures
        node_by_id: dict[UUID, UCGNode] = {n.id: n for n in nodes}
        class_nodes = [n for n in nodes if n.node_type.upper() == "CLASS"]
        function_nodes = [n for n in nodes if n.node_type.upper() in ("FUNCTION", "METHOD")]

        # Incoming/outgoing edge maps
        incoming: dict[UUID, list[UCGEdge]] = defaultdict(list)
        outgoing: dict[UUID, list[UCGEdge]] = defaultdict(list)
        for e in edges:
            incoming[e.target_node_id].append(e)
            outgoing[e.source_node_id].append(e)

        # --- Rule 1: God Class (method_count > 10) ---
        await self.emit_progress(context, "Detecting God Classes", percent=25)
        candidates.extend(
            self._detect_god_class(class_nodes, outgoing, node_by_id)
        )

        # --- Rule 2: Large Class (LOC > 300) ---
        candidates.extend(
            self._detect_large_class(class_nodes)
        )

        # --- Rule 3: Long Method (LOC > 50) ---
        await self.emit_progress(context, "Detecting Long Methods", percent=35)
        candidates.extend(
            self._detect_long_method(function_nodes)
        )

        # --- Rule 4: JDBC Direct Usage ---
        candidates.extend(
            self._detect_jdbc_usage(nodes)
        )

        # --- Rule 5: Cyclic Dependencies ---
        await self.emit_progress(context, "Detecting Cyclic Dependencies", percent=45)
        candidates.extend(
            self._detect_cyclic_dependencies(nodes, edges, node_by_id)
        )

        # --- Rule 6: Dead Code ---
        candidates.extend(
            self._detect_dead_code(nodes, incoming, outgoing)
        )

        # --- Rule 7: Feature Envy ---
        await self.emit_progress(context, "Detecting Feature Envy", percent=55)
        candidates.extend(
            self._detect_feature_envy(function_nodes, outgoing, node_by_id)
        )

        # --- Rule 8: Anemic Domain Model ---
        candidates.extend(
            self._detect_anemic_domain_model(class_nodes, outgoing, node_by_id)
        )

        # LLM enrichment is optional and off by default for speed.
        # Enable via job config: {"llm_enrich_smells": true}
        if context.llm is not None and context.job_config.get("llm_enrich_smells", False):
            await self.emit_progress(context, "Enriching smells with LLM", percent=65)
            candidates = await self._enrich_with_llm(context, candidates, node_by_id)

        for smell in candidates:
            if smell.affected_node_ids:
                node = node_by_id.get(smell.affected_node_ids[0])
                if node and node.file_path:
                    smell.evidence = {**smell.evidence, "file_path": node.file_path}

        await self.emit_progress(context, "Persisting smells to database", percent=80)

        # Persist smells to DB
        smell_records = await self._persist_smells(context, candidates)

        # Update job smell_count
        await self._update_job_smell_count(context, len(smell_records))

        self.logger.info(
            "[%s] SmellDetector complete: %d smells detected.",
            job_id, len(smell_records),
        )

        return {
            "smell_count": len(smell_records),
            "smells": [
                {
                    "type": s.smell_type,
                    "severity": s.severity,
                    "node_ids": [str(nid) for nid in s.affected_node_ids],
                    "rationale": s.llm_rationale,
                }
                for s in candidates
            ],
        }

    # ── Rule-Based Detectors ─────────────────────────────────────────────────

    def _detect_god_class(
        self,
        class_nodes: list[UCGNode],
        outgoing: dict[UUID, list[UCGEdge]],
        node_by_id: dict[UUID, UCGNode],
    ) -> list[SmellResult]:
        results = []
        for cls in class_nodes:
            # Count CONTAINS edges to METHOD/FUNCTION nodes
            contained = outgoing.get(cls.id, [])
            methods = [
                e for e in contained
                if e.edge_type.upper() == "CONTAINS"
                and node_by_id.get(e.target_node_id) is not None
                and node_by_id[e.target_node_id].node_type.upper() in ("METHOD", "FUNCTION")
            ]
            method_count = len(methods)
            if method_count > 10:
                results.append(SmellResult(
                    smell_type="god_class",
                    severity="high",
                    affected_node_ids=[cls.id],
                    description=(
                        f"Class '{cls.qualified_name}' has {method_count} methods, "
                        f"exceeding the threshold of 10. Consider splitting it into "
                        f"focused, single-responsibility classes."
                    ),
                    evidence={"method_count": method_count, "threshold": 10},
                    confidence=0.85,
                ))
        return results

    def _detect_large_class(self, class_nodes: list[UCGNode]) -> list[SmellResult]:
        results = []
        for cls in class_nodes:
            loc = _compute_loc(cls)
            if loc > 300:
                results.append(SmellResult(
                    smell_type="large_class",
                    severity="medium",
                    affected_node_ids=[cls.id],
                    description=(
                        f"Class '{cls.qualified_name}' has {loc} lines of code, "
                        f"exceeding the threshold of 300 LOC. Consider decomposing it."
                    ),
                    evidence={"loc": loc, "threshold": 300},
                    confidence=0.80,
                ))
        return results

    def _detect_long_method(self, function_nodes: list[UCGNode]) -> list[SmellResult]:
        results = []
        for fn in function_nodes:
            loc = _compute_loc(fn)
            if loc > 50:
                results.append(SmellResult(
                    smell_type="long_method",
                    severity="medium",
                    affected_node_ids=[fn.id],
                    description=(
                        f"Method/function '{fn.qualified_name}' has {loc} lines of code, "
                        f"exceeding the threshold of 50 LOC. Consider extracting smaller methods."
                    ),
                    evidence={"loc": loc, "threshold": 50},
                    confidence=0.80,
                ))
        return results

    def _detect_jdbc_usage(self, nodes: list[UCGNode]) -> list[SmellResult]:
        results = []
        jdbc_keywords = {"jdbc", "preparedstatement", "resultset", "drivermanager",
                         "connection.preparestatement", "createstatement",
                         "conn.preparestatement", "preparestatement("}
        for n in nodes:
            props_str = json.dumps(n.properties).lower()
            name_lower = (n.qualified_name or "").lower()
            combined = props_str + " " + name_lower
            if any(kw in combined for kw in jdbc_keywords):
                results.append(SmellResult(
                    smell_type="tight_coupling",
                    severity="high",
                    affected_node_ids=[n.id],
                    description=(
                        f"Node '{n.qualified_name}' contains direct JDBC usage. "
                        f"Replace with a JPA/Repository abstraction for better maintainability."
                    ),
                    evidence={"detected_keywords": [kw for kw in jdbc_keywords if kw in combined]},
                    confidence=0.90,
                ))
        return results

    def _detect_cyclic_dependencies(
        self,
        nodes: list[UCGNode],
        edges: list[UCGEdge],
        node_by_id: dict[UUID, UCGNode],
    ) -> list[SmellResult]:
        """Detect cycles using DFS on DEPENDS_ON and IMPORTS edges."""
        results = []

        # Build adjacency list for module/file nodes only
        relevant_types = {"MODULE", "FILE"}
        dep_edge_types = {"DEPENDS_ON", "IMPORTS"}

        module_nodes = {n.id for n in nodes if n.node_type.upper() in relevant_types}
        adj: dict[UUID, set[UUID]] = defaultdict(set)
        for e in edges:
            if e.edge_type.upper() in dep_edge_types:
                if e.source_node_id in module_nodes and e.target_node_id in module_nodes:
                    adj[e.source_node_id].add(e.target_node_id)

        visited: set[UUID] = set()
        rec_stack: set[UUID] = set()
        cycles_found: set[frozenset] = set()

        def dfs(node_id: UUID, path: list[UUID]) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for neighbor in adj.get(node_id, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle; extract the cyclic portion
                    cycle_start = path.index(neighbor)
                    cycle_nodes = path[cycle_start:]
                    cycle_key = frozenset(cycle_nodes)
                    if cycle_key not in cycles_found and len(cycle_nodes) >= 2:
                        cycles_found.add(cycle_key)
                        names = [
                            node_by_id[nid].qualified_name
                            for nid in cycle_nodes
                            if nid in node_by_id
                        ]
                        results.append(SmellResult(
                            smell_type="circular_dependency",
                            severity="critical",
                            affected_node_ids=list(cycle_nodes),
                            description=(
                                f"Circular dependency detected involving: "
                                f"{' -> '.join(names[:5])}{'...' if len(names) > 5 else ''}. "
                                f"Introduce an abstraction layer or dependency inversion to break the cycle."
                            ),
                            evidence={
                                "cycle_length": len(cycle_nodes),
                                "cycle_nodes": [str(nid) for nid in cycle_nodes],
                            },
                            confidence=0.95,
                        ))

            path.pop()
            rec_stack.discard(node_id)

        for node_id in module_nodes:
            if node_id not in visited:
                dfs(node_id, [])

        return results

    def _detect_dead_code(
        self,
        nodes: list[UCGNode],
        incoming: dict[UUID, list[UCGEdge]],
        outgoing: dict[UUID, list[UCGEdge]],
    ) -> list[SmellResult]:
        """Detect nodes with no incoming CALLS/USES_TYPE edges (except modules/files)."""
        results = []
        skip_types = {"MODULE", "FILE", "IMPORT", "ANNOTATION", "PARAMETER",
                      "FIELD", "COMMENT", "LITERAL", "TYPE_REF"}
        call_edge_types = {"CALLS", "USES_TYPE", "INSTANTIATES"}

        for n in nodes:
            if n.node_type.upper() in skip_types:
                continue
            in_edges = incoming.get(n.id, [])
            relevant_in = [e for e in in_edges if e.edge_type.upper() in call_edge_types]
            if not relevant_in:
                # Check if it's a public method/function
                props = n.properties or {}
                visibility = props.get("visibility", "public")
                name = n.qualified_name or ""
                # Skip dunder/magic methods — they're called implicitly
                if name.endswith("__init__") or name.endswith("__str__") or \
                   name.endswith("__repr__") or "main" in name.lower():
                    continue
                if visibility == "private":
                    results.append(SmellResult(
                        smell_type="dead_code",
                        severity="low",
                        affected_node_ids=[n.id],
                        description=(
                            f"'{n.qualified_name}' appears to be dead code: "
                            f"no incoming CALLS or USES_TYPE edges found. "
                            f"Consider removing or documenting this code path."
                        ),
                        evidence={
                            "incoming_call_edges": 0,
                            "node_type": n.node_type,
                            "visibility": visibility,
                        },
                        confidence=0.60,
                    ))
        return results

    def _detect_feature_envy(
        self,
        function_nodes: list[UCGNode],
        outgoing: dict[UUID, list[UCGEdge]],
        node_by_id: dict[UUID, UCGNode],
    ) -> list[SmellResult]:
        """Detect methods calling many methods on other classes (>5 unique targets)."""
        results = []
        for fn in function_nodes:
            call_edges = [
                e for e in outgoing.get(fn.id, [])
                if e.edge_type.upper() == "CALLS"
            ]
            unique_target_classes: set[str] = set()
            for e in call_edges:
                target = node_by_id.get(e.target_node_id)
                if target:
                    # Get the parent class from qualified name
                    parts = target.qualified_name.rsplit(".", 1)
                    if len(parts) > 1:
                        unique_target_classes.add(parts[0])

            if len(unique_target_classes) > 5:
                results.append(SmellResult(
                    smell_type="feature_envy",
                    severity="medium",
                    affected_node_ids=[fn.id],
                    description=(
                        f"'{fn.qualified_name}' calls methods on {len(unique_target_classes)} "
                        f"different classes, suggesting it may belong elsewhere. "
                        f"Consider moving this method to the class it interacts with most."
                    ),
                    evidence={
                        "unique_target_classes": len(unique_target_classes),
                        "threshold": 5,
                        "targets": list(unique_target_classes)[:10],
                    },
                    confidence=0.75,
                ))
        return results

    def _detect_anemic_domain_model(
        self,
        class_nodes: list[UCGNode],
        outgoing: dict[UUID, list[UCGEdge]],
        node_by_id: dict[UUID, UCGNode],
    ) -> list[SmellResult]:
        """Detect classes where > 80% of methods are getters/setters/is-ers."""
        results = []
        getter_setter_prefixes = ("get", "set", "is", "has", "can", "should")

        for cls in class_nodes:
            contained = outgoing.get(cls.id, [])
            methods = [
                node_by_id[e.target_node_id]
                for e in contained
                if e.edge_type.upper() == "CONTAINS"
                and e.target_node_id in node_by_id
                and node_by_id[e.target_node_id].node_type.upper() in ("METHOD", "FUNCTION")
            ]
            if len(methods) < 3:
                continue  # Too few methods to judge

            accessor_count = sum(
                1 for m in methods
                if any(
                    (m.qualified_name or "").split(".")[-1].lower().startswith(prefix)
                    for prefix in getter_setter_prefixes
                )
            )
            ratio = accessor_count / len(methods)
            if ratio > 0.8:
                results.append(SmellResult(
                    smell_type="anemic_domain_model",
                    severity="low",
                    affected_node_ids=[cls.id],
                    description=(
                        f"Class '{cls.qualified_name}' has {accessor_count}/{len(methods)} "
                        f"accessor methods ({ratio:.0%}), suggesting an anemic domain model. "
                        f"Consider adding domain logic to enrich this class."
                    ),
                    evidence={
                        "method_count": len(methods),
                        "accessor_count": accessor_count,
                        "accessor_ratio": round(ratio, 3),
                        "threshold_ratio": 0.8,
                    },
                    confidence=0.70,
                ))
        return results

    # ── LLM Enrichment ────────────────────────────────────────────────────────

    async def _enrich_with_llm(
        self,
        context: JobContext,
        candidates: list[SmellResult],
        node_by_id: dict[UUID, UCGNode],
    ) -> list[SmellResult]:
        """Use LLM to enrich high/critical severity smells with detailed rationale."""
        # Only send high/critical smells to LLM to control costs
        high_priority = [s for s in candidates if s.severity in ("critical", "high")]
        low_priority = [s for s in candidates if s.severity not in ("critical", "high")]

        async def _enrich_one(smell: SmellResult) -> SmellResult:
            try:
                node_names = [
                    node_by_id[nid].qualified_name
                    for nid in smell.affected_node_ids
                    if nid in node_by_id
                ]
                prompt = (
                    f"<task>Analyze this code smell and provide a detailed rationale.</task>\n"
                    f"<smell_type>{smell.smell_type}</smell_type>\n"
                    f"<severity>{smell.severity}</severity>\n"
                    f"<affected_nodes>{', '.join(node_names[:5])}</affected_nodes>\n"
                    f"<evidence>{json.dumps(smell.evidence)}</evidence>\n"
                    f"<output_format>Provide a 2-3 sentence technical rationale explaining "
                    f"why this is a problem and what the impact is. Be concise.</output_format>"
                )
                result = await context.llm.complete(
                    system="You are an expert software architect specializing in legacy code modernization.",
                    user=prompt,
                    temperature=0.3,
                    max_tokens=512,
                )
                smell.llm_rationale = result.content.strip()
                smell.confidence = min(smell.confidence + 0.05, 1.0)
            except Exception as exc:
                self.logger.warning(
                    "[%s] LLM enrichment failed for smell '%s': %s",
                    context.job_id, smell.smell_type, exc,
                )
            return smell

        enriched = list(await asyncio.gather(*(_enrich_one(s) for s in high_priority)))
        enriched.extend(low_priority)
        return enriched

    # ── DB Persistence ────────────────────────────────────────────────────────

    async def _persist_smells(
        self,
        context: JobContext,
        candidates: list[SmellResult],
    ) -> list[SmellResult]:
        """Insert smell records into the smells table."""
        if not candidates:
            return []

        rows = []
        for s in candidates:
            rows.append({
                "id": uuid.uuid4(),
                "job_id": context.job_id,
                "smell_type": s.smell_type,
                "severity": s.severity,
                "description": s.description,
                "confidence": s.confidence,
                "affected_node_ids": s.affected_node_ids,
                "evidence": s.evidence,
                "llm_rationale": s.llm_rationale,
                "dismissed": False,
                "created_at": datetime.now(UTC),
            })

        try:
            await context.db_session.execute(insert(Smell), rows)
            await context.db_session.commit()
        except Exception as exc:
            await context.db_session.rollback()
            self.logger.error(
                "[%s] Failed to bulk-insert smells: %s. Trying row-by-row.", context.job_id, exc
            )
            successful: list[SmellResult] = []
            for i, row in enumerate(rows):
                try:
                    await context.db_session.execute(insert(Smell), [row])
                    await context.db_session.commit()
                    successful.append(candidates[i])
                except Exception as row_exc:
                    await context.db_session.rollback()
                    self.logger.warning(
                        "[%s] Skipping smell '%s': %s",
                        context.job_id, row.get("smell_type"), row_exc,
                    )
            return successful

        return candidates

    async def _update_job_smell_count(self, context: JobContext, count: int) -> None:
        try:
            stmt = (
                update(Job)
                .where(Job.id == context.job_id)
                .values(smell_count=count, updated_at=datetime.now(UTC))
            )
            await context.db_session.execute(stmt)
            await context.db_session.commit()
        except Exception as exc:
            self.logger.error(
                "[%s] Failed to update job smell_count: %s", context.job_id, exc
            )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_loc(node: UCGNode) -> int:
    """Compute lines of code for a node from line_start/line_end."""
    if node.line_start is not None and node.line_end is not None:
        return max(0, node.line_end - node.line_start + 1)
    return 0
