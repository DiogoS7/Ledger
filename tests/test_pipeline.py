"""End to end: generate a small database, check it is sane, and build the report."""

import json
import sqlite3

from ledger import rules as R
from ledger.db import connect, query
from ledger.generate import build
from ledger.report import build_data, build_site


def test_generation_is_deterministic(tmp_path, small_db):
    again = build(tmp_path / "again.db", seed=11, customers=250)
    sql = "SELECT COUNT(*), ROUND(SUM(amount_eur), 2), MAX(ts) FROM transactions"
    a = sqlite3.connect(small_db).execute(sql).fetchone()
    b = sqlite3.connect(again).execute(sql).fetchone()
    assert a == b


def test_data_is_consistent(small_db):
    con = sqlite3.connect(small_db)
    one = lambda q: con.execute(q).fetchone()[0]  # noqa: E731
    assert one("SELECT COUNT(*) FROM transactions") > 20_000
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert one("SELECT MIN(ts) FROM transactions") >= "2025-11-01"
    assert one("SELECT MAX(ts) FROM transactions") < "2026-11-01"
    # only approved payments can be charged back
    assert one("SELECT COUNT(*) FROM chargebacks JOIN transactions USING (txn_id) WHERE status <> 'Approved'") == 0
    # every reason is there, and fraud is rare
    assert one("SELECT COUNT(DISTINCT reason) FROM chargebacks") == 2
    assert one("SELECT 1.0 * COUNT(*) / (SELECT COUNT(*) FROM transactions) FROM chargebacks WHERE reason = 'fraud'") < 0.01


def test_every_analysis_query_runs(small_db):
    with connect(small_db) as con:
        for name in ["01_monthly_volume", "02_category_mix", "03_channel_trend", "04_hour_weekday",
                     "05_segment_spend", "06_fraud_monthly", "07_fraud_hotspots", "08_time_to_report",
                     "09_district_spend", "10_kpis"]:
            assert len(query(con, f"analysis/{name}")) > 0, name
        months = query(con, "analysis/01_monthly_volume")
        assert len(months) == 12
        mix = query(con, "analysis/02_category_mix")
        assert abs(mix.pct_of_volume.sum() - 100) < 0.1


def test_combined_score_beats_the_noisiest_rule(small_db):
    with connect(small_db) as con:
        table, scored, truth = R.evaluate(con)
    t = table.set_index("code")
    assert t.loc["BLOCK", "precision"] > t.loc["R4", "precision"]
    assert t.loc["REVIEW", "value_recall"] >= t.loc["BLOCK", "value_recall"]
    assert (scored.risk_score > 0).all()


def test_report_site(tmp_path, small_db):
    out = build_site(small_db, tmp_path / "site")
    for f in ["index.html", "app.js", "styles.css", "favicon.svg", "data.json"]:
        assert (out / f).exists(), f
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert len(data["findings"]) == 6
    assert {r["code"] for r in data["rules"]} == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert data == json.loads(json.dumps(build_data(small_db)))   # data.json matches a fresh build
