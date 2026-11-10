-- Headline numbers for the report.
SELECT
    (SELECT COUNT(*) FROM customers)                                      AS customers,
    (SELECT COUNT(*) FROM cards)                                          AS cards,
    (SELECT COUNT(*) FROM merchants)                                      AS merchants,
    COUNT(*)                                                              AS txns,
    SUM(status = 'Approved')                                              AS approved_txns,
    ROUND(SUM(CASE WHEN status = 'Approved' THEN amount_eur END), 2)      AS volume_eur,
    ROUND(AVG(CASE WHEN status = 'Approved' THEN amount_eur END), 2)      AS avg_ticket_eur,
    (SELECT COUNT(*) FROM chargebacks WHERE reason = 'fraud')             AS fraud_txns,
    (SELECT ROUND(SUM(t.amount_eur), 2) FROM chargebacks cb JOIN transactions t USING (txn_id)
      WHERE cb.reason = 'fraud')                                          AS fraud_eur,
    (SELECT COUNT(DISTINCT t.card_id) FROM chargebacks cb JOIN transactions t USING (txn_id)
      WHERE cb.reason = 'fraud')                                          AS cards_hit,
    MIN(date(ts))                                                         AS first_day,
    MAX(date(ts))                                                         AS last_day
FROM transactions;
