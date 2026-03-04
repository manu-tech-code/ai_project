"""
Pydantic v2 schemas for UCG node, edge, graph, and metrics responses.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import PaginationMeta


class UCGNodeResponse(BaseModel):
    """A single UCG node as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_type: str
    qualified_name: str
    language: str
    file_path: str | None
    line_start: int | None
    line_end: int | None
    col_start: int | None
    col_end: int | None
    properties: dict
    created_at: datetime


class UCGEdgeResponse(BaseModel):
    """A single UCG edge as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    edge_type: str
    source_node_id: UUID
    target_node_id: UUID
    weight: float
    properties: dict
    created_at: datetime


class UCGGraphResponse(BaseModel):
    """Full UCG graph response (paginated nodes + optional edges)."""

    job_id: UUID
    nodes: list[UCGNodeResponse]
    edges: list[UCGEdgeResponse]
    pagination: PaginationMeta


class UCGNodeListResponse(BaseModel):
    """Paginated list of UCG nodes."""

    data: list[UCGNodeResponse]
    pagination: PaginationMeta


class UCGEdgeListResponse(BaseModel):
    """Paginated list of UCG edges."""

    data: list[UCGEdgeResponse]
    pagination: PaginationMeta


class IncomingEdgeDetail(BaseModel):
    """Condensed edge representation for the single-node detail endpoint."""

    edge_type: str
    source_node_id: UUID
    source_node_type: str
    source_qualified_name: str


class OutgoingEdgeDetail(BaseModel):
    """Condensed edge representation for the single-node detail endpoint."""

    edge_type: str
    target_node_id: UUID
    target_node_type: str
    target_qualified_name: str


class UCGNodeDetailResponse(BaseModel):
    """Single node with its immediate neighbors."""

    node: UCGNodeResponse
    incoming_edges: list[IncomingEdgeDetail]
    outgoing_edges: list[OutgoingEdgeDetail]


class TopCoupledNode(BaseModel):
    node_id: UUID
    qualified_name: str
    afferent_coupling: int
    efferent_coupling: int
    instability: float


class TopComplexFunction(BaseModel):
    node_id: UUID
    qualified_name: str
    cyclomatic_complexity: int
    lines_of_code: int


class GraphMetricsSummary(BaseModel):
    total_nodes: int
    total_edges: int
    average_coupling: float
    max_cyclomatic_complexity: int
    circular_dependency_count: int
    dead_code_node_count: int


class GraphMetricsResponse(BaseModel):
    """Computed graph metrics for a completed job."""

    job_id: UUID
    computed_at: datetime
    summary: GraphMetricsSummary
    top_coupled_nodes: list[TopCoupledNode]
    top_complex_functions: list[TopComplexFunction]


class SubgraphRequest(BaseModel):
    """Request body for POST /graph/{job_id}/subgraph."""

    seed_node_ids: list[UUID] = Field(..., min_length=1)
    depth: int = Field(default=2, ge=1, le=5)
    edge_types: list[str] | None = Field(
        default=None,
        description="Edge types to traverse (null = all types)",
    )
    direction: str = Field(
        default="both",
        description="Traversal direction: 'inbound' | 'outbound' | 'both'",
    )


class SubgraphResponse(BaseModel):
    """Extracted subgraph response."""

    nodes: list[UCGNodeResponse]
    edges: list[UCGEdgeResponse]
    seed_node_ids: list[UUID]
    depth: int
