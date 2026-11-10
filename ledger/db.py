"""Run the project's .sql files against the SQLite database and get DataFrames back."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from . import DB_PATH, SQL_DIR


@contextmanager
def connect(db_path: Path = DB_PATH):
    if not Path(db_path).exists():
        raise FileNotFoundError(f"{db_path} not found. Run `python -m ledger generate` first.")
    con = sqlite3.connect(db_path)
    try:
        yield con
    finally:
        con.close()


def sql_text(name: str) -> str:
    """Read sql/<name>.sql, e.g. 'analysis/01_monthly_volume' or 'rules/r1_velocity'."""
    return (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")


def query(con: sqlite3.Connection, name: str, **params) -> pd.DataFrame:
    """Run a named SQL file. Named parameters (:window_s, ...) come from **params."""
    return pd.read_sql_query(sql_text(name), con, params=params or None)
