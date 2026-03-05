"""
JavaAdapter — delegates to the Java Parser Service (Spring Boot + JavaParser).

Makes HTTP POST requests to the java-parser-service with the repo path.
The service returns pre-built UCG nodes and edges as JSON.

External: http://java-parser:8090/parse
"""

from pathlib import Path
from uuid import UUID, uuid4

import httpx

from app.adapters.base import BaseAdapter, UCGEdgeRaw, UCGNodeRaw, UCGOutput
from app.core.config import settings


class JavaAdapter(BaseAdapter):
    """
    Parses Java source files by delegating to the java-parser-service.

    The Java parser service runs JavaParser 3.26.2 inside a Spring Boot 3.4.2
    application and returns a structured UCG JSON payload.

    Files are sent as a ZIP archive via multipart upload.
    """

    language = "java"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.JAVA_PARSER_URL,
            timeout=float(settings.java_parser_timeout),
        )

    async def parse_files(self, files: list[Path], repo_root: Path) -> UCGOutput:
        """
        Send the repo path to the java-parser-service and parse the response.
        The service reads files directly from the shared filesystem path.
        """
        output = UCGOutput()

        if not files:
            return output

        try:
            response = await self._client.post(
                "/parse",
                json={"repoPath": str(repo_root)},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.ConnectError as exc:
            output.parse_errors.append({
                "file_path": str(repo_root),
                "error_message": f"Java parser service not reachable: {exc}",
                "line_number": None,
            })
            return output
        except httpx.HTTPStatusError as exc:
            output.parse_errors.append({
                "file_path": str(repo_root),
                "error_message": (
                    f"Java parser service HTTP error {exc.response.status_code}: {exc.response.text[:500]}"
                ),
                "line_number": None,
            })
            return output
        except Exception as exc:
            output.parse_errors.append({
                "file_path": str(repo_root),
                "error_message": f"Unexpected error calling Java parser service: {exc}",
                "line_number": None,
            })
            return output

        # Parse the response JSON into UCGNodeRaw / UCGEdgeRaw structures
        raw_nodes = data.get("nodes", [])
        raw_edges = data.get("edges", [])
        service_errors = data.get("errors", [])

        # Build a mapping of service-side node IDs -> local UUIDs
        id_map: dict[str, UUID] = {}
        for raw in raw_nodes:
            service_id = raw.get("id", str(uuid4()))
            local_id = uuid4()
            id_map[service_id] = local_id

            node = UCGNodeRaw(
                node_type=_normalize_node_type(raw.get("type", "CLASS")),
                qualified_name=raw.get("qualifiedName") or raw.get("name") or service_id,
                language="java",
                file_path=raw.get("filePath") or raw.get("file_path") or "",
                line_start=raw.get("lineStart") or raw.get("line_start"),
                line_end=raw.get("lineEnd") or raw.get("line_end"),
                col_start=raw.get("colStart") or raw.get("col_start"),
                col_end=raw.get("colEnd") or raw.get("col_end"),
                properties=raw.get("properties") or raw.get("metadata") or {},
            )
            node._id = local_id
            output.nodes.append(node)

        for raw in raw_edges:
            src_service = raw.get("source") or raw.get("sourceNodeId") or ""
            tgt_service = raw.get("target") or raw.get("targetNodeId") or ""
            src_uuid = id_map.get(src_service)
            tgt_uuid = id_map.get(tgt_service)
            if src_uuid is None or tgt_uuid is None:
                continue
            if src_uuid == tgt_uuid:
                continue
            edge = UCGEdgeRaw(
                edge_type=_normalize_edge_type(raw.get("type", "CONTAINS")),
                source_node_id=src_uuid,
                target_node_id=tgt_uuid,
                properties=raw.get("properties") or {},
                weight=float(raw.get("weight", 1.0)),
            )
            output.edges.append(edge)

        for err in service_errors:
            if isinstance(err, str):
                output.parse_errors.append({
                    "file_path": "",
                    "error_message": err,
                    "line_number": None,
                })
            elif isinstance(err, dict):
                output.parse_errors.append({
                    "file_path": err.get("filePath") or err.get("file_path") or "",
                    "error_message": err.get("message") or str(err),
                    "line_number": err.get("lineNumber") or err.get("line_number"),
                })

        return output

    async def close(self) -> None:
        await self._client.aclose()


# ── Normalization helpers ────────────────────────────────────────────────────

_VALID_NODE_TYPES = {
    "FILE", "MODULE", "CLASS", "FUNCTION", "METHOD", "FIELD",
    "VARIABLE", "PARAMETER", "IMPORT", "ANNOTATION", "BLOCK",
    "LITERAL", "CALL_SITE", "TYPE_REF", "COMMENT",
}

_VALID_EDGE_TYPES = {
    "CONTAINS", "CALLS", "EXTENDS", "IMPLEMENTS", "IMPORTS",
    "USES_TYPE", "HAS_PARAMETER", "HAS_FIELD", "HAS_ANNOTATION",
    "RETURNS", "THROWS", "OVERRIDES", "DEPENDS_ON", "INSTANTIATES",
    "READS", "WRITES", "DEFINED_IN",
}


def _normalize_node_type(raw: str) -> str:
    upper = raw.upper()
    return upper if upper in _VALID_NODE_TYPES else "CLASS"


def _normalize_edge_type(raw: str) -> str:
    upper = raw.upper()
    return upper if upper in _VALID_EDGE_TYPES else "CONTAINS"
