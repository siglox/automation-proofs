# Grant Application Intake & Routing

A working backend that takes raw grant-application submissions and decides, for
each one, whether it is complete enough to go to the review committee or needs a
person to look at it first.

**Nothing is ever silently dropped.** Every application comes out either
accepted or in the exceptions queue with a reason attached — a missing required
field, a duplicate of an earlier submission, an unrecognised category. Every
state change is written to an audit log.

This is a personal project, not client work.

## Try it in one minute

```bash
python3 tests/test_todo.py
```

```
13 tests run.
ALL TESTS OK
```

Then run it on the sample data:

```bash
python3 src/intake.py tests/datos/ejemplo-solicitudes.json processed.json
python3 src/report.py processed.json
```

```
Processed 9 submission(s).
  4 ready for the committee
  5 in the exceptions queue

9 application(s)

By status
  ACCEPTED             4
  DUPLICATE            1
  INCOMPLETE           2
  NEEDS_REVIEW         1
  UNKNOWN_CATEGORY     1
```

Four plus five is nine. That the counts add up is not a comment — it is a test,
because an intake system that loses an application without saying so is worse
than one that rejects it.

## What is in here

| Path | What it is |
|---|---|
| `src/intake.py` | The intake: validation, deduplication, category routing, audit log |
| `src/report.py` | Reads the processed file and reports by status, category and funding cycle |
| `src/config.json` | Categories, required fields per category, the review ceiling. Editable without touching code |
| `src/airtable/*.csv` | An Airtable schema ready to import |
| `docs/README.md` | The runbook, written for non-technical staff: errors, what they mean, what to do |
| `docs/HOW_IT_WORKS.md` | One page on what happens inside |
| `docs/AIRTABLE_AND_MAKE.md` | Module-by-module Make.com design to connect it |
| `tests/test_todo.py` | 13 tests, one per acceptance criterion |

## The statuses

| Status | What it means |
|---|---|
| `ACCEPTED` | Complete and ready for the committee |
| `INCOMPLETE` | A required field is missing, or the email is unusable |
| `DUPLICATE` | Same applicant, same cycle, already applied |
| `UNKNOWN_CATEGORY` | The category is not one of the configured ones — usually a form problem |
| `NEEDS_REVIEW` | Complete, but the amount requested is above the ceiling. A person decides |

## What this does not prove

It runs on files, so you can try it on your own data without connecting it to
anything. That is also its limit: the tests demonstrate the routing logic, not a
live Airtable integration. The runbook makes that first real connection a guided
step rather than something claimed as already verified.
