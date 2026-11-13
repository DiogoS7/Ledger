"""ledger-mcp: an MCP server over Ledger's card payments and fraud checks."""

from __future__ import annotations

import argparse
from pathlib import Path

__version__ = "0.1.0"


def main() -> None:
    p = argparse.ArgumentParser(prog="ledger-mcp", description=__doc__)
    sub = p.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the MCP server over stdio (the default)")
    s = sub.add_parser("setup", help="clone Ledger if needed and generate its database")
    s.add_argument("--home", type=Path, help="where the Ledger checkout lives (default: $LEDGER_HOME "
                                             "or ~/.ledger-mcp/Ledger)")
    s.add_argument("--customers", type=int, default=1500)
    s.add_argument("--seed", type=int, default=7)
    a = p.parse_args()

    if a.command == "setup":
        from .locate import setup

        print(f"Ready: {setup(a.home, a.customers, a.seed)}")
        return

    from .server import run

    run()
