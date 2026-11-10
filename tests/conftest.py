import sqlite3
from pathlib import Path

import pytest

from ledger import SQL_DIR
from ledger.generate import build

# merchant ids used by the hand-made fixtures
GROCER_LX, GIFTS_CN, ELEC_CN, ATM_MA, CAFE_LX, CRYPTO_LT = 1, 2, 3, 4, 5, 6


class MiniDB(sqlite3.Connection):
    def add(self, ts, amount, merchant=GROCER_LX, channel="Contactless", country="PT",
            status="Approved", fraud=False):
        """Add one payment on card 1; fraud=True also files a fraud chargeback."""
        cur = self.execute(
            "INSERT INTO transactions (card_id, merchant_id, ts, amount_eur, channel, country, status) "
            "VALUES (1,?,?,?,?,?,?)", (merchant, ts, amount, channel, country, status))
        if fraud and status == "Approved":
            self.execute("INSERT INTO chargebacks VALUES (?, '2026-12-01', 'fraud')", (cur.lastrowid,))
        return cur.lastrowid


@pytest.fixture
def mini():
    """An empty Ledger database in memory, with a few merchants and one card."""
    con = sqlite3.connect(":memory:", factory=MiniDB)
    con.executescript((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
    con.execute("INSERT INTO customers VALUES (1,'35-44','Lisboa','Everyday','2020-01-01')")
    con.execute("INSERT INTO cards VALUES (1,1,'Credit','2021-01-01',2500)")
    con.executemany("INSERT INTO merchants VALUES (?,?,?,?,?,?,?,?)", [
        (GROCER_LX, "Mercado Lisboa", "5411", "Groceries", "PT", "Lisboa", 0, 0),
        (GIFTS_CN, "Gift Codes CN", "5815", "Gift cards & vouchers", "CN", "Online", 1, 1),
        (ELEC_CN, "Volt Shop CN", "5732", "Electronics", "CN", "Online", 1, 1),
        (ATM_MA, "ATM Marraquexe", "6011", "ATM cash", "MA", "Marraquexe", 0, 0),
        (CAFE_LX, "Café Lisboa", "5814", "Cafés & bakeries", "PT", "Lisboa", 0, 0),
        (CRYPTO_LT, "Coin Swap LT", "6051", "Crypto exchange", "LT", "Online", 1, 1),
    ])

    yield con
    con.close()


@pytest.fixture(scope="session")
def small_db(tmp_path_factory) -> Path:
    """A small generated database, shared by the slower end-to-end tests."""
    path = tmp_path_factory.mktemp("db") / "ledger.db"
    return build(path, seed=11, customers=250)
