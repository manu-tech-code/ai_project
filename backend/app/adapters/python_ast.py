"""
PythonASTAdapter — parses Python source files using the stdlib ast module.

Walks the AST to extract:
  - MODULE nodes (from module-level)
  - CLASS nodes (from ClassDef)
  - FUNCTION nodes (from FunctionDef/AsyncFunctionDef at module level)
  - METHOD nodes (from FunctionDef/AsyncFunctionDef inside ClassDef)
  - IMPORT nodes (from Import/ImportFrom)
  - CALL_SITE nodes (from Call expressions)
  - FIELD nodes (from class-level assignments)

Edges:
  - CONTAINS: module -> class/function, class -> method/field
  - IMPORTS: file -> import
  - CALLS: function/method -> call_site
  - DEFINED_IN: any -> file
"""

import ast
from pathlib import Path

from app.adapters.base import BaseAdapter, UCGEdgeRaw, UCGNodeRaw, UCGOutput


class PythonASTAdapter(BaseAdapter):
    """
    Parses Python source files using the stdlib `ast` module.
    No subprocess or external service required.
    """

    language = "python"

    async def parse_files(self, files: list[Path], repo_root: Path) -> UCGOutput:
        """Parse all Python files and return UCG nodes and edges."""
        output = UCGOutput()

        for file_path in files:
            # Skip hidden directories and __pycache__
            parts = file_path.parts
            if any(p.startswith(".") or p == "__pycache__" for p in parts):
                continue
            try:
                source = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source, filename=str(file_path))
                relative_path = str(file_path.relative_to(repo_root))
                self._process_file(tree, file_path, relative_path, source, output)
            except SyntaxError as exc:
                output.parse_errors.append({
                    "file_path": str(file_path),
                    "error_message": str(exc),
                    "line_number": exc.lineno,
                })
            except Exception as exc:
                output.parse_errors.append({
                    "file_path": str(file_path),
                    "error_message": f"Unexpected error parsing {file_path}: {exc}",
                    "line_number": None,
                })

        return output

    def _process_file(
        self,
        tree: ast.AST,
        file_path: Path,
        relative_path: str,
        source: str,
        output: UCGOutput,
    ) -> None:
        """Walk the AST and extract UCG nodes and edges for a single file."""
        source_lines = source.splitlines()
        total_lines = len(source_lines)

        # Create FILE node
        file_node = UCGNodeRaw(
            node_type="FILE",
            qualified_name=relative_path,
            language="python",
            file_path=relative_path,
            line_start=1,
            line_end=total_lines or 1,
            properties={
                "path": relative_path,
                "language": "python",
                "size_bytes": len(source.encode("utf-8")),
            },
        )
        output.nodes.append(file_node)

        # Create MODULE node (same as file for Python)
        module_name = relative_path.replace("/", ".").removesuffix(".py")
        module_node = UCGNodeRaw(
            node_type="MODULE",
            qualified_name=module_name,
            language="python",
            file_path=relative_path,
            line_start=1,
            line_end=total_lines or 1,
            properties={"qualified_name": module_name, "language": "python"},
        )
        output.nodes.append(module_node)

        # MODULE is DEFINED_IN file
        output.edges.append(UCGEdgeRaw(
            edge_type="DEFINED_IN",
            source_node_id=module_node.id,
            target_node_id=file_node.id,
        ))

        # Track top-level class names to avoid treating nested functions as top-level
        top_level_class_nodes: dict[str, UCGNodeRaw] = {}  # class name -> node

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                class_node = self._make_class_node(
                    node, relative_path, module_name, source_lines
                )
                output.nodes.append(class_node)
                top_level_class_nodes[node.name] = class_node

                # MODULE CONTAINS class
                output.edges.append(UCGEdgeRaw(
                    edge_type="CONTAINS",
                    source_node_id=module_node.id,
                    target_node_id=class_node.id,
                ))
                # class DEFINED_IN file
                output.edges.append(UCGEdgeRaw(
                    edge_type="DEFINED_IN",
                    source_node_id=class_node.id,
                    target_node_id=file_node.id,
                ))

                # Walk class body for methods and fields
                self._process_class_body(
                    node, class_node, file_node, relative_path,
                    module_name, source_lines, output
                )

                # Handle base classes (EXTENDS edges)
                for base in node.bases:
                    base_name = _unparse_safe(base)
                    if base_name and base_name not in ("object",):
                        # We'll record this as a property; we can't resolve UUIDs
                        # for external base classes without a full symbol table.
                        pass

            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                fn_node = self._make_function_node(
                    node, relative_path, module_name, source_lines, is_method=False
                )
                output.nodes.append(fn_node)
                output.edges.append(UCGEdgeRaw(
                    edge_type="CONTAINS",
                    source_node_id=module_node.id,
                    target_node_id=fn_node.id,
                ))
                output.edges.append(UCGEdgeRaw(
                    edge_type="DEFINED_IN",
                    source_node_id=fn_node.id,
                    target_node_id=file_node.id,
                ))
                # Collect call sites inside this function
                self._collect_call_sites(node, fn_node, file_node, relative_path, output)

            elif isinstance(node, ast.Import | ast.ImportFrom):
                import_node = self._make_import_node(node, relative_path)
                output.nodes.append(import_node)
                output.edges.append(UCGEdgeRaw(
                    edge_type="IMPORTS",
                    source_node_id=module_node.id,
                    target_node_id=import_node.id,
                ))

    def _process_class_body(
        self,
        class_def: ast.ClassDef,
        class_node: UCGNodeRaw,
        file_node: UCGNodeRaw,
        relative_path: str,
        module_name: str,
        source_lines: list[str],
        output: UCGOutput,
    ) -> None:
        """Extract methods and fields from a class body."""
        for item in ast.iter_child_nodes(class_def):
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                method_node = self._make_function_node(
                    item, relative_path, module_name, source_lines,
                    is_method=True, class_name=class_def.name
                )
                output.nodes.append(method_node)
                output.edges.append(UCGEdgeRaw(
                    edge_type="CONTAINS",
                    source_node_id=class_node.id,
                    target_node_id=method_node.id,
                ))
                output.edges.append(UCGEdgeRaw(
                    edge_type="DEFINED_IN",
                    source_node_id=method_node.id,
                    target_node_id=file_node.id,
                ))
                # Parameters
                for i, arg in enumerate(item.args.args):
                    param_node = UCGNodeRaw(
                        node_type="PARAMETER",
                        qualified_name=f"{module_name}.{class_def.name}.{item.name}.{arg.arg}",
                        language="python",
                        file_path=relative_path,
                        line_start=item.lineno,
                        properties={
                            "name": arg.arg,
                            "position": i,
                            "has_default": False,
                            "type_annotation": _annotation_str(arg.annotation),
                        },
                    )
                    output.nodes.append(param_node)
                    output.edges.append(UCGEdgeRaw(
                        edge_type="HAS_PARAMETER",
                        source_node_id=method_node.id,
                        target_node_id=param_node.id,
                    ))
                # Call sites inside method
                self._collect_call_sites(item, method_node, file_node, relative_path, output)

            elif isinstance(item, ast.Assign | ast.AnnAssign):
                # Class-level field assignments
                fields = _extract_field_names(item)
                for field_name, annotation in fields:
                    field_node = UCGNodeRaw(
                        node_type="FIELD",
                        qualified_name=f"{module_name}.{class_def.name}.{field_name}",
                        language="python",
                        file_path=relative_path,
                        line_start=item.lineno,
                        line_end=getattr(item, "end_lineno", item.lineno),
                        properties={
                            "name": field_name,
                            "type_annotation": annotation,
                            "visibility": "private" if field_name.startswith("_") else "public",
                            "is_static": False,
                        },
                    )
                    output.nodes.append(field_node)
                    output.edges.append(UCGEdgeRaw(
                        edge_type="HAS_FIELD",
                        source_node_id=class_node.id,
                        target_node_id=field_node.id,
                    ))

    def _collect_call_sites(
        self,
        func_node: ast.AST,
        parent_node: UCGNodeRaw,
        file_node: UCGNodeRaw,
        relative_path: str,
        output: UCGOutput,
    ) -> None:
        """Find all Call nodes within a function/method body and create CALL_SITE nodes."""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                callee_name = _get_callee_name(node.func)
                if not callee_name:
                    continue
                call_node = UCGNodeRaw(
                    node_type="CALL_SITE",
                    qualified_name=f"{parent_node.qualified_name}:call:{callee_name}@{getattr(node, 'lineno', 0)}",
                    language="python",
                    file_path=relative_path,
                    line_start=getattr(node, "lineno", None),
                    properties={
                        "callee_name": callee_name,
                        "argument_count": len(node.args) + len(node.keywords),
                        "line_number": getattr(node, "lineno", None),
                    },
                )
                output.nodes.append(call_node)
                output.edges.append(UCGEdgeRaw(
                    edge_type="CALLS",
                    source_node_id=parent_node.id,
                    target_node_id=call_node.id,
                ))

    def _make_class_node(
        self,
        node: ast.ClassDef,
        relative_path: str,
        module_name: str,
        source_lines: list[str],
    ) -> UCGNodeRaw:
        bases = [_unparse_safe(b) for b in node.bases]
        return UCGNodeRaw(
            node_type="CLASS",
            qualified_name=f"{module_name}.{node.name}",
            language="python",
            file_path=relative_path,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            properties={
                "qualified_name": f"{module_name}.{node.name}",
                "is_abstract": _is_abstract_class(node),
                "is_interface": False,
                "bases": bases,
                "name": node.name,
            },
        )

    def _make_function_node(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        relative_path: str,
        module_name: str,
        source_lines: list[str],
        is_method: bool = False,
        class_name: str = "",
    ) -> UCGNodeRaw:
        node_type = "METHOD" if is_method else "FUNCTION"
        if is_method and class_name:
            qname = f"{module_name}.{class_name}.{node.name}"
        else:
            qname = f"{module_name}.{node.name}"

        visibility = "private" if node.name.startswith("_") and not node.name.startswith("__") else "public"
        return_annotation = _annotation_str(node.returns)

        return UCGNodeRaw(
            node_type=node_type,
            qualified_name=qname,
            language="python",
            file_path=relative_path,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            properties={
                "qualified_name": qname,
                "name": node.name,
                "signature": _build_signature(node),
                "return_type": return_annotation,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "visibility": visibility,
                "is_static": _is_static_method(node),
                "class": class_name if is_method else None,
            },
        )

    def _make_import_node(
        self,
        node: ast.Import | ast.ImportFrom,
        relative_path: str,
    ) -> UCGNodeRaw:
        if isinstance(node, ast.Import):
            source_module = ", ".join(alias.name for alias in node.names)
            imported_names = [alias.asname or alias.name for alias in node.names]
            is_wildcard = False
        else:  # ImportFrom
            source_module = node.module or ""
            imported_names = []
            is_wildcard = False
            for alias in node.names:
                if alias.name == "*":
                    is_wildcard = True
                else:
                    imported_names.append(alias.asname or alias.name)

        qname = f"import:{relative_path}:{source_module}:{node.lineno}"
        return UCGNodeRaw(
            node_type="IMPORT",
            qualified_name=qname,
            language="python",
            file_path=relative_path,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            properties={
                "source_module": source_module,
                "imported_names": imported_names,
                "is_wildcard": is_wildcard,
            },
        )


