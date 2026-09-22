#!/usr/bin/env python3
"""One test per behaviour a clinic would recognise. Standard library only."""

import unittest

import demo


APPOINTMENTS = demo.load("appointments.json")


def msg(sender, payload=None, text=None):
    return {"from": sender, "button_payload": payload, "button_text": text,
            "received_at": "2026-09-23T10:00:00Z"}


class ResolveTests(unittest.TestCase):

    def setUp(self):
        self.applied = set()

    def resolve(self, message):
        return demo.resolve(message, APPOINTMENTS, self.applied)

    def test_confirm_resolves_to_the_appointment_in_the_payload(self):
        out = self.resolve(msg("+971500000001", "CONFIRM:APT-1001:1"))
        self.assertEqual(out["outcome"], demo.APPLIED)
        self.assertEqual(out["appointment_id"], "APT-1001")
        self.assertEqual(out["new_status"], "CONFIRMED")

    def test_two_patients_on_one_number_stay_separate(self):
        """The case a phone-number-keyed design gets wrong without anyone noticing."""
        first = self.resolve(msg("+971500000001", "CONFIRM:APT-1001:1"))
        second = self.resolve(msg("+971500000001", "CANCEL:APT-1002:1"))
        self.assertEqual(first["appointment_id"], "APT-1001")
        self.assertEqual(second["appointment_id"], "APT-1002")
        self.assertEqual(second["new_status"], "CANCELLED")

    def test_tapping_the_same_button_twice_writes_once(self):
        self.resolve(msg("+971500000001", "CONFIRM:APT-1001:1"))
        again = self.resolve(msg("+971500000001", "CONFIRM:APT-1001:1"))
        self.assertEqual(again["outcome"], demo.DUPLICATE)

    def test_reply_to_a_slot_that_has_since_moved_is_not_applied(self):
        out = self.resolve(msg("+971500000003", "CONFIRM:APT-1004:1"))
        self.assertEqual(out["outcome"], demo.STALE)

    def test_free_text_on_a_shared_number_goes_to_a_human(self):
        out = self.resolve(msg("+971500000001", text="yes that works"))
        self.assertEqual(out["outcome"], demo.AMBIGUOUS)

    def test_free_text_resolves_when_the_number_has_one_open_slot(self):
        out = self.resolve(msg("+971500000002", text="Reschedule please"))
        self.assertEqual(out["outcome"], demo.APPLIED)
        self.assertEqual(out["appointment_id"], "APT-1003")
        self.assertEqual(out["new_status"], "RESCHEDULE_REQUESTED")

    def test_unknown_number_is_not_guessed(self):
        out = self.resolve(msg("+971509999999", text="Confirm"))
        self.assertEqual(out["outcome"], demo.UNKNOWN_SENDER)

    def test_payload_from_the_wrong_number_is_refused(self):
        """Forwarded or spoofed payload: the sender must own the appointment."""
        out = self.resolve(msg("+971500000002", "CONFIRM:APT-1001:1"))
        self.assertEqual(out["outcome"], demo.AMBIGUOUS)

    def test_malformed_payload_falls_back_to_text_and_stays_safe(self):
        out = self.resolve(msg("+971500000001", "CONFIRM-APT-1001"))
        self.assertEqual(out["outcome"], demo.UNPARSEABLE)

    def test_sample_inbox_never_applies_more_than_the_expected_writes(self):
        results = demo.run(demo.load("inbound.json"), APPOINTMENTS)
        applied = [r for r in results if r["outcome"] == demo.APPLIED]
        self.assertEqual(len(applied), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
