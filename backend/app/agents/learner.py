"""
Agent 7: Learner

Vectorizes completed job artifacts and stores embeddings for cross-project
similarity search using pgvector.

Embedding model: text-embedding-3-small (OpenAI, 1536 dimensions)
Entities embedded: CLASS/FUNCTION nodes, smell descriptions, plan task descriptions.

Output:
  - Updates ucg_nodes.embedding
  - Inserts into embeddings table
  - Queries similar past jobs via cosine similarity
  - Returns LearnerOutput
"""

import json
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select, text

from app.agents.base import BaseAgent, JobContext
from app.models.plan import PlanTask
from app.models.smell import Smell
from app.models.ucg import Embedding, UCGNode

EMBED_BATCH_SIZE = 100  # texts per embedding API call
SIMILAR_JOB_LIMIT = 5   # max similar jobs to return


class LearnerAgent(BaseAgent):
    """
    Embeds job artifacts into pgvector for cross-project similarity search.
    Runs last in the pipeline after validation is complete.
    """

    stage_name = "learning"

    async def run(self, context: JobContext) -> dict:
        """
        Load CLASS/FUNCTION nodes, smells, and plan tasks from DB.
        Embed in batches using LLM provider's embed() method.
        Store in embeddings table. Query pgvector for similar past jobs.
        """
        job_id = context.job_id
        db = context.db_session

        if context.llm is None:
            self.logger.warning(
                "[%s] No LLM provider configured. Skipping embedding generation.", job_id
            )
            return {"embeddings_created": 0, "patterns_indexed": 0, "similar_jobs": []}

        self.logger.info("[%s] Learner agent started.", job_id)

        # Load UCG class and function nodes
        await self.emit_progress(context, "Loading UCG nodes for embedding", percent=10)
        node_result = await db.execute(
            select(UCGNode)
            .where(UCGNode.job_id == job_id)
            .where(UCGNode.node_type.in_(["CLASS", "FUNCTION", "METHOD"]))
        )
        nodes: list[UCGNode] = list(node_result.scalars().all())

        # Load smells
        smell_result = await db.execute(
            select(Smell).where(Smell.job_id == job_id)
        )
        smells: list[Smell] = list(smell_result.scalars().all())

        # Load plan tasks
        task_result = await db.execute(
            select(PlanTask).where(PlanTask.job_id == job_id)
        )
        tasks: list[PlanTask] = list(task_result.scalars().all())

        self.logger.info(
            "[%s] Embedding %d nodes, %d smells, %d tasks.",
            job_id, len(nodes), len(smells), len(tasks),
        )

        embeddings_created = 0

        # Embed UCG nodes
        if nodes:
            await self.emit_progress(context, "Embedding UCG class/function nodes", percent=20)
            count = await self._embed_nodes(context, nodes)
            embeddings_created += count

        # Embed smells
        if smells:
            await self.emit_progress(context, "Embedding smell descriptions", percent=50)
            count = await self._embed_smells(context, smells)
            embeddings_created += count

        # Embed plan tasks
        if tasks:
            await self.emit_progress(context, "Embedding plan task descriptions", percent=70)
            count = await self._embed_tasks(context, tasks)
            embeddings_created += count

        # Query for similar past jobs
        await self.emit_progress(context, "Querying similar past jobs", percent=85)
        similar_jobs = await self._find_similar_jobs(context, smells)

        self.logger.info(
            "[%s] Learner complete: %d embeddings created, %d similar jobs found.",
            job_id, embeddings_created, len(similar_jobs),
        )

        return {
            "embeddings_created": embeddings_created,
            "patterns_indexed": len(nodes) + len(smells) + len(tasks),
            "similar_jobs": [str(jid) for jid in similar_jobs],
        }

    async def _embed_nodes(self, context: JobContext, nodes: list[UCGNode]) -> int:
        """Generate embeddings for UCG class/function nodes."""
        db = context.db_session
        count = 0

        # Build text representations for embedding
        texts = []
        for node in nodes:
            props = node.properties or {}
            text_repr = (
                f"language:{node.language} "
                f"type:{node.node_type} "
                f"name:{node.qualified_name} "
                f"file:{node.file_path or ''} "
                f"bases:{props.get('bases', [])} "
                f"is_abstract:{props.get('is_abstract', False)} "
                f"visibility:{props.get('visibility', 'public')}"
            )
            texts.append(text_repr)

        # Process in batches
        for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch_texts = texts[batch_start: batch_start + EMBED_BATCH_SIZE]
            batch_nodes = nodes[batch_start: batch_start + EMBED_BATCH_SIZE]

            try:
                result = await context.llm.embed(batch_texts)
                embedding_rows = []

                for node, text_repr, embedding_vec in zip(
                    batch_nodes, batch_texts, result.embeddings
                ):
                    embedding_rows.append({
                        "id": uuid.uuid4(),
                        "job_id": context.job_id,
                        "entity_type": "ucg_node",
                        "entity_id": node.id,
                        "content_text": text_repr[:4000],
                        "embedding": embedding_vec,
                        "model_used": result.model,
                        "created_at": datetime.now(UTC),
                    })

                if embedding_rows:
                    await db.execute(insert(Embedding), embedding_rows)
                    await db.commit()
                    count += len(embedding_rows)

            except Exception as exc:
                await db.rollback()
                self.logger.error(
                    "[%s] Failed to embed node batch (start=%d): %s",
                    context.job_id, batch_start, exc,
                )

        return count

    async def _embed_smells(self, context: JobContext, smells: list[Smell]) -> int:
        """Generate embeddings for smell descriptions."""
        db = context.db_session
        count = 0

        texts = []
        for smell in smells:
            text_repr = (
                f"smell_type:{smell.smell_type} "
                f"severity:{smell.severity} "
                f"description:{smell.description} "
                f"evidence:{json.dumps(smell.evidence)[:500]}"
            )
            texts.append(text_repr)

        for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch_texts = texts[batch_start: batch_start + EMBED_BATCH_SIZE]
            batch_smells = smells[batch_start: batch_start + EMBED_BATCH_SIZE]

            try:
                result = await context.llm.embed(batch_texts)
                rows = [
                    {
                        "id": uuid.uuid4(),
                        "job_id": context.job_id,
                        "entity_type": "smell",
                        "entity_id": smell.id,
                        "content_text": text_repr[:4000],
                        "embedding": emb_vec,
                        "model_used": result.model,
                        "created_at": datetime.now(UTC),
                    }
                    for smell, text_repr, emb_vec in zip(batch_smells, batch_texts, result.embeddings)
                ]
                if rows:
                    await db.execute(insert(Embedding), rows)
                    await db.commit()
                    count += len(rows)
            except Exception as exc:
                await db.rollback()
                self.logger.error(
                    "[%s] Failed to embed smell batch: %s", context.job_id, exc
                )

        return count

    async def _embed_tasks(self, context: JobContext, tasks: list[PlanTask]) -> int:
        """Generate embeddings for plan task descriptions."""
        db = context.db_session
        count = 0

        texts = []
        for task in tasks:
            text_repr = (
                f"title:{task.title} "
                f"pattern:{task.refactor_pattern} "
                f"description:{task.description[:500]} "
                f"automated:{task.automated} "
                f"effort:{task.estimated_hours}"
            )
            texts.append(text_repr)

        for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch_texts = texts[batch_start: batch_start + EMBED_BATCH_SIZE]
            batch_tasks = tasks[batch_start: batch_start + EMBED_BATCH_SIZE]

            try:
                result = await context.llm.embed(batch_texts)
                rows = [
                    {
                        "id": uuid.uuid4(),
                        "job_id": context.job_id,
                        "entity_type": "plan_task",
                        "entity_id": task.id,
                        "content_text": text_repr[:4000],
                        "embedding": emb_vec,
                        "model_used": result.model,
                        "created_at": datetime.now(UTC),
                    }
                    for task, text_repr, emb_vec in zip(batch_tasks, batch_texts, result.embeddings)
                ]
                if rows:
                    await db.execute(insert(Embedding), rows)
                    await db.commit()
                    count += len(rows)
            except Exception as exc:
                await db.rollback()
                self.logger.error(
                    "[%s] Failed to embed task batch: %s", context.job_id, exc
                )

        return count

    async def _find_similar_jobs(
        self, context: JobContext, smells: list[Smell]
    ) -> list[UUID]:
        """
        Query the embeddings table for similar jobs using smell profile similarity.
        Uses pgvector cosine similarity if embeddings are available.
        """
        if not smells:
            return []

        db = context.db_session

        # Build a smell profile string for this job
        profile_text = " ".join(
            f"{s.smell_type}:{s.severity}" for s in smells[:20]
        )

        try:
            embedding_result = await context.llm.embed([profile_text])
            if not embedding_result.embeddings:
                return []
            query_vec = embedding_result.embeddings[0]
        except Exception as exc:
            self.logger.warning("[%s] Could not embed job profile: %s", context.job_id, exc)
            return []

        # Query pgvector for similar embeddings in other jobs
        try:
            vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"
            stmt = text(
                """
                SELECT DISTINCT e.job_id, 1 - (e.embedding <=> :vec::vector) AS similarity
                FROM embeddings e
                WHERE e.entity_type = 'smell'
                  AND e.job_id != :job_id
                ORDER BY similarity DESC
                LIMIT :limit
                """
            )
            result = await db.execute(
                stmt,
                {"vec": vec_str, "job_id": context.job_id, "limit": SIMILAR_JOB_LIMIT},
            )
            rows = result.fetchall()
            return [row[0] for row in rows if row[1] > 0.7]  # cosine similarity > 0.7

        except Exception as exc:
            self.logger.warning(
                "[%s] pgvector similarity query failed (pgvector may not be enabled): %s",
                context.job_id, exc,
            )
            return []
