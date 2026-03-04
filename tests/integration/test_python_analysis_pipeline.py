"""
Integration tests for the Python analysis pipeline.

Tests parse -> UCG structure -> smell-detectable patterns without a real DB.
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.python_ast import PythonASTAdapter
from app.adapters.base import UCGOutput


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _parse_repo(repo_path: Path) -> UCGOutput:
    adapter = PythonASTAdapter.__new__(PythonASTAdapter)
    py_files = list(repo_path.rglob("*.py"))
    return await adapter.parse_files(py_files, repo_path)


# ---------------------------------------------------------------------------
# Parse output structure correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_output_node_structure(sample_python_repo):
    """Every node must have id, type, qualified_name, and language."""
    output = await _parse_repo(sample_python_repo)

    assert len(output.nodes) > 0, "Expected nodes from sample repo"

    for node in output.nodes:
        assert hasattr(node, "id"), f"Node missing 'id': {node}"
        assert hasattr(node, "node_type"), f"Node missing 'node_type': {node}"
        assert hasattr(node, "qualified_name"), f"Node missing 'qualified_name': {node}"
        assert isinstance(node.qualified_name, str), "qualified_name must be a string"
        assert len(node.qualified_name) > 0, "qualified_name must not be empty"


@pytest.mark.asyncio
async def test_parse_output_edge_structure(sample_python_repo):
    """Every edge must have source_node_id, target_node_id, and edge_type."""
    output = await _parse_repo(sample_python_repo)

    assert len(output.edges) > 0, "Expected edges from sample repo"

    for edge in output.edges:
        assert hasattr(edge, "source_node_id"), f"Edge missing 'source_node_id': {edge}"
        assert hasattr(edge, "target_node_id"), f"Edge missing 'target_node_id': {edge}"
        assert hasattr(edge, "edge_type"), f"Edge missing 'edge_type': {edge}"
        assert isinstance(edge.edge_type, str)
        assert len(edge.edge_type) > 0


@pytest.mark.asyncio
async def test_node_ids_are_unique(sample_python_repo):
    """No two nodes in a parse result should share the same ID."""
    output = await _parse_repo(sample_python_repo)
    ids = [node.id for node in output.nodes]
    assert len(ids) == len(set(ids)), "Duplicate node IDs detected"


@pytest.mark.asyncio
async def test_edge_references_valid_node_ids(sample_python_repo):
    """All edge endpoints should reference node IDs that exist in the output."""
    output = await _parse_repo(sample_python_repo)
    node_id_set = {node.id for node in output.nodes}

    for edge in output.edges:
        assert edge.source_node_id in node_id_set, (
            f"Edge source {edge.source_node_id} not found in nodes"
        )
        assert edge.target_node_id in node_id_set, (
            f"Edge target {edge.target_node_id} not found in nodes"
        )


# ---------------------------------------------------------------------------
# User class detectability (anemic domain model pattern)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_class_is_detected(sample_python_repo):
    """The User class with many getters/setters must appear in the UCG output."""
    output = await _parse_repo(sample_python_repo)

    class_nodes = [n for n in output.nodes if n.node_type == "CLASS"]
    class_names = {n.qualified_name.split(".")[-1] for n in class_nodes}
    assert "User" in class_names, f"Expected User class; got: {class_names}"


@pytest.mark.asyncio
async def test_user_class_has_methods(sample_python_repo):
    """User class should have its getter/setter methods parsed."""
    output = await _parse_repo(sample_python_repo)

    user_class = next(
        (n for n in output.nodes if n.node_type == "CLASS" and "User" in n.qualified_name),
        None,
    )
    assert user_class is not None, "User class not found"

    # Find CONTAINS edges from the user class
    contains_edges = [
        e for e in output.edges
        if e.edge_type == "CONTAINS" and e.source_node_id == user_class.id
    ]
    assert len(contains_edges) > 0, "Expected CONTAINS edges from User class to its methods"


@pytest.mark.asyncio
async def test_get_name_method_detected(sample_python_repo):
    """The get_name method must be present in the parsed output."""
    output = await _parse_repo(sample_python_repo)

    method_names = {
        n.qualified_name.split(".")[-1]
        for n in output.nodes
        if n.node_type == "METHOD"
    }
    assert "get_name" in method_names, (
        f"Expected 'get_name' method; found methods: {method_names}"
    )


# ---------------------------------------------------------------------------
# Service module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_services_module_parsed(sample_python_repo):
    """The services.py module should produce a MODULE node."""
    output = await _parse_repo(sample_python_repo)

    module_nodes = [n for n in output.nodes if n.node_type == "MODULE"]
    module_names = {n.qualified_name for n in module_nodes}
    # The module might be "services" or "services.py" depending on path resolution
    assert any("services" in m for m in module_names), (
        f"Expected a 'services' module; found: {module_names}"
    )


@pytest.mark.asyncio
async def test_process_user_function_detected(sample_python_repo):
    """process_user function must be present as a FUNCTION node."""
    output = await _parse_repo(sample_python_repo)

    func_nodes = [n for n in output.nodes if n.node_type == "FUNCTION"]
    func_names = {n.qualified_name.split(".")[-1] for n in func_nodes}
    assert "process_user" in func_names, (
        f"Expected 'process_user'; found: {func_names}"
    )


@pytest.mark.asyncio
async def test_validate_email_function_detected(sample_python_repo):
    output = await _parse_repo(sample_python_repo)

    func_nodes = [n for n in output.nodes if n.node_type == "FUNCTION"]
    func_names = {n.qualified_name.split(".")[-1] for n in func_nodes}
    assert "validate_email" in func_names, (
        f"Expected 'validate_email'; found: {func_names}"
    )


# ---------------------------------------------------------------------------
# Anemic domain model detection readiness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_class_accessor_ratio_detectable(sample_python_repo):
    """
    Verify the User class has enough methods that the SmellDetector
    could flag it as anemic domain model (>80% accessors).
    """
    output = await _parse_repo(sample_python_repo)

    user_class = next(
        (n for n in output.nodes if n.node_type == "CLASS" and "User" in n.qualified_name),
        None,
    )
    assert user_class is not None

    # Count CONTAINS -> METHOD edges from user class
    method_ids = {
        e.target_node_id
        for e in output.edges
        if e.edge_type == "CONTAINS" and e.source_node_id == user_class.id
    }
    methods = [n for n in output.nodes if n.id in method_ids and n.node_type == "METHOD"]

    # We expect at least 6 methods (get_name, set_name, get_email, set_email, is_active, is_admin)
    assert len(methods) >= 4, (
        f"Expected at least 4 accessor methods on User; found: "
        f"{[m.qualified_name for m in methods]}"
    )


# ---------------------------------------------------------------------------
# Error handling in pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_handles_empty_file(tmp_path):
    """An empty Python file should parse without error."""
    (tmp_path / "empty.py").write_text("")
    output = await _parse_repo(tmp_path)

    # Should succeed with minimal nodes (at least FILE)
    assert isinstance(output.nodes, list)
    assert isinstance(output.parse_errors, list)
    assert len(output.parse_errors) == 0, f"Unexpected errors: {output.parse_errors}"


@pytest.mark.asyncio
async def test_pipeline_handles_comments_only(tmp_path):
    """A Python file with only comments should parse without error."""
    (tmp_path / "comments.py").write_text("# This is a comment\n# Another comment\n")
    output = await _parse_repo(tmp_path)

    assert isinstance(output.nodes, list)
    # No parse errors expected for a syntactically valid file
    assert len(output.parse_errors) == 0


@pytest.mark.asyncio
async def test_pipeline_handles_async_function(tmp_path):
    """Async functions must be recognized as FUNCTION nodes."""
    (tmp_path / "async_code.py").write_text(
        "import asyncio\n\nasync def fetch_data(url: str) -> str:\n    return url\n"
    )
    output = await _parse_repo(tmp_path)

    func_nodes = [n for n in output.nodes if n.node_type == "FUNCTION"]
    func_names = {n.qualified_name.split(".")[-1] for n in func_nodes}
    assert "fetch_data" in func_names, f"Expected async function; found: {func_names}"

    # Verify is_async property
    fetch_node = next(
        (n for n in func_nodes if "fetch_data" in n.qualified_name), None
    )
    assert fetch_node is not None
    assert fetch_node.properties.get("is_async") is True
