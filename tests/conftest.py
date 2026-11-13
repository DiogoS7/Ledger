"""Tests run against a small generated Ledger database.

Set LEDGER_HOME to a Ledger checkout (CI clones it next to this repo).
"""

import os
from pathlib import Path

import pytest

if "LEDGER_HOME" not in os.environ:
    pytest.exit("Set LEDGER_HOME to a checkout of https://github.com/DiogoS7/Ledger", returncode=2)

_DB = Path(os.environ.get("PYTEST_LEDGER_DB", Path(__file__).parent / ".cache" / "ledger-small.db"))
os.environ["LEDGER_DB"] = str(_DB)

from ledger_mcp import locate  # noqa: E402

locate.import_ledger()
if not _DB.exists():
    from ledger.generate import build

    build(_DB, seed=11, customers=250)


@pytest.fixture(scope="session")
def server():
    from ledger_mcp.server import mcp

    return mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"
