-- When people pay: approved transactions per weekday (0 = Monday) and hour.
SELECT
    (CAST(strftime('%w', ts) AS INTEGER) + 6) % 7  AS weekday,
    CAST(strftime('%H', ts) AS INTEGER)            AS hour,
    COUNT(*)                                       AS txns
FROM transactions
WHERE status = 'Approved'
GROUP BY weekday, hour
ORDER BY weekday, hour;
