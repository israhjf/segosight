# Architectural decisions

Why SegoSight is built the way it is. Each entry states the decision, what was
rejected, and the evidence that settled it. Read this before proposing a
redesign — most of these look arbitrary until you know what they are defending
against.

Derived from the build conversation, September 2026. Where an entry cites a
count, that count was true at the time of writing and is regenerable from the
warehouse; the *reasoning* is what this document is for.

---

## Contents

1. [Storage and compute](#1-storage-and-compute)
2. [Data modelling](#2-data-modelling)
3. [Identity and reconciliation](#3-identity-and-reconciliation)
4. [Rules and alerting](#4-rules-and-alerting)
5. [Prose extraction and AI](#5-prose-extraction-and-ai)
6. [Application architecture](#6-application-architecture)
7. [Code organisation](#7-code-organisation)
8. [Data quirks the code defends against](#8-data-quirks-the-code-defends-against)
9. [Known limitations](#9-known-limitations)

---

## 1. Storage and compute

### 1.1 DuckDB with stdlib parsing

**Rejected:** pandas (silent NaN and dtype guessing on mixed-format dates —
exactly the failure mode we need to control), Polars (heavier for ~2k rows),
pure SQLite (no window functions worth the name; the 3-consecutive-services
trend rule becomes hand-rolled loops).

Parsing happens in stdlib `csv` for per-row control over date and unit quirks;
aggregation happens in SQL so the business rules stay readable by someone who
isn't the author.

### 1.2 Bulk loading goes through SQL, never `executemany`

DuckDB costs ~1.3 ms per statement from Python. An early build used
`executemany` with `INSERT OR IGNORE` and the suite took **92 seconds**. The
engine wasn't slow — it inserts 6,000 rows in 10 ms — the per-statement
round-trip was. Landing now uses `read_csv(all_varchar=true)` inside DuckDB;
Python-built rows stage through a temp CSV (`shared/warehouse.bulk_insert`).
Suite went 92 s → under 7 s.

`all_varchar` is not incidental: it stops type inference mangling a value before
we've decided what it means.

---

## 2. Data modelling

### 2.1 Readings are long/narrow, one row per parameter

**Rejected:** the source's wide shape, a hybrid.

Decisive reason: the source's `units` column carries a unit **per parameter**
(`cond=uS/cm;hard=gpg`). A wide row physically cannot carry the correct
`raw_unit` for each column. Long form also lets one bad parameter be quarantined
without discarding the whole sample. 1,702 source rows → 6,502 events; trivial
at this scale.

### 2.2 Corrections append and supersede; they never overwrite

**Rejected:** last-batch-wins.

`RD-00923` is re-issued in the September batch with pH corrected from 91.2 to
9.1 — same primary key, no version column. Batch sequence is the only recency
signal. Both rows are kept; `is_current` marks the survivor. Guidelines §2
require annotation rather than deletion, and a hospital compliance packet has to
show that a correction *happened*, not just its result.

**Stricter variant chosen:** a physically impossible value is quarantined on its
own merits, independent of whether a correction later arrives — so an
*uncorrected* typo is caught too.

### 2.3 Trend series are separated by collection method

**Rejected:** pooling all sources per system+parameter.

On SYS-0006 the contract lab reads iron at 0.14–0.51 ppm while the field reads
0.19–1.50 ppm, same equipment, same days. Pooling flattens the corrosion trend
that preceded a $41,800 tube failure. Series identity is
`system × parameter × collection_method`. Guidelines §10: resolve units, sample
point and timing before concluding the water changed.

### 2.4 Chemical doses are mostly unattributable, and we say so

269 of 316 chemical-bearing visits serve multiple systems, and `chemicals_added`
is a flat concatenation with no per-system boundary. Those doses record a null
system and `attribution = 'facility'`. Inventing an assignment would corrupt the
consumption analytics the guidelines rely on to spot a leaking closed loop.

**Consequence:** per-system chemical consumption is not derivable from these
sources. Facility-grain still works — Pintura's 131 gallons of CL-40 is visible.

---

## 3. Identity and reconciliation

### 3.1 Crosswalk confidence gates alerting, not visibility

The lab sample-point crosswalk exists only in a technician's note, and its
author split it into what he was "sure of" and "mostly sure of". That split is
preserved as `confidence`. All six codes resolve and are browsable; the two
medium-confidence ones contribute **zero** alert-eligible readings.

`MRMC-B1` is the reason. Maeser Ridge has two fire-tube boilers, so "boiler 1"
is genuinely ambiguous — and it is a healthcare account, where a wrong join puts
another unit's chemistry into a compliance record.

### 3.2 Duplicate facilities merged on equipment evidence

**Initially decided the opposite,** then reversed when the evidence turned up.

`F-0022` and `F-0021` each own **zero systems**, share a street address with a
sibling facility, and every visit booked against them services the sibling's
equipment. The records contradict themselves; the equipment reference is ground
truth. Left unmerged they split Timpanogos' history 11/3 and Bonneville
Clearfield's 12/2, producing false coverage alerts on A- and B-tier accounts.

Only the Timpanogos merge is documented (Rosa's go-live email). The Bonneville
one appears in no email or note and is mapped at **medium** confidence pending
confirmation — its only corroboration is a `customers.csv` note reading "Entered
during 2025 CRM cleanup".

### 3.3 Equipment replacement is lineage, not a merge

`SYS-0006` and `SYS-0101` are distinct physical units and both records survive
intact. Rosa is explicit: "Do not 'fix' old records, both IDs are real." A test
asserts no `system`-domain merge mapping exists for either ID, so a future
"simplification" fails loudly.

---

## 4. Rules and alerting

### 4.1 Thresholds are configuration with a stamped rule version

`config/treatment_programs.toml` holds every limit, ladder, cadence and seasonal
term. Every assessment records `rule_version` and the exact band applied, so an
operator can see which guideline revision produced a judgement.

### 4.2 Conditional bands read system state, and *unconfirmed* ≠ *failed*

CT-HC2's wide 2,400–3,400 band applies while chloride < 300 ppm and inhibitor
≥ 12 ppm. A BMS telemetry row measures conductivity alone and cannot re-prove
them, so conditions carry forward from the last field test within
`condition_validity_days`.

An early build required them in the same sample. Every BMS point failed the
check and fell back to CT-STD, producing **787 false exceedances** — precisely
what §6.1 forbids reporting. Now: *failed* (measured, out of range) reverts to
CT-STD; *unconfirmed* (not measured) yields `not_evaluated`. False positives: 0.
SYS-0016's genuine inhibitor drop to 11 ppm still reverts the band correctly.

### 4.3 Trend rule: strict consecutive runs, deduplicated downstream

**Rejected:** a net-rise-over-window variant (fires earlier and doesn't flicker,
but diverges from the written guideline an operator would check against).

Literal §4.2 reading: 3+ consecutive same-direction services (`trend_min_run`).
On SYS-0006 iron the condition is first satisfied **2026-03-31 — 155 days before
the failure** — with iron at **0.40 ppm** inside a 2.0 band. The first run is
recorded spanning 2026-03-17 to 2026-04-14. The rule flickers as the series
sawtooths; that is handled by alert deduplication, not by loosening the rule.

### 4.4 High-frequency feeds are resampled to service cadence

§4.2 counts "consecutive services". Three consecutive rising days on a tower is
noise. BMS series are collapsed to a weekly median (median, not mean, so one
dropout can't drag a week) before the same rule runs.

### 4.5 Promotion to an alert differs by risk class

589 raw trend signals is not a queue. Each class earns promotion differently:

- **Corrosion** — fraction of headroom travelled toward its action level.
- **Scaling** — only when a tower actually leaves its band, or drifts 6+
  services. Towers cycle between bleeds by design. Boiler conductivity is
  excluded entirely: blowdown cycles it deliberately, and the guideline's
  example is explicitly towers.
- **Residual loss** — only when the **trough** is falling. Every treated system
  consumes chemical between doses; a sawtooth that recovers is normal operation.
  The guidelines point at the opposite case: a loop that "repeatedly consumes"
  inhibitor.

Result: 589 signals → 32 structured alerts.

> **A bug worth remembering.** The trough test used `min(first_value)` /
> `max(last_value)`, correct for rising series and wrong for falling ones. It
> silently dropped Pintura's nitrite collapse (1050→410 over 15 consecutive
> services), the most dramatic trend in the corpus. Then a headroom guard
> dropped it *again* because its third reading already sat below the floor.
> Both fixed. Directional asymmetry is easy to get wrong.

### 4.6 Coverage is an absence, and seasonal closure is the guard

`visit_status` is 'completed' on 321 of 324 visits — an unserviced site produces
no row at all. Gaps are measured as days since last visit against contracted
cadence.

Powder Basin is 123 days past its last visit **and entirely on schedule**; its
contract reads "monthly (seasonal: closed mid-May to mid-Oct)". Jenn Fowler's
note says it outright: *"That is the contract, not us forgetting them. It trips
people up every summer."* A test asserts no seasonally-closed site ever raises a
coverage alert.

### 4.7 A late work order cannot retroactively document an escalation

§9 requires the record within one business day. Maeser Ridge's CT-2 has exactly
one work order, raised 2026-09-09. Accepting any later work order as evidence
reported a **three-month compliance gap as fully documented**. Evidence must
land inside `documentation_window_days`; later remediation is recorded
separately.

### 4.8 Evaluation date comes from the data, not the clock

`as_of` defaults to the latest observation in the warehouse. Results stay
reproducible, tests assert fixed numbers, and a recorded demo still matches. It
is also honest: the system cannot know about service that happened after its
data ends.

---

## 5. Prose extraction and AI

### 5.1 Deterministic extractors are the product; the LLM is additive

**Rejected:** LLM-only (breaks clone-to-running, non-deterministic tests, no
floor if the model is unavailable).

Rule-based extraction ships and runs with zero setup. `--llm` routes the same
text through a local open-weight model for *additional* candidates at capped
confidence, through the identical review gate.

### 5.2 Nothing from prose is fact until a human approves it

Every extraction lands `status = 'pending_review'` with a confidence score and
the verbatim sentence it came from. Approval is attributable and promotes into
governed tables; rejection detaches evidence without deleting the row. A test
asserts the governed crosswalk still holds exactly its curated mappings despite
identity candidates being proposed.

### 5.3 The model must cite its evidence or be discarded

A candidate whose `quote` does not appear verbatim in the source document is
dropped. Fabricated quotes are the main failure mode, and this contains it —
the failure becomes lost recall, not corrupted data. Entity attribution from the
model is ignored and re-derived deterministically.

### 5.4 Provenance is labelled honestly

The UI shows "Confidence" with a **Rule-based** or **AI-assisted** chip driven
by the `extractor` column. Labelling regex output as AI would overstate what the
system does and hide the rows that genuinely warrant more scepticism.

### 5.5 Fulfilment evidence must match the deliverable

A service visit evidences a promised *visit*. It evidences nothing about a
promised accreditation packet. An early build marked Maeser Ridge's
documentation request fulfilled because an unrelated site visit happened.
Document and plan commitments now stay `NULL` with the reason stated — there is
no outbound-document store to evidence them.

---

## 6. Application architecture

### 6.1 One process owns the warehouse, so ingestion is a product action

DuckDB permits one writer. Rather than fight it, the API holds the connection
and exposes the pipeline as a button with before/after counts. Re-running is
safe (the raw tier is content-addressed) and reviewer decisions are re-applied
after a rebuild — a human judgement is not a derived value.

Side benefit: "incorporate the second data batch" becomes something the
operations director does herself.

### 6.2 Every request gets its own cursor

FastAPI runs sync endpoints in a threadpool. A DuckDB connection holds its
result set on the connection, so three concurrent dashboard requests sharing one
connection read each other's rows — `/api/overview` deserialised review rows and
returned a 500. `get_connection()` now returns `conn.cursor()`.

`TestConcurrency` catches it: reverting the fix fails 3 tests. `TestClient`
issues requests serially, which is exactly why the original bug survived the
suite.

### 6.3 The UI degrades panel by panel

`Promise.allSettled`, not `Promise.all`. One failing endpoint used to discard
two successful responses and blank a page that still had most of its data.

### 6.4 Chart colours were validated, not chosen

The Material scheme is monochromatic by design: its primary (#415f91) and
tertiary (#705575) sit at **ΔE 7.9** in normal vision against a floor of 15.
Using them as two chart series would have produced a chart most people cannot
read. `ui/src/design-system/chart.ts` holds a separate verified pair per mode,
clear of the reserved status colours.

---

## 7. Code organisation

### 7.1 Features are vertical slices with tier sub-folders

Domain first, tier second: `features/chemistry/{clean,canonical,curated}/`.
Answering "how does a reading become an alert" is one directory instead of five,
while the tier stays visible in the path. Routers live with their feature.

### 7.2 Configuration stays central

`segosight/config/*.toml` are operator-editable governance artefacts, not code.
`treatment_programs.toml` transcribes the client's binder; `identity.toml`
records approved merges. A steward should find every tunable in one directory
without navigating source. Features own the typed loaders.

### 7.3 `shared/` means at least two consumers

Cross-cutting normalization (dates, numerics, delimited fields) is shared.
`units.py` and `quality.py` encode water-treatment rules and live in
`chemistry`. The test applied throughout: *would a second product reuse this
unchanged?*

---

## 8. Data quirks the code defends against

Before simplifying a parser, check this list.

| Quirk | Where | Defence |
| --- | --- | --- |
| Two date formats **inside one file** — BMS rows `M/D/YY`, field rows ISO | `water_readings.csv` | Format detected per value. The supplied data dictionary says otherwise and is wrong. |
| `inhibitor_ppm` is **polymorphic** — molybdate (188–311 ppm) or inhibitor (7.2–19 ppm) | readings | Resolved from the `units` declaration, never the column name. Different control bands. |
| Conductivity switches mS/cm → uS/cm on **2026-07-14**, mid-file | SYS-0014..0017 BMS | `units` column governs. Corroborated by Fowler's 7/15 note about a controller swap. |
| Hardness sometimes in grains per gallon | 21 rows | × 17.1, only when notation confirms it. |
| Same primary key re-issued with corrections | `RD-00923` | Append + supersede by batch sequence. |
| Zero conductivity (3 rows) vs zero hardness (22 rows) | readings | Zero conductivity is a dropout → suspect. Zero hardness is the boiler **target** → valid. |
| pH 91.2 | `RD-00923` original | Physically impossible → quarantined regardless of correction. |
| Lab writes its own sample codes into `system_id` | 36 lab rows | Governed crosswalk with confidence; 0 orphans remain. |
| Duplicate facilities owning zero systems | `F-0021`, `F-0022` | Merged on equipment evidence. |
| Technician names vs FieldFlow initials | visits | Canonical employee resolution; ambiguous initials flagged, never guessed. |
| `systems_serviced` / `chemicals_added` are delimited strings | visits | Exploded to first-class events; repeated segments are real doses, not duplicates. |
| Seasonal closure hidden inside `service_frequency` | `F-0008` | Parsed; cadence takes the leading token only. |

---

## 9. Known limitations

- **Per-system chemical consumption is not derivable** (§2.4). Facility grain only.
- **Inventory is a snapshot with no transaction history.** Stockout risk and
  projected days-of-supply are not built; `chemical_inventory.csv` is landed but
  unused by alerting.
- **Alert evidence is matched at facility level**, so some prose citations are
  loosely relevant. Each carries its review status so provenance is visible
  rather than asserted.
- **The UI has not been visually verified** by its author — no browser tooling
  was available. Types check, the bundle builds, the API is tested against real
  data, but layout and chart rendering at real widths are unconfirmed.
- **Two source documents are not in the repo**: the supplied data dictionary and
  the Foundry ontology design existed only as conversation attachments. Several
  decisions above reference them.
