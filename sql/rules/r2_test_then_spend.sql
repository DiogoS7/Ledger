-- R2 · Test, then spend
-- After the tiny test charges work, fraudsters go for big online purchases.
-- Flag an online payment of at least :big_eur when the same card made
-- :min_micro or more online charges under :micro_eur in the previous :lookback_s seconds.
-- Params: micro_eur = 3, min_micro = 3, big_eur = 200, lookback_s = 7200
WITH flagged AS (
    SELECT txn_id, card_id, ts, amount_eur, channel, status,
           SUM(CASE WHEN channel = 'Online' AND amount_eur < :micro_eur THEN 1 ELSE 0 END) OVER (
               PARTITION BY card_id
               ORDER BY unixepoch(ts)
               RANGE BETWEEN :lookback_s PRECEDING AND 1 PRECEDING
           ) AS micro_before
    FROM transactions
)
SELECT txn_id,
       'R2' AS rule,
       micro_before || ' test charges, then €' || printf('%.2f', amount_eur) AS evidence
FROM flagged
WHERE status = 'Approved'
  AND channel = 'Online'
  AND amount_eur >= :big_eur
  AND micro_before >= :min_micro;
