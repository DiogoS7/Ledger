"""The fraud rules: run each SQL rule, score it against the chargebacks, and
combine the rules into one risk score."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from .db import query


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    file: str
    params: dict
    weight: int              # points added to the risk score when the rule fires
    catches: str             # the attack it is aimed at
    tune: tuple = field(default=())   # (param, [values]) for the tuning chart
    plain: str = ""          # the rule in everyday words, for the report
    reason: str = ""         # short reason shown on an example alert


RULES = [
    Rule("R1", "Rapid-fire charges", "r1_velocity",
         {"window_s": 600, "min_txns": 4}, 40, "Card testing",
         ("min_txns", [2, 3, 4, 5, 6, 8]),
         "The same card is charged 4 or more times within 10 minutes.",
         "lots of charges in a few minutes"),
    Rule("R2", "Test, then spend", "r2_test_then_spend",
         {"micro_eur": 3, "min_micro": 3, "big_eur": 200, "lookback_s": 7200}, 60, "Card testing", (),
         "A big online purchase (€200+) comes right after a few tiny test charges of under €3.",
         "tiny test charges, then a big one"),
    Rule("R3", "Two places at once", "r3_impossible_travel",
         {"max_hours": 2}, 50, "Copied card",
         ("max_hours", [1, 2, 3, 4, 6, 8]),
         "The card is used in a shop abroad less than 2 hours before or after being used in Portugal.",
         "in two countries within 2 hours"),
    Rule("R4", "Unusually big payment", "r4_amount_spike",
         {"history": 50, "multiple": 8, "floor_eur": 250}, 30, "Hijacked account",
         ("multiple", [3, 4, 6, 8, 10, 15]),
         "A payment of €250+ that is 8 times bigger than what this card usually spends.",
         "far bigger than usual"),
    Rule("R5", "Late-night risky shop", "r5_night_high_risk",
         {"from_hour": 0, "to_hour": 5, "min_eur": 150}, 35, "Hijacked account", (),
         "An online purchase of €150+ between midnight and 5am at a risky kind of shop (electronics, jewellery, gift cards or crypto).",
         "risky shop in the middle of the night"),
    Rule("R6", "New country, risky shop", "r6_new_country_high_risk",
         {"min_eur": 100}, 25, "Hijacked account", (),
         "The first time this card ever pays a risky kind of shop in that foreign country (€100+).",
         "first risky shop in a new country"),
]
BLOCK_THRESHOLD = 60    # risk score at which the payment is blocked and the customer called
REVIEW_THRESHOLD = 35   # risk score at which it goes to the analysts' review queue


def labels(con: sqlite3.Connection) -> pd.DataFrame:
    return query(con, "rules/ground_truth")


def run_rule(con: sqlite3.Connection, rule: Rule, **override) -> pd.DataFrame:
    return query(con, f"rules/{rule.file}", **{**rule.params, **override})


def score(alerts: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Precision, recall and value caught for a set of alerted txn_ids."""
    ids = set(alerts["txn_id"])
    fraud = truth[truth.is_fraud == 1]
    hits = fraud[fraud.txn_id.isin(ids)]
    n = len(ids)
    return {
        "alerts": n,
        "true_positives": len(hits),
        "false_positives": n - len(hits),
        "precision": len(hits) / n if n else 0.0,
        "recall": len(hits) / len(fraud) if len(fraud) else 0.0,
        "fraud_eur_caught": float(hits.amount_eur.sum()),
        "value_recall": float(hits.amount_eur.sum() / fraud.amount_eur.sum()) if len(fraud) else 0.0,
    }


def evaluate(con: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Score every rule on its own and the combined risk score.

    Returns (rule_table, scored_alerts, truth).
    """
    truth = labels(con)
    rows, fired = [], []
    for r in RULES:
        a = run_rule(con, r)
        fired.append(a.assign(weight=r.weight))
        rows.append({"code": r.code, "rule": r.name, "catches": r.catches, "weight": r.weight,
                     **score(a, truth)})
    allfired = pd.concat(fired, ignore_index=True)
    scored = (allfired.groupby("txn_id")
              .agg(risk_score=("weight", "sum"),
                   rules=("rule", lambda s: " + ".join(sorted(set(s)))),
                   evidence=("evidence", " · ".join))
              .reset_index()
              .merge(truth, on="txn_id", how="left"))
    for code, label, lo in (("BLOCK", f"Block · score ≥ {BLOCK_THRESHOLD}", BLOCK_THRESHOLD),
                            ("REVIEW", f"Block + review · score ≥ {REVIEW_THRESHOLD}", REVIEW_THRESHOLD)):
        rows.append({"code": code, "rule": label, "catches": "All three", "weight": None,
                     **score(scored[scored.risk_score >= lo], truth)})
    return pd.DataFrame(rows), scored, truth


def threshold_curve(scored: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Precision and recall of the combined score at every possible alert threshold."""
    out = []
    for t in sorted(scored.risk_score.unique()):
        out.append({"threshold": int(t), **score(scored[scored.risk_score >= t], truth)})
    return pd.DataFrame(out)


def tuning(con: sqlite3.Connection, truth: pd.DataFrame) -> pd.DataFrame:
    """Sweep one parameter per tunable rule to show the precision/recall trade-off."""
    out = []
    for r in RULES:
        if not r.tune:
            continue
        param, values = r.tune
        for v in values:
            s = score(run_rule(con, r, **{param: v}), truth)
            out.append({"code": r.code, "rule": r.name, "param": param, "value": v,
                        "is_default": v == r.params[param], **s})
    return pd.DataFrame(out)
