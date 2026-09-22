#!/usr/bin/env python3
"""One test per behaviour a client would recognise from their own bot.

Standard library only. Run directly:

    python3 test_demo.py
"""

import unittest

from demo import Conversation, InvalidTransition, State


class TestBotAnswersByDefault(unittest.TestCase):
    def test_new_conversation_starts_with_bot(self):
        c = Conversation()
        handler = c.customer_message(at=0, text="what are your hours?")
        self.assertEqual(handler, "bot")
        self.assertEqual(c.state, State.BOT)


class TestEscalation(unittest.TestCase):
    def test_customer_request_moves_to_escalated(self):
        c = Conversation()
        c.request_human(at=1, reason="customer asked for a human")
        self.assertEqual(c.state, State.ESCALATED)

    def test_cannot_escalate_twice(self):
        c = Conversation()
        c.request_human(at=1, reason="first")
        with self.assertRaises(InvalidTransition):
            c.request_human(at=2, reason="second")

    def test_messages_while_escalated_are_queued_not_answered_by_bot(self):
        c = Conversation()
        c.request_human(at=1, reason="asked for a human")
        handler = c.customer_message(at=2, text="hello?")
        self.assertEqual(handler, "queued")


class TestClaiming(unittest.TestCase):
    def test_human_claims_an_escalated_conversation(self):
        c = Conversation()
        c.request_human(at=1, reason="asked")
        claimed = c.human_claim(at=2, agent="alice")
        self.assertTrue(claimed)
        self.assertEqual(c.state, State.WITH_HUMAN)
        self.assertEqual(c.assigned_to, "alice")

    def test_second_claim_is_a_noop_not_a_takeover(self):
        """Two agents click 'claim' within the same second. This is the
        exact race a real support tool has to handle — the second claim
        must not silently steal the conversation from the first agent."""
        c = Conversation()
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        second = c.human_claim(at=2, agent="bob")
        self.assertFalse(second)
        self.assertEqual(c.assigned_to, "alice")

    def test_cannot_claim_a_conversation_still_with_the_bot(self):
        c = Conversation()
        with self.assertRaises(InvalidTransition):
            c.human_claim(at=1, agent="alice")


class TestNoDoubleAnswer(unittest.TestCase):
    """The scenario the brief never names, and the one that actually
    embarrasses a business: the bot and a human both reply to the same
    customer message."""

    def test_bot_never_answers_once_a_human_owns_the_conversation(self):
        c = Conversation()
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")

        handler = c.customer_message(at=3, text="are you still there?")

        self.assertEqual(handler, "queued")
        self.assertEqual(c.state, State.WITH_HUMAN)
        kinds = [e.kind for e in c.log]
        self.assertNotIn("bot_reply", kinds[2:])  # nothing bot-shaped after claim


class TestHumanReplyAndClose(unittest.TestCase):
    def test_human_reply_clears_the_unanswered_flag(self):
        c = Conversation()
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        c.customer_message(at=3, text="are you there?")
        self.assertIsNotNone(c.unanswered_since)

        c.human_reply(at=4, agent="alice")
        self.assertIsNone(c.unanswered_since)

    def test_wrong_agent_cannot_reply_or_close(self):
        c = Conversation()
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        with self.assertRaises(InvalidTransition):
            c.human_reply(at=3, agent="bob")
        with self.assertRaises(InvalidTransition):
            c.human_close(at=3, agent="bob")

    def test_owning_agent_can_close(self):
        c = Conversation()
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        c.human_close(at=3, agent="alice")
        self.assertEqual(c.state, State.CLOSED)
        self.assertEqual(c.last_closed_by, "alice")

    def test_cannot_close_with_an_unanswered_message_pending(self):
        """This is the guard against the exact failure the brief never
        describes: a human clicks 'resolve' while the customer's last
        message is still sitting there unanswered."""
        c = Conversation()
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        c.customer_message(at=3, text="one more thing...")
        with self.assertRaises(InvalidTransition):
            c.human_close(at=4, agent="alice")


class TestIdleHumanReEscalates(unittest.TestCase):
    """What happens when the human doesn't come back — the question the
    original brief never asks."""

    def test_idle_tick_does_nothing_when_nothing_is_waiting(self):
        c = Conversation(idle_timeout_minutes=15)
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        # No unanswered message. The human being quiet is not, by itself,
        # a problem — most of a conversation is silence.
        fired = c.check_idle(at=100)
        self.assertFalse(fired)
        self.assertEqual(c.state, State.WITH_HUMAN)

    def test_idle_tick_reescalates_when_a_message_is_left_unanswered(self):
        c = Conversation(idle_timeout_minutes=15)
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        c.customer_message(at=3, text="hello?")

        fired_early = c.check_idle(at=10)  # 7 minutes idle: not yet
        self.assertFalse(fired_early)

        fired_late = c.check_idle(at=20)  # 17 minutes idle: now it fires
        self.assertTrue(fired_late)
        self.assertEqual(c.state, State.ESCALATED)
        self.assertIsNone(c.assigned_to)

    def test_reescalation_is_distinguishable_from_first_escalation(self):
        """Ops needs to tell 'nobody picked this up' apart from 'somebody
        picked it up and went dark' — they are different failures with
        different fixes."""
        c = Conversation(idle_timeout_minutes=15)
        c.request_human(at=1, reason="customer asked for a human")
        c.human_claim(at=2, agent="alice")
        c.customer_message(at=3, text="hello?")
        c.check_idle(at=20)

        kinds = [e.kind for e in c.log]
        self.assertIn("escalated", kinds)
        self.assertIn("re_escalated_idle_human", kinds)
        self.assertNotEqual(
            c.log[kinds.index("escalated")].detail,
            c.log[kinds.index("re_escalated_idle_human")].detail,
        )


class TestReopenAfterClose(unittest.TestCase):
    def test_message_soon_after_close_goes_back_to_same_human(self):
        c = Conversation(reopen_grace_minutes=10)
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        c.human_close(at=5, agent="alice")

        handler = c.customer_message(at=12, text="actually, one more question")
        self.assertEqual(handler, "human")
        self.assertEqual(c.state, State.WITH_HUMAN)
        self.assertEqual(c.assigned_to, "alice")

    def test_message_long_after_close_starts_fresh_with_the_bot(self):
        c = Conversation(reopen_grace_minutes=10)
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        c.human_close(at=5, agent="alice")

        handler = c.customer_message(at=200, text="hi, new question")
        self.assertEqual(handler, "bot")
        self.assertEqual(c.state, State.BOT)
        self.assertIsNone(c.assigned_to)


class TestAuditLog(unittest.TestCase):
    def test_every_transition_is_logged_in_order(self):
        c = Conversation()
        c.request_human(at=1, reason="asked")
        c.human_claim(at=2, agent="alice")
        c.customer_message(at=3, text="hi")
        c.human_reply(at=4, agent="alice")
        c.human_close(at=5, agent="alice")

        kinds = [e.kind for e in c.log]
        self.assertEqual(
            kinds,
            ["escalated", "claimed", "queued_for_human", "human_reply", "closed"],
        )
        times = [e.at for e in c.log]
        self.assertEqual(times, sorted(times))


if __name__ == "__main__":
    unittest.main(verbosity=1)
