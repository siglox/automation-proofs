"""Run with:  python3 test_supplier_sync.py

No dependencies, no accounts, no keys. Every test is a behaviour a shop owner
would recognise, written against synthetic supplier data.
"""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from supplier_sync import (Product, SupplierConfig, merge, normalise, sync)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
RATES = {"EUR": Decimal("1.00"), "DKK": Decimal("0.134"), "USD": Decimal("0.92")}


def hours_ago(n):
    return (NOW - timedelta(hours=n)).isoformat()


# Five suppliers, five different shapes. This is the whole point.
VIDAXL = SupplierConfig(
    name="vidaxl", sku_field="sku", price_field="price", stock_field="qty",
    updated_field="updated_at", currency="EUR", max_age=timedelta(hours=24),
    markup=Decimal("1.35"))

NORDIC = SupplierConfig(
    name="nordic", sku_field="ItemNo", price_field="ListPrice",
    stock_field="Availability", updated_field="LastSync", currency="DKK",
    stock_map={"in stock": 50, "low": 3, "out of stock": 0, "discontinued": 0},
    max_age=timedelta(hours=12), time_format="%d-%m-%Y %H:%M",
    markup=Decimal("1.40"))

FLATFEED = SupplierConfig(
    name="flatfeed", sku_field="id", price_field="cost", stock_field="available",
    updated_field="ts", currency="USD", max_age=timedelta(hours=6),
    markup=Decimal("1.50"))


class TestShapes(unittest.TestCase):
    """Every supplier speaks a different dialect; the store sees one."""

    def test_counts_words_and_booleans_all_become_a_number(self):
        feeds = {
            "vidaxl": [{"sku": "A-1", "price": "10.00", "qty": 7,
                        "updated_at": hours_ago(1)}],
            "nordic": [{"ItemNo": "B-1", "ListPrice": "149,50",
                        "Availability": "low",
                        "LastSync": (NOW - timedelta(hours=1)).strftime("%d-%m-%Y %H:%M")}],
            "flatfeed": [{"id": "C-1", "cost": "1,234.56", "available": True,
                          "ts": hours_ago(1)}],
        }
        written = {}
        count, log = sync(feeds, {"vidaxl": VIDAXL, "nordic": NORDIC,
                                  "flatfeed": FLATFEED},
                          RATES, NOW, lambda p: written.__setitem__(p.sku, p))

        self.assertEqual(count, 3)
        self.assertEqual(written["A-1"].stock, 7)
        self.assertEqual(written["B-1"].stock, 3)      # "low" -> 3
        self.assertEqual(written["C-1"].stock, 999)    # True -> treat as plenty
        self.assertEqual(log, [])

    def test_european_and_anglo_decimal_separators_do_not_collide(self):
        # "1.234,56" is one thousand two hundred; "1,234.56" is the same number
        # written the other way. Getting this wrong is a 1000x pricing error.
        anglo, _ = normalise(
            [{"id": "C-1", "cost": "1,234.56", "available": 1, "ts": hours_ago(1)}],
            FLATFEED, RATES, NOW)
        euro, _ = normalise(
            [{"ItemNo": "B-1", "ListPrice": "1.234,56", "Availability": "in stock",
              "LastSync": (NOW - timedelta(hours=1)).strftime("%d-%m-%Y %H:%M")}],
            NORDIC, RATES, NOW)

        # 1234.56 USD * 0.92 * 1.50 markup
        self.assertEqual(anglo[0].price_eur, Decimal("1703.70"))
        # 1234.56 DKK -> 165.43 EUR, then * 1.40 markup
        self.assertEqual(euro[0].price_eur, Decimal("231.60"))


