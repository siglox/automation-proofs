"""One test per behaviour the client would recognise from their own portal.

    python -m unittest discover -s demos/2102347721123513018
"""

import unittest

from demo import Portal, engagement_key, normalise, resolve

CONTACTS = [
    {
        "id": "101",
        "email": "dana.whitfield@northgate-supply.com",
        "secondary_emails": ["d.whitfield@northgate-supply.com"],
    },
    {"id": "102", "email": "marcus@obi-fabrication.com", "secondary_emails": []},
    {"id": "103", "email": "Marcus@Obi-Fabrication.com", "secondary_emails": []},
    {
        "id": "104",
        "email": "priya.raman@lattice-works.io",
        "secondary_emails": ["priya+billing@lattice-works.io"],
    },
]


def event(message_id, to, subject="Subject", sent_at="2026-09-22T08:00:00Z"):
    return {
        "message_id": message_id,
        "to": to,
        "subject": subject,
        "sent_at": sent_at,
    }


class Matching(unittest.TestCase):
    def test_exact_address_resolves_to_one_contact(self):
        match = resolve("dana.whitfield@northgate-supply.com", CONTACTS)
        self.assertEqual(("resolved", "101"), (match.status, match.contact_id))

    def test_casing_and_whitespace_do_not_prevent_a_match(self):
        match = resolve("  Dana.Whitfield@Northgate-Supply.COM ", CONTACTS)
        self.assertEqual("101", match.contact_id)

    def test_a_secondary_address_resolves_to_the_same_contact(self):
        match = resolve("d.whitfield@northgate-supply.com", CONTACTS)
        self.assertEqual("101", match.contact_id)
        self.assertEqual("secondary_email", match.rule)

    def test_plus_tagged_address_is_the_same_human(self):
        match = resolve("priya+anything@lattice-works.io", CONTACTS)
        self.assertEqual("104", match.contact_id)

    def test_two_contacts_on_one_address_is_ambiguous_not_first_wins(self):
        match = resolve("marcus@obi-fabrication.com", CONTACTS)
        self.assertEqual("ambiguous", match.status)
        self.assertEqual({"102", "103"}, set(match.candidates))
        self.assertIsNone(match.contact_id)

    def test_an_unknown_address_is_reported_as_unknown(self):
        match = resolve("nobody@example.org", CONTACTS)
        self.assertEqual("unknown", match.status)


class Logging(unittest.TestCase):
    def setUp(self):
        self.portal = Portal(contacts=CONTACTS)

    def test_a_matched_email_creates_one_engagement(self):
        outcome = self.portal.log_outbound_email(
            event("msg-1", "dana.whitfield@northgate-supply.com")
        )
        self.assertEqual("created", outcome)
        self.assertEqual(1, len(self.portal.engagements))

    def test_the_same_send_retried_does_not_duplicate(self):
        self.portal.log_outbound_email(
            event("msg-1", "dana.whitfield@northgate-supply.com")
        )
        outcome = self.portal.log_outbound_email(
            event(
                "msg-1",
                "dana.whitfield@northgate-supply.com",
                sent_at="2026-09-22T09:30:00Z",
            )
        )
        self.assertEqual("duplicate_ignored", outcome)
        self.assertEqual(1, len(self.portal.engagements))

    def test_two_different_sends_to_one_contact_both_land(self):
        self.portal.log_outbound_email(
            event("msg-1", "dana.whitfield@northgate-supply.com")
        )
        self.portal.log_outbound_email(
            event("msg-2", "dana.whitfield@northgate-supply.com")
        )
        self.assertEqual(2, len(self.portal.engagements))

    def test_an_ambiguous_address_is_parked_and_not_written(self):
        outcome = self.portal.log_outbound_email(
            event("msg-9", "marcus@obi-fabrication.com")
        )
        self.assertEqual("queued_ambiguous", outcome)
        self.assertEqual(0, len(self.portal.engagements))
        self.assertEqual(1, len(self.portal.needs_review))
        self.assertEqual(
            {"102", "103"}, set(self.portal.needs_review[0]["candidates"])
        )

    def test_an_unknown_address_is_parked_not_dropped(self):
        outcome = self.portal.log_outbound_email(
            event("msg-9", "stranger@example.org")
        )
        self.assertEqual("queued_unknown", outcome)
        self.assertEqual(0, len(self.portal.engagements))
        self.assertEqual(1, len(self.portal.needs_review))


class Keys(unittest.TestCase):
    def test_the_key_does_not_depend_on_send_time(self):
        self.assertEqual(
            engagement_key("msg-1", "101"), engagement_key("msg-1", "101")
        )

    def test_different_contacts_get_different_keys(self):
        self.assertNotEqual(
            engagement_key("msg-1", "101"), engagement_key("msg-1", "102")
        )

    def test_an_address_without_an_at_sign_is_left_alone(self):
        self.assertEqual("not-an-address", normalise("  Not-An-Address "))


if __name__ == "__main__":
    unittest.main()
