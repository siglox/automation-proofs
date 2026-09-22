"""Resolve which HubSpot contact an outbound email belongs to, and log the
engagement so a retry cannot duplicate it.

Synthetic data only. Nothing here talks to a real HubSpot portal.

The job posting describes the symptom: emails sent through n8n are not
consistently visible on the matching HubSpot contact record. The cause is
almost never the send. It is one of three things, and this module models all
three:

  1. The lookup returns more than one contact, and the code silently takes the
     first one. The activity lands on a real contact -- the wrong one.
  2. The lookup returns nothing, and the write is dropped instead of parked.
  3. A retry re-sends the same engagement, and HubSpot happily stores it twice.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).parent / "data"


# --------------------------------------------------------------------------
# Matching


@dataclass(frozen=True)
class Match:
    """Outcome of resolving an outbound email to a HubSpot contact."""

    status: str  # "resolved" | "ambiguous" | "unknown"
    contact_id: str | None = None
    rule: str | None = None
    candidates: tuple[str, ...] = ()


def normalise(address: str) -> str:
    """Lowercase, strip, and drop gmail-style +tags from the local part.

    Two records that differ only by a +tag are the same human. Treating them as
    different contacts is how a portal ends up with duplicates in the first
    place.
    """
    address = address.strip().lower()
    if "@" not in address:
        return address
    local, _, domain = address.partition("@")
    local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def resolve(recipient: str, contacts: list[dict]) -> Match:
    """Find the contact an outbound email belongs to.

    Rules are tried in order and the first one that yields exactly one contact
    wins. A rule that yields several does not fall through to a looser rule --
    it reports ambiguity, because a looser rule can only make it worse.
    """
    target = normalise(recipient)

    # Rule 1: exact match on the primary email.
    hits = [c for c in contacts if normalise(c["email"]) == target]
    if len(hits) == 1:
        return Match("resolved", hits[0]["id"], rule="primary_email")
    if len(hits) > 1:
        return Match("ambiguous", candidates=tuple(c["id"] for c in hits))

    # Rule 2: match on a secondary address the contact is known by.
    hits = [
        c
        for c in contacts
        if any(normalise(a) == target for a in c.get("secondary_emails", []))
    ]
    if len(hits) == 1:
        return Match("resolved", hits[0]["id"], rule="secondary_email")
    if len(hits) > 1:
        return Match("ambiguous", candidates=tuple(c["id"] for c in hits))

    return Match("unknown")


# --------------------------------------------------------------------------
# Idempotent logging


def engagement_key(message_id: str, contact_id: str) -> str:
    """Stable key for one engagement.

    Derived from the provider's message id, not from a timestamp or a counter,
    so the same send retried an hour later produces the same key.
    """
    raw = f"{message_id}|{contact_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass
class Portal:
    """Stand-in for the HubSpot side. Stores engagements and a review queue."""

    contacts: list[dict]
    engagements: dict[str, dict] = field(default_factory=dict)
    needs_review: list[dict] = field(default_factory=list)

    def log_outbound_email(self, event: dict) -> str:
        """Log one outbound email. Returns what happened, for the caller's log.

        Return values: "created", "duplicate_ignored", "queued_ambiguous",
        "queued_unknown".
        """
        match = resolve(event["to"], self.contacts)

        if match.status != "resolved":
            self.needs_review.append(
                {
                    "message_id": event["message_id"],
                    "to": event["to"],
                    "subject": event["subject"],
                    "reason": match.status,
                    "candidates": list(match.candidates),
                }
            )
            return f"queued_{match.status}"

        key = engagement_key(event["message_id"], match.contact_id)
        if key in self.engagements:
            return "duplicate_ignored"

        self.engagements[key] = {
            "contact_id": match.contact_id,
            "message_id": event["message_id"],
            "subject": event["subject"],
            "sent_at": event["sent_at"],
            "matched_by": match.rule,
        }
        return "created"


# --------------------------------------------------------------------------
# Runner


def load(name: str):
    with open(DATA / name, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    portal = Portal(contacts=load("contacts.json"))
    events = load("outbound_emails.json")

    print(f"{len(portal.contacts)} contacts, {len(events)} outbound emails\n")

    for event in events:
        outcome = portal.log_outbound_email(event)
        print(f"  {outcome:<18} {event['message_id']:<12} -> {event['to']}")

    print(f"\nengagements written : {len(portal.engagements)}")
    print(f"parked for review   : {len(portal.needs_review)}")
    for item in portal.needs_review:
        detail = (
            f"matches {item['candidates']}"
            if item["candidates"]
            else "no contact found"
        )
        print(f"  - {item['to']}: {item['reason']}, {detail}")

    print(
        "\nNothing was silently dropped and nothing was written twice."
        "\nThat is the whole point."
    )


if __name__ == "__main__":
    main()
