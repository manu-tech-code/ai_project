"""
BaseAdapter — abstract base class for all language-specific UCG adapters.

Each adapter receives a list of source files and produces UCG nodes and edges
in the format expected by the Mapper agent for bulk database insertion.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4


@dataclass
class UCGNodeRaw:
    """Intermediate UCG node representation before DB insertion."""

    node_type: str
    qualified_name: str
    language: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    col_start: int | None = None
    col_end: int | None = None
    properties: dict = field(default_factory=dict)
    _id: UUID = field(default_factory=uuid4)

    @property
    def id(self) -> UUID:
        return self._id


@dataclass
class UCGEdgeRaw:
    """Intermediate UCG edge representation before DB insertion."""

    edge_type: str
    source_node_id: UUID
    target_node_id: UUID
    properties: dict = field(default_factory=dict)
    weight: float = 1.0


@dataclass
class UCGOutput:
    """Complete output of a language adapter's parse operation."""

    nodes: list[UCGNodeRaw] = field(default_factory=list)
    edges: list[UCGEdgeRaw] = field(default_factory=list)
    parse_errors: list[dict] = field(default_factory=list)


class BaseAdapter(ABC):
    """
    Abstract base class for language-specific AST -> UCG adapters.

    Subclasses must implement `parse_files(files, repo_root)`.
    """

    #: The language this adapter handles.
    language: str = "unknown"

    @abstractmethod
    async def parse_files(self, files: list[Path], repo_root: Path) -> UCGOutput:
        """
        Parse the given source files and return UCG nodes and edges.

        Args:
            files: Source files to parse (all belong to this adapter's language).
            repo_root: Repository root for computing relative paths.

        Returns:
            UCGOutput with nodes, edges, and any parse errors encountered.
        """
