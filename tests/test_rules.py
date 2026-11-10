"""Each SQL rule against hand-made transactions: it must fire on the attack it
targets and stay quiet on the look-alike genuine behaviour."""

from ledger import rules as R
from conftest import ATM_MA, CAFE_LX, CRYPTO_LT, ELEC_CN, GIFTS_CN, GROCER_LX

RULE = {r.code: r for r in R.RULES}


def fired(con, code, **override):
    return set(R.run_rule(con, RULE[code], **override).txn_id)


def history(con, n=20, amount=40.0):
    """A normal month of grocery shopping before the interesting part."""
    for d in range(n):
        con.add(f"2026-03-{d + 1:02d} 18:00:00", amount)


# R1 velocity -------------------------------------------------------------

def test_velocity_fires_on_a_burst_counting_declined_attempts(mini):
    ids = [mini.add(f"2026-04-01 17:0{i}:00", 1.5, GIFTS_CN, "Online", "CN",
                    status="Declined" if i == 1 else "Approved") for i in range(5)]
    hit = fired(mini, "R1")
    assert ids[3] in hit and ids[4] in hit          # 4th and 5th charge within 10 minutes
    assert ids[0] not in hit and ids[1] not in hit  # first charges, and never a declined one


def test_velocity_ignores_spread_out_payments(mini):
    for i in range(6):
        mini.add(f"2026-04-01 1{i}:00:00", 12.0)
    assert fired(mini, "R1") == set()


# R2 test then spend ------------------------------------------------------

def test_big_online_payment_after_test_charges(mini):
    for i in range(3):
        mini.add(f"2026-04-01 17:0{i}:00", 1.2, GIFTS_CN, "Online", "CN")
    big = mini.add("2026-04-01 18:10:00", 900.0, ELEC_CN, "Online", "CN")
    assert fired(mini, "R2") == {big}


def test_big_payment_long_after_small_ones_is_fine(mini):
    for i in range(3):
        mini.add(f"2026-04-01 09:0{i}:00", 1.2, GIFTS_CN, "Online", "CN")
    mini.add("2026-04-01 15:00:00", 900.0, ELEC_CN, "Online", "CN")   # 6 hours later
    assert fired(mini, "R2") == set()


# R3 impossible travel ----------------------------------------------------

def test_card_used_abroad_and_at_home_within_hours(mini):
    mini.add("2026-05-10 10:00:00", 20.0)
    atm = mini.add("2026-05-10 11:00:00", 300.0, ATM_MA, "ATM", "MA")
    assert fired(mini, "R3") == {atm}


def test_traveller_landing_after_a_long_gap_is_fine(mini):
    mini.add("2026-05-10 07:00:00", 3.0, CAFE_LX)                         # airport coffee
    mini.add("2026-05-10 13:30:00", 60.0, ATM_MA, "ATM", "MA")            # 6.5 hours later
    assert fired(mini, "R3") == set()
    assert len(fired(mini, "R3", max_hours=8)) == 1                        # loosen it and it fires


def test_online_payments_do_not_count_as_travel(mini):
    mini.add("2026-05-10 10:00:00", 20.0)
    mini.add("2026-05-10 10:30:00", 50.0, ELEC_CN, "Online", "CN")
    assert fired(mini, "R3") == set()


# R4 amount spike ---------------------------------------------------------

def test_spike_needs_history_multiple_and_floor(mini):
    history(mini, 20, 40.0)
    spike = mini.add("2026-04-02 20:00:00", 600.0, ELEC_CN, "Online", "CN")   # 15x
    mini.add("2026-04-03 20:00:00", 200.0)                                    # 5x and under the floor
    assert fired(mini, "R4") == {spike}


def test_no_spike_without_enough_history(mini):
    history(mini, 5, 40.0)
    mini.add("2026-04-02 20:00:00", 900.0)
    assert fired(mini, "R4") == set()


# R5 night-time high-risk -------------------------------------------------

def test_night_purchase_at_high_risk_merchant(mini):
    night = mini.add("2026-04-02 03:15:00", 400.0, CRYPTO_LT, "Online", "LT")
    mini.add("2026-04-02 14:15:00", 400.0, CRYPTO_LT, "Online", "LT")         # daytime
    mini.add("2026-04-02 03:30:00", 400.0, GROCER_LX, "Online", "PT")         # not high-risk
    assert fired(mini, "R5") == {night}


# R6 first high-risk merchant abroad --------------------------------------

def test_only_the_first_high_risk_payment_per_country(mini):
    first = mini.add("2026-04-02 12:00:00", 300.0, ELEC_CN, "Online", "CN")
    mini.add("2026-04-09 12:00:00", 300.0, GIFTS_CN, "Online", "CN")
    assert fired(mini, "R6") == {first}


# scoring -----------------------------------------------------------------

def test_score_counts_hits_and_misses(mini):
    a = mini.add("2026-04-02 03:15:00", 400.0, CRYPTO_LT, "Online", "LT", fraud=True)
    mini.add("2026-04-02 03:45:00", 300.0, CRYPTO_LT, "Online", "LT")         # genuine, also fires
    mini.add("2026-04-05 12:00:00", 100.0, GROCER_LX, fraud=True)            # fraud nobody catches
    s = R.score(R.run_rule(mini, RULE["R5"]), R.labels(mini))
    assert s["alerts"] == 2 and s["true_positives"] == 1 and s["false_positives"] == 1
    assert s["precision"] == 0.5 and s["recall"] == 0.5
    assert s["fraud_eur_caught"] == 400.0 and s["value_recall"] == 0.8
    assert a in set(R.run_rule(mini, RULE["R5"]).txn_id)
