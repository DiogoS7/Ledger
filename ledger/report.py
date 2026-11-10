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

    findings = [
        {"title": "Fraud lives online and abroad",
         "text": f"{fraud_online:.0%} of fraud losses came through online payments and {fraud_foreign:.0%} "
                 f"from foreign merchants, while only {foreign_share:.1%} of all transactions happen abroad."},
        {"title": "Two tiers beat one big net",
         "text": f"Blocking at a risk score of {R.BLOCK_THRESHOLD} stops {block.value_recall:.0%} of fraud value "
                 f"with {block.precision:.0%} precision. Adding a review queue from {R.REVIEW_THRESHOLD} lifts that to "
                 f"{review.value_recall:.0%} of value, at the cost of {int(review.false_positives)} genuine payments to check."},
        {"title": "Single rules are noisy",
         "text": f"On its own, the amount-spike rule catches the most fraud value but only {rule_table.set_index('code').loc['R4', 'precision']:.1%} "
                 f"of its alerts are fraud. Combined with the other signals it stops being a false-alarm machine."},
        {"title": "Customers notice late",
         "text": f"Half of the fraud is reported {median_days:.0f} days or more after the payment, which is why "
                 f"rules have to act at the moment of payment rather than wait for chargebacks."},
        {"title": "Contactless keeps growing",
         "text": f"Contactless went from {first.contactless_pct:.0f}% to {last.contactless_pct:.0f}% of card-present payments "
                 f"between {first.label} and {last.label}. Spending peaked in {peak.label} at €{peak.volume_eur/1e6:.2f}M."},
        {"title": "False alarms come from big tickets",
         "text": f"{top_cat.category} is the biggest category by value ({top_cat.pct_of_volume:.0f}%), but genuine payments flagged for review "
                 f"are mostly {fp_cats[0]}, {fp_cats[1]} and {fp_cats[2]} ({fp_share:.0%} of them): big one-off purchases, and travellers paying abroad soon after a payment at home."},
    ]

    rule_meta = [{"code": r.code, "name": r.name, "catches": r.catches, "weight": r.weight,
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
                                  "risk_score", "rules", "evidence", "action", "outcome"]]),
        "queue_size": {"block": int((queue.action == "Block").sum()), "review": int((queue.action == "Review").sum())},
    }


def build_site(db_path: Path = DB_PATH, out: Path = SITE_DIR) -> Path:
    data = build_data(db_path)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB_DIR, out)
    (out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
