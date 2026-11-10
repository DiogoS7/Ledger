-- Where the money goes: transactions and value per merchant category,
-- with each category's share of the total.
WITH by_cat AS (
    SELECT m.category,
           COUNT(*)            AS txns,
           SUM(t.amount_eur)   AS volume_eur
    FROM transactions t
    JOIN merchants m USING (merchant_id)
    WHERE t.status = 'Approved'
    GROUP BY m.category
)
SELECT category,
       txns,
       ROUND(volume_eur, 2)                                        AS volume_eur,
       ROUND(volume_eur / txns, 2)                                 AS avg_ticket_eur,
       ROUND(100.0 * txns / SUM(txns) OVER (), 2)                  AS pct_of_txns,
       ROUND(100.0 * volume_eur / SUM(volume_eur) OVER (), 2)      AS pct_of_volume
FROM by_cat
ORDER BY volume_eur DESC;