class TestStaleness(unittest.TestCase):
    """The expensive failure is not an error, it is an old number written anyway."""

    def test_a_record_older_than_its_supplier_allows_is_refused(self):
        # Same age, two suppliers, different tolerance: 8 hours is fine for
        # vidaxl (24h) and too old for flatfeed (6h).
        kept_v, rej_v = normalise(
            [{"sku": "A-1", "price": "10.00", "qty": 5, "updated_at": hours_ago(8)}],
            VIDAXL, RATES, NOW)
        kept_f, rej_f = normalise(
            [{"id": "C-1", "cost": "10.00", "available": 5, "ts": hours_ago(8)}],
            FLATFEED, RATES, NOW)

        self.assertEqual(len(kept_v), 1)
        self.assertEqual(rej_v, [])
        self.assertEqual(kept_f, [])
        self.assertIn("stale by", rej_f[0].reason)

    def test_a_dead_feed_leaves_stock_untouched_and_says_so(self):
        # If a supplier's whole feed is unusable, the run must not look healthy
        # just because the other suppliers worked.
        feeds = {
            "vidaxl": [{"sku": "A-1", "price": "10.00", "qty": 5,
                        "updated_at": hours_ago(1)}],
            "flatfeed": [{"id": "C-1", "cost": "10.00", "available": 5,
                          "ts": hours_ago(48)}],
        }
        written = []
        count, log = sync(feeds, {"vidaxl": VIDAXL, "flatfeed": FLATFEED},
                          RATES, NOW, written.append)

        self.assertEqual(count, 1)
        self.assertEqual(written[0].sku, "A-1")
        reasons = [r.reason for r in log if r.supplier == "flatfeed"]
        self.assertTrue(any("whole feed rejected" in r for r in reasons))
        self.assertTrue(any("stock left untouched" in r for r in reasons))


class TestRejectionsAreNamed(unittest.TestCase):
    """A silent skip is how a shop quietly stops selling half its catalogue."""

    def test_every_refused_record_is_reported_with_its_sku_and_reason(self):
        records = [
            {"sku": "A-1", "price": "10.00", "qty": 5, "updated_at": hours_ago(1)},
            {"sku": "A-2", "price": "0.00", "qty": 5, "updated_at": hours_ago(1)},
            {"sku": "A-3", "price": "ask us", "qty": 5, "updated_at": hours_ago(1)},
            {"sku": "A-4", "price": "10.00", "updated_at": hours_ago(1)},
            {"price": "10.00", "qty": 5, "updated_at": hours_ago(1)},
        ]
        kept, rejected = normalise(records, VIDAXL, RATES, NOW)

        self.assertEqual([p.sku for p in kept], ["A-1"])
        self.assertEqual(
            [(r.sku, r.reason.split()[0]) for r in rejected],
            [("A-2", "non-positive"), ("A-3", "unreadable"),
             ("A-4", "missing"), ("<missing>", "record")])


class TestSameSkuFromTwoSuppliers(unittest.TestCase):
    """Five suppliers overlap. Somebody has to win, and it has to be explainable."""

    def _p(self, supplier, price, hours, sku="A-1"):
        return Product(sku=sku, supplier=supplier, price_eur=Decimal(price),
                       stock=5, updated_at=NOW - timedelta(hours=hours))

    def test_freshest_record_wins(self):
        winners, notes = merge([self._p("nordic", "30.00", 6),
                                self._p("vidaxl", "50.00", 1)])
        self.assertEqual(winners["A-1"].supplier, "vidaxl")
        self.assertEqual(notes[0].supplier, "nordic")
        self.assertIn("superseded by vidaxl", notes[0].reason)

    def test_equally_fresh_means_the_cheaper_one_wins(self):
        winners, _ = merge([self._p("nordic", "30.00", 1),
                            self._p("vidaxl", "50.00", 1)])
        self.assertEqual(winners["A-1"].supplier, "nordic")

    def test_the_overlap_is_logged_so_a_bad_mapping_is_visible(self):
        _, notes = merge([self._p("nordic", "30.00", 2),
                          self._p("vidaxl", "50.00", 1),
                          self._p("flatfeed", "40.00", 9, sku="B-9")])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].sku, "A-1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
