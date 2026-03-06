"""
UCG Graph endpoints — full graph, nodes, edges, metrics, subgraph extraction.

GET  /graph/{job_id}                   — full UCG (paginated nodes + edges)
GET  /graph/{job_id}/nodes             — list nodes with type/language/search filters
GET  /graph/{job_id}/nodes/{node_id}   — single node with neighbor edges
GET  /graph/{job_id}/edges             — list edges with type filters
GET  /graph/{job_id}/metrics           — computed graph metrics
POST /graph/{job_id}/subgraph          — extract subgraph by seed node set
"""

from collections import deque
from datetime import UTC, datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.core.cache import cache_get, cache_set
from app.models.job import Job
from app.models.ucg import UCGEdge, UCGNode
from app.schemas.job import PaginationMeta
from app.schemas.ucg import (
    GraphMetricsResponse,
    GraphMetricsSummary,
    IncomingEdgeDetail,
    OutgoingEdgeDetail,
    SubgraphRequest,
    SubgraphResponse,
    TopComplexFunction,
    TopCoupledNode,
    UCGEdgeListResponse,
    UCGEdgeResponse,
    UCGGraphResponse,
    UCGNodeDetailResponse,
    UCGNodeListResponse,
    UCGNodeResponse,
)

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


def _node_to_schema(node: UCGNode) -> UCGNodeResponse:
    return UCGNodeResponse(
        id=node.id,
        node_type=node.node_type,
        qualified_name=node.qualified_name,
        language=node.language,
        file_path=node.file_path,
        line_start=node.line_start,
        line_end=node.line_end,
        col_start=node.col_start,
        col_end=node.col_end,
        properties=node.properties or {},
        created_at=node.created_at,
    )


