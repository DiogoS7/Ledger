-- Channel mix per month. Contactless share is measured against card-present
-- payments only (chip & PIN plus contactless), the usual adoption metric.
SELECT
    strftime('%Y-%m', ts) AS month,
    ROUND(100.0 * SUM(channel = 'Contactless') / SUM(channel IN ('Contactless', 'Chip & PIN')), 2) AS contactless_pct,
    ROUND(100.0 * SUM(channel = 'Online') / COUNT(*), 2)                                         AS online_pct,
    ROUND(100.0 * SUM(channel = 'ATM') / COUNT(*), 2)                                            AS atm_pct,
    SUM(channel = 'Contactless') AS contactless,
    SUM(channel = 'Chip & PIN')  AS chip_pin,
    SUM(channel = 'Online')      AS online,
    SUM(channel = 'ATM')         AS atm
FROM transactions
WHERE status = 'Approved'
GROUP BY month
ORDER BY month;
