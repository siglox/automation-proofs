# Bot → human handoff — state machine proof of concept

"Make the bot stop talking when a human answers" sounds like one boolean
flag. It isn't, and the questions a brief never asks are exactly the ones
that break in production:

- **When does the bot start answering again?**
- **What happens if the human goes idle and never closes the conversation?**
- **What stops the bot from replying while a human already owns the chat?**

This is a proof of concept for the state machine underneath a handoff,
not a chatbot. It runs on synthetic events — there is no bot, no agent UI
and no messaging platform behind it.

This is a personal project, not client work.

## The four states

```
BOT ──request_human──▶ ESCALATED ──human_claim──▶ WITH_HUMAN ──human_close──▶ CLOSED
 ▲                                                     │  ▲                      │
 └─────────────────── (grace window passed) ───────────┘  └── idle timeout ──────┘
                       reopen: customer message                 with an
                                after CLOSED                  unanswered
                                                              message left
```

- **BOT** — the bot answers.
- **ESCALATED** — a human has been asked for; nobody has claimed it yet.
- **WITH_HUMAN** — one specific human owns it; the bot stays silent, no
  matter how long that human takes to reply.
- **CLOSED** — the human ended it. What happens next depends on *when* the
  customer writes again, not just *whether* they do.

## The four guards that actually matter

1. **A second claim is a no-op, not a takeover.** Two agents clicking
   "claim" on the same conversation is a real race in any multi-agent
   support tool. The second one does nothing; it does not steal the
   conversation from the first.
2. **The bot never answers once a human owns the conversation** — even if
   the human is silent for a while. A new customer message while
   `WITH_HUMAN` is queued, never routed back to the bot.
3. **An idle human with an unanswered message re-escalates automatically**,
   and this is logged as a *different* event from the first escalation —
   "nobody picked this up" and "somebody picked it up and went dark" are
   different failures with different fixes, and a business needs to be
   able to tell them apart.
4. **A human cannot close a conversation with an unanswered message
   pending.** Closing is a claim that nothing is waiting; the code enforces
   that claim instead of trusting it.

## Try it

```bash
python3 test_demo.py
```

```
..................
----------------------------------------------------------------------
Ran 18 tests in 0.001s

OK
```

Eighteen tests, one per behaviour above and its edge case — including the
one a client will actually ask about: *"what if the agent just leaves?"*

## What this is not

No bot, no messaging platform, no agent dashboard. The synthetic clock
(`at=`, a plain integer) stands in for real timestamps so the idle-timeout
and reopen-window tests are deterministic. Wiring this to a real inbox is
a different, much bigger project — this is the logic that would sit
underneath it, proven against the failure cases that matter, not the
happy path.
