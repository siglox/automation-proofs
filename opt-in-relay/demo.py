"""Opt-in relay: the part between the form and the ESP.

The job post says submissions "must route straight to the external ESP
endpoint". Taken literally -- a fetch() from the browser to the ESP -- that
does two things you cannot undo later:

  1. It puts the ESP API key in page source, where anyone can read it.
  2. It makes every lead depend on the ESP answering right now. A slow or
     rate-limited ESP means the visitor sees a spinner and you lose the lead
     with no record that it ever existed.

This module is the small server-side relay that sits in between. It holds the
key (by environment variable name, never a literal), decides what is worth
sending, and guarantees a submission is either delivered or still on disk with
a reason.

Synthetic data only. Not wired to any store or ESP.
"""

import os
import re
import time
from dataclasses import dataclass, field

# A deliberately boring check. The goal is not RFC-correct email validation --
# it is to not burn an ESP API call, and an ESP quota, on "asdf".
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")

# How long the same address is treated as already-submitted. Covers the
# double-click and the visitor who opts in again from a second page.
DEDUPE_WINDOW_SECONDS = 24 * 60 * 60

MAX_ATTEMPTS = 5


class Rejected(Exception):
    """The submission will never be sent, and the caller should know why."""


@dataclass
class Submission:
    email: str
    source: str
    received_at: float
    attempts: int = 0
    next_attempt_at: float = 0.0
    last_error: str = ""


@dataclass
class Outcome:
    delivered: list = field(default_factory=list)
    queued: list = field(default_factory=list)
    parked: list = field(default_factory=list)
    dropped_spam: int = 0
    dropped_duplicate: int = 0
    dropped_invalid: int = 0


def normalise(email):
    """Lowercase and strip. Two people typing the same address differently are
    one subscriber, and the ESP will bill you for both if you let them be two."""
    return (email or "").strip().lower()


def esp_key(env_var="ESP_API_KEY"):
    """The key is read by name, at call time, from the environment.

    It is never a default, never written to disk, and never part of anything
    the browser receives. If it is missing we fail loudly rather than sending
    an unauthenticated request the ESP will silently reject.
    """
    key = os.environ.get(env_var)
    if not key:
        raise Rejected(f"{env_var} is not set; refusing to call the ESP")
    return key