def _edge_to_schema(edge: UCGEdge) -> UCGEdgeResponse:
    return UCGEdgeResponse(
        id=edge.id,
        edge_type=edge.edge_type,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        weight=edge.weight,
        properties=edge.properties or {},
        created_at=edge.created_at,
    )


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get("/{job_id}", response_model=UCGGraphResponse)
async def get_graph(
    job_id: UUID,
    page: int = 1,
    page_size: int = 100,
    include_edges: bool = True,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> UCGGraphResponse:
    """Get the full UCG for a job with paginated nodes and optional edges."""
    page_size = max(1, min(page_size, 500))
    page = max(1, page)
    offset = (page - 1) * page_size

    job = await _get_job_or_404(job_id, db)

    # Serve from cache for completed jobs.
    cache_key = f"alm:graph:{job_id}:p{page}:ps{page_size}:e{int(include_edges)}"
    if job.status == "complete":
        cached = await cache_get(cache_key)
        if cached:
            return UCGGraphResponse(**cached)

    # Count total nodes for pagination.
    count_result = await db.execute(
        select(func.count()).select_from(UCGNode).where(UCGNode.job_id == job_id)
    )
    total_nodes = count_result.scalar_one()
    total_pages = ceil(total_nodes / page_size) if total_nodes > 0 else 1

    # Fetch the page of nodes.
    nodes_result = await db.execute(
        select(UCGNode)
        .where(UCGNode.job_id == job_id)
        .order_by(UCGNode.created_at)
        .offset(offset)
        .limit(page_size)
    )
    nodes = nodes_result.scalars().all()
    node_ids = {n.id for n in nodes}

    # Fetch edges that connect nodes on this page (optional).
    edges: list[UCGEdge] = []
    if include_edges and node_ids:
        edges_result = await db.execute(
            select(UCGEdge).where(
                UCGEdge.job_id == job_id,
                or_(
                    UCGEdge.source_node_id.in_(node_ids),
                    UCGEdge.target_node_id.in_(node_ids),
                ),
            )
        )
        edges = edges_result.scalars().all()

    response = UCGGraphResponse(
        job_id=job_id,
        nodes=[_node_to_schema(n) for n in nodes],
        edges=[_edge_to_schema(e) for e in edges],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_nodes,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )

    if job.status == "complete":
        await cache_set(cache_key, response.model_dump(), ttl=3600)

    return response


@router.get("/{job_id}/nodes", response_model=UCGNodeListResponse)
async def list_nodes(
    job_id: UUID,
    node_type: str | None = None,
    language: str | None = None,
    file_path: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> UCGNodeListResponse:
    """List UCG nodes with optional type, language, path, and text filters."""
    page_size = max(1, min(page_size, 500))
    page = max(1, page)
    offset = (page - 1) * page_size

    await _get_job_or_404(job_id, db)

    query = select(UCGNode).where(UCGNode.job_id == job_id)
    count_query = select(func.count()).select_from(UCGNode).where(UCGNode.job_id == job_id)

    if node_type:
        query = query.where(UCGNode.node_type == node_type.upper())
        count_query = count_query.where(UCGNode.node_type == node_type.upper())
    if language:
        query = query.where(UCGNode.language == language.lower())
        count_query = count_query.where(UCGNode.language == language.lower())
    if file_path:
        query = query.where(UCGNode.file_path.like(f"{file_path}%"))
        count_query = count_query.where(UCGNode.file_path.like(f"{file_path}%"))
    if search:
        query = query.where(UCGNode.qualified_name.ilike(f"%{search}%"))
        count_query = count_query.where(UCGNode.qualified_name.ilike(f"%{search}%"))

    total_items = (await db.execute(count_query)).scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    nodes_result = await db.execute(
        query.order_by(UCGNode.qualified_name).offset(offset).limit(page_size)
    )
    nodes = nodes_result.scalars().all()

    return UCGNodeListResponse(
        data=[_node_to_schema(n) for n in nodes],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get("/{job_id}/nodes/{node_id}", response_model=UCGNodeDetailResponse)
async def get_node(
    job_id: UUID,
    node_id: UUID,
    depth: int = 1,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> UCGNodeDetailResponse:
    """Get a single UCG node with its direct incoming and outgoing edges."""
    depth = max(1, min(depth, 3))

    node_result = await db.execute(
        select(UCGNode).where(UCGNode.id == node_id, UCGNode.job_id == job_id)
    )
    node = node_result.scalar_one_or_none()
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "node_not_found", "message": f"No node {node_id} in job {job_id}"},
        )

    # Fetch incoming edges to this node.
    incoming_result = await db.execute(
        select(UCGEdge, UCGNode)
        .join(UCGNode, UCGNode.id == UCGEdge.source_node_id)
        .where(UCGEdge.target_node_id == node_id, UCGEdge.job_id == job_id)
        .limit(200)
    )
    incoming_edges = [
        IncomingEdgeDetail(
            edge_type=row[0].edge_type,
            source_node_id=row[0].source_node_id,
            source_node_type=row[1].node_type,
            source_qualified_name=row[1].qualified_name,
        )
        for row in incoming_result.all()
    ]

    # Fetch outgoing edges from this node.
    outgoing_result = await db.execute(
        select(UCGEdge, UCGNode)
        .join(UCGNode, UCGNode.id == UCGEdge.target_node_id)
        .where(UCGEdge.source_node_id == node_id, UCGEdge.job_id == job_id)
        .limit(200)
    )
    outgoing_edges = [
        OutgoingEdgeDetail(
            edge_type=row[0].edge_type,
            target_node_id=row[0].target_node_id,
            target_node_type=row[1].node_type,
            target_qualified_name=row[1].qualified_name,
        )
        for row in outgoing_result.all()
    ]

    return UCGNodeDetailResponse(
        node=_node_to_schema(node),
        incoming_edges=incoming_edges,
        outgoing_edges=outgoing_edges,
    )


@router.get("/{job_id}/edges", response_model=UCGEdgeListResponse)
async def list_edges(
    job_id: UUID,
    edge_type: str | None = None,
    source_node_id: UUID | None = None,
    target_node_id: UUID | None = None,
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> UCGEdgeListResponse:
    """List UCG edges with optional edge type and node ID filters."""
    page_size = max(1, min(page_size, 500))
    page = max(1, page)
    offset = (page - 1) * page_size

    await _get_job_or_404(job_id, db)

    query = select(UCGEdge).where(UCGEdge.job_id == job_id)
    count_query = select(func.count()).select_from(UCGEdge).where(UCGEdge.job_id == job_id)

    if edge_type:
        query = query.where(UCGEdge.edge_type == edge_type.upper())
        count_query = count_query.where(UCGEdge.edge_type == edge_type.upper())
    if source_node_id:
        query = query.where(UCGEdge.source_node_id == source_node_id)
        count_query = count_query.where(UCGEdge.source_node_id == source_node_id)
    if target_node_id:
        query = query.where(UCGEdge.target_node_id == target_node_id)
        count_query = count_query.where(UCGEdge.target_node_id == target_node_id)

    total_items = (await db.execute(count_query)).scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    edges_result = await db.execute(
        query.order_by(UCGEdge.created_at).offset(offset).limit(page_size)
    )
    edges = edges_result.scalars().all()

    return UCGEdgeListResponse(
        data=[_edge_to_schema(e) for e in edges],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


@router.get("/{job_id}/metrics", response_model=GraphMetricsResponse)
async def get_metrics(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> GraphMetricsResponse:
    """
    Get computed graph metrics for a job.

    Computes coupling statistics, cyclomatic complexity, and dead code counts
    from the UCG node/edge data. Results are cached in Redis for completed jobs.
    """
    job = await _get_job_or_404(job_id, db)

    # Serve from cache for completed jobs (metrics never change after completion).
    cache_key = f"alm:metrics:{job_id}"
    if job.status == "complete":
        cached = await cache_get(cache_key)
        if cached:
            return GraphMetricsResponse(**cached)

    total_nodes = (
        await db.execute(
            select(func.count()).select_from(UCGNode).where(UCGNode.job_id == job_id)
        )
    ).scalar_one()
    total_edges = (
        await db.execute(
            select(func.count()).select_from(UCGEdge).where(UCGEdge.job_id == job_id)
        )
    ).scalar_one()

    average_coupling = round(total_edges / total_nodes, 2) if total_nodes > 0 else 0.0

    # Top coupled nodes: compute in/out coupling counts in a single aggregated query
    # to avoid the N+1 pattern of issuing 2 queries per CLASS/MODULE node.
    #
    # Strategy: fetch all CLASS/MODULE node IDs for this job, then run a single
    # GROUP BY aggregate over UCGEdge that counts inbound and outbound edges per node.
    class_node_ids_result = await db.execute(
        select(UCGNode.id, UCGNode.qualified_name)
        .where(UCGNode.job_id == job_id, UCGNode.node_type.in_(["CLASS", "MODULE"]))
        .limit(200)
    )
    class_node_rows = class_node_ids_result.all()  # list of (id, qualified_name)
    class_node_ids = [row[0] for row in class_node_rows]
    class_node_names = {row[0]: row[1] for row in class_node_rows}

    top_coupled: list[TopCoupledNode] = []
    if class_node_ids:
        # Single query: count inbound edges per target_node_id + outbound per source_node_id.
        # We union both directions then sum by node_id.
        coupling_edges = ["CALLS", "DEPENDS_ON"]

        in_subq = (
            select(
                UCGEdge.target_node_id.label("node_id"),
                func.count().label("in_count"),
            )
            .where(
                UCGEdge.job_id == job_id,
                UCGEdge.target_node_id.in_(class_node_ids),
                UCGEdge.edge_type.in_(coupling_edges),
            )
            .group_by(UCGEdge.target_node_id)
            .subquery()
        )

        out_subq = (
            select(
                UCGEdge.source_node_id.label("node_id"),
                func.count().label("out_count"),
            )
            .where(
                UCGEdge.job_id == job_id,
                UCGEdge.source_node_id.in_(class_node_ids),
                UCGEdge.edge_type.in_(coupling_edges),
            )
            .group_by(UCGEdge.source_node_id)
            .subquery()
        )

        # Full outer join on node_id to get both in and out counts in one row set.
        # SQLAlchemy doesn't support FULL OUTER JOIN portably, so we use two LEFT JOINs
        # anchored to the list of class node IDs via a VALUES-style subquery approach.
        # Simpler: just fetch both subqueries and merge in Python (still 2 queries, not 2*N).
        in_rows_result = await db.execute(select(in_subq))
        out_rows_result = await db.execute(select(out_subq))

        in_map: dict = {row.node_id: row.in_count for row in in_rows_result.all()}
        out_map: dict = {row.node_id: row.out_count for row in out_rows_result.all()}

        for node_id in class_node_ids:
            in_count = in_map.get(node_id, 0)
            out_count = out_map.get(node_id, 0)
            total = in_count + out_count
            if total == 0:
                continue
            instability = round(out_count / total, 3)
            top_coupled.append(
                TopCoupledNode(
                    node_id=node_id,
                    qualified_name=class_node_names[node_id],
                    afferent_coupling=in_count,
                    efferent_coupling=out_count,
                    instability=instability,
                )
            )

    top_coupled.sort(key=lambda x: x.afferent_coupling + x.efferent_coupling, reverse=True)
    top_coupled = top_coupled[:10]

    # Top complex functions: approximated by line count.
    func_nodes_result = await db.execute(
        select(UCGNode)
        .where(
            UCGNode.job_id == job_id,
            UCGNode.node_type.in_(["FUNCTION", "METHOD"]),
            UCGNode.line_start.isnot(None),
            UCGNode.line_end.isnot(None),
        )
        .order_by((UCGNode.line_end - UCGNode.line_start).desc())  # type: ignore[operator]
        .limit(10)
    )
    func_nodes = func_nodes_result.scalars().all()

    top_complex = [
        TopComplexFunction(
            node_id=n.id,
            qualified_name=n.qualified_name,
            # Cyclomatic complexity stored in properties by the mapper agent.
            cyclomatic_complexity=n.properties.get("cyclomatic_complexity", 1) if n.properties else 1,
            lines_of_code=(n.line_end - n.line_start) if n.line_end and n.line_start else 0,
        )
        for n in func_nodes
    ]

    max_cc = max((t.cyclomatic_complexity for t in top_complex), default=0)

    # Dead code count: nodes with zero inbound edges (excluding FILE/MODULE at top level).
    dead_code_count = 0
    leaf_node_types = ["FUNCTION", "METHOD", "CLASS"]
    leaf_result = await db.execute(
        select(UCGNode.id).where(
            UCGNode.job_id == job_id,
            UCGNode.node_type.in_(leaf_node_types),
        )
    )
    leaf_ids = [row[0] for row in leaf_result.all()]

    # Batch check for nodes with no inbound CALLS edges.
    if leaf_ids:
        referenced_result = await db.execute(
            select(UCGEdge.target_node_id).where(
                UCGEdge.job_id == job_id,
                UCGEdge.target_node_id.in_(leaf_ids),
                UCGEdge.edge_type == "CALLS",
            ).distinct()
        )
        referenced_ids = {row[0] for row in referenced_result.all()}
        dead_code_count = len(set(leaf_ids) - referenced_ids)

    # Circular dependency count: approximated by CIRCULAR_DEPENDENCY smells.
    from app.models.smell import Smell  # noqa: PLC0415
    circ_dep_count = (
        await db.execute(
            select(func.count()).select_from(Smell).where(
                Smell.job_id == job_id,
                Smell.smell_type == "circular_dependency",
                Smell.dismissed.is_(False),
            )
        )
    ).scalar_one()

    response = GraphMetricsResponse(
        job_id=job_id,
        computed_at=datetime.now(UTC),
        summary=GraphMetricsSummary(
            total_nodes=total_nodes,
            total_edges=total_edges,
            average_coupling=average_coupling,
            max_cyclomatic_complexity=max_cc,
            circular_dependency_count=circ_dep_count,
            dead_code_node_count=dead_code_count,
        ),
        top_coupled_nodes=top_coupled,
        top_complex_functions=top_complex,
    )

    if job.status == "complete":
        await cache_set(cache_key, response.model_dump(), ttl=3600)

    return response


@router.post("/{job_id}/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    job_id: UUID,
    body: SubgraphRequest,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> SubgraphResponse:
    """
    Extract a subgraph around a set of seed nodes using BFS.

    Traverses up to ``depth`` hops from each seed node following the specified
    edge types in the given direction. Returns all reachable nodes and the
    edges connecting them.
    """
    await _get_job_or_404(job_id, db)

    # Validate that seed nodes belong to this job.
    seed_result = await db.execute(
        select(UCGNode).where(
            UCGNode.id.in_(body.seed_node_ids),
            UCGNode.job_id == job_id,
        )
    )
    seed_nodes = {n.id: n for n in seed_result.scalars().all()}
    if not seed_nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "nodes_not_found", "message": "No seed nodes found in this job."},
        )

    # BFS traversal.
    visited_node_ids: set[UUID] = set(seed_nodes.keys())
    frontier: deque[UUID] = deque(seed_nodes.keys())
    collected_edges: dict[UUID, UCGEdge] = {}
    collected_nodes: dict[UUID, UCGNode] = dict(seed_nodes)

    for _ in range(body.depth):
        if not frontier:
            break
        current_ids = list(frontier)
        frontier.clear()

        edge_query = select(UCGEdge).where(UCGEdge.job_id == job_id)
        if body.edge_types:
            upper_types = [t.upper() for t in body.edge_types]
            edge_query = edge_query.where(UCGEdge.edge_type.in_(upper_types))

        if body.direction == "outbound":
            edge_query = edge_query.where(UCGEdge.source_node_id.in_(current_ids))
        elif body.direction == "inbound":
            edge_query = edge_query.where(UCGEdge.target_node_id.in_(current_ids))
        else:  # "both"
            edge_query = edge_query.where(
                or_(
                    UCGEdge.source_node_id.in_(current_ids),
                    UCGEdge.target_node_id.in_(current_ids),
                )
            )

        edges_result = await db.execute(edge_query)
        new_edges = edges_result.scalars().all()

        for edge in new_edges:
            collected_edges[edge.id] = edge
            for neighbor_id in (edge.source_node_id, edge.target_node_id):
                if neighbor_id not in visited_node_ids:
                    visited_node_ids.add(neighbor_id)
                    frontier.append(neighbor_id)

        # Fetch newly discovered nodes.
        if frontier:
            new_node_ids = list(frontier)
            new_nodes_result = await db.execute(
                select(UCGNode).where(
                    UCGNode.id.in_(new_node_ids),
                    UCGNode.job_id == job_id,
                )
            )
            for n in new_nodes_result.scalars().all():
                collected_nodes[n.id] = n

    return SubgraphResponse(
        nodes=[_node_to_schema(n) for n in collected_nodes.values()],
        edges=[_edge_to_schema(e) for e in collected_edges.values()],
        seed_node_ids=list(seed_nodes.keys()),
        depth=body.depth,
    )
