"""Command line: python -m ledger [generate|report|all]"""

import argparse

from . import DB_PATH, SITE_DIR
from .generate import build
from .report import build_site


def main() -> None:
    p = argparse.ArgumentParser(prog="ledger", description="Card transaction and fraud analytics")
    p.add_argument("command", nargs="?", default="all", choices=["generate", "report", "all", "mcp"],
                   help="generate the database, build the report site, both (default), "
                        "or run the MCP server for AI assistants")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--customers", type=int, default=1500)
    a = p.parse_args()
    if a.command == "mcp":
        from .mcp import main as serve
        serve()
        return
    if a.command in ("generate", "all"):
        print(f"Generating {DB_PATH} ...")
        build(DB_PATH, a.seed, a.customers)
    if a.command in ("report", "all"):
        print(f"Building report in {SITE_DIR} ...")
        build_site()
    print("Done.")


if __name__ == "__main__":
    main()
