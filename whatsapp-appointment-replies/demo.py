#!/usr/bin/env python3
"""Resolve inbound WhatsApp replies back to exactly one appointment.

Sending the reminder is the easy half. The hard half is the reply: WhatsApp
hands you a phone number and a button payload, and a phone number is not an
identity -- a household, a carer or a company reception desk can cover several
appointments at once. On top of that, a reply can arrive long after the slot it
refers to has already been moved or cancelled.

This module decides, for one inbound message, which appointment it belongs to
and whether the status write should happen at all. Everything runs on the
synthetic files in datos/; nothing here talks to WhatsApp, a calendar or an EHR.

Run:
    python3 demo.py            # walk the sample inbox
    python3 -m unittest test_demo -v
"""

import json
from pathlib import Path

DATOS = Path(__file__).parent / "datos"

# Outcomes. Only APPLIED writes to the source system; everything else is either
# a no-op or a ticket for the reception team.
APPLIED = "APPLIED"
DUPLICATE = "DUPLICATE"
STALE = "STALE"
AMBIGUOUS = "AMBIGUOUS"
UNKNOWN_SENDER = "UNKNOWN_SENDER"
UNPARSEABLE = "UNPARSEABLE"

# A reply only ever moves an appointment out of this state.
OPEN = "SCHEDULED"

ACTIONS = {"CONFIRM": "CONFIRMED", "CANCEL": "CANCELLED", "RESCHEDULE": "RESCHEDULE_REQUESTED"}

# Free text we are willing to act on, but only when the sender is unambiguous.
KEYWORDS = {
    "confirm": "CONFIRM",
    "yes": "CONFIRM",
    "cancel": "CANCEL",
    "reschedule": "RESCHEDULE",
}


def load(name):
    with open(DATOS / name, encoding="utf-8") as fh:
        return json.load(fh)


def parse_payload(payload):
    """Split the quick-reply payload we put in the outbound template.

    The payload is the only place an appointment id can survive the round trip,
    which is why the reminder carries one: ACTION:APPOINTMENT_ID:VERSION.
    Returns None if the payload is missing or malformed.
    """
    if not payload:
        return None
    parts = payload.split(":")
    if len(parts) != 3:
        return None
    action, appointment_id, version = parts
    if action not in ACTIONS or not appointment_id.strip():
        return None
    if not version.isdigit():
        return None
    return action, appointment_id, int(version)


def keyword_action(text):
    """Map free text to an action, or None if we cannot tell."""
    if not text:
        return None
    lowered = text.lower()
    found = {action for word, action in KEYWORDS.items() if word in lowered}
    return found.pop() if len(found) == 1 else None


def resolve(message, appointments, already_applied):
    """Decide what a single inbound message means.

    `already_applied` is the set of payloads this system has acted on before.
    It is what makes a second tap on the same button a no-op instead of a second
    write -- patients do tap twice, and WhatsApp itself can redeliver.

    Returns a dict with `outcome`, and `appointment_id` / `new_status` when the
    outcome is APPLIED.
    """
    by_id = {a["appointment_id"]: a for a in appointments}
    parsed = parse_payload(message.get("button_payload"))

    if parsed:
        action, appointment_id, version = parsed
        appointment = by_id.get(appointment_id)
        if appointment is None:
            return {"outcome": UNKNOWN_SENDER, "reason": "no such appointment"}
        # The number that replied must be the number the reminder went to.
        if appointment["phone"] != message["from"]:
            return {"outcome": AMBIGUOUS, "reason": "payload and sender disagree"}
    else:
        action = keyword_action(message.get("button_text"))
        if action is None:
            return {"outcome": UNPARSEABLE, "reason": "no button and no clear keyword"}
        open_slots = [a for a in appointments
                      if a["phone"] == message["from"] and a["status"] == OPEN]
        if not open_slots:
            return {"outcome": UNKNOWN_SENDER, "reason": "no open appointment for this number"}
        if len(open_slots) > 1:
            # This is the case a phone-number-keyed design gets wrong silently.
            return {"outcome": AMBIGUOUS,
                    "reason": f"{len(open_slots)} open appointments on this number"}
        appointment = open_slots[0]
        appointment_id = appointment["appointment_id"]
        version = appointment["version"]

    key = f"{action}:{appointment_id}:{version}"
    if key in already_applied:
        return {"outcome": DUPLICATE, "appointment_id": appointment_id}

    # The reminder quoted version N. If the slot has moved since, the patient
    # answered a question about a time that no longer exists.
    if version != appointment["version"] or appointment["status"] != OPEN:
        return {"outcome": STALE, "appointment_id": appointment_id,
                "reason": f"appointment is {appointment['status']} at version "
                          f"{appointment['version']}"}

    already_applied.add(key)
    return {"outcome": APPLIED, "appointment_id": appointment_id,
            "new_status": ACTIONS[action]}


def run(messages, appointments):
    """Process an inbox in order, sharing one applied-set across the batch."""
    already_applied = set()
    return [resolve(m, appointments, already_applied) for m in messages]


def main():
    appointments = load("appointments.json")
    messages = load("inbound.json")
    for message, result in zip(messages, run(messages, appointments)):
        print(f"{result['outcome']:<15} {message['from']}  "
              f"{message.get('button_payload') or repr(message.get('button_text'))}")
        detail = result.get("reason") or result.get("new_status")
        if detail:
            print(f"{'':<15} -> {detail}")


if __name__ == "__main__":
    main()
