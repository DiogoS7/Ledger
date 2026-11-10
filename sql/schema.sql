-- Ledger · card transactions of Banco Marés (a fictional Portuguese retail bank)
-- One row per customer, card, merchant and card transaction.
-- chargebacks holds the transactions customers later disputed; reason = 'fraud'
-- is the ground truth the fraud rules are scored against.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS chargebacks;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS merchants;
DROP TABLE IF EXISTS cards;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    age_band      TEXT    NOT NULL CHECK (age_band IN ('18-24','25-34','35-44','45-54','55-64','65+')),
    district      TEXT    NOT NULL,            -- home district in Portugal
    segment       TEXT    NOT NULL CHECK (segment IN ('Everyday','Premium','Student','Business')),
    joined_on     TEXT    NOT NULL             -- ISO date
);

CREATE TABLE cards (
    card_id       INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers (customer_id),
    card_type     TEXT    NOT NULL CHECK (card_type IN ('Debit','Credit')),
    issued_on     TEXT    NOT NULL,
    credit_limit  REAL                          -- NULL for debit cards
);

CREATE TABLE merchants (
    merchant_id   INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL,
    mcc           TEXT    NOT NULL,             -- ISO 18245 merchant category code
    category      TEXT    NOT NULL,
    country       TEXT    NOT NULL,             -- ISO 3166 alpha-2
    city          TEXT    NOT NULL,
    is_online     INTEGER NOT NULL CHECK (is_online IN (0, 1)),
    high_risk     INTEGER NOT NULL CHECK (high_risk IN (0, 1))   -- electronics, jewellery, gift cards, crypto
);

CREATE TABLE transactions (
    txn_id        INTEGER PRIMARY KEY,
    card_id       INTEGER NOT NULL REFERENCES cards (card_id),
    merchant_id   INTEGER NOT NULL REFERENCES merchants (merchant_id),
    ts            TEXT    NOT NULL,             -- ISO timestamp, Europe/Lisbon local time
    amount_eur    REAL    NOT NULL CHECK (amount_eur > 0),
    channel       TEXT    NOT NULL CHECK (channel IN ('Chip & PIN','Contactless','Online','ATM')),
    country       TEXT    NOT NULL,             -- where the transaction happened
    status        TEXT    NOT NULL CHECK (status IN ('Approved','Declined'))
);

CREATE TABLE chargebacks (
    txn_id        INTEGER PRIMARY KEY REFERENCES transactions (txn_id),
    reported_on   TEXT    NOT NULL,
    reason        TEXT    NOT NULL CHECK (reason IN ('fraud','dispute'))
);

CREATE INDEX idx_txn_card_ts   ON transactions (card_id, ts);
CREATE INDEX idx_txn_merchant  ON transactions (merchant_id);
CREATE INDEX idx_txn_ts        ON transactions (ts);
CREATE INDEX idx_cards_customer ON cards (customer_id);
