-- Monthly card volume: approved transactions, value, average ticket and active cards.
SELECT
    strftime('%Y-%m', ts)            AS month,
    COUNT(*)                         AS txns,
    ROUND(SUM(amount_eur), 2)        AS volume_eur,
    ROUND(AVG(amount_eur), 2)        AS avg_ticket_eur,
    COUNT(DISTINCT card_id)          AS active_cards
FROM transactions
WHERE status = 'Approved'
GROUP BY month
ORDER BY month;
