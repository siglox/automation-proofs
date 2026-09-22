#!/usr/bin/env python3
"""A support-bot handoff state machine.

"Make the bot stop when a human answers" sounds like one boolean flag. It
is not, and the three questions the brief never asks are exactly the ones
that break in production:

  1. When does the bot start answering again?
  2. What happens if the human goes idle and never closes the conversation?
  3. What stops the bot from answering while a human already owns the chat?

This is a proof of concept for the state machine underneath, not a chatbot.
It runs entirely on the synthetic events in this file — there is no bot, no
human agent UI and no messaging platform behind it.

States
------
BOT           the bot answers new customer messages
ESCALATED     a human has been asked for, nobody has claimed it yet
WITH_HUMAN    a specific human owns the conversation; the bot stays silent
CLOSED        the human ended it; a new message decides what happens next

The four rules that matter
---------------------------
- Only one human can claim an escalated conversation. A second claim is a
  no-op, not a race.
- While a human owns the conversation, incoming customer messages are
  queued for the human. They never trigger a bot reply, and the "did the
  bot answer while a human owned it" case is exactly what a test asserts
  never happens.
- If a human goes idle with an unanswered customer message sitting there,
  the conversation escalates again automatically. This is the actual
  content of "what if the human doesn't come back": it does not silently
  return to the bot, and it does not sit there forever. It reopens as a
  new escalation, distinguishable in the log from the first one.
- Closing does not end the story. A customer who replies soon after
  closing goes back to the *same human*, because that person already has
  context. A customer who replies later starts fresh with the bot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    BOT = "BOT"
    ESCALATED = "ESCALATED"
    WITH_HUMAN = "WITH_HUMAN"
    CLOSED = "CLOSED"


class InvalidTransition(Exception):
    """Raised when an action doesn't make sense in the current state.

    A state machine that accepts any action from any state isn't a state
    machine, it's a boolean pretending to be one. Guarding this is the
    point of the exercise.
    """


@dataclass
class Event:
    kind: str
    at: int  # synthetic clock, minutes since conversation start
    detail: str = ""


@dataclass
class Conversation:
    """One customer conversation, tracked through the handoff lifecycle.

    `reopen_grace_minutes` is the window after a close where a follow-up
    message goes back to the same human instead of the bot. `idle_timeout`
    is how long a human can go quiet, with an unanswered customer message
    pending, before the conversation escalates again.
    """

    reopen_grace_minutes: int = 10
    idle_timeout_minutes: int = 15

    state: State = State.BOT
    assigned_to: str | None = None
    last_closed_by: str | None = None
    closed_at: int | None = None

    # The last customer message time that has not yet been answered by a
    # human. None means "nothing waiting on a human right now."
    unanswered_since: int | None = None

    log: list[Event] = field(default_factory=list)

    def _record(self, kind: str, at: int, detail: str = "") -> None:
        self.log.append(Event(kind=kind, at=at, detail=detail))

    # -- customer side ----------------------------------------------------

    def customer_message(self, at: int, text: str) -> str:
        """A message arrives. Returns who/what handles it: "bot", "human", or
        "queued" (waiting for a human to pick it up)."""

        if self.state == State.BOT:
            self._record("bot_reply", at, text)
            return "bot"

        if self.state == State.ESCALATED:
            # Already waiting for a human; this just extends the wait.
            self.unanswered_since = self.unanswered_since or at
            self._record("queued_for_human", at, text)
            return "queued"

        if self.state == State.WITH_HUMAN:
            # This is the guard that matters most: the bot does NOT answer
            # here, no matter how long the human has been silent. Silence
            # is handled by check_idle(), not by falling back to the bot
            # mid-conversation.
            if self.unanswered_since is None:
                self.unanswered_since = at
            self._record("queued_for_human", at, text)
            return "queued"

        if self.state == State.CLOSED:
            if (
                self.last_closed_by is not None
                and self.closed_at is not None
                and at - self.closed_at <= self.reopen_grace_minutes
            ):
                # Same human, same context. No bot in between.
                self.state = State.WITH_HUMAN
                self.assigned_to = self.last_closed_by
                self.unanswered_since = at
                self._record(
                    "reopened_to_human", at, f"{text} (agent={self.assigned_to})"
                )
                return "human"

            # Outside the grace window: this is effectively a new
            # conversation, and the bot handles it like one.
            self.state = State.BOT
            self.assigned_to = None
            self.last_closed_by = None
            self.closed_at = None
            self._record("bot_reply", at, text)
            return "bot"

        raise InvalidTransition(f"no handler for state {self.state}")

    def request_human(self, at: int, reason: str) -> None:
        """The bot (or the customer) asks for a human."""
        if self.state != State.BOT:
            raise InvalidTransition(
                f"can only escalate from BOT, currently {self.state}"
            )
        self.state = State.ESCALATED
        self._record("escalated", at, reason)

    # -- human side ---------------------------------------------------------

    def human_claim(self, at: int, agent: str) -> bool:
        """A human claims the conversation. Returns False if someone already
        owns it — a second claim is a no-op, not an error and not a
        takeover."""

        if self.state == State.WITH_HUMAN:
            self._record("claim_ignored", at, f"already with {self.assigned_to}")
            return False

        if self.state != State.ESCALATED:
            raise InvalidTransition(
                f"can only claim from ESCALATED, currently {self.state}"
            )

        self.state = State.WITH_HUMAN
        self.assigned_to = agent
        self._record("claimed", at, agent)
        return True

    def human_reply(self, at: int, agent: str) -> None:
        if self.state != State.WITH_HUMAN or self.assigned_to != agent:
            raise InvalidTransition(f"{agent} does not own this conversation")
        self.unanswered_since = None
        self._record("human_reply", at, agent)

    def human_close(self, at: int, agent: str) -> None:
        if self.state != State.WITH_HUMAN or self.assigned_to != agent:
            raise InvalidTransition(f"{agent} cannot close a conversation they don't own")
        if self.unanswered_since is not None:
            # A human should not be able to silently walk away from a
            # customer message they never answered. In a real system this
            # would block the UI action; here it is a hard guard.
            raise InvalidTransition(
                "cannot close with an unanswered customer message pending"
            )
        self.state = State.CLOSED
        self.last_closed_by = agent
        self.closed_at = at
        self._record("closed", at, agent)

    # -- the clock ------------------------------------------------------

    def check_idle(self, at: int) -> bool:
        """Call this periodically (a scheduled tick, not a customer action).

        Returns True if this tick caused a re-escalation. Only fires when
        there is an actual unanswered message sitting with an idle human —
        it does not escalate a conversation just because the human hasn't
        said anything, if there was nothing to answer.
        """

        if self.state != State.WITH_HUMAN or self.unanswered_since is None:
            return False

        if at - self.unanswered_since < self.idle_timeout_minutes:
            return False

        # The human went quiet on an actual customer message. This is a
        # DIFFERENT event from the first escalation: ops needs to be able
        # to tell "nobody picked this up yet" apart from "somebody picked
        # it up and then went dark."
        previous_agent = self.assigned_to
        self.state = State.ESCALATED
        self.assigned_to = None
        self._record(
            "re_escalated_idle_human",
            at,
            f"previous_agent={previous_agent}, silent for "
            f"{at - self.unanswered_since}min",
        )
        return True
