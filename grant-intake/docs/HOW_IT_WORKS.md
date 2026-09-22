# How it works

One page, so anyone can pick this up later.

## The shape of it

```
submissions.json → category? → identity? → duplicate? → complete? → unusual?
                        ↓           ↓           ↓            ↓          ↓
                   exceptions  exceptions  exceptions   exceptions   review
                                                                        ↓
                                                                    ACCEPTED
```

Every application leaves with a status, and the ones that got far enough leave
with an ID. Nothing exits without one or the other.

## Why the checks run in that order

**Category first.** Until we know the category, we cannot know what "complete"
means: a research grant requires a supervisor's email, an emergency grant does
not. Checking completeness before category would apply the wrong rules.

**Identity second.** An application with no usable email cannot be tracked,
answered, or compared against others. It goes to a person immediately rather
than being given an ID it can never be reached by.

**Duplicates third, and never deleted.** Only a human can tell a resubmission
("I think the first one failed") from a second, legitimate application. The
system marks it, points at the application it repeats, and stops.

**Completeness fourth**, using that category's own field list.

**Unusual last.** An application can be perfectly complete and still deserve a
second look — an amount far above the normal ceiling, for instance. That is
`NEEDS_REVIEW`, not a rejection.

## The decisions worth knowing

**IDs are readable, not random.** `COM-2026-Q4-0001` is a community grant, the
fourth quarter of 2026, the first of that cycle. Staff read these out on calls
and write them on paper; a random string would make every one of those moments
harder. The sequence restarts each cycle, because anyone reading `0001` expects
it to mean the first.

**The same input always produces the same IDs.** Re-running on the same file
gives the same result. If IDs depended on when you ran it, you could never
re-run to check something.

**Email comparison ignores case and stray spaces.** `ANA@example.org ` and
`ana@example.org` are one person. This is the single most common reason
duplicates survive a naive check.

**Every automatic decision writes a line of history in plain words.** Not a code,
not a flag — a sentence saying what was decided and why. This is what makes the
audit trail usable by somebody who was not there.

**The rules live in a config file, not in the code.** Categories, required
fields, the amount ceiling and the duplicate rule are all in `src/config.json`.
Changing a rule is editing a list, and the tests tell you immediately if the
change broke something you agreed to.

## The counts always add up

`by_status`, `by_category` and `by_cycle` each total the number of applications
processed. A test enforces it. If that ever stops being true, applications are
going missing somewhere and the report cannot be trusted — which is why the
report says so out loud instead of printing numbers that look fine.

## What is not covered

The tests run against synthetic applications, so they prove the decision rules,
not the connection to your Airtable base or your form. Nothing here has ever
talked to your accounts. The first real run is step 4 of the runbook, on your
own data, on your own machine.
