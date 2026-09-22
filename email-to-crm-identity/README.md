# Outbound email → HubSpot contact: matching and idempotent logging

A small proof of concept for the part of your posting I think is actually hard.

## What this is

Your posting describes a symptom: emails and notifications triggered through n8n
are not consistently visible on the corresponding HubSpot contact record. In my
experience that is rarely a send problem. It is one of three association
problems, and this models all three:

1. **The lookup returns more than one contact.** A portal that has been running
   for a while has duplicates — the same address imported twice with different
   casing, for example. Most code takes the first hit. The activity then lands
   on a real contact, just not the right one, which is the hardest version of
   this bug to notice.
2. **The lookup returns nothing.** The write gets dropped and no one finds out.
3. **A retry re-sends the same engagement.** The engagement is stored twice, and
   the contact timeline now shows a follow-up that never happened.

The code resolves the contact by ordered rules, refuses to guess when a rule
returns several candidates, parks anything it cannot resolve in a review queue
instead of dropping it, and derives an idempotency key from the provider's
message id so a retry is a no-op rather than a duplicate.

## What this is NOT

It runs on synthetic data in `data/`. It is **not** connected to your portal, it
does not call the HubSpot API, and it does not prove the integration works
against your environment — only the logic. Any real fix would start by reading
what your n8n workflows actually send and how your portal is shaped.

## Run it

```
python demo.py                       # walk six outbound emails through the logic
python -m unittest test_demo -v      # 14 tests, one per behaviour
```

No install, no accounts, no credentials. Python 3.10+, standard library only.

## What the six sample emails show

| Message | What happens | Why it matters |
|---|---|---|
| `msg-0001` | created | the normal path |
| `msg-0002` | created | secondary address, different casing, trailing space — same contact |
| `msg-0003` | **queued_ambiguous** | two contacts share this address; first-match-wins would have been silently wrong |
| `msg-0001` again | **duplicate_ignored** | a retry of an already-logged send |
| `msg-0004` | created | `priya+billing@` is the same human as `priya@` |
| `msg-0005` | **queued_unknown** | no contact found — parked for review, not dropped |
