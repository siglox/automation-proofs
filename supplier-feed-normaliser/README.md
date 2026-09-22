# Multi-supplier feed normaliser — proof of concept

**What this is.** A small, runnable piece of the job you posted: taking five
dropshipping suppliers that each ship their catalogue in a different shape, and
turning them into one safe write into WooCommerce.

**What it is not.** It is not connected to your store or to any supplier, and it
does not prove an integration works — I have no credentials and would not ask for
them before a contract. Everything below runs on synthetic supplier records.

## Run it

```
python3 test_supplier_sync.py
```

No dependencies, no accounts, no keys. Standard library only. About a second.

```
Ran 8 tests in 0.003s

OK
```

## The part I think is actually hard here

Connecting to a supplier is plumbing. The part that costs money is that **each
supplier has a different idea of what "in stock" means and a different rate at
which its numbers go stale** — so the expensive failure is not an error, it is an
old number written into WooCommerce and a customer buying something nobody has.

The four behaviours the tests cover:

| Test group | What it shows |
|---|---|
| `TestShapes` | Counts (`7`), words (`"low"`) and booleans (`true`) all become one number. `1.234,56` and `1,234.56` are the same price, and confusing them is a 1000× pricing error. |
| `TestStaleness` | Each supplier has its own `max_age`. The same 8-hour-old record is fine from one supplier and refused from another. If a supplier's whole feed is unusable, its stock is **left untouched** and the run says so rather than looking healthy. |
| `TestRejectionsAreNamed` | Every refused record is reported with its SKU and reason. A silent skip is how a shop quietly stops selling half its catalogue. |
| `TestSameSkuFromTwoSuppliers` | Five suppliers overlap. Freshest wins, ties go to the cheaper one, and the loser is logged — because a SKU that keeps flipping supplier is usually a mapping mistake, not competition. |

## Why it is shaped this way

Each supplier is a `SupplierConfig`: where its fields live, what its stock words
mean, its currency, its timestamp format, how long its data stays trustworthy,
and the markup. Supplier six is a dict, not another integration.

The actual write sits behind a `write` callback, so the same logic runs against
the tests here and against the WooCommerce REST API in production without the
normalisation code knowing the difference.

## What the real version would add

- The supplier clients themselves (REST, CSV-over-FTP, whatever each one offers).
- A rejection report delivered somewhere you read — email or Slack — every morning.
- Live FX rates instead of the fixed table used here.
- Idempotent writes keyed on SKU so a retry cannot double-apply anything.
