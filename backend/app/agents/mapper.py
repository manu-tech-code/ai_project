"""
Agent 2: Mapper (UCG Builder)

Dispatches to language-specific adapters to parse source files into UCG nodes and edges.
Bulk-inserts the results into the ucg_nodes and ucg_edges tables.

Output:
  - Inserts into ucg_nodes, ucg_edges
  - Updates jobs.ucg_node_count, jobs.ucg_edge_count
  - Returns UCGStats
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert, update

from app.adapters.base import UCGEdgeRaw, UCGNodeRaw, UCGOutput
from app.agents.base import BaseAgent, JobContext
from app.models.job import Job
from app.models.ucg import UCGEdge, UCGNode

# Extension to language mapping (mirrors language_detector)
EXTENSION_MAP: dict[str, str] = {
    ".java": "java",
    ".py": "python",
    ".php": "php",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}

SKIP_DIRS: set[str] = {
    "node_modules", "vendor", ".git", "__pycache__",
    ".venv", "venv", "env", "dist", "build", "target",
    ".idea", ".vscode", "coverage", ".tox",
}

BATCH_SIZE = 50  # files per adapter batch


@dataclass
class ParseError:
    file_path: str
    error_message: str
    line_number: int | None = None


@dataclass
class UCGStats:
    node_count: int = 0
    edge_count: int = 0
    nodes_by_type: dict = field(default_factory=dict)
    edges_by_type: dict = field(default_factory=dict)
    parse_errors: list = field(default_factory=list)


class MapperAgent(BaseAgent):
    """
    Builds the Universal Code Graph by dispatching to language-specific adapters.

    Adapter dispatch:
      java       -> JavaAdapter (calls java-parser-service HTTP)
      python     -> PythonASTAdapter (stdlib ast module)
      php        -> PHPAdapter (subprocess nikic/php-parser)
      javascript -> JSTSAdapter (subprocess @typescript-eslint/parser)
      typescript -> JSTSAdapter (TypeScript mode)
    """

    stage_name = "mapping"

    async def run(self, context: JobContext) -> dict:
        """
        For each detected language, load the appropriate adapter and
        parse all source files, collecting UCG nodes and edges.
        """
        stats = UCGStats()

        if not context.languages:
            self.logger.warning("[%s] No languages detected; skipping mapping.", context.job_id)
            return vars(stats)

        # Collect all source files grouped by language
        files_by_lang: dict[str, list[Path]] = {lang: [] for lang in context.languages}
        for path in _walk_source_files(context.repo_path):
            ext = path.suffix.lower()
            lang = EXTENSION_MAP.get(ext)
            if lang and lang in files_by_lang:
                files_by_lang[lang].append(path)

        total_nodes: list[UCGNodeRaw] = []
        total_edges: list[UCGEdgeRaw] = []

        for lang in context.languages:
            files = files_by_lang.get(lang, [])
            if not files:
                self.logger.info("[%s] No files for language '%s'.", context.job_id, lang)
                continue

            adapter = _get_adapter(lang)
            if adapter is None:
                self.logger.warning(
                    "[%s] No adapter available for language '%s'.", context.job_id, lang
                )
                continue

            self.logger.info(
                "[%s] Parsing %d %s files...", context.job_id, len(files), lang
            )
            await self.emit_progress(
                context,
                f"Parsing {len(files)} {lang} files",
                percent=20,
            )

            # Process in batches
            for batch_start in range(0, len(files), BATCH_SIZE):
                batch = files[batch_start: batch_start + BATCH_SIZE]
                try:
                    output: UCGOutput = await adapter.parse_files(batch, context.repo_path)
                    total_nodes.extend(output.nodes)
                    total_edges.extend(output.edges)
                    for err in output.parse_errors:
                        stats.parse_errors.append(err)
                except Exception as exc:
                    self.logger.error(
                        "[%s] Adapter error for language '%s': %s", context.job_id, lang, exc
                    )
                    stats.parse_errors.append({
                        "file_path": str(context.repo_path),
                        "error_message": f"Adapter error for {lang}: {exc}",
                        "line_number": None,
                    })

        self.logger.info(
            "[%s] Parsed %d nodes and %d edges total.",
            context.job_id, len(total_nodes), len(total_edges),
        )
        await self.emit_progress(context, "Bulk-inserting UCG into database", percent=70)

        # Bulk-insert nodes into ucg_nodes
        if total_nodes:
            await self._bulk_insert_nodes(context, total_nodes, stats)

        # Bulk-insert edges into ucg_edges
        if total_edges:
            await self._bulk_insert_edges(context, total_edges, stats)

        # Update jobs table summary counters
        await self._update_job_stats(context, stats)

        self.logger.info(
            "[%s] Mapper complete: %d nodes, %d edges inserted.",
            context.job_id, stats.node_count, stats.edge_count,
        )

        return {
            "node_count": stats.node_count,
            "edge_count": stats.edge_count,
            "nodes_by_type": stats.nodes_by_type,
            "edges_by_type": stats.edges_by_type,
            "parse_error_count": len(stats.parse_errors),
            "languages": context.languages,
        }

    async def _bulk_insert_nodes(
        self,
        context: JobContext,
        nodes: list[UCGNodeRaw],
        stats: UCGStats,
    ) -> None:
        """Bulk-insert UCGNodeRaw objects into ucg_nodes table."""
        INSERT_CHUNK = 500  # rows per INSERT statement
        job_id = context.job_id

        for chunk_start in range(0, len(nodes), INSERT_CHUNK):
            chunk = nodes[chunk_start: chunk_start + INSERT_CHUNK]
            rows = []
            for n in chunk:
                rows.append({
                    "id": n.id,
                    "job_id": job_id,
                    "node_type": n.node_type.upper(),
                    "qualified_name": n.qualified_name or n.file_path or str(n.id),
                    "language": n.language,
                    "file_path": n.file_path,
                    "line_start": n.line_start,
                    "line_end": n.line_end,
                    "col_start": n.col_start,
                    "col_end": n.col_end,
                    "properties": n.properties,
                    "created_at": datetime.now(UTC),
                })
                node_type = n.node_type.upper()
                stats.nodes_by_type[node_type] = stats.nodes_by_type.get(node_type, 0) + 1

            try:
                await context.db_session.execute(insert(UCGNode), rows)
                await context.db_session.commit()
                stats.node_count += len(rows)
            except Exception as exc:
                await context.db_session.rollback()
                self.logger.error(
                    "[%s] Failed to insert node chunk (%d rows): %s",
                    context.job_id, len(rows), exc,
                )
                # Try row-by-row as fallback
                for row in rows:
                    try:
                        await context.db_session.execute(insert(UCGNode), [row])
                        await context.db_session.commit()
                        stats.node_count += 1
                    except Exception as row_exc:
                        await context.db_session.rollback()
                        self.logger.warning(
                            "[%s] Skipping node '%s': %s",
                            context.job_id, row.get("qualified_name"), row_exc,
                        )

    async def _bulk_insert_edges(
        self,
        context: JobContext,
        edges: list[UCGEdgeRaw],
        stats: UCGStats,
    ) -> None:
        """Bulk-insert UCGEdgeRaw objects into ucg_edges table."""
        INSERT_CHUNK = 500
        job_id = context.job_id

        for chunk_start in range(0, len(edges), INSERT_CHUNK):
            chunk = edges[chunk_start: chunk_start + INSERT_CHUNK]
            rows = []
            for e in chunk:
                if e.source_node_id == e.target_node_id:
                    continue  # DB constraint: no self-loops
                rows.append({
                    "id": uuid.uuid4(),
                    "job_id": job_id,
                    "edge_type": e.edge_type.upper(),
                    "source_node_id": e.source_node_id,
                    "target_node_id": e.target_node_id,
                    "properties": e.properties,
                    "weight": max(e.weight, 0.001),  # DB constraint: weight > 0
                    "created_at": datetime.now(UTC),
                })
                edge_type = e.edge_type.upper()
                stats.edges_by_type[edge_type] = stats.edges_by_type.get(edge_type, 0) + 1

            if not rows:
                continue

            try:
                await context.db_session.execute(insert(UCGEdge), rows)
                await context.db_session.commit()
                stats.edge_count += len(rows)
            except Exception as exc:
                await context.db_session.rollback()
                self.logger.error(
                    "[%s] Failed to insert edge chunk (%d rows): %s",
                    context.job_id, len(rows), exc,
                )
                # Try row-by-row as fallback
                for row in rows:
                    try:
                        await context.db_session.execute(insert(UCGEdge), [row])
                        await context.db_session.commit()
                        stats.edge_count += 1
                    except Exception as row_exc:
                        await context.db_session.rollback()
                        self.logger.warning(
                            "[%s] Skipping edge %s->%s: %s",
                            context.job_id,
                            row.get("source_node_id"),
                            row.get("target_node_id"),
                            row_exc,
                        )

    async def _update_job_stats(self, context: JobContext, stats: UCGStats) -> None:
        """Update the job record with UCG statistics."""
        try:
            stmt = (
                update(Job)
                .where(Job.id == context.job_id)
                .values(
                    ucg_node_count=stats.node_count,
                    ucg_edge_count=stats.edge_count,
                    updated_at=datetime.now(UTC),
                )
            )
            await context.db_session.execute(stmt)
            await context.db_session.commit()
        except Exception as exc:
            self.logger.error(
                "[%s] Failed to update job UCG stats: %s", context.job_id, exc
            )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _walk_source_files(root: Path):
    """Yield source files, skipping known vendor/build directories."""
    for item in root.rglob("*"):
        if item.is_file():
            if any(part in SKIP_DIRS for part in item.parts):
                continue
            if any(p.startswith(".") for p in item.relative_to(root).parts[:-1]):
                continue
            yield item


def _get_adapter(language: str):
    """Return the adapter for the given language, or None if not implemented."""
    try:
        if language == "java":
            from app.adapters.java import JavaAdapter
            return JavaAdapter()
        elif language == "python":
            from app.adapters.python_ast import PythonASTAdapter
            return PythonASTAdapter()
        elif language == "php":
            from app.adapters.php import PHPAdapter
            return PHPAdapter()
        elif language in ("javascript", "typescript"):
            from app.adapters.js_ts import JSTSAdapter
            return JSTSAdapter(language=language)
        else:
            return None
    except Exception as exc:
        import logging
        logging.getLogger("alm.agents.MapperAgent").warning(
            "Could not instantiate adapter for '%s': %s", language, exc
        )
        return None
