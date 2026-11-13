"""The Ledger MCP server.

Gives an AI assistant read-only access to Ledger's card payments and fraud
checks: ask about spending, explain why a payment was stopped, find fraud that
slipped through, and try out stricter or looser settings before changing them.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import locate

ledger = locate.import_ledger()
from ledger import SQL_DIR  # noqa: E402  (needs the checkout on sys.path first)
from ledger import rules as L  # noqa: E402
from ledger.db import query  # noqa: E402

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
MAX_ROWS = 500
QUERY_SECONDS = 20

mcp = MCPServer(
    name="ledger",
    title="Ledger: card payments and fraud checks",
    website_url="https://github.com/DiogoS7/Ledger",
    instructions=(
        "Ledger is a year of synthetic card payments at Meridian Bank, a made-up Portuguese bank, "
        "with three kinds of planted fraud and six SQL checks that score every payment. "
        "A payment's risk score is the sum of the points of the checks it trips: under "
        f"{L.REVIEW_THRESHOLD} it goes through, {L.REVIEW_THRESHOLD}-{L.BLOCK_THRESHOLD - 1} an analyst "
        f"reviews it, {L.BLOCK_THRESHOLD}+ it is blocked. Fraud chargebacks are the ground truth. "
        "Start with ledger_overview, use list_checks/check_scorecard for the checks, "
        "explain_payment for a single payment, and query_sql for anything else (read-only SQLite). "
        "All amounts are in euros. Explain findings in plain words."
    ),
)


# ------------------------------------------------------------------ plumbing

def _connect() -> sqlite3.Connection:
    path = locate.db_path()
    if not path.exists():
        raise ToolError(f"Ledger database not found at {path}. Run `ledger-mcp setup` first.")
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)


def _records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    return json.loads(df.to_json(orient="records", force_ascii=False))


def _decision(score: float) -> str:
    if score >= L.BLOCK_THRESHOLD:
        return "BLOCK"
    if score >= L.REVIEW_THRESHOLD:
        return "REVIEW"
    return "ALLOW"


def _rule(code: str) -> L.Rule:
    for r in L.RULES:
        if r.code == code.upper():
            return r
    raise ToolError(f"Unknown check {code!r}. Valid codes: {', '.join(r.code for r in L.RULES)}.")


def _rounded(d: dict) -> dict:
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}


class _Evaluation:
    """Runs all six checks once per database file and keeps the result."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: tuple | None = None
        self.table = self.scored = self.truth = None

    def get(self) -> "_Evaluation":
        path = locate.db_path()
        key = (str(path), path.stat().st_mtime_ns) if path.exists() else None
        with self._lock:
            if key is None or key != self._key:
                with _connect() as con:
                    self.table, self.scored, self.truth = L.evaluate(con)
                self._key = key
        return self


_eval = _Evaluation()


# ------------------------------------------------------------------ overview & data

@mcp.tool(annotations=READ_ONLY)
def ledger_overview() -> dict:
    """Headline numbers: customers, cards, payments, money spent, fraud losses, the date range
    and the points needed to review or block a payment."""
    with _connect() as con:
        kpis = _records(query(con, "analysis/10_kpis"))[0]
    kpis["fraud_share_of_volume"] = round(kpis["fraud_eur"] / kpis["volume_eur"], 5)
    kpis["review_threshold"] = L.REVIEW_THRESHOLD
    kpis["block_threshold"] = L.BLOCK_THRESHOLD
    return kpis


@mcp.tool(annotations=READ_ONLY)
def describe_schema() -> dict:
    """Tables, columns and row counts of the Ledger database, plus the commented schema SQL.
    Read this before writing a query_sql query."""
    tables = {}
    with _connect() as con:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        for t in names:
            cols = [{"name": c[1], "type": c[2], "not_null": bool(c[3]), "primary_key": bool(c[5])}
                    for c in con.execute(f'PRAGMA table_info("{t}")')]
            rows = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            tables[t] = {"rows": rows, "columns": cols}
    return {"tables": tables, "schema_sql": (SQL_DIR / "schema.sql").read_text(encoding="utf-8")}


def _analyses() -> dict[str, Path]:
    return {p.stem: p for p in sorted((SQL_DIR / "analysis").glob("*.sql"))}


