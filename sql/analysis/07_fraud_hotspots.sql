-- Fraud rate by channel, merchant category and domestic vs foreign.
-- Rate = share of approved value that later came back as fraud, in basis points.
SELECT
    t.channel,
    m.category,
    CASE WHEN t.country = 'PT' THEN 'Domestic' ELSE 'Foreign' END            AS geography,
    COUNT(*)                                                                  AS txns,
    SUM(cb.reason = 'fraud')                                                  AS fraud_txns,
    ROUND(SUM(CASE WHEN cb.reason = 'fraud' THEN t.amount_eur ELSE 0 END), 2) AS fraud_eur,
    ROUND(10000.0 * SUM(CASE WHEN cb.reason = 'fraud' THEN t.amount_eur ELSE 0 END)
                  / SUM(t.amount_eur), 1)                                     AS fraud_bps
FROM transactions t
JOIN merchants m USING (merchant_id)
LEFT JOIN chargebacks cb USING (txn_id)
WHERE t.status = 'Approved'
GROUP BY t.channel, m.category, geography
ORDER BY fraud_eur DESC;
