-- R1 · Rapid-fire charges
-- Card testing shows up as many charges on one card in a few minutes.
-- Count every attempt (declined ones too) on the card in the last :window_s
-- seconds and flag approved transactions once the count reaches :min_txns.
-- Params: window_s = 600, min_txns = 4
WITH counted AS (
    SELECT txn_id, card_id, ts, amount_eur, status,
           COUNT(*) OVER (
               PARTITION BY card_id
               ORDER BY unixepoch(ts)
               RANGE BETWEEN :window_s PRECEDING AND CURRENT ROW
           ) AS txns_in_window
    FROM transactions
)
SELECT txn_id,
       'R1' AS rule,
       txns_in_window || ' charges in ' || (:window_s / 60) || ' min' AS evidence
FROM counted
WHERE status = 'Approved'
  AND txns_in_window >= :min_txns;