def _header(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("--"):
            break
        lines.append(line.lstrip("- ").strip())
    return " ".join(lines)


@mcp.tool(annotations=READ_ONLY)
def list_analyses() -> list[dict]:
    """The ready-made analysis queries that power Ledger's report (monthly volume, category mix,
    contactless trend, fraud hotspots, time to report, ...), with what each one answers."""
    return [{"name": name, "description": _header(p)} for name, p in _analyses().items()]


@mcp.tool(annotations=READ_ONLY)
def run_analysis(name: str, max_rows: int = 100) -> dict:
    """Run one of the ready-made analysis queries by name (see list_analyses), e.g.
    '07_fraud_hotspots'. A unique prefix such as '07' also works."""
    found = _analyses()
    matches = [n for n in found if n == name] or [n for n in found if n.startswith(name)]
    if len(matches) != 1:
        raise ToolError(f"No single analysis matches {name!r}. Choose from: {', '.join(found)}.")
    n = matches[0]
    with _connect() as con:
        df = query(con, f"analysis/{n}")
    max_rows = max(1, min(max_rows, MAX_ROWS))
    return {"name": n, "description": _header(found[n]), "total_rows": len(df),
            "rows": _records(df, max_rows), "sql": found[n].read_text(encoding="utf-8")}


_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                    getattr(sqlite3, "SQLITE_RECURSIVE", 33)}


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


@mcp.tool(annotations=READ_ONLY)
def query_sql(sql: str, max_rows: int = 100) -> dict:
    """Run one read-only SQLite SELECT (or WITH ... SELECT) against the Ledger database.
    Tables: customers, cards, merchants, transactions, chargebacks (see describe_schema).
    Timestamps are ISO text in Lisbon time; use strftime/date/unixepoch. Writes, PRAGMAs and
    ATTACH are refused; long queries are stopped after 20 seconds."""
    text = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", text):
        raise ToolError("Only a single SELECT (or WITH ... SELECT) statement is allowed.")
    if not sqlite3.complete_statement(text + ";") or ";" in _strip_literals(text):
        raise ToolError("Send exactly one complete statement.")
    max_rows = max(1, min(max_rows, MAX_ROWS))
    con = _connect()
    deadline = time.monotonic() + QUERY_SECONDS
    try:
        con.set_authorizer(_authorizer)
        con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        cur = con.execute(text)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    except sqlite3.DatabaseError as e:
        msg = "query took longer than 20 seconds" if "interrupted" in str(e) else str(e)
        raise ToolError(f"SQLite error: {msg}") from None
    finally:
        con.close()
    truncated = len(rows) > max_rows
    return {"columns": cols, "rows": [list(r) for r in rows[:max_rows]],
            "row_count": min(len(rows), max_rows), "truncated": truncated}


def _strip_literals(sql: str) -> str:
    """Remove string literals and comments, so a ';' inside them is not mistaken for a second statement."""
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    sql = re.sub(r'"(?:[^"]|"")*"', '""', sql)
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"/\*.*?\*/", "", sql, flags=re.S)


# ------------------------------------------------------------------ the checks

@mcp.tool(annotations=READ_ONLY)
def list_checks() -> list[dict]:
    """The six fraud checks: what each looks for in plain words, the attack it targets, how many
    points it adds, its settings, which setting can be tuned, and its SQL."""
    return [{
        "code": r.code, "name": r.name, "plain_words": r.plain, "aimed_at": r.catches,
        "points": r.weight, "settings": r.params,
        "tunable": {"setting": r.tune[0], "suggested_values": r.tune[1]} if r.tune else None,
        "sql": (SQL_DIR / "rules" / f"{r.file}.sql").read_text(encoding="utf-8"),
    } for r in L.RULES]


@mcp.tool(annotations=READ_ONLY)
def check_scorecard() -> dict:
    """How well each check works on its own, and how well the points system works together:
    alerts raised, real fraud caught, false alarms, precision (share of alerts that are fraud),
    recall (share of fraud payments caught) and value_recall (share of stolen euros caught)."""
    e = _eval.get()
    table = e.table.copy()
    table["weight"] = table["weight"].astype("Int64")
    fraud = e.truth[e.truth.is_fraud == 1]
    return {"fraud_payments": len(fraud), "fraud_eur": round(float(fraud.amount_eur.sum()), 2),
            "checks": [_rounded(r) for r in _records(table)]}


@mcp.tool(annotations=READ_ONLY)
def try_check_setting(code: str, setting: str, value: float) -> dict:
    """Re-run one check with one setting changed and compare it with the current setting,
    e.g. code='R1', setting='min_txns', value=3. Nothing is saved; this is a what-if."""
    r = _rule(code)
    if setting not in r.params:
        raise ToolError(f"{r.code} has no setting {setting!r}. Its settings are: {r.params}.")
    if isinstance(r.params[setting], int) and float(value).is_integer():
        value = int(value)
    e = _eval.get()
    with _connect() as con:
        current = L.score(L.run_rule(con, r), e.truth)
        changed = L.score(L.run_rule(con, r, **{setting: value}), e.truth)
    return {"check": f"{r.code} {r.name}", "setting": setting,
            "current": {"value": r.params[setting], **_rounded(current)},
            "what_if": {"value": value, **_rounded(changed)}}


