-- R4 · Unusually big payment
-- A payment far above what this card normally spends.
-- Baseline = average of the card's previous :history approved payments (at least 10 of them).
-- Flag when the amount is :multiple times the baseline and at least :floor_eur.
-- Params: history = 50, multiple = 8, floor_eur = 250
WITH baseline AS (
    SELECT txn_id, amount_eur, status,
           AVG(CASE WHEN status = 'Approved' THEN amount_eur END) OVER w   AS avg_before,
           COUNT(CASE WHEN status = 'Approved' THEN 1 END)        OVER w   AS n_before
    FROM transactions
    WINDOW w AS (PARTITION BY card_id ORDER BY ts, txn_id
                 ROWS BETWEEN :history PRECEDING AND 1 PRECEDING)
)
SELECT txn_id,
       'R4' AS rule,
       '€' || printf('%.2f', amount_eur) || ' = ' || printf('%.1f', amount_eur / avg_before)
         || '× the usual €' || printf('%.2f', avg_before) AS evidence
FROM baseline
WHERE status = 'Approved'
  AND n_before >= 10
  AND amount_eur >= :floor_eur
  AND amount_eur >= :multiple * avg_before;
