# Opt-in relay — proof of concept

## What this is

The logic that sits between a WooCommerce opt-in form and an external ESP.
Roughly 200 lines of Python, standard library only.

## What it is not

It is **not** wired to your store, your ESP, or any account of yours, and it
does not prove an integration. It runs entirely on synthetic data and a fake
ESP. It shows how I would handle the part of this job that isn't the form.

## The problem it addresses

"Route submissions straight to the external ESP endpoint" has a literal
reading — a `fetch()` from the browser to the ESP — that costs you two things
you can't get back:

1. **The API key ends up in page source.** Anyone who views source has it.
2. **Every lead depends on the ESP answering right now.** When the ESP is
   rate-limiting or down, the visitor sees a spinner and the address is gone.
   There is no record it ever existed, so you never find out.

The relay holds the key server-side and guarantees a submission ends up in
exactly one of four states, all of them visible:

| State | When |
|---|---|
| **delivered** | ESP accepted it |
| **queued** | ESP was rate-limited, down, or unreachable — retried with backoff |
| **parked** | ESP understood and refused (e.g. 422), or retries were exhausted — kept with the reason |
| **dropped** | honeypot, malformed address, or a duplicate inside 24h — counted, never silent |

## Run it

No install, no accounts, no keys.

```
python demo.py        # the scenario, including a flaky ESP
python test_demo.py   # 15 tests
```

`demo.py` walks seven submissions through an ESP that returns 500, 429, 200,
422, then recovers, and shows where each address lands.

## What the tests cover

One test per behaviour you would recognise on your own site:

- `Ada@Example.com ` and `ada@example.com` are one subscriber, billed once
- the same person *can* opt in again after 24 hours
- a honeypot submission never reaches the ESP
- `not-an-email` never burns an ESP call or quota
- a 429 or 500 keeps the lead and retries it; the visitor never waits
- a 422 is parked with its reason rather than retried forever
- backoff grows between attempts
- a permanently failing address stops after a bounded number of tries and is
  still readable afterwards
- the ESP key is read from an environment variable by name, and there is no
  credential anywhere in the source

## Note on credentials

`esp_key()` reads the key from the environment at call time. There is no
default, nothing is written to disk, and nothing the browser receives contains
it. A test asserts the source carries no credential.
