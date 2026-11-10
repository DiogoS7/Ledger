-- Fraud losses per month: confirmed fraud (chargebacks with reason 'fraud')
-- against approved volume, in basis points (1 bp = 0.01%).
SELECT
    strftime('%Y-%m', t.ts)                                                   AS month,
    SUM(cb.reason = 'fraud')                                                  AS fraud_txns,
    ROUND(SUM(CASE WHEN cb.reason = 'fraud' THEN t.amount_eur ELSE 0 END), 2) AS fraud_eur,
    ROUND(SUM(t.amount_eur), 2)                                               AS volume_eur,
    ROUND(10000.0 * SUM(CASE WHEN cb.reason = 'fraud' THEN t.amount_eur ELSE 0 END)
                  / SUM(t.amount_eur), 2)                                     AS fraud_bps,
    COUNT(DISTINCT CASE WHEN cb.reason = 'fraud' THEN t.card_id END)          AS cards_hit
FROM transactions t
LEFT JOIN chargebacks cb USING (txn_id)
WHERE t.status = 'Approved'
GROUP BY month
ORDER BY month;
