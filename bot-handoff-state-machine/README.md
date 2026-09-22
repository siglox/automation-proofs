# Bot → human handoff — state machine proof of concept

"Make the bot stop talking when a human answers" sounds like one boolean
flag. It isn't, and the questions a brief never asks are exactly the ones
that break in production:

- **When does the bot start answering again?**
- **What happens if the human goes idle and never closes the conversation?**
- **What stops the bot from replying while a human already owns the chat?**

This is a proof of concept for the state machine underneath a handoff,
not a chatbot. The tested core (`demo.py`, `test_demo.py`) runs on
synthetic events — there is no messaging platform and no agent UI behind
it. `chat.py` adds a terminal you can type into yourself, with a
deliberately trivial keyword-based bot brain, so the rules below aren't
just something you read about — you can trigger every one of them from
your own keyboard.

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

## Talk to it yourself

```bash
python3 chat.py
```

You play both sides: type as the customer, `/agent alice` to switch and
answer as a human, `/tick 20` to fast-forward the clock instead of waiting
15 real minutes for the idle timeout. This is a real transcript, not a
mockup:

```
[t=0] customer> what are your hours?
bot: We're open Monday to Friday, 9am to 6pm.

[t=1] customer> I need to talk to a human about a refund
bot: Let me get you a human for that — one moment.

[t=2] customer> /agent alice
(you are now speaking as agent 'alice')

[t=3] alice> /claim
claimed it.

[t=4] alice> Hi, I can help with your refund - what's the order number?
(alice replied - sent to the customer)

[t=6] customer> #4471, it never arrived
(queued - a human will see this, the bot stays quiet)

[t=8] alice> /tick 20
20 minutes pass with no reply...
  [!] the conversation went idle and re-escalated (a customer message was left unanswered)

[t=29] alice> /state
state=ESCALATED  assigned_to=None  unanswered_since=7
```

Alice went quiet on an actual customer message, so the conversation
re-escalated and she lost ownership of it — the guard worked as designed.
She has to `/claim` it again before she can reply or close it; typing
either without reclaiming first is refused with the actual reason, not a
generic error. That's the guard from point 3 above, live, not described.

`chat.py` is a thin REPL around the `Conversation` class the 18 tests
already cover — it isn't itself part of that suite, and doesn't need to be:
every rule it demonstrates is one the tests already proved.

## What this is not

No bot, no messaging platform, no agent dashboard. The synthetic clock
(`at=`, a plain integer) stands in for real timestamps so the idle-timeout
and reopen-window tests are deterministic. Wiring this to a real inbox is
a different, much bigger project — this is the logic that would sit
underneath it, proven against the failure cases that matter, not the
happy path.
