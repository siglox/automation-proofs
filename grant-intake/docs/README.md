# Grant Intake — What it does and how to run it

## 1. What this does

It takes the grant applications that come in from your form and decides, for
each one, whether it is complete enough to go to the committee or needs somebody
to look at it first. It gives every application a readable ID, spots the
duplicates, and writes a report of where everything stands.

Nothing is ever thrown away. An application it cannot process comes out in the
exceptions list with a plain-English reason, never silently dropped.

## 2. What you need

Python 3.9 or newer. Nothing else — no accounts, no installs, no subscriptions.
To check whether you have it:

```
python3 --version
```

If that shows a version number, you are ready. If it says the command was not
found, install Python from python.org and tick "Add Python to PATH".

## 3. Your credentials

**For this tool: none.** It works on files and never connects to anything. You
can run it on real applications without giving it access to any account.

You only need these if you later connect it directly to Airtable, which is not
part of this delivery:

| Name | What it is |
|---|---|
| `AIRTABLE_API_KEY` | Your Airtable personal access token |
| `AIRTABLE_BASE_ID` | The base it should write to |

We never see or store either one.

## 4. First run

Put your submissions in a file called `submissions.json`, then:

```
python3 src/intake.py submissions.json processed.json
```

You should see something like:

```
Processed 9 submission(s).
  4 ready for the committee
  5 in the exceptions queue
Written to processed.json
```

Open `processed.json`. Every application carries a `status`, an
`application_id`, and a `history` explaining in plain words what was decided and
why. The `history` is what you show an auditor.

To see the counts:

```
python3 src/report.py processed.json
```

There is a sample file to try it on before you use your own data:

```
python3 src/intake.py tests/datos/ejemplo-solicitudes.json processed.json
```

## 5. Check it works

```
python3 tests/test_todo.py
```

Expected output: `ALL TESTS OK`. Run this after changing anything in
`src/config.json`, and any time you are not sure the rules are behaving. It
touches none of your data.

## 6. What the statuses mean

| Status | What it means | What to do |
|---|---|---|
| `ACCEPTED` | Complete and ready | Send it to the committee |
| `INCOMPLETE` | A required field is missing or the email is unusable | Check `missing_fields`, ask the applicant |
| `DUPLICATE` | Same applicant, same cycle, already applied | Decide whether it is a resubmission or a second application |
| `UNKNOWN_CATEGORY` | The category is not one of yours | Usually a form problem — check your form's options |
| `NEEDS_REVIEW` | Complete, but unusual: the amount is above your ceiling | A person decides |

## 7. When something breaks

| What you see | What it means | What to do |
|---|---|---|
| `expected a list of submissions` | The input file is not a JSON list | Re-export it; it must start with `[` |
| `No such file or directory` | Wrong filename or wrong folder | Check you are in the folder with `src/` in it |
| Everything comes out `UNKNOWN_CATEGORY` | Your form's category values do not match | Fix the names in `src/config.json`, section `categories` |
| `WARNING: the counts do not add up` | Applications are going missing | Stop and tell us. This should never happen; a test exists to prevent it |
| More duplicates than expected | Your form is accepting resubmissions | Normal — check the `duplicate_of` field to confirm |

## 8. Changing it yourself

Everything adjustable is in `src/config.json`. Edit it in any text editor, save,
run again. You never need to touch the code.

- **Add or rename a category.** Add an entry under `categories` with its `label`,
  a three-letter `code` for the IDs, and the fields it requires.
- **Change what a category requires.** Edit its `required_fields` list.
- **Change what every category requires.** Edit `always_required`.
- **Change the amount that triggers a review.** Edit `amount_ceiling`. Set it to
  `0` to switch the check off.
- **Change what counts as a duplicate.** Set `duplicate_scope` to `"cycle"` (same
  email twice in one cycle) or `"ever"` (same email at any time).
- **Change the current cycle.** Edit `cycle.current`. Applications that do not
  carry their own cycle get this one.

After any change, run step 5. If a test fails, the change broke a rule you
agreed to, and the failure says which.

## 9. Connecting it to Airtable and Make

See `AIRTABLE_AND_MAKE.md` in this folder: the table structures to import, the
views your staff will actually use, and the two Make scenarios module by module.

## 10. If you hand this to another developer

- `src/intake.py` — all the decisions: validation, duplicates, IDs, routing.
- `src/report.py` — the counts.
- `src/config.json` — every rule that can change without code.
- `src/airtable/*.csv` — the table structures, ready to import.
- `tests/test_todo.py` — every test, one command, no dependencies.
- `HOW_IT_WORKS.md` — the design and the reasoning, in one page.

Standard library only. There is nothing to install and nothing that can go out
of date underneath you.
