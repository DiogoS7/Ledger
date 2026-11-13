import json

import pytest
from mcp import Client

from ledger_mcp import server as S

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {
    "ledger_overview", "describe_schema", "list_analyses", "run_analysis", "query_sql",
    "list_checks", "check_scorecard", "try_check_setting", "try_thresholds",
    "explain_payment", "card_activity", "find_payments",
}


async def call(server, name, args=None):
    async with Client(server) as c:
        r = await c.call_tool(name, args or {})
    assert not r.is_error, r.content[0].text
    items = [json.loads(c.text) for c in r.content]
    return items if len(items) > 1 else items[0]


async def call_error(server, name, args):
    async with Client(server) as c:
        r = await c.call_tool(name, args)
    assert r.is_error
    return r.content[0].text


async def test_lists_tools_resources_and_prompts(server):
    async with Client(server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        resources = {str(r.uri) for r in (await c.list_resources()).resources}
        prompts = {p.name for p in (await c.list_prompts()).prompts}
    assert EXPECTED_TOOLS <= set(tools)
    assert all(t.annotations.read_only_hint for t in tools.values())
    assert {"ledger://schema", "ledger://checks"} <= resources
    assert {"investigate_payment", "tune_the_checks"} <= prompts


async def test_overview(server):
    o = await call(server, "ledger_overview")
    assert o["customers"] == 250 and o["txns"] > 1000
    assert 0 < o["fraud_eur"] < o["volume_eur"]
    assert o["review_threshold"] < o["block_threshold"]


async def test_analyses(server):
    names = [a["name"] for a in await call(server, "list_analyses")]
    assert "07_fraud_hotspots" in names and len(names) == 10
    r = await call(server, "run_analysis", {"name": "01", "max_rows": 3})
    assert r["name"] == "01_monthly_volume" and len(r["rows"]) == 3


async def test_query_sql_reads(server):
    r = await call(server, "query_sql",
                   {"sql": "SELECT channel, COUNT(*) n FROM transactions WHERE channel <> ';' GROUP BY channel"})
    assert r["columns"] == ["channel", "n"] and not r["truncated"]
    r = await call(server, "query_sql", {"sql": "SELECT txn_id FROM transactions", "max_rows": 5})
    assert r["row_count"] == 5 and r["truncated"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM transactions",
    "UPDATE cards SET credit_limit = 0",
    "SELECT 1; DROP TABLE customers",
    "WITH x AS (SELECT 1) DELETE FROM chargebacks",
    "ATTACH DATABASE 'x.db' AS x",
    "PRAGMA table_info(cards)",
    "SELECT load_extension('evil')",
])
async def test_query_sql_refuses_anything_but_reads(server, sql):
    await call_error(server, "query_sql", {"sql": sql})
    o = await call(server, "ledger_overview")
    assert o["customers"] == 250


async def test_checks_and_scorecard(server):
    checks = await call(server, "list_checks")
    assert [c["code"] for c in checks] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert all("SELECT" in c["sql"] for c in checks)
    card = await call(server, "check_scorecard")
    codes = {c["code"] for c in card["checks"]}
    assert {"R1", "BLOCK", "REVIEW"} <= codes
    for c in card["checks"]:
        assert 0 <= c["precision"] <= 1 and 0 <= c["recall"] <= 1


async def test_try_check_setting(server):
    r = await call(server, "try_check_setting", {"code": "r1", "setting": "min_txns", "value": 2})
    assert r["current"]["value"] == 4 and r["what_if"]["value"] == 2
    assert r["what_if"]["alerts"] >= r["current"]["alerts"]  # looser setting, more alerts
    msg = await call_error(server, "try_check_setting", {"code": "R1", "setting": "nope", "value": 1})
    assert "settings" in msg


async def test_try_thresholds(server):
    r = await call(server, "try_thresholds", {"review_at": 25, "block_at": 90})
    assert r["what_if"]["blocked"]["payments"] <= r["current"]["blocked"]["payments"]
    assert 0 <= r["current"]["share_of_stolen_eur_caught_with_review"] <= 1


async def test_find_and_explain_payments(server):
    caught = await call(server, "find_payments", {"kind": "caught", "limit": 3})
    assert caught["total"] > 0
    p = caught["payments"][0]
    assert p["is_fraud"] == 1 and p["risk_score"] >= 35

    e = await call(server, "explain_payment", {"txn_id": p["txn_id"]})
    assert e["was_fraud"] and e["verdict"] == "caught"
    assert e["risk_score"] == sum(c["points"] for c in e["checks_tripped"]) == p["risk_score"]
    assert all(c["evidence"] for c in e["checks_tripped"])

    missed = await call(server, "find_payments", {"kind": "missed", "limit": 1})
    if missed["total"]:
        m = await call(server, "explain_payment", {"txn_id": missed["payments"][0]["txn_id"]})
        assert m["verdict"] == "missed" and m["decision"] == "ALLOW"

    a = await call(server, "card_activity", {"card_id": p["card_id"], "around_txn_id": p["txn_id"], "limit": 6})
    assert p["txn_id"] in [x["txn_id"] for x in a["payments"]]


async def test_unknown_payment(server):
    assert "No payment" in await call_error(server, "explain_payment", {"txn_id": 10**9})


async def test_resources_and_prompt(server):
    async with Client(server) as c:
        schema = await c.read_resource("ledger://schema")
        checks = await c.read_resource("ledger://checks")
        prompt = await c.get_prompt("investigate_payment", {"txn_id": "42"})
    assert "CREATE TABLE transactions" in schema.contents[0].text
    assert len(json.loads(checks.contents[0].text)) == 6
    assert "42" in prompt.messages[0].content.text


def test_database_is_opened_read_only():
    con = S._connect()
    with pytest.raises(Exception):
        con.execute("DELETE FROM chargebacks")
    con.close()
