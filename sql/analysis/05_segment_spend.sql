-- Average monthly spend per customer, by segment and age band.
WITH monthly AS (
    SELECT c.customer_id, c.segment, c.age_band,
           strftime('%Y-%m', t.ts)  AS month,
           SUM(t.amount_eur)        AS spend
    FROM transactions t
    JOIN cards     k USING (card_id)
    JOIN customers c ON c.customer_id = k.customer_id
    WHERE t.status = 'Approved'
    GROUP BY c.customer_id, month
)
SELECT segment, age_band,
       COUNT(DISTINCT customer_id)   AS customers,
       ROUND(AVG(spend), 2)          AS avg_monthly_spend_eur
FROM monthly
GROUP BY segment, age_band
ORDER BY segment, age_band;
