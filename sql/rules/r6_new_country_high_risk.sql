-- R6 · First high-risk merchant abroad
-- The first time a card ever pays a high-risk merchant in a given foreign country.
-- Params: min_eur = 100
WITH firsts AS (
    SELECT t.txn_id, t.status, t.amount_eur, t.country, m.high_risk, m.category,
           ROW_NUMBER() OVER (PARTITION BY t.card_id, t.country, m.high_risk ORDER BY t.ts) AS nth
    FROM transactions t
    JOIN merchants m USING (merchant_id)
)
SELECT txn_id,
       'R6' AS rule,
       'first ' || category || ' payment in ' || country AS evidence
FROM firsts
WHERE status = 'Approved'
  AND high_risk = 1
  AND country <> 'PT'
  AND nth = 1
  AND amount_eur >= :min_eur;
