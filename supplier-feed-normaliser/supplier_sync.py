"""Normalise differently-shaped supplier feeds into one WooCommerce write.

Proof of concept for the hard part of multi-supplier dropshipping: every
supplier ships its catalogue in its own shape, with its own idea of what
"in stock" means and how often it refreshes. The risk is not a failed HTTP
call — it is writing a stale number into WooCommerce and selling something
nobody has.

Runs on synthetic data. Not wired to any real supplier or store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable


# --------------------------------------------------------------------------
# One config per supplier. Adding supplier six is a dict, not a new integration.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SupplierConfig:
    name: str
    # Where each canonical field lives in this supplier's record.
    sku_field: str
    price_field: str
    stock_field: str
    updated_field: str
    # How the supplier expresses availability, when it is not a plain number.
    stock_map: dict[str, int] = field(default_factory=dict)
    # Currency the price arrives in.
    currency: str = "EUR"
    # How long a record from this supplier stays trustworthy.
    max_age: timedelta = timedelta(hours=24)
    # Supplier-specific timestamp format; None means ISO-8601.
    time_format: str | None = None
    # Markup applied to the supplier price to get the shop price.
    markup: Decimal = Decimal("1.0")


@dataclass(frozen=True)
class Product:
    """What WooCommerce is asked to store. One shape, whatever the source."""
    sku: str
    supplier: str
    price_eur: Decimal
    stock: int
    updated_at: datetime


@dataclass(frozen=True)
class Rejection:
    """A record that must not reach the store, and why."""
    supplier: str
    sku: str
    reason: str


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

class StaleFeed(Exception):
    """The whole feed is older than the supplier is allowed to be."""


def _parse_time(raw: Any, fmt: str | None) -> datetime:
    if isinstance(raw, datetime):
        dt = raw
    elif fmt is None:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    else:
        dt = datetime.strptime(str(raw), fmt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_stock(raw: Any, stock_map: dict[str, int]) -> int:
    """Suppliers express stock as a count, a word, or a yes/no flag."""
    if isinstance(raw, bool):
        return 999 if raw else 0
    if isinstance(raw, int):
        return max(raw, 0)
    key = str(raw).strip().lower()
    if key in stock_map:
        return stock_map[key]
    try:
        return max(int(float(key)), 0)
    except ValueError as exc:
        raise ValueError(f"unreadable stock value {raw!r}") from exc


def _parse_price(raw: Any, currency: str, rates: dict[str, Decimal]) -> Decimal:
    text = str(raw).strip().replace("€", "").replace("$", "")
    # "1.234,56" (European) vs "1,234.56" (Anglo). Decide by which comes last.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"unreadable price {raw!r}") from exc
    if amount <= 0:
        raise ValueError(f"non-positive price {raw!r}")
    if currency not in rates:
        raise ValueError(f"no rate for currency {currency!r}")
    return (amount * rates[currency]).quantize(Decimal("0.01"))


def normalise(
    records: list[dict[str, Any]],
    config: SupplierConfig,
    rates: dict[str, Decimal],
    now: datetime,
) -> tuple[list[Product], list[Rejection]]:
    """Turn one supplier's records into the canonical shape.

    A record that cannot be read, or that is older than this supplier's
    max_age, is rejected by name rather than skipped silently. That list is
    the thing the shop owner actually needs to see every morning.
    """
    kept: list[Product] = []
    rejected: list[Rejection] = []

    for record in records:
        sku = str(record.get(config.sku_field, "")).strip()
        if not sku:
            rejected.append(Rejection(config.name, "<missing>", "record has no SKU"))
            continue
        try:
            updated_at = _parse_time(record[config.updated_field], config.time_format)
            stock = _parse_stock(record[config.stock_field], config.stock_map)
            price = _parse_price(record[config.price_field], config.currency, rates)
        except KeyError as exc:
            rejected.append(Rejection(config.name, sku, f"missing field {exc.args[0]}"))
            continue
        except ValueError as exc:
            rejected.append(Rejection(config.name, sku, str(exc)))
            continue

        age = now - updated_at
        if age > config.max_age:
            rejected.append(Rejection(
                config.name, sku,
                f"stale by {age - config.max_age} (feed timestamp {updated_at:%Y-%m-%d %H:%M})"))
            continue

        kept.append(Product(
            sku=sku,
            supplier=config.name,
            price_eur=(price * config.markup).quantize(Decimal("0.01")),
            stock=stock,
            updated_at=updated_at,
        ))

    return kept, rejected


# --------------------------------------------------------------------------
# Merging: the same SKU can arrive from more than one supplier
# --------------------------------------------------------------------------

def merge(products: list[Product]) -> tuple[dict[str, Product], list[Rejection]]:
    """Pick one winner per SKU.

    Freshest record wins; a tie goes to the cheaper one. The loser is reported,
    not dropped, because a SKU that keeps flipping between suppliers is usually
    a mapping mistake rather than real competition.
    """
    winners: dict[str, Product] = {}
    notes: list[Rejection] = []

    for product in products:
        current = winners.get(product.sku)
        if current is None:
            winners[product.sku] = product
            continue
        better = (
            product.updated_at > current.updated_at
            or (product.updated_at == current.updated_at
                and product.price_eur < current.price_eur)
        )
        winner, loser = (product, current) if better else (current, product)
        winners[product.sku] = winner
        notes.append(Rejection(
            loser.supplier, loser.sku,
            f"superseded by {winner.supplier} (same SKU from two suppliers)"))

    return winners, notes


# --------------------------------------------------------------------------
# The write itself, behind a seam so the demo never needs a real store
# --------------------------------------------------------------------------

def sync(
    feeds: dict[str, list[dict[str, Any]]],
    configs: dict[str, SupplierConfig],
    rates: dict[str, Decimal],
    now: datetime,
    write: Callable[[Product], None],
) -> tuple[int, list[Rejection]]:
    """Run every supplier, then write the survivors once. Returns (written, log)."""
    all_products: list[Product] = []
    log: list[Rejection] = []

    for name, records in feeds.items():
        config = configs[name]
        kept, rejected = normalise(records, config, rates, now)
        log.extend(rejected)
        if not kept and records:
            # Every record from this supplier was unusable. Do not let the
            # other suppliers' data make the run look healthy.
            log.append(Rejection(name, "*", "whole feed rejected; stock left untouched"))
        all_products.extend(kept)

    winners, notes = merge(all_products)
    log.extend(notes)

    for product in sorted(winners.values(), key=lambda p: p.sku):
        write(product)

    return len(winners), log
