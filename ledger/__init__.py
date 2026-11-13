"""Ledger: card transaction and fraud analytics in Python and SQL."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "ledger.db"
SITE_DIR = ROOT / "site"

__version__ = "1.1.0"
