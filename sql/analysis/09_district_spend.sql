-- Customers and average yearly card spend per home district.
WITH per_customer AS (
    SELECT c.customer_id, c.district, SUM(t.amount_eur) AS spend
    FROM customers c
    JOIN cards        k ON k.customer_id = c.customer_id
    JOIN transactions t ON t.card_id = k.card_id AND t.status = 'Approved'
    GROUP BY c.customer_id
)
SELECT district,
       COUNT(*)              AS customers,
       ROUND(AVG(spend), 2)  AS avg_yearly_spend_eur,
       ROUND(SUM(spend), 2)  AS total_spend_eur
FROM per_customer
GROUP BY district
ORDER BY customers DESC;
