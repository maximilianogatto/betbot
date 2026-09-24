"""`python -m interfaces.mcp`: servidor MCP de BetBot por stdio."""

from __future__ import annotations

import logging
import sys


def main() -> None:
    # stdout es el canal del protocolo: los logs van a stderr. El SDK además desvía
    # el fd 1 a stderr mientras corre, así que un print suelto no rompe la sesión.
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    from interfaces.mcp.server import server

    server.run("stdio")


if __name__ == "__main__":
    main()