# ── Helper utilities ──────────────────────────────────────────────────────────

def _unparse_safe(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _annotation_str(annotation: ast.expr | None) -> str:
    if annotation is None:
        return ""
    return _unparse_safe(annotation)


def _build_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        args = ast.unparse(node.args)
        ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return f"{node.name}({args}){ret}"
    except Exception:
        return node.name


def _is_abstract_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = _unparse_safe(base)
        if "ABC" in name or "Abstract" in name:
            return True
    for item in ast.walk(node):
        if isinstance(item, ast.FunctionDef):
            for decorator in item.decorator_list:
                if _unparse_safe(decorator) in ("abstractmethod", "abc.abstractmethod"):
                    return True
    return False


def _is_static_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        name = _unparse_safe(dec)
        if name in ("staticmethod", "classmethod"):
            return True
    return False


def _get_callee_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return _unparse_safe(func)[:80]


def _extract_field_names(node: ast.Assign | ast.AnnAssign) -> list[tuple[str, str]]:
    """Return list of (name, type_annotation) from assignment nodes."""
    results: list[tuple[str, str]] = []
    if isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name):
            results.append((node.target.id, _annotation_str(node.annotation)))
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                results.append((target.id, ""))
            elif isinstance(target, ast.Tuple):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        results.append((elt.id, ""))
    return results
