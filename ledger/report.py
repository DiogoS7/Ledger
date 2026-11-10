"""Run every analysis and rule, then write the static report site.

site/ ends up with index.html, styles.css, app.js (copied from web/) and
data.json, which holds every number the page shows. GitHub Pages serves it as is.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from . import DB_PATH, ROOT, SITE_DIR, __version__
from . import rules as R
from .db import connect, query, sql_text

WEB_DIR = ROOT / "web"
MONTHS_PT = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
             "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}


def _label(month: str) -> str:
    y, m = month.split("-")
    return f"{MONTHS_PT[m]} {y[2:]}"


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", double_precision=4))


def build_data(db_path: Path = DB_PATH) -> dict:
    with connect(db_path) as con:
        q = lambda name, **p: query(con, f"analysis/{name}", **p)  # noqa: E731
        kpi = q("10_kpis").iloc[0].to_dict()
        monthly = q("01_monthly_volume")
        cats = q("02_category_mix")
        channels = q("03_channel_trend")
        heat = q("04_hour_weekday")
        segments = q("05_segment_spend")
        fraud_m = q("06_fraud_monthly")
        hotspots = q("07_fraud_hotspots")
        report_days = q("08_time_to_report")
        districts = q("09_district_spend")

        rule_table, scored, truth = R.evaluate(con)
        curve = R.threshold_curve(scored, truth)
        tuning = R.tuning(con, truth)

    for df in (monthly, channels, fraud_m):
        df["label"] = df["month"].map(_label)

    base_rate = truth.is_fraud.mean()
    rule_table["lift"] = rule_table["precision"] / base_rate

    # alert queue: the highest-scoring alerts, as the fraud team would see them
    queue = (scored[scored.risk_score >= R.REVIEW_THRESHOLD]
             .sort_values(["risk_score", "amount_eur"], ascending=False))
    queue = queue.assign(
        action=queue.risk_score.map(lambda s: "Block" if s >= R.BLOCK_THRESHOLD else "Review"),
        outcome=queue.is_fraud.map({1: "Fraud", 0: "Genuine"}))
    sample = pd.concat([queue[queue.is_fraud == 1].head(9), queue[queue.is_fraud == 0].head(3)]) \
        .sort_values(["risk_score", "amount_eur"], ascending=False)

    # segment spend: one number per segment (weighted by customers)
    seg = (segments.assign(w=segments.avg_monthly_spend_eur * segments.customers)
           .groupby("segment").agg(customers=("customers", "max"), w=("w", "sum"), n=("customers", "sum"))
           .assign(avg_monthly_spend_eur=lambda d: d.w / d.n).reset_index()
           .sort_values("avg_monthly_spend_eur", ascending=False)[["segment", "avg_monthly_spend_eur"]])

    # geography split of fraud
    geo = hotspots.groupby("geography")[["txns", "fraud_txns", "fraud_eur"]].sum().reset_index()
    chan = hotspots.groupby("channel")[["txns", "fraud_txns", "fraud_eur"]].sum().reset_index()
    top_hot = hotspots[hotspots.fraud_eur > 0].head(8)

    block = rule_table.set_index("code").loc["BLOCK"]
    review = rule_table.set_index("code").loc["REVIEW"]
    first, last = channels.iloc[0], channels.iloc[-1]
    peak = monthly.loc[monthly.volume_eur.idxmax()]
    fraud_online = chan.set_index("channel").fraud_eur.get("Online", 0) / chan.fraud_eur.sum()
    fraud_foreign = geo.set_index("geography").fraud_eur.get("Foreign", 0) / geo.fraud_eur.sum()
    foreign_share = geo.set_index("geography").txns.get("Foreign", 0) / geo.txns.sum()
    median_days = float(pd.Series(report_days.days_to_report.repeat(report_days.fraud_txns)).median())
    top_cat = cats.iloc[0]
    fp = queue[queue.is_fraud == 0].category.value_counts()
    fp_cats = [c.lower() for c in fp.index[:3]]
    fp_share = fp.iloc[:3].sum() / fp.sum()

    online_eur = chan.set_index("channel").fraud_eur
    contactless_fraud = online_eur.get("Contactless", 0)
    per_day = review.false_positives / 365
    findings = [
        {"icon": "laptop", "title": "Most fraud happens online",
         "text": f"€{fraud_online * 100:.0f} of every €100 stolen was taken through online shopping. "
                 + ("Tapping a card in a shop: €0." if contactless_fraud == 0 else "")},
        {"icon": "globe", "title": "Fraudsters spend abroad",
         "text": f"{fraud_foreign:.0%} of the stolen money went to shops and websites outside Portugal, "
                 f"even though only {foreign_share * 100:.0f} in 100 payments happen abroad."},
        {"icon": "shield", "title": "Simple checks stop most of it",
         "text": f"Six simple checks working together stop {block.value_recall:.0%} of the stolen money automatically, "
                 f"and {block.precision * 10:.0f} out of 10 payments they stop really are fraud."},
        {"icon": "eye", "title": "A quick human look catches more",
         "text": f"If staff also look at the less obvious cases, {review.value_recall:.0%} of the stolen money is caught. "
                 f"That means checking {'less than one' if per_day < 1 else f'about {per_day:.0f}'} honest payment a day."},
        {"icon": "clock", "title": "People notice too late",
         "text": f"Half of the victims only reported the fraud {median_days:.0f} days or more after it happened, "
                 f"so the bank has to spot it the moment the payment is made."},
        {"icon": "tap", "title": "Tapping is taking over",
         "text": f"Paying by tapping the card went from {first.contactless_pct:.0f}% to {last.contactless_pct:.0f}% "
                 f"of payments in shops in one year."},
    ]

    # a handful of real examples, one of each kind, told in plain words
    reasons = {r.code: r.reason for r in R.RULES}
    def pick(mask):
        rows = queue[mask]
        return rows.iloc[0] if len(rows) else None
    has = lambda code: queue.rules.str.contains(code)  # noqa: E731
    picks = [
        ("Card testing", pick((queue.is_fraud == 1) & has("R2"))),
        ("Copied card", pick((queue.is_fraud == 1) & has("R3"))),
        ("Hijacked account", pick((queue.is_fraud == 1) & has("R5") & ~has("R2"))),
        ("Caught by a person", pick((queue.is_fraud == 1) & (queue.action == "Review"))),
        ("False alarm", pick((queue.is_fraud == 0) & has("R3"))),
        ("False alarm", pick((queue.is_fraud == 0) & (queue.action == "Block"))),
    ]
    examples = []
    for kind, r in picks:
        if r is None:
            continue
        examples.append({
            "kind": kind, "ts": r.ts, "amount_eur": float(r.amount_eur), "merchant": r.merchant,
            "category": r.category, "channel": r.channel, "country": r.country,
            "score": int(r.risk_score), "action": r.action, "is_fraud": int(r.is_fraud),
            "reasons": [reasons[c] for c in r.rules.split(" + ")],
        })

    rule_meta = [{"code": r.code, "name": r.name, "catches": r.catches, "weight": r.weight,
                  "plain": r.plain, "reason": r.reason,
                  "params": r.params, "sql": sql_text(f"rules/{r.file}"), "file": f"sql/rules/{r.file}.sql"}
                 for r in R.RULES]

    return {
        "version": __version__,
        "kpi": {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in kpi.items()},
        "base_rate": float(base_rate),
        "thresholds": {"block": R.BLOCK_THRESHOLD, "review": R.REVIEW_THRESHOLD},
        "findings": findings,
        "monthly": _records(monthly),
        "categories": _records(cats),
        "channels": _records(channels),
        "heatmap": _records(heat),
        "segments": _records(seg),
        "districts": _records(districts),
        "fraud_monthly": _records(fraud_m),
        "fraud_by_channel": _records(chan),
        "fraud_by_geo": _records(geo),
        "hotspots": _records(top_hot),
        "time_to_report": _records(report_days),
        "rules": rule_meta,
        "scorecard": _records(rule_table),
        "curve": _records(curve),
        "tuning": _records(tuning),
        "queue": _records(sample[["txn_id", "ts", "amount_eur", "channel", "country", "category",
                                  "merchant", "risk_score", "rules", "evidence", "action", "outcome"]]),
        "examples": examples,
        "queue_size": {"block": int((queue.action == "Block").sum()), "review": int((queue.action == "Review").sum())},
    }


def build_site(db_path: Path = DB_PATH, out: Path = SITE_DIR) -> Path:
    data = build_data(db_path)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB_DIR, out)
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