def _outcome(scored: pd.DataFrame, review: int, block: int) -> dict:
    out = {}
    for label, lo, hi in (("blocked", block, None), ("reviewed", review, block)):
        sel = scored[scored.risk_score >= lo] if hi is None else scored[(scored.risk_score >= lo) & (scored.risk_score < hi)]
        out[label] = {"payments": len(sel), "fraud": int(sel.is_fraud.sum()),
                      "false_alarms": int((sel.is_fraud == 0).sum()),
                      "fraud_eur": round(float(sel.loc[sel.is_fraud == 1, "amount_eur"].sum()), 2)}
    return out


@mcp.tool(annotations=READ_ONLY)
def try_thresholds(review_at: int = L.REVIEW_THRESHOLD, block_at: int = L.BLOCK_THRESHOLD) -> dict:
    """What happens if the bank changes the points needed to review or block a payment.
    Compares the given thresholds with the current ones: payments blocked and sent to review,
    fraud caught, false alarms (genuine customers stopped) and stolen euros caught."""
    if not 0 < review_at <= block_at:
        raise ToolError("Need 0 < review_at <= block_at.")
    e = _eval.get()
    fraud = e.truth[e.truth.is_fraud == 1]
    total_eur = float(fraud.amount_eur.sum())

    def summary(review: int, block: int) -> dict:
        o = _outcome(e.scored, review, block)
        caught_auto = o["blocked"]["fraud_eur"]
        caught_all = caught_auto + o["reviewed"]["fraud_eur"]
        return {"review_at": review, "block_at": block, **o,
                "share_of_stolen_eur_blocked_automatically": round(caught_auto / total_eur, 4),
                "share_of_stolen_eur_caught_with_review": round(caught_all / total_eur, 4)}

    return {"fraud_eur_total": round(total_eur, 2),
            "current": summary(L.REVIEW_THRESHOLD, L.BLOCK_THRESHOLD),
            "what_if": summary(review_at, block_at)}


# ------------------------------------------------------------------ single payments & cards

@mcp.tool(annotations=READ_ONLY)
def explain_payment(txn_id: int) -> dict:
    """Everything about one payment: amount, time, shop, channel, country, the customer and card,
    which checks it tripped and why, its risk score and decision, and whether it really was fraud
    (a fraud chargeback) - so you can say if the checks got it right."""
    with _connect() as con:
        df = pd.read_sql_query("""
            SELECT t.txn_id, t.ts, t.amount_eur, t.channel, t.country, t.status,
                   m.merchant_id, m.name AS merchant, m.category, m.city AS merchant_city,
                   m.country AS merchant_country, m.is_online, m.high_risk,
                   c.card_id, c.card_type, cu.customer_id, cu.age_band, cu.district, cu.segment,
                   cb.reason AS chargeback_reason, cb.reported_on AS chargeback_reported_on
            FROM transactions t
            JOIN merchants m USING (merchant_id)
            JOIN cards c USING (card_id)
            JOIN customers cu USING (customer_id)
            LEFT JOIN chargebacks cb USING (txn_id)
            WHERE t.txn_id = ?""", con, params=(txn_id,))
    if df.empty:
        raise ToolError(f"No payment with txn_id {txn_id}.")
    p = _records(df)[0]
    e = _eval.get()
    hit = e.scored[e.scored.txn_id == txn_id]
    score = int(hit.risk_score.iloc[0]) if len(hit) else 0
    fired = []
    if len(hit):
        codes = sorted(hit.rules.iloc[0].split(" + "))
        for code, ev in zip(codes, _evidence(txn_id, codes, hit.evidence.iloc[0])):
            r = _rule(code)
            fired.append({"code": r.code, "name": r.name, "points": r.weight, "evidence": ev,
                          "why": r.reason})
    decision = _decision(score) if p["status"] == "Approved" else "ALREADY DECLINED"
    is_fraud = p["chargeback_reason"] == "fraud"
    verdict = None
    if p["status"] == "Approved":
        stopped = decision in ("BLOCK", "REVIEW")
        verdict = {(True, True): "caught", (True, False): "missed",
                   (False, True): "false alarm", (False, False): "correctly allowed"}[(is_fraud, stopped)]
    return {"payment": p, "risk_score": score, "decision": decision, "checks_tripped": fired,
            "was_fraud": is_fraud, "verdict": verdict}


def _evidence(txn_id: int, codes: list[str], joined: str) -> list[str]:
    """Split Ledger's joined evidence text back into one line per tripped check.

    evaluate() joins the evidence with " · " in check order (R1..R6). If the pieces do not line up
    (an evidence text that itself contains " · "), re-run just those checks for the exact text.
    """
    parts = joined.split(" · ")
    if len(parts) == len(codes):
        return parts
    out = []
    with _connect() as con:
        for code in codes:
            a = L.run_rule(con, _rule(code))
            out.append(" · ".join(a.loc[a.txn_id == txn_id, "evidence"]))
    return out


