# Ledger MCP

[![CI](https://github.com/DiogoS7/Ledger-MCP/actions/workflows/ci.yml/badge.svg)](https://github.com/DiogoS7/Ledger-MCP/actions/workflows/ci.yml)

**Ask an AI assistant about card fraud, and let it check the answers in the data.**

An [MCP](https://modelcontextprotocol.io) server for [Ledger](https://github.com/DiogoS7/Ledger), my project on a year of card payments at Meridian Bank, a made-up Portuguese bank: 430,000 payments, three kinds of planted fraud, and six SQL checks that score every payment.

With this server, Claude (or any MCP client) can:

- **answer questions about the data:** "Which country do stolen cards get used in most?"
- **explain a decision:** "Why was payment 406064 blocked? Was it really fraud?"
- **find the mistakes:** "Show me the biggest frauds the checks missed."
- **try changes before making them:** "What if we block at 50 points instead of 60?"

It doesn't copy anything from Ledger. It imports the `ledger` package from a Ledger checkout, so the checks, scoring and points system are the same code that builds [the report](https://diogos7.github.io/Ledger/).

![explain_payment in the MCP Inspector: payment 406064 was blocked by two checks (65 points) and really was fraud](docs/screenshots/inspector.png)

*`explain_payment` run in the [MCP Inspector](https://github.com/modelcontextprotocol/inspector): payment 406064 tripped two checks (65 points), was blocked, and really was fraud.*

## Tools

| Tool | What it does |
| --- | --- |
| `ledger_overview` | Headline numbers: customers, payments, money spent, fraud losses, thresholds |
| `describe_schema` | Tables, columns, row counts and the commented schema |
| `list_analyses` / `run_analysis` | The 10 ready-made SQL analyses behind the report (category mix, contactless trend, fraud hotspots, time to report, ...) |
| `query_sql` | Any read-only `SELECT` / `WITH` query, capped at 500 rows and 20 seconds |
| `list_checks` | The six checks in plain words, with their points, settings and SQL |
| `check_scorecard` | Precision, recall and euros caught, for each check and for the combined points system |
| `try_check_setting` | Re-run one check with one setting changed and compare (e.g. R1 `min_txns` 4 → 3) |
| `try_thresholds` | Change the review/block thresholds and see fraud caught vs genuine customers stopped |
| `explain_payment` | One payment in full: shop, card, customer, checks tripped with evidence, score, decision, and whether it really was fraud |
| `card_activity` | A card's payments in order, optionally around one payment (to spot test charges or a trip abroad) |
| `find_payments` | Example payments by outcome: `caught`, `missed`, `false_alarm`, `reviewed` |

It also has two **resources** (`ledger://schema`, `ledger://checks`) and two **prompts** (`investigate_payment`, `tune_the_checks`).

Every tool is read-only. The database is opened with SQLite's `mode=ro`. `query_sql` also uses an authorizer that only allows reads, so writes, `ATTACH`, `PRAGMA` and extension loading are refused even if they get past the single-statement check. The what-if tools change settings for that call only and save nothing.

## Example

> **You:** Why was payment 406064 stopped?
>
> **Claude** *(calls `explain_payment`, then `card_activity`)*: It was a €1,495 online purchase at an electronics shop at 4:53 in the morning, on the debit card of a customer aged 65+ from Lisboa. Two checks fired. **Unusually big payment** (+30): it was 14.4× this card's usual €103.90. **Late-night risky shop** (+35): electronics, at 04:53. That makes 65 points, over the 60 needed to block it. The customer reported it as fraud five days later, so blocking it was right. This looks like a hijacked account.

What the tools return on the full dataset:

```text
try_thresholds(review_at=30, block_at=50)
  current : blocked automatically 77.2% of stolen €, 93.6% with review
  what-if : blocked 389 payments, 253 of them genuine customers ...

try_check_setting("R4", "multiple", 12)
  current (8×) : 3,517 alerts, precision 2.8%, catches 78.7% of stolen €
  what-if (12×): 1,626 alerts, precision 4.4%, catches 62.1% of stolen €
```

## Set it up

Needs Python 3.12+, `git` and [uv](https://docs.astral.sh/uv/).

**1. Get Ledger and build its database** (one time, about a minute):

```bash
uvx --from git+https://github.com/DiogoS7/Ledger-MCP ledger-mcp setup
```

This clones Ledger into `~/.ledger-mcp/Ledger` and generates `data/ledger.db`. If you already have a checkout, set `LEDGER_HOME` to it (and run `python -m ledger generate` there if there's no database yet).

**2. Add it to your MCP client.**

Claude Code:

```bash
claude mcp add ledger -- uvx --from git+https://github.com/DiogoS7/Ledger-MCP ledger-mcp
```

Claude Desktop (`claude_desktop_config.json`), or any client that takes the same format:

```json
{
  "mcpServers": {
    "ledger": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/DiogoS7/Ledger-MCP", "ledger-mcp"],
      "env": { "LEDGER_HOME": "/path/to/Ledger" }
    }
  }
}
```

`env` is optional. Without it the server uses `~/.ledger-mcp/Ledger`. Set `LEDGER_DB` to use a database somewhere else.

## How it works

```
MCP client (Claude)
   │  stdio
   ▼
ledger_mcp/server.py      12 tools · 2 resources · 2 prompts   (mcp 2.x MCPServer)
   │  imports
   ▼
Ledger checkout           ledger.rules  → the six checks, scoring, thresholds
($LEDGER_HOME)            ledger.db     → runs sql/analysis/*.sql and sql/rules/*.sql
   │  read-only
   ▼
data/ledger.db            customers · cards · merchants · transactions · chargebacks
```

The first call that needs the checks runs all six over the 430k payments (about 7 seconds) and keeps the result in memory until the database file changes. After that, `explain_payment`, `find_payments` and `try_thresholds` answer instantly. `try_check_setting` re-runs a single check, which takes about 3 seconds.

## Develop

```bash
git clone https://github.com/DiogoS7/Ledger-MCP && cd Ledger-MCP
git clone https://github.com/DiogoS7/Ledger ../Ledger
LEDGER_HOME=../Ledger uv run pytest -q
```

The tests build a small Ledger database (250 customers) and talk to the server through an in-memory MCP client. They cover every tool, both resources, a prompt, and the read-only guarantees. To try it by hand, use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector): `npx @modelcontextprotocol/inspector uv run ledger-mcp`.

The data is synthetic. No real people or banks are involved.

## License

MIT
