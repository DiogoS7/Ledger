"""Ledger MCP: lets Claude or another AI assistant work with Ledger's data.

Run it with `python -m ledger mcp` (or the `ledger-mcp` command after
`pip install -e ".[mcp]"`). It talks MCP over stdio, opens the database
read-only, and uses the same checks, scoring and points as the report.
"""


def main() -> None:
    try:
        from .server import run
    except ImportError as e:  # the mcp package is an optional extra
        raise SystemExit(f'{e}. Install the MCP extra first: pip install -e ".[mcp]"') from None
    run()