@mcp.tool(annotations=READ_ONLY)
def card_activity(card_id: int, around_txn_id: int | None = None, limit: int = 30) -> dict:
    """Payments on one card in time order, with risk scores. Give around_txn_id to see the
    payments just before and after a suspicious one (useful to spot test charges or a trip abroad)."""
    limit = max(1, min(limit, 200))
    with _connect() as con:
        df = pd.read_sql_query("""
            SELECT t.txn_id, t.ts, t.amount_eur, t.channel, t.country, t.status,
                   m.name AS merchant, m.category, cb.reason AS chargeback
            FROM transactions t JOIN merchants m USING (merchant_id)
            LEFT JOIN chargebacks cb USING (txn_id)
            WHERE t.card_id = ? ORDER BY t.ts, t.txn_id""", con, params=(card_id,))
    if df.empty:
        raise ToolError(f"No payments on card {card_id}.")
    e = _eval.get()
    df = df.merge(e.scored[["txn_id", "risk_score", "rules"]], on="txn_id", how="left")
    df["risk_score"] = df["risk_score"].fillna(0).astype(int)
    if around_txn_id is not None:
        idx = df.index[df.txn_id == around_txn_id]
        if not len(idx):
            raise ToolError(f"Payment {around_txn_id} is not on card {card_id}.")
        i = int(idx[0])
        df = df.iloc[max(0, i - limit // 2): i + limit // 2 + 1]
    else:
        df = df.tail(limit)
    return {"card_id": card_id, "payments": _records(df)}


@mcp.tool(annotations=READ_ONLY)
def find_payments(kind: Literal["caught", "missed", "false_alarm", "reviewed"],
                  min_amount_eur: float = 0, limit: int = 10) -> dict:
    """Find example payments by outcome, biggest first:
    caught = fraud the checks stopped (score >= review threshold);
    missed = fraud that went through; false_alarm = genuine payments that were stopped;
    reviewed = payments in the analyst review band."""
    limit = max(1, min(limit, 100))
    e = _eval.get()
    s = e.truth.merge(e.scored[["txn_id", "risk_score", "rules", "evidence"]], on="txn_id", how="left")
    s["risk_score"] = s["risk_score"].fillna(0).astype(int)
    stopped = s.risk_score >= L.REVIEW_THRESHOLD
    mask = {"caught": (s.is_fraud == 1) & stopped,
            "missed": (s.is_fraud == 1) & ~stopped,
            "false_alarm": (s.is_fraud == 0) & stopped,
            "reviewed": stopped & (s.risk_score < L.BLOCK_THRESHOLD)}[kind]
    sel = s[mask & (s.amount_eur >= min_amount_eur)].sort_values("amount_eur", ascending=False)
    sel = sel.assign(decision=sel.risk_score.map(_decision))
    cols = ["txn_id", "card_id", "ts", "amount_eur", "channel", "country", "merchant", "category",
            "risk_score", "decision", "rules", "evidence", "is_fraud"]
    return {"kind": kind, "total": len(sel), "payments": _records(sel[cols], limit)}


# ------------------------------------------------------------------ resources & prompts

@mcp.resource("ledger://schema", name="schema", mime_type="text/plain",
              description="The commented SQL schema of the Ledger database.")
def schema_resource() -> str:
    return (SQL_DIR / "schema.sql").read_text(encoding="utf-8")


@mcp.resource("ledger://checks", name="checks", mime_type="application/json",
              description="The six fraud checks with their settings and points.")
def checks_resource() -> str:
    return json.dumps(list_checks(), ensure_ascii=False, indent=2)


@mcp.prompt(title="Investigate a payment")
def investigate_payment(txn_id: str) -> str:
    """Walk through one payment like a fraud analyst would."""
    return (f"Investigate Ledger payment {txn_id}. Use explain_payment to see what it is and which "
            "checks it tripped, then card_activity around it to see what the card did before and "
            "after. Say in plain words whether this looks like fraud, which trick it resembles "
            "(card testing, copied card, hijacked account), whether the bank's decision was right, "
            "and what (if anything) a check could have done better.")


@mcp.prompt(title="Tune the checks")
def tune_the_checks() -> str:
    """Look for a better balance between catching fraud and annoying genuine customers."""
    return ("Use check_scorecard to see how each Ledger check performs. Pick the noisiest check, "
            "try two or three settings with try_check_setting, and try a couple of review/block "
            "thresholds with try_thresholds. Recommend one change, with the fraud it would catch "
            "or miss and how many genuine customers it would stop, in plain words.")


def run() -> None:
    mcp.run("stdio")
