-- R3 · Impossible travel
-- A cloned card is used in a shop abroad while the real card is still being
-- used at home. Flag a card-present payment abroad when the same card also
-- made a card-present payment in Portugal less than :max_hours hours before
-- or after it: nobody flies there and back that fast.
-- Params: max_hours = 3
WITH present AS (
    SELECT txn_id, card_id, ts, country, status,
           MAX(CASE WHEN country = 'PT' THEN 1 ELSE 0 END) OVER (
               PARTITION BY card_id
               ORDER BY unixepoch(ts)
               RANGE BETWEEN :max_hours * 3600 PRECEDING AND :max_hours * 3600 FOLLOWING
           ) AS home_nearby
    FROM transactions
    WHERE channel <> 'Online'
)
SELECT txn_id,
       'R3' AS rule,
       'card-present in ' || country || ' and in PT within ' || :max_hours || ' h' AS evidence
FROM present
WHERE status = 'Approved'
  AND country <> 'PT'
  AND home_nearby = 1;
