"""Generate the Banco Marés card dataset into SQLite.

Everything is synthetic and seeded, so the same seed always produces the same
database. Twelve months of everyday card spending for a few thousand customers,
with three kinds of fraud attack planted in it:

* card testing   - a burst of tiny online charges, then big ones
* cloned card    - card-present spending abroad while the real customer is at home
* account takeover - a night-time online spree at high-risk merchants

Every fraudulent transaction that was approved gets a chargeback with
reason 'fraud'. That is the ground truth the SQL rules are scored against.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from . import DB_PATH, SQL_DIR

START = datetime(2025, 11, 1)
MONTHS = 12

# ---------------------------------------------------------------- reference data

DISTRICTS = {  # district: (main city, weight)
    "Lisboa": ("Lisboa", 0.27), "Porto": ("Porto", 0.18), "Setúbal": ("Setúbal", 0.08),
    "Braga": ("Braga", 0.08), "Aveiro": ("Aveiro", 0.07), "Leiria": ("Leiria", 0.06),
    "Coimbra": ("Coimbra", 0.06), "Faro": ("Faro", 0.06), "Madeira": ("Funchal", 0.04),
    "Viseu": ("Viseu", 0.04), "Évora": ("Évora", 0.03), "Açores": ("Ponta Delgada", 0.03),
}

FOREIGN_CITIES = {  # country: cities travellers visit
    "ES": ["Madrid", "Barcelona", "Sevilha"], "FR": ["Paris", "Lyon"], "GB": ["Londres"],
    "IT": ["Roma", "Milão"], "DE": ["Berlim"], "NL": ["Amesterdão"], "BR": ["São Paulo"],
    "US": ["Nova Iorque"], "MA": ["Marraquexe"],
}
TRAVEL_WEIGHTS = {"ES": .30, "FR": .18, "GB": .12, "IT": .12, "DE": .06, "NL": .06,
                  "BR": .07, "US": .05, "MA": .04}

@dataclass(frozen=True)
class Category:
    name: str
    mcc: str
    mean: float          # typical ticket in EUR (lognormal median)
    sigma: float         # spread of the lognormal
    weight: float        # share of everyday transactions
    hours: tuple         # (peak hour, spread)
    online: float        # share bought online
    high_risk: bool = False

CATEGORIES = [
    Category("Groceries",              "5411", 28,  .65, .22,  (18, 3.0), .04),
    Category("Cafés & bakeries",       "5814", 3.2, .45, .17,  (10, 2.5), .00),
    Category("Restaurants",            "5812", 21,  .55, .11,  (13, 3.5), .08),
    Category("Fuel",                   "5541", 48,  .35, .07,  (17, 3.5), .00),
    Category("Transport",              "4111", 6,   .70, .08,  (8,  2.5), .30),
    Category("Pharmacy",               "5912", 15,  .70, .05,  (15, 3.0), .05),
    Category("Clothing",               "5651", 45,  .70, .05,  (16, 3.0), .35),
    Category("Online marketplace",     "5964", 32,  .80, .06,  (21, 2.5), 1.0),
    Category("Streaming & subscriptions", "4899", 10, .40, .04, (20, 3.0), 1.0),
    Category("Utilities & telecom",    "4900", 52,  .40, .02,  (11, 2.5), 1.0),
    Category("Travel & airlines",      "4511", 180, .70, .01,  (21, 2.5), .90),
    Category("Hotels",                 "7011", 120, .60, .01,  (19, 3.0), .70),
    Category("ATM cash",               "6011", 60,  .55, .06,  (12, 4.0), .00),
    Category("Electronics",            "5732", 140, .90, .010, (17, 3.0), .55, True),
    Category("Jewellery",              "5944", 180, .80, .002, (16, 2.5), .30, True),
    Category("Gift cards & vouchers",  "5815", 30,  .60, .006, (20, 3.0), 1.0, True),
    Category("Crypto exchange",        "6051", 150, .90, .002, (22, 3.0), 1.0, True),
]
CAT = {c.name: c for c in CATEGORIES}

NAME_PARTS = {
    "Groceries": (["Mercado", "Supermercado", "Minimercado", "Frescos"], ["do Bairro", "Central", "Atlântico", "da Praça", "Bom Dia"]),
    "Cafés & bakeries": (["Pastelaria", "Café", "Padaria", "Confeitaria"], ["Aurora", "do Largo", "Estrela", "Doce Lar", "Nata"]),
    "Restaurants": (["Restaurante", "Tasca", "Taberna", "Cervejaria"], ["do Mar", "Velha", "Lusitana", "O Pátio", "da Ribeira"]),
    "Fuel": (["Posto", "Bomba"], ["Rota Norte", "Via Sul", "Estrada Real", "Combustíveis Ria"]),
    "Transport": (["Transportes", "Metro"], ["Urbanos", "Metropolitanos", "Linha Azul"]),
    "Pharmacy": (["Farmácia"], ["Saúde", "Central", "Moderna", "do Rossio", "Vida"]),
    "Clothing": (["Loja", "Boutique", "Atelier"], ["Linho", "Algodão", "Moda Mar", "Riscas", "Fio"]),
    "Online marketplace": (["Mercado", "Bazar"], ["Online", "Digital", "Clique", "Num Instante"]),
    "Streaming & subscriptions": (["Ondas", "Ecrã", "Som"], ["Play", "TV", "Plus", "Stream"]),
    "Utilities & telecom": (["Energia", "Águas", "Telecom"], ["Litoral", "do Tejo", "Nova", "Rede"]),
    "Travel & airlines": (["Voa", "Viagens", "Rumo"], ["Air", "Atlântico", "Mundo", "Férias"]),
    "Hotels": (["Hotel", "Pousada", "Guest House"], ["Miramar", "Jardim", "do Castelo", "Bela Vista"]),
    "ATM cash": (["Multibanco", "ATM"], ["Rede", "Praça", "Estação", "Centro"]),
    "Electronics": (["Tecno", "Digital", "Volt"], ["Store", "Center", "Shop", "Hub"]),
    "Jewellery": (["Ourivesaria", "Joalharia"], ["Brilho", "Ouro Velho", "Safira", "Pérola"]),
    "Gift cards & vouchers": (["Vale", "Gift", "Cartão"], ["Presente", "Card Hub", "Codes", "Instant"]),
    "Crypto exchange": (["Coin", "Bloco", "Chain"], ["Trade", "Exchange", "Swap", "Vault"]),
}
FOREIGN_SUFFIX = {"ES": "ES", "FR": "FR", "GB": "UK", "IT": "IT", "DE": "DE", "NL": "NL",
                  "BR": "BR", "US": "US", "MA": "MA", "CN": "CN", "LT": "LT", "CY": "CY"}

# ---------------------------------------------------------------- helpers

def _season(month_index: int) -> float:
    """Spending multiplier per month, starting November 2025."""
    #        Nov  Dec  Jan  Feb  Mar  Apr  May  Jun  Jul  Aug  Sep  Oct
    return [1.00, 1.28, .86, .90, .97, 1.00, 1.02, 1.06, 1.12, 1.18, 1.00, 1.01][month_index]

def _month_start(i: int) -> datetime:
    y, m = START.year + (START.month - 1 + i) // 12, (START.month - 1 + i) % 12 + 1
    return datetime(y, m, 1)

def _month_days(i: int) -> int:
    return (_month_start(i + 1) - _month_start(i)).days

class Builder:
    def __init__(self, seed: int, customers: int):
        self.rng = np.random.default_rng(seed)
        self.n_customers = customers
        self.customers, self.cards, self.merchants = [], [], []
        self.txns: list[tuple] = []
        self.chargebacks: list[tuple] = []
        self.fraud_ids: set[int] = set()
        self._by_cat_city: dict = {}
        self._online_by_cat: dict = {}

    # -------------------------------------------------- merchants
    def _add_merchant(self, cat: Category, country: str, city: str, online: bool) -> int:
        rng = self.rng
        a, b = NAME_PARTS[cat.name]
        name = f"{rng.choice(a)} {rng.choice(b)}"
        if online:
            name += " Online" if country == "PT" else f" {FOREIGN_SUFFIX.get(country, country)}"
        elif country == "PT":
            name += f" {city}"
        else:
            name += f" {city}"
        mid = len(self.merchants) + 1
        self.merchants.append((mid, str(name), cat.mcc, cat.name, str(country), str(city), int(online), int(cat.high_risk)))
        return mid

    def build_merchants(self) -> None:
        for district, (city, w) in DISTRICTS.items():
            scale = max(1, round(w * 30))
            for cat in CATEGORIES:
                if cat.online >= 1.0:
                    continue
                n = max(1, round(scale * (cat.weight * 6 + .3))) if not cat.high_risk else 1
                self._by_cat_city[(cat.name, city)] = [self._add_merchant(cat, "PT", city, False) for _ in range(n)]
        for cat in CATEGORIES:
            if cat.online <= 0:
                continue
            ids = [self._add_merchant(cat, "PT", "Online", True) for _ in range(4)]
            ids += [self._add_merchant(cat, c, "Online", True) for c in ("ES", "GB", "NL")]
            self._online_by_cat[cat.name] = ids
        for country, cities in FOREIGN_CITIES.items():
            for city in cities:
                for cat in CATEGORIES:
                    if cat.online >= 1.0 or cat.high_risk and cat.name != "Electronics":
                        continue
                    self._by_cat_city[(cat.name, city)] = [self._add_merchant(cat, country, city, False) for _ in range(2)]
        # merchants that only show up in attacks: high-risk shops abroad
        self.fraud_online = {c: [self._add_merchant(CAT[n], c, "Online", True)
                                 for n in ("Electronics", "Gift cards & vouchers", "Crypto exchange")]
                             for c in ("CN", "LT", "CY", "US")}
        self.fraud_testing = [self._add_merchant(CAT["Gift cards & vouchers"], c, "Online", True)
                              for c in ("CN", "LT", "CY")]
        for city, country in (("Marraquexe", "MA"), ("São Paulo", "BR"), ("Nova Iorque", "US"), ("Londres", "GB")):
            self._by_cat_city.setdefault(("Jewellery", city), [self._add_merchant(CAT["Jewellery"], country, city, False)])
        self.city_country = {city: c for c, cities in FOREIGN_CITIES.items() for city in cities}
        self.city_country.update({city: "PT" for city, _ in DISTRICTS.values()})

    # -------------------------------------------------- customers and cards
    def build_customers(self) -> None:
        rng = self.rng
        districts = list(DISTRICTS)
        weights = np.array([DISTRICTS[d][1] for d in districts]); weights /= weights.sum()
        ages = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
        age_w = [.11, .20, .21, .19, .15, .14]
        for cid in range(1, self.n_customers + 1):
            age = rng.choice(ages, p=age_w)
            seg = "Student" if age == "18-24" and rng.random() < .6 else rng.choice(
                ["Everyday", "Premium", "Business"], p=[.74, .16, .10])
            joined = datetime(2012, 1, 1) + timedelta(days=int(rng.integers(0, 4900)))
            self.customers.append((cid, str(age), str(rng.choice(districts, p=weights)), str(seg), joined.date().isoformat()))
            issued = max(joined, datetime(2021, 1, 1)) + timedelta(days=int(rng.integers(0, 900)))
            issued = min(issued, START - timedelta(days=30))
            self.cards.append((len(self.cards) + 1, cid, "Debit", issued.date().isoformat(), None))
            p_credit = {"Premium": .85, "Business": .7, "Everyday": .35, "Student": .08}[seg]
            if rng.random() < p_credit:
                limit = float(rng.choice([1000, 1500, 2500, 5000, 7500] if seg != "Student" else [500]))
                self.cards.append((len(self.cards) + 1, cid, "Credit", issued.date().isoformat(), limit))

    # -------------------------------------------------- everyday spending
    def _ts(self, day: datetime, cat: Category) -> datetime:
        peak, spread = cat.hours
        hour = float(self.rng.normal(peak, spread))
        if not 6.5 <= hour < 23.9:                     # shops are shut: move it into opening hours
            hour = float(self.rng.uniform(7, 22))
        if cat.online >= 1.0 and self.rng.random() < .08:      # some legit late-night online shopping
            hour = float(self.rng.uniform(0, 5))
        return day + timedelta(hours=hour)

    def _amount(self, cat: Category, factor: float) -> float:
        return round(max(.5, float(self.rng.lognormal(np.log(cat.mean * factor), cat.sigma))), 2)

    def _channel(self, cat: Category, online: bool, t: datetime) -> str:
        if cat.name == "ATM cash":
            return "ATM"
        if online:
            return "Online"
        progress = (t - START).days / 365
        p_contactless = .52 + .20 * progress            # contactless keeps growing over the year
        return "Contactless" if self.rng.random() < p_contactless else "Chip & PIN"

    def build_spending(self) -> None:
        rng = self.rng
        cust = {c[0]: c for c in self.customers}
        cats = CATEGORIES
        base_w = np.array([c.weight for c in cats]); base_w /= base_w.sum()
        self.trips: dict[int, list] = {}
        for card in self.cards:
            card_id, cid, ctype = card[0], card[1], card[2]
            _, age, district, seg, _ = cust[cid]
            home = DISTRICTS[district][0]
            rate = {"Debit": 19, "Credit": 7}[ctype] * {"Premium": 1.3, "Business": 1.15, "Everyday": 1.0, "Student": .75}[seg]
            rate *= float(rng.lognormal(0, .35))
            spend = {"Premium": 1.7, "Business": 1.35, "Everyday": 1.0, "Student": .6}[seg] * (1.25 if ctype == "Credit" else 1)
            w = base_w.copy()
            if ctype == "Credit":                          # credit cards skew to bigger, online purchases
                for i, c in enumerate(cats):
                    if c.name in ("Cafés & bakeries", "Transport", "ATM cash"):
                        w[i] *= .25
                    if c.name in ("Travel & airlines", "Hotels", "Online marketplace", "Electronics", "Clothing"):
                        w[i] *= 2.2
                w /= w.sum()
            if age in ("55-64", "65+"):
                w = w * np.array([1.6 if c.name in ("Pharmacy", "Groceries") else .7 if c.online >= 1 else 1 for c in cats])
                w /= w.sum()
            trips = self.trips.setdefault(cid, []) if ctype == "Debit" else self.trips.get(cid, [])
            if ctype == "Debit" and rng.random() < {"Premium": .7, "Business": .6, "Everyday": .32, "Student": .25}[seg]:
                for _ in range(int(rng.integers(1, 3))):
                    country = rng.choice(list(TRAVEL_WEIGHTS), p=list(TRAVEL_WEIGHTS.values()))
                    start = START + timedelta(days=int(rng.integers(10, 350)))
                    trips.append((start, start + timedelta(days=int(rng.integers(3, 9))), country,
                                  rng.choice(FOREIGN_CITIES[country])))
            for m in range(MONTHS):
                m0, days = _month_start(m), _month_days(m)
                n = rng.poisson(rate * _season(m))
                for _ in range(n):
                    day = m0 + timedelta(days=int(rng.integers(0, days)))
                    if day.weekday() >= 5 and rng.random() < .15:
                        continue
                    cat = cats[rng.choice(len(cats), p=w)]
                    t = self._ts(day, cat)
                    trip = next((tr for tr in trips if tr[0] <= t < tr[1]), None)
                    online = rng.random() < cat.online
                    if trip and not online:
                        city, country = trip[3], trip[2]
                        key = (cat.name, city)
                        if key not in self._by_cat_city:
                            continue
                        merchant = int(rng.choice(self._by_cat_city[key]))
                        amount = self._amount(cat, spend * (1.3 if country in ("GB", "US", "NL") else 1))
                        self._add_txn(card_id, merchant, t, amount, self._channel(cat, False, t), country)
                        continue
                    if online:
                        pool = self._online_by_cat[cat.name]
                        merchant = int(rng.choice(pool[:4] if rng.random() < .82 else pool[4:]))
                        country = self.merchants[merchant - 1][4]
                    else:
                        merchant = int(rng.choice(self._by_cat_city[(cat.name, home)]))
                        country = "PT"
                    self._add_txn(card_id, merchant, t, self._amount(cat, spend), self._channel(cat, online, t), country)
            if ctype == "Debit":                           # bookings and airport spending for each trip
                for start, end, country, city in trips:
                    book = start - timedelta(days=int(rng.integers(7, 60)))
                    self._add_txn(card_id, int(rng.choice(self._online_by_cat["Travel & airlines"])),
                                  book + timedelta(hours=float(rng.uniform(19, 23))),
                                  self._amount(CAT["Travel & airlines"], spend * 1.4), "Online", "PT")
                    if rng.random() < .7:
                        self._add_txn(card_id, int(rng.choice(self._online_by_cat["Hotels"])),
                                      book + timedelta(hours=float(rng.uniform(19, 23)), days=int(rng.integers(0, 3))),
                                      self._amount(CAT["Hotels"], spend * 2.5), "Online", "ES")
                    dep = start + timedelta(hours=float(rng.uniform(6, 9)))          # coffee at the home airport
                    self._add_txn(card_id, int(rng.choice(self._by_cat_city[("Cafés & bakeries", home)])),
                                  dep, self._amount(CAT["Cafés & bakeries"], 1.6), "Contactless", "PT")
                    flight = {"ES": 1.3, "FR": 2.3, "GB": 2.6, "IT": 3.0, "DE": 3.2, "NL": 2.7,
                              "BR": 10, "US": 8, "MA": 1.5}[country]
                    arr = dep + timedelta(hours=flight + float(rng.uniform(.4, 2.5)))
                    self._add_txn(card_id, int(rng.choice(self._by_cat_city[("Restaurants", city)])),
                                  arr, self._amount(CAT["Restaurants"], spend * 1.2), "Contactless", country)

    def _add_txn(self, card_id, merchant, t, amount, channel, country, status=None, fraud=False) -> int:
        tid = len(self.txns) + 1
        card_id, merchant, amount, country = int(card_id), int(merchant), float(amount), str(country)
        if status is None:
            card = self.cards[card_id - 1]
            status = "Declined" if self.rng.random() < .012 else "Approved"
            if card[4] and amount > card[4] * .5 and self.rng.random() < .5:
                status = "Declined"
        self.txns.append([tid, card_id, merchant, t, amount, channel, country, status])
        if fraud:
            self.fraud_ids.add(tid)
        return tid

    # -------------------------------------------------- fraud
    def inject_fraud(self, share: float = .03) -> None:
        rng = self.rng
        n_cards = len(self.cards)
        victims = rng.choice(np.arange(1, n_cards + 1), size=int(n_cards * share), replace=False)
        cust = {c[0]: c for c in self.customers}
        for card_id in victims:
            card = self.cards[card_id - 1]
            home = DISTRICTS[cust[card[1]][2]][0]
            day = START + timedelta(days=int(rng.integers(20, 360)))
            kind = rng.choice(["testing", "cloned", "takeover"], p=[.36, .26, .38])
            if card[2] == "Debit" and kind == "testing" and rng.random() < .5:
                kind = "cloned"
            if kind == "testing":
                t = day + timedelta(hours=float(rng.uniform(0, 24)))
                tester = int(rng.choice(self.fraud_testing))
                for _ in range(int(rng.integers(4, 12))):
                    t += timedelta(seconds=float(rng.uniform(20, 110)))
                    status = "Declined" if rng.random() < .3 else "Approved"
                    self._add_txn(card_id, tester, t, round(float(rng.uniform(.5, 2.5)), 2), "Online",
                                  self.merchants[tester - 1][4], status, fraud=True)
                t += timedelta(minutes=float(rng.uniform(15, 80)))
                country = rng.choice(list(self.fraud_online))
                for _ in range(int(rng.integers(1, 4))):
                    t += timedelta(minutes=float(rng.uniform(2, 20)))
                    m = int(rng.choice(self.fraud_online[country]))
                    self._add_txn(card_id, m, t, round(float(rng.uniform(250, 1400)), 2), "Online", country,
                                  "Declined" if rng.random() < .15 else "Approved", fraud=True)
            elif kind == "cloned":
                city = rng.choice(["Marraquexe", "São Paulo", "Nova Iorque", "Londres", "Madrid", "Paris"])
                country = self.city_country[city]
                # the real customer is still shopping at home that day
                t_home = day + timedelta(hours=float(rng.uniform(8, 12)))
                self._add_txn(card_id, int(rng.choice(self._by_cat_city[("Groceries", home)])), t_home,
                              self._amount(CAT["Groceries"], 1), "Contactless", "PT")
                t = t_home + timedelta(hours=float(rng.uniform(.5, 4)))
                for _ in range(int(rng.integers(2, 6))):
                    t += timedelta(minutes=float(rng.uniform(5, 50)))
                    if rng.random() < .6:
                        m, amt, ch = int(rng.choice(self._by_cat_city[("ATM cash", city)])), float(rng.choice([200, 300, 400])), "ATM"
                    else:
                        cat = rng.choice(["Electronics", "Jewellery"])
                        key = (cat, city) if (cat, city) in self._by_cat_city else ("Electronics", city)
                        m, amt, ch = int(rng.choice(self._by_cat_city[key])), round(float(rng.uniform(300, 1600)), 2), "Chip & PIN"
                    self._add_txn(card_id, m, t, amt, ch, country,
                                  "Declined" if rng.random() < .2 else "Approved", fraud=True)
                # ...and keeps using the real card at home a few hours later
                for _ in range(int(rng.integers(1, 3))):
                    t_back = t_home + timedelta(hours=float(rng.uniform(2, 9)))
                    cat = CAT[rng.choice(["Groceries", "Restaurants", "Cafés & bakeries", "Fuel"])]
                    self._add_txn(card_id, int(rng.choice(self._by_cat_city[(cat.name, home)])), t_back,
                                  self._amount(cat, 1), "Contactless", "PT")
            else:  # takeover
                t = day + timedelta(hours=float(rng.uniform(0, 4.5)))
                country = rng.choice(list(self.fraud_online))
                for _ in range(int(rng.integers(2, 7))):
                    t += timedelta(minutes=float(rng.uniform(3, 35)))
                    m = int(rng.choice(self.fraud_online[country] + self._online_by_cat["Electronics"]))
                    self._add_txn(card_id, m, t, round(float(rng.uniform(180, 1500)), 2), "Online",
                                  self.merchants[m - 1][4], "Declined" if rng.random() < .18 else "Approved",
                                  fraud=True)

    # -------------------------------------------------- finish
    def finalise(self) -> None:
        """Sort by time, renumber, and add chargebacks."""
        rng = self.rng
        order = sorted(range(len(self.txns)), key=lambda i: (self.txns[i][3], self.txns[i][1]))
        new_id = {self.txns[i][0]: n + 1 for n, i in enumerate(order)}
        end = _month_start(MONTHS)
        rows = []
        for i in order:
            r = self.txns[i]
            if r[3] >= end or r[3] < START:
                continue
            rows.append((new_id[r[0]], r[1], r[2], r[3].strftime("%Y-%m-%d %H:%M:%S"), r[4], r[5], r[6], r[7]))
        kept = {r[0] for r in rows}
        self.fraud_ids = {new_id[t] for t in self.fraud_ids if new_id[t] in kept}
        status = {r[0]: r[7] for r in rows}
        ts = {r[0]: r[3] for r in rows}
        for tid in sorted(self.fraud_ids):
            if status[tid] == "Approved":
                reported = datetime.fromisoformat(ts[tid]) + timedelta(days=int(rng.integers(1, 25)))
                self.chargebacks.append((tid, reported.date().isoformat(), "fraud"))
        legit = [r[0] for r in rows if r[0] not in self.fraud_ids and r[7] == "Approved" and r[4] > 15]
        for tid in rng.choice(legit, size=max(1, len(legit) // 2500), replace=False):
            reported = datetime.fromisoformat(ts[int(tid)]) + timedelta(days=int(rng.integers(5, 45)))
            self.chargebacks.append((int(tid), reported.date().isoformat(), "dispute"))
        self.chargebacks.sort()
        self.rows = rows


def build(db_path: Path = DB_PATH, seed: int = 7, customers: int = 1500) -> Path:
    b = Builder(seed, customers)
    b.build_merchants()
    b.build_customers()
    b.build_spending()
    b.inject_fraud()
    b.finalise()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", b.customers)
    con.executemany("INSERT INTO cards VALUES (?,?,?,?,?)", b.cards)
    con.executemany("INSERT INTO merchants VALUES (?,?,?,?,?,?,?,?)", b.merchants)
    con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)", b.rows)
    con.executemany("INSERT INTO chargebacks VALUES (?,?,?)", b.chargebacks)
    con.commit()
    con.execute("ANALYZE")
    con.close()
    return db_path


def main() -> None:
    p = argparse.ArgumentParser(description="Generate the Ledger SQLite database")
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--customers", type=int, default=1500)
    a = p.parse_args()
    path = build(a.db, a.seed, a.customers)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
