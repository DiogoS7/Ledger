-- R5 · Late-night risky shop
-- Account takeovers often run while the customer sleeps.
-- Flag online payments of at least :min_eur at high-risk merchants
-- (electronics, jewellery, gift cards, crypto) between :from_hour and :to_hour.
-- Params: from_hour = 0, to_hour = 5, min_eur = 150
SELECT t.txn_id,
       'R5' AS rule,
       m.category || ' at ' || strftime('%H:%M', t.ts) AS evidence
FROM transactions t
JOIN merchants m USING (merchant_id)
WHERE t.status = 'Approved'
  AND t.channel = 'Online'
  AND m.high_risk = 1
  AND t.amount_eur >= :min_eur
  AND CAST(strftime('%H', t.ts) AS INTEGER) BETWEEN :from_hour AND :to_hour - 1;
