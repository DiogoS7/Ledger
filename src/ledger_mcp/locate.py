"""Find the Ledger project on disk, import it, and (optionally) set it up.

ledger-mcp does not copy any of Ledger's code. It points at a checkout of
https://github.com/DiogoS7/Ledger and imports the `ledger` package from it, so the
SQL checks, the scoring and the points system are exactly the ones Ledger ships.

Where it looks:
  LEDGER_HOME   the Ledger checkout (default: ~/.ledger-mcp/Ledger)
  LEDGER_DB     the SQLite database  (default: $LEDGER_HOME/data/ledger.db)
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

LEDGER_REPO = "https://github.com/DiogoS7/Ledger.git"
DEFAULT_HOME = Path.home() / ".ledger-mcp" / "Ledger"


def ledger_home() -> Path:
    return Path(os.environ.get("LEDGER_HOME", DEFAULT_HOME)).expanduser().resolve()


def db_path() -> Path:
    env = os.environ.get("LEDGER_DB")
    return Path(env).expanduser().resolve() if env else ledger_home() / "data" / "ledger.db"


def import_ledger(home: Path | None = None) -> ModuleType:
    """Import the `ledger` package from the Ledger checkout."""
    home = (home or ledger_home()).resolve()
    if not (home / "ledger" / "__init__.py").exists():
        raise RuntimeError(
            f"No Ledger checkout at {home}. Run `ledger-mcp setup`, "
            f"or set LEDGER_HOME to a clone of {LEDGER_REPO}."
        )
    if str(home) not in sys.path:
        sys.path.insert(0, str(home))
    pkg = importlib.import_module("ledger")
    if Path(pkg.__file__).resolve().parent.parent != home:
        raise RuntimeError(f"Imported `ledger` from {pkg.__file__}, expected it under {home}.")
    return pkg


def setup(home: Path | None = None, customers: int = 1500, seed: int = 7) -> Path:
    """Clone Ledger (if needed) and generate its database. Returns the database path."""
    home = (home or ledger_home()).resolve()
    if not home.exists():
        home.parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloning {LEDGER_REPO} into {home} ...", file=sys.stderr)
        subprocess.run(["git", "clone", "--depth", "1", LEDGER_REPO, str(home)], check=True)
    import_ledger(home)
    from ledger.generate import build

    target = db_path() if os.environ.get("LEDGER_DB") else home / "data" / "ledger.db"
    print(f"Generating {target} ({customers} customers, seed {seed}); about a minute ...", file=sys.stderr)
    build(target, seed, customers)
    return target
