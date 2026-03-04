# app.adapters — language-specific AST parsers that produce UCG nodes and edges
from app.adapters.base import BaseAdapter, UCGOutput
from app.adapters.java import JavaAdapter
from app.adapters.js_ts import JSTSAdapter
from app.adapters.php import PHPAdapter
from app.adapters.python_ast import PythonASTAdapter

__all__ = ["BaseAdapter", "JavaAdapter", "JSTSAdapter", "PHPAdapter", "PythonASTAdapter", "UCGOutput"]