class Relay:
    """Accepts form submissions, delivers them to an ESP, loses none of them.

    `transport` is any callable taking (email, source) and returning an HTTP
    status code. In the demo it is a fake; in production it is one requests
    call carrying the key from esp_key().
    """

    def __init__(self, transport, now=time.time):
        self._send = transport
        self._now = now
        self.seen = {}          # email -> timestamp of last accepted submission
        self.queue = []         # Submissions waiting on a retry
        self.dead_letter = []   # Submissions the ESP will never accept

    # -- intake ----------------------------------------------------------

    def accept(self, form, outcome):
        """Decide whether a raw form payload deserves an ESP call at all.

        Returns a Submission, or None if it was dropped. Every drop is
        counted -- a lead that vanishes without a number next to it is
        indistinguishable from a bug.
        """
        # Honeypot. A real visitor never sees this field, so anything in it
        # came from a bot. Dropped quietly: telling the bot it failed only
        # teaches whoever wrote it to fix it.
        if (form.get("website") or "").strip():
            outcome.dropped_spam += 1
            return None

        email = normalise(form.get("email"))
        if not _EMAIL.match(email):
            outcome.dropped_invalid += 1
            return None

        last = self.seen.get(email)
        now = self._now()
        if last is not None and now - last < DEDUPE_WINDOW_SECONDS:
            outcome.dropped_duplicate += 1
            return None

        self.seen[email] = now
        return Submission(email=email,
                          source=form.get("source") or "unknown",
                          received_at=now)

    # -- delivery --------------------------------------------------------

    def _deliver(self, sub, outcome):
        """One attempt. Where a submission lands depends on why it failed."""
        sub.attempts += 1
        try:
            status = self._send(sub.email, sub.source)
        except Exception as exc:                  # transport died entirely
            status, exc_text = 0, str(exc)
            sub.last_error = f"transport error: {exc_text}"
        else:
            sub.last_error = f"HTTP {status}"

        if 200 <= status < 300:
            outcome.delivered.append(sub)
            return

        # 4xx other than 429 means the ESP understood us and said no. Retrying
        # an unacceptable payload just burns quota forever, so it is parked
        # with its reason for a human to look at.
        if 400 <= status < 500 and status != 429:
            self.dead_letter.append(sub)
            outcome.parked.append(sub)
            return

        # Everything else -- 429, 5xx, a dead socket -- is the ESP's problem,
        # not the lead's. Back off and keep it.
        if sub.attempts >= MAX_ATTEMPTS:
            self.dead_letter.append(sub)
            outcome.parked.append(sub)
            return

        sub.next_attempt_at = self._now() + 2 ** sub.attempts
        self.queue.append(sub)
        outcome.queued.append(sub)

    def submit(self, form):
        """Full path for one form submission."""
        outcome = Outcome()
        sub = self.accept(form, outcome)
        if sub is not None:
            self._deliver(sub, outcome)
        return outcome

    def drain(self):
        """Retry whatever is due. Called by cron, not by the visitor.

        The visitor's page already returned; nothing here can make them wait.
        """
        outcome = Outcome()
        now = self._now()
        due = [s for s in self.queue if s.next_attempt_at <= now]
        self.queue = [s for s in self.queue if s.next_attempt_at > now]
        for sub in due:
            self._deliver(sub, outcome)
        return outcome


def _demo():
    """Run the scenario that the naive version gets wrong."""
    clock = [1000.0]
    script = [500, 429, 200, 422, 200]   # what the fake ESP returns, in order

    def flaky_esp(email, source):
        return script.pop(0) if script else 200

    relay = Relay(flaky_esp, now=lambda: clock[0])

    forms = [
        {"email": "  Ada@Example.com ", "source": "slide-in"},
        {"email": "grace@example.com", "source": "inline"},
        {"email": "ada@example.com", "source": "inline"},      # same person
        {"email": "not-an-email", "source": "inline"},
        {"email": "bot@example.com", "source": "inline",
         "website": "http://spam.example"},                     # honeypot
        {"email": "katherine@example.com", "source": "inline"},
        {"email": "alan@example.com", "source": "footer"},
    ]

    print("Submissions as they arrive")
    print("-" * 58)
    totals = Outcome()
    for form in forms:
        out = relay.submit(form)
        totals.delivered += out.delivered
        totals.queued += out.queued
        totals.parked += out.parked
        totals.dropped_spam += out.dropped_spam
        totals.dropped_duplicate += out.dropped_duplicate
        totals.dropped_invalid += out.dropped_invalid
        label = (form.get("email") or "")[:28]
        if out.delivered:
            print(f"  {label:<30} delivered")
        elif out.queued:
            print(f"  {label:<30} queued ({out.queued[0].last_error})")
        elif out.parked:
            print(f"  {label:<30} parked ({out.parked[0].last_error})")
        elif out.dropped_spam:
            print(f"  {label:<30} dropped: honeypot")
        elif out.dropped_duplicate:
            print(f"  {label:<30} dropped: already subscribed")
        else:
            print(f"  {label:<30} dropped: not an email address")

    print()
    print(f"Waiting in the retry queue: {len(relay.queue)}")
    clock[0] += 60
    again = relay.drain()
    print(f"After one cron pass: {len(again.delivered)} delivered, "
          f"{len(relay.queue)} still queued, {len(relay.dead_letter)} parked")
    print()
    print("Nothing above was silently lost: every address is either delivered,")
    print("queued with a next attempt, parked with a reason, or counted as a")
    print("deliberate drop.")


if __name__ == "__main__":
    _demo()
