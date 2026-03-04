"""
JSTSAdapter — parses JavaScript and TypeScript source files via
@typescript-eslint/parser subprocess.

Runs a Node.js script that uses @typescript-eslint/parser to produce
an ESTree-compatible AST, then converts it to UCG format.

Subprocess command:
  node scripts/parse-js-ts.js <file1> <file2> ...

Handles both JavaScript (.js, .jsx, .mjs) and TypeScript (.ts, .tsx) files.
"""
# TODO: implement

from pathlib import Path

from app.adapters.base import BaseAdapter, UCGOutput


class JSTSAdapter(BaseAdapter):
    """
    Parses JavaScript and TypeScript source files using @typescript-eslint/parser.
    Requires Node.js runtime with the parser package installed.
    """

    language = "javascript"  # also handles typescript

    def __init__(self, language: str = "javascript") -> None:
        self.language = language

    async def parse_files(self, files: list[Path], repo_root: Path) -> UCGOutput:
        """
        Invoke the Node.js @typescript-eslint/parser subprocess.
        Parse the JSON AST output into UCG nodes and edges.
        """
        # TODO: implement subprocess execution, AST -> UCG conversion
        return UCGOutput()
