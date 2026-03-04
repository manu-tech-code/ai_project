"""
Unit tests for app.adapters.python_ast.PythonASTAdapter.

Verifies UCG node/edge extraction from Python source files.
No database or external services required.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from app.adapters.python_ast import PythonASTAdapter
from app.adapters.base import UCGOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter() -> PythonASTAdapter:
    """Instantiate adapter with a stub settings object."""
    settings = MagicMock()
    adapter = PythonASTAdapter.__new__(PythonASTAdapter)
    return adapter


async def _parse(tmp_path: Path) -> UCGOutput:
    adapter = _make_adapter()
    py_files = list(tmp_path.rglob("*.py"))
    return await adapter.parse_files(py_files, tmp_path)


# ---------------------------------------------------------------------------
# Basic parse output structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_returns_nodes_and_edges(sample_python_repo):
    output = await _parse(sample_python_repo)

    assert hasattr(output, "nodes"), "UCGOutput must have a 'nodes' attribute"
    assert hasattr(output, "edges"), "UCGOutput must have an 'edges' attribute"
    assert hasattr(output, "parse_errors"), "UCGOutput must have a 'parse_errors' attribute"


@pytest.mark.asyncio
async def test_parse_produces_nodes(sample_python_repo):
    output = await _parse(sample_python_repo)
    assert len(output.nodes) > 0, "Expected at least one UCG node from the sample Python repo"


@pytest.mark.asyncio
async def test_every_node_has_required_fields(sample_python_repo):
    output = await _parse(sample_python_repo)

    for node in output.nodes:
        assert hasattr(node, "id"), "Node missing 'id'"
        assert hasattr(node, "node_type"), "Node missing 'node_type'"
        assert hasattr(node, "qualified_name"), "Node missing 'qualified_name'"
        assert hasattr(node, "language"), "Node missing 'language'"
        assert node.language == "python", f"Expected language='python', got {node.language!r}"


@pytest.mark.asyncio
async def test_every_edge_has_required_fields(sample_python_repo):
    output = await _parse(sample_python_repo)

    for edge in output.edges:
        assert hasattr(edge, "edge_type"), "Edge missing 'edge_type'"
        assert hasattr(edge, "source_node_id"), "Edge missing 'source_node_id'"
        assert hasattr(edge, "target_node_id"), "Edge missing 'target_node_id'"


# ---------------------------------------------------------------------------
# Node type detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extracts_file_nodes(sample_python_repo):
    output = await _parse(sample_python_repo)
    file_nodes = [n for n in output.nodes if n.node_type == "FILE"]
    assert len(file_nodes) >= 2, "Expected at least one FILE node per .py file"


@pytest.mark.asyncio
async def test_extracts_module_nodes(sample_python_repo):
    output = await _parse(sample_python_repo)
    module_nodes = [n for n in output.nodes if n.node_type == "MODULE"]
    assert len(module_nodes) >= 1, "Expected at least one MODULE node"


@pytest.mark.asyncio
async def test_extracts_class_nodes(sample_python_repo):
    output = await _parse(sample_python_repo)
    class_nodes = [n for n in output.nodes if n.node_type == "CLASS"]
    assert len(class_nodes) > 0, "Expected at least one CLASS node"


@pytest.mark.asyncio
async def test_extracts_user_class_by_name(sample_python_repo):
    output = await _parse(sample_python_repo)
    class_names = {
        n.qualified_name.split(".")[-1]
        for n in output.nodes
        if n.node_type == "CLASS"
    }
    assert "User" in class_names, f"Expected 'User' class; found classes: {class_names}"


@pytest.mark.asyncio
async def test_extracts_bigclass_by_name(sample_python_repo):
    output = await _parse(sample_python_repo)
    class_names = {
        n.qualified_name.split(".")[-1]
        for n in output.nodes
        if n.node_type == "CLASS"
    }
    assert "BigClass" in class_names, f"Expected 'BigClass'; found: {class_names}"


@pytest.mark.asyncio
async def test_extracts_method_nodes(sample_python_repo):
    output = await _parse(sample_python_repo)
    method_nodes = [n for n in output.nodes if n.node_type == "METHOD"]
    assert len(method_nodes) > 0, "Expected at least one METHOD node from User class"


@pytest.mark.asyncio
async def test_extracts_function_nodes(sample_python_repo):
    output = await _parse(sample_python_repo)
    func_nodes = [n for n in output.nodes if n.node_type == "FUNCTION"]
    assert len(func_nodes) > 0, "Expected at least one FUNCTION node (process_user, validate_email)"


@pytest.mark.asyncio
async def test_extracts_import_nodes(sample_python_repo):
    output = await _parse(sample_python_repo)
    import_nodes = [n for n in output.nodes if n.node_type == "IMPORT"]
    assert len(import_nodes) > 0, "Expected at least one IMPORT node (from models import User)"


# ---------------------------------------------------------------------------
# Edge type detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contains_edges_exist(sample_python_repo):
    output = await _parse(sample_python_repo)
    contains_edges = [e for e in output.edges if e.edge_type == "CONTAINS"]
    assert len(contains_edges) > 0, "Expected CONTAINS edges (module->class, class->method)"


@pytest.mark.asyncio
async def test_defined_in_edges_exist(sample_python_repo):
    output = await _parse(sample_python_repo)
    defined_in_edges = [e for e in output.edges if e.edge_type == "DEFINED_IN"]
    assert len(defined_in_edges) > 0, "Expected DEFINED_IN edges"


@pytest.mark.asyncio
async def test_imports_edges_exist(sample_python_repo):
    output = await _parse(sample_python_repo)
    import_edges = [e for e in output.edges if e.edge_type == "IMPORTS"]
    assert len(import_edges) > 0, "Expected IMPORTS edges (module->import node)"


# ---------------------------------------------------------------------------
# Line number extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_class_nodes_have_line_numbers(sample_python_repo):
    output = await _parse(sample_python_repo)
    class_nodes = [n for n in output.nodes if n.node_type == "CLASS"]
    for node in class_nodes:
        assert node.line_start is not None, f"Class {node.qualified_name!r} missing line_start"


@pytest.mark.asyncio
async def test_method_nodes_have_line_numbers(sample_python_repo):
    output = await _parse(sample_python_repo)
    method_nodes = [n for n in output.nodes if n.node_type == "METHOD"]
    for node in method_nodes:
        assert node.line_start is not None, f"Method {node.qualified_name!r} missing line_start"


# ---------------------------------------------------------------------------
# Properties content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_class_node_properties_has_name(sample_python_repo):
    output = await _parse(sample_python_repo)
    user_class = next(
        (n for n in output.nodes if n.node_type == "CLASS" and "User" in n.qualified_name),
        None,
    )
    assert user_class is not None
    assert "name" in user_class.properties
    assert user_class.properties["name"] == "User"


@pytest.mark.asyncio
async def test_method_node_properties_has_signature(sample_python_repo):
    output = await _parse(sample_python_repo)
    method_nodes = [n for n in output.nodes if n.node_type == "METHOD"]
    assert len(method_nodes) > 0
    for node in method_nodes:
        assert "signature" in node.properties, f"Method {node.qualified_name!r} missing 'signature'"


# ---------------------------------------------------------------------------
# Syntax error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handles_syntax_error_gracefully(tmp_path):
    """Broken Python syntax should produce a parse_error entry, not raise."""
    (tmp_path / "broken.py").write_text("def foo(: <<<broken syntax")
    adapter = _make_adapter()
    output = await adapter.parse_files([tmp_path / "broken.py"], tmp_path)

    # Should not raise — should record an error instead
    assert isinstance(output.nodes, list)
    assert isinstance(output.parse_errors, list)
    assert len(output.parse_errors) > 0, "Expected at least one parse error for broken syntax"


@pytest.mark.asyncio
async def test_syntax_error_records_file_path(tmp_path):
    broken = tmp_path / "broken.py"
    broken.write_text("class Foo(: bad")
    adapter = _make_adapter()
    output = await adapter.parse_files([broken], tmp_path)

    assert any("broken.py" in str(e.get("file_path", "")) for e in output.parse_errors)


@pytest.mark.asyncio
async def test_valid_files_parsed_despite_one_broken(tmp_path):
    """A broken file should not prevent other files from being parsed."""
    (tmp_path / "broken.py").write_text("def foo(: bad")
    (tmp_path / "good.py").write_text("class Good:\n    pass\n")
    adapter = _make_adapter()
    output = await adapter.parse_files(
        [tmp_path / "broken.py", tmp_path / "good.py"], tmp_path
    )

    class_nodes = [n for n in output.nodes if n.node_type == "CLASS"]
    assert len(class_nodes) > 0, "Expected Good class from the valid file"


# ---------------------------------------------------------------------------
# Empty directory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_file_list_returns_empty_output(tmp_path):
    adapter = _make_adapter()
    output = await adapter.parse_files([], tmp_path)

    assert output.nodes == []
    assert output.edges == []
    assert output.parse_errors == []
