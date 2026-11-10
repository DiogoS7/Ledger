-- How long customers take to report fraud: days from the transaction to the chargeback.
SELECT
    CAST(julianday(cb.reported_on) - julianday(date(t.ts)) AS INTEGER) AS days_to_report,
    COUNT(*)                                                           AS fraud_txns,
    ROUND(SUM(t.amount_eur), 2)                                        AS fraud_eur
FROM chargebacks cb
JOIN transactions t USING (txn_id)
WHERE cb.reason = 'fraud'
GROUP BY days_to_report
ORDER BY days_to_report;
