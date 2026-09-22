"""One test per behaviour the site owner would recognise.

    python test_demo.py
"""

import os
import unittest

from demo import (DEDUPE_WINDOW_SECONDS, MAX_ATTEMPTS, Rejected, Relay,
                  esp_key, normalise)


def transport_returning(*statuses):
    """A fake ESP that answers with each status in turn, then 200 forever."""
    script = list(statuses)

    def send(email, source):
        return script.pop(0) if script else 200
    return send


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class TestIntake(unittest.TestCase):

    def test_good_address_reaches_the_esp(self):
        relay = Relay(transport_returning(200))
        out = relay.submit({"email": "ada@example.com", "source": "inline"})
        self.assertEqual(len(out.delivered), 1)
        self.assertEqual(out.delivered[0].email, "ada@example.com")

    def test_same_address_typed_differently_is_one_subscriber(self):
        # "  Ada@Example.com " and "ada@example.com" must not become two
        # contacts, and must not be billed twice.
        clock = Clock()
        relay = Relay(transport_returning(200, 200), now=clock)
        first = relay.submit({"email": "  Ada@Example.com ", "source": "a"})
        second = relay.submit({"email": "ada@example.com", "source": "b"})
        self.assertEqual(len(first.delivered), 1)
        self.assertEqual(second.dropped_duplicate, 1)
        self.assertEqual(len(second.delivered), 0)

    def test_the_same_person_can_opt_in_again_much_later(self):
        clock = Clock()
        relay = Relay(transport_returning(200, 200), now=clock)
        relay.submit({"email": "ada@example.com", "source": "a"})
        clock.advance(DEDUPE_WINDOW_SECONDS + 1)
        again = relay.submit({"email": "ada@example.com", "source": "a"})
        self.assertEqual(len(again.delivered), 1)

    def test_honeypot_submission_never_reaches_the_esp(self):
        calls = []
        relay = Relay(lambda e, s: calls.append(e) or 200)
        out = relay.submit({"email": "bot@example.com",
                            "website": "http://spam.example"})
        self.assertEqual(out.dropped_spam, 1)
        self.assertEqual(calls, [])

    def test_junk_in_the_field_does_not_burn_an_api_call(self):
        calls = []
        relay = Relay(lambda e, s: calls.append(e) or 200)
        out = relay.submit({"email": "not-an-email"})
        self.assertEqual(out.dropped_invalid, 1)
        self.assertEqual(calls, [])

    def test_normalise_handles_missing_field(self):
        self.assertEqual(normalise(None), "")


class TestWhenTheEspMisbehaves(unittest.TestCase):

    def test_a_rate_limited_lead_is_kept_not_lost(self):
        relay = Relay(transport_returning(429))
        out = relay.submit({"email": "grace@example.com"})
        self.assertEqual(len(out.delivered), 0)
        self.assertEqual(len(relay.queue), 1)
        self.assertEqual(relay.queue[0].email, "grace@example.com")

    def test_a_server_error_is_kept_and_delivered_on_retry(self):
        clock = Clock()
        relay = Relay(transport_returning(500, 200), now=clock)
        relay.submit({"email": "grace@example.com"})
        self.assertEqual(len(relay.queue), 1)
        clock.advance(60)
        out = relay.drain()
        self.assertEqual(len(out.delivered), 1)
        self.assertEqual(relay.queue, [])

    def test_a_transport_that_dies_is_treated_as_retryable(self):
        def dies(email, source):
            raise OSError("connection reset")
        relay = Relay(dies)
        relay.submit({"email": "grace@example.com"})
        self.assertEqual(len(relay.queue), 1)
        self.assertIn("connection reset", relay.queue[0].last_error)

    def test_a_rejected_payload_is_parked_not_retried_forever(self):
        # 422 means the ESP understood and refused. Retrying cannot help.
        relay = Relay(transport_returning(422))
        out = relay.submit({"email": "katherine@example.com"})
        self.assertEqual(len(relay.queue), 0)
        self.assertEqual(len(out.parked), 1)
        self.assertIn("422", relay.dead_letter[0].last_error)

    def test_retries_back_off_instead_of_hammering(self):
        clock = Clock()
        relay = Relay(transport_returning(500, 500), now=clock)
        relay.submit({"email": "grace@example.com"})
        first_gap = relay.queue[0].next_attempt_at - clock()
        clock.advance(first_gap)
        relay.drain()
        second_gap = relay.queue[0].next_attempt_at - clock()
        self.assertGreater(second_gap, first_gap)

    def test_a_permanently_broken_lead_stops_after_a_bounded_number_of_tries(self):
        clock = Clock()
        relay = Relay(transport_returning(*([500] * (MAX_ATTEMPTS + 2))),
                      now=clock)
        relay.submit({"email": "grace@example.com"})
        for _ in range(MAX_ATTEMPTS + 1):
            clock.advance(10_000)
            relay.drain()
        self.assertEqual(relay.queue, [])
        self.assertEqual(len(relay.dead_letter), 1)
        # Parked, not vanished: the address is still readable.
        self.assertEqual(relay.dead_letter[0].email, "grace@example.com")


class TestTheKeyStaysOnTheServer(unittest.TestCase):

    def test_key_is_read_from_the_environment_by_name(self):
        os.environ["DEMO_ESP_KEY"] = "sk-not-a-real-key"
        try:
            self.assertEqual(esp_key("DEMO_ESP_KEY"), "sk-not-a-real-key")
        finally:
            del os.environ["DEMO_ESP_KEY"]

    def test_missing_key_fails_loudly_instead_of_sending_nothing(self):
        os.environ.pop("DEMO_ABSENT_KEY", None)
        with self.assertRaises(Rejected):
            esp_key("DEMO_ABSENT_KEY")

    def test_no_credential_is_hardcoded_in_this_demo(self):
        # The relay only ever learns the key through esp_key(), so there is
        # nothing in the source for a browser or a repo to leak.
        with open(os.path.join(os.path.dirname(__file__) or ".", "demo.py"),
                  encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("sk-", source)
        self.assertNotIn("api_key=", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
