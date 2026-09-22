# Setting up Airtable and Make

Everything here happens inside **your** accounts. Nothing was built in advance,
because that would mean handing over credentials — which we do not ask for and
do not store. What follows is the exact shape to build, so it takes minutes
rather than guesswork.

## Part 1 — The Airtable base

In `src/airtable/` there are three CSV files. Import each one as a new table:

1. In Airtable, open your base and choose **Add a table → Import data → CSV file**.
2. Import `applications.csv`, then `exceptions.csv`, then `audit_log.csv`.
3. Each file contains one example row so Airtable guesses the column types.
   **Delete that row after importing.** The columns stay.

Then fix the four column types Airtable will get wrong:

| Table | Column | Change it to | Options |
|---|---|---|---|
| Applications | `status` | Single select | ACCEPTED, INCOMPLETE, DUPLICATE, UNKNOWN_CATEGORY, NEEDS_REVIEW |
| Applications | `category` | Single select | community, research, emergency |
| Applications | `review_status` | Single select | Not started, In review, Needs info, Decided |
| Applications | `final_disposition` | Single select | Pending, Awarded, Declined, Withdrawn |

Leave `decision_history` as a long text field. It is the plain-language record of
every automatic decision, and it is what makes an audit painless.

### The views your staff actually use

Create these as views on Applications. This is the part that decides whether the
system feels organised or feels like a spreadsheet:

- **Needs a person** — filter: `status` is not `ACCEPTED`. This is the exceptions
  queue. If it is empty, nothing is waiting on you.
- **Ready for committee** — filter: `status` is `ACCEPTED` and `review_status` is
  `Not started`.
- **In review** — filter: `review_status` is `In review`.
- **This cycle** — filter: `cycle` is the current one. Group by `category`.
- **Decided** — filter: `final_disposition` is not `Pending`.

A person opening the base should be able to answer "what needs me today?" by
clicking one view. That is the whole point of the arrangement.

## Part 2 — The Make scenarios

Two scenarios. Build them in your own Make account.

### Scenario 1 — Intake

Runs on every form submission.

| # | Module | What it does |
|---|---|---|
| 1 | Webhook (Custom webhook) | Receives the form submission. Copy the URL Make gives you into your form tool as the destination. |
| 2 | HTTP or Airtable → Search records | Look for the same email in the same cycle. This is what catches duplicates. |
| 3 | Router | Splits into the paths below. |
| 3a | Airtable → Create record (Applications) | Complete and not a duplicate: write it with `status` = ACCEPTED. |
| 3b | Airtable → Create record (Exceptions) | Anything else: write it with the reason. |
| 4 | Airtable → Create record (Audit log) | One row per decision, on both paths. |
| 5 | Email | Notify the applicant. Use different text per path; see the note below. |

**Error handling:** on modules 3a, 3b and 4, right-click → **Add error handler**
→ *Resume*, and route the failure to a row in Exceptions with the error text.
Without this, a failed write disappears silently and the application is simply
lost, which is the one failure mode you cannot detect later.

### Scenario 2 — Cycle report

Runs on a schedule, weekly or at cycle close.

| # | Module | What it does |
|---|---|---|
| 1 | Schedule | Weekly, or whatever suits. |
| 2 | Airtable → Search records | All applications in the current cycle. |
| 3 | Aggregator | Count by status and by category. |
| 4 | Email | Send the counts to the administrators. |

## Part 3 — Where the Python tool fits

The validation rules — which fields each category requires, what counts as a
duplicate, how IDs are built, when something needs review — live in
`src/intake.py`, not in Make. That is deliberate:

- You can run it on a file and see exactly what it would decide, **before**
  anything is written to your base.
- Changing a rule means editing `src/config.json`, not rebuilding a scenario.
- The rules are covered by tests you can run yourself in one command.

Two ways to use it:

- **On its own.** Export submissions to a JSON file, run the tool, import the
  result. Good for a backlog or a cycle close, and it needs no Make at all.
- **Inside Make.** Rebuild the same rules as Make modules using this tool as the
  specification, and keep the tool as the reference you test against.

Start with the first. It works today and depends on nothing.
