"""
PHPAdapter — parses PHP source files via nikic/php-parser subprocess.

Runs a PHP CLI script that uses nikic/php-parser to parse files and output
UCG-compatible JSON. Requires PHP 8.x and nikic/php-parser in vendor/.

Subprocess command:
  php vendor/bin/php-parse-ucg.php <file1> <file2> ...
"""
# TODO: implement

from pathlib import Path

from app.adapters.base import BaseAdapter, UCGOutput


class PHPAdapter(BaseAdapter):
    """
    Parses PHP source files using a nikic/php-parser subprocess.
    Requires PHP runtime and nikic/php-parser to be available in the system.
    """

    language = "php"

    async def parse_files(self, files: list[Path], repo_root: Path) -> UCGOutput:
        """
        Invoke nikic/php-parser CLI subprocess for each batch of PHP files.
        Parse the JSON output into UCG nodes and edges.
        """
        # TODO: implement subprocess execution, JSON parsing, UCG construction
        return UCGOutput()
