# Resolving WhatsApp replies back to one appointment

A small proof of concept for the part of an appointment-reminder system that
tends to cause the real damage: not sending the reminder, but handling what
comes back.

## What it shows

WhatsApp gives you a phone number and a button payload. A phone number is not an
identity — a household, a carer or a reception desk can cover several
appointments at once. And a reply can land hours after the slot it refers to has
already moved. This code decides, per inbound message, which appointment it
belongs to and whether the status write should happen at all:

- **Two patients on one number stay separate.** The appointment id travels in
  the quick-reply payload, so the reply resolves to a row, not to a number.
- **A second tap writes once.** Patients do tap twice, and WhatsApp itself can
  redeliver.
- **A reply to a slot that has since moved is not applied.** The payload quotes
  a version; if the appointment has changed, the patient answered a question
  about a time that no longer exists.
- **Free text on a shared number goes to a human** instead of guessing — and
  resolves cleanly when the number has exactly one open slot.
- **An unknown number is never guessed into a match.**

## What it is not

This runs entirely on the synthetic files in `datos/`. It is **not connected to
any WhatsApp Business account, calendar or EHR**, and it does not prove the
integration — only the logic that sits between them.

## Run it

No install, no accounts, no keys. Python 3, standard library only.

```
python3 demo.py            # walk the sample inbox
python3 -m unittest test_demo -v   # 10 tests, one per behaviour above
```
