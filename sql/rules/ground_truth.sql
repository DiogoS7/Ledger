-- Every approved transaction with its label: 1 if it came back as a fraud chargeback.
SELECT t.txn_id, t.card_id, t.ts, t.amount_eur, t.channel, t.country,
       m.category,
       CASE WHEN cb.reason = 'fraud' THEN 1 ELSE 0 END AS is_fraud
FROM transactions t
JOIN merchants m USING (merchant_id)
LEFT JOIN chargebacks cb USING (txn_id)
WHERE t.status = 'Approved';
