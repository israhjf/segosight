# Writeup

## What I built, and why

One ranked queue of sites needing attention, with the evidence attached.

SYS-0006's iron climbed from 0.19 to 1.50 ppm over five months, then the boiler
failed and cost $41,800. Every reading was
inside its limit, so a threshold dashboard would have shown green throughout.
The system detects *trends* (guidelines §4.2); limits are secondary.

## Who it's for

Dana Whitlock, Operations Director. Not a data person. She gets a list sorted by
consequence that she can act on.

## Architecture

Python, DuckDB, FastAPI, React/MUI. Four tiers as DuckDB schemas: raw
(immutable, content-addressed), clean (parsed, superseded), canonical (identity
resolved), curated (business rules).

DuckDB because the client has no IT staff and no platform budget — it's one
file. The tradeoff is a single writer, so the API owns the connection and
ingestion is a button, not a terminal command.

Thresholds live in TOML with a `rule_version` stamped on every judgement: a
guideline revision is a config change, not code.

## Assumptions

- The `treatment_program` on the system record governs, never the observed
  chemistry. 2,900 µS/cm is normal on a CT-HC2 tower and serious on a BP-HP
  boiler.
- The `units` column governs; a unit is never inferred from a value's size.
  Conductivity switches mS/cm to uS/cm mid-file, and guessing would invent a
  1000× excursion.
- Batch order decides which re-issued record wins — there's no version column,
  so it's the only recency signal.

## Limitations and risks

- **85% of chemical doses can't be attributed to a system.** 269 of 316 visits
  serve several systems and `chemicals_added` is one flat string. Left null
  rather than split evenly, which would be fabrication.
- **Inventory is loaded but unused.** A snapshot with no transaction history, so
  any stockout projection would be a guess.
- **The upload flow's confirm step has never run end to end.** Its parts are
  unit-tested, but it writes to real config, so I didn't test it live.
- **No frontend test runner.** The UI is covered by typecheck and build only.

## Unresolved

The lab crosswalk exists only in a technician's note, where he split it into
what he was "sure of" and "mostly sure of". I kept that split: uncertain codes
resolve but raise no alerts. Maeser Ridge has two fire-tube boilers, so "boiler
1" is genuinely ambiguous — and it's a hospital.

I also merged a duplicate facility no email or note mentions. Flagged medium
confidence, pending confirmation.

## AI inside the product

Off by default. A local model proposes extra candidates from prose, capped at
0.55 confidence, through the same review gate. Its quote must appear verbatim in
the source or the candidate is discarded, which kills the fabrication failure
mode. The deterministic extractors are the product; the model is additive.

Nothing from prose reaches a compliance record without a named human approving
it.

## What I'd build next

Alert triage: assign, snooze, close with a reason. Dana can see the queue but
can't record what she did, so week two is as noisy as week one.
