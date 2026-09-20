# Data quirks

Every deliberate trap in the Sego corpus, what defends against it, and how to
verify the defence still works.

**Read this before simplifying a parser.** Code in this repo that looks
over-defensive usually isn't — most of it is holding one of these lines. Each
entry names the test that fails if the defence is removed.

Figures verified against the warehouse; regenerate with
`./.venv/bin/python -m segosight.app.pipeline`.

---

## 1. Two date formats inside one file

**Where** `water_readings.csv` — BMS rows use `M/D/YY H:MM`, field and lab rows
use `YYYY-MM-DD HH:MM`. Same file, same column.

**The trap** The supplied data dictionary states that legacy files are ISO and
only the FieldFlow batch is American-format. That is wrong. A parser that picks
one format per file drops roughly half the readings or misreads them.

**Defence** Format is detected **per value** against an ordered candidate list
(`shared/normalize/temporal.py`). Month-first is the declared convention for
slash dates (Rosa Camacho's go-live note); ambiguous values are resolved
month-first and flagged `ambiguous` in `detail` for audit.

**Guard** `test_temporal.py::TestMixedFormatsWithinOneFile` and
`test_corpus.py::test_both_conventions_are_actually_present_in_the_legacy_file`
— the latter asserts the dictionary's claim is false.

---

## 2. `inhibitor_ppm` is a polymorphic column

**Where** `water_readings.csv` — the same column carries two different
chemicals with two different control bands.

| Declared in `units` | Parameter | Observed range | Band |
| --- | --- | --- | --- |
| `moly` | molybdate | 188–311 ppm | CL-M: 200–300 |
| `inhib` | corrosion inhibitor | 7.2–19 ppm | CT-770: 8–14 · CT-785: 12–18 |

**The trap** Judging the column by its name evaluates molybdate against an
inhibitor band. 234 ppm is normal molybdate and absurd as a tower inhibitor
residual.

**Defence** Parameter **identity** is resolved from the `units` declaration, not
the column name (`features/chemistry/units.py`, `resolve_parameter`). Four rows
declare nothing; they fall back with `UNIT_NOT_DECLARED` rather than being
guessed from magnitude.

**Guard** `test_units.py::TestPolymorphicInhibitorColumn`, including
`test_molybdate_and_inhibitor_occupy_disjoint_ranges`.

---

## 3. Conductivity units switch mid-file

**Where** `SYS-0014`–`SYS-0017` BMS feed, **2026-07-14**. mS/cm → uS/cm.
All four series carry `distinct_raw_units = 2` across 197 observations.

**The trap** Raw values jump from ~2.9 to ~2900 overnight on four *critical*
cooling towers simultaneously. Inferring units from magnitude manufactures a
1000× excursion.

**Defence** The `units` column governs, always. Guidelines §2: *"Where a record
carries its own unit notation, the notation governs over any assumption."*
Conversion happens only when notation confirms the source unit. Post-conversion,
SYS-0014's mean is **2861.0 before** and **2845.8 after** — 0.5% apart.

**Corroboration** Jenn Fowler's note of 2026-07-15 explains it: a vendor swapped
the tower controller on 7/14 and the alarm thresholds carried over unchanged.

**Guard** `test_clean.py::test_unit_switch_does_not_create_a_step_change`.

---

## 4. Hardness sometimes in grains per gallon

**Where** 21 readings declare `hard=gpg` instead of `ppm CaCO3`.

**The trap** 22.5 gpg and 385 ppm are the same water. Unconverted, gpg rows look
like near-zero hardness.

**Defence** × 17.1 (guidelines §2), applied only when the notation confirms it.

**Guard** `test_units.py::test_grains_per_gallon_scales_by_17_1`.

---

## 5. A primary key re-issued with corrections

**Where** `RD-00923` appears in both batches. pH `91.2` → `9.1`, with a note:
*"CORRECTED RECORD: pH transcription error in prior export."*

**The trap** There is no version column. Corrections arrive as same-key
re-issues, so a naive load either duplicates or silently overwrites — and
overwriting destroys the evidence that a correction happened, which a hospital
compliance packet needs.

**Defence** Append and supersede, keyed on batch sequence
(`features/ingestion/clean/versioning.py`). Both rows survive; `is_current`
marks the survivor.

**Independent corroboration** Dale Hardy's PDF field record for the same system
and date reads `PH 9.1 NITRITE 1000 COND 2675` — the corrected value.

**Guard** `test_clean.py::TestVersioning`, including
`test_the_superseded_version_is_retained_not_deleted`.

---

## 6. Zero means different things in different columns

| Column | Rows at zero | Verdict | Why |
| --- | --- | --- | --- |
| conductivity | 3 | **suspect** | Treated water always conducts; this is a BMS dropout |
| total_hardness | 22 | **valid** | Zero is the *target* on boiler feedwater (§3.1: below 2 ppm) |
| sulfite | 1 | **valid** | Real depletion — a finding for the rules layer, not a parse defect |

**The trap** A blanket "zero is missing data" rule discards 22 healthy boiler
readings and hides a genuine sulfite depletion.

**Defence** `features/chemistry/quality.py` checks zero **only** for
conductivity.

**Guard** `test_quality.py::TestZeroHandling`.

---

## 7. Physically impossible values

**Where** `RD-00923` original: pH **91.2**.

**Defence** Guidelines §4.1 — values outside the 0–14 pH scale and negative
concentrations are instrument or recording errors *by definition* and must not
drive a treatment response. Quarantined as `invalid`, **retained** as evidence,
and quarantined **on their own merits** — so an uncorrected typo is caught even
without a later correction.

**Guard** `test_quality.py::test_impossible_value_is_quarantined_without_needing_a_correction`.

---

## 8. The lab writes its own codes into `system_id`

**Where** 36 lab readings carry sample-point codes — `BONF-OGD-B2`, `MRMC-B1`,
`SALT-HP1/2`, `CLPK-B1`, `BONF-CLF-B1` — not Sego system IDs.

**The trap** These orphan against `systems.csv`. Dropped, the contract lab's
data vanishes; force-joined, it lands on the wrong equipment.

**Defence** A governed crosswalk (`config/identity.toml`) built from Marcus
Webb's note of 2026-04-16 — which separates what he was *sure of* from what he
was *mostly sure of*. That split is preserved as `confidence`:

- **high** (4 codes) — resolve and are alert-eligible.
- **medium** (`CLPK-B1`, `MRMC-B1`) — resolve for display, contribute **zero**
  alert-eligible readings.

`MRMC-B1` is the reason the distinction exists: Maeser Ridge has two fire-tube
boilers, so "boiler 1" is ambiguous — at a healthcare account, where a wrong
join puts another unit's chemistry into a compliance record.

**Result** 0 orphaned reading events.

**Guard** `test_canonical.py::TestLabSamplePointResolution`.

---

## 9. Duplicate customers and facilities

| Source | Canonical | Confidence | Evidence |
| --- | --- | --- | --- |
| CUST-0019 | CUST-0007 | high | Rosa's go-live email, explicit |
| F-0022 | F-0009 | high | Same address; **zero systems**; visits service F-0009's equipment |
| F-0021 | F-0003 | **medium** | Same pattern — documented **nowhere** |

**The tell** Both duplicate facilities own **zero systems**. You cannot service
a plant with no equipment. Every visit booked against them references the
sibling's systems, so the records contradict themselves and the equipment
reference is ground truth.

**The trap** Left unmerged, service history splits 11/3 (Timpanogos) and 12/2
(Bonneville Clearfield), producing **false coverage alerts on A- and B-tier
accounts**.

**Note** F-0021 appears in no email, note or data dictionary. Its only
corroboration is a `customers.csv` note: *"Entered during 2025 CRM cleanup."*
Medium confidence, pending confirmation.

**Guard** `test_canonical.py::TestFacilityMerge`.

---

## 10. Technician names versus FieldFlow initials

**Where** Legacy ServiceTrak exports use full names (`Jenn Fowler`); the
September FieldFlow batch uses initials (`JF`, `MW`, `TR`, `DH`, `AS`).

**Defence** Canonical employee resolution (`shared/normalize/actors.py`).
Initials resolve **only when unambiguous**; a collision flags
`AMBIGUOUS_ACTOR` rather than guessing. Non-person actors (`BMS export`,
`Central Analytical`) are typed separately and excluded from initials matching.

Departed staff still resolve — Kyle Bishop left mid-July 2026, and his
March–July visits are legitimate history.

**Guard** `test_identity.py`, including
`test_ambiguous_initials_are_flagged_rather_than_guessed`.

---

## 11. N:M relationships trapped in delimited strings

**Where** `systems_serviced` (`SYS-0001;SYS-0002`) and `chemicals_added`
(`BW-210 3 gal; BW-305 1 gal`).

**The trap** Repeated segments look like duplicates. Visit V-0001 lists
`CT-770 6 gal; BIO-12 1 gal; CT-770 6 gal; BIO-12 1 gal` because **two towers
were each dosed**. Deduplicating halves recorded consumption.

**Harder limit** 269 of 316 chemical-bearing visits serve multiple systems, and
the dose list is a flat concatenation with no per-system boundary. Attribution
is **not recoverable** for ~85% of doses — those record a null system and
`attribution = 'facility'` rather than inventing one.

**Guard** `test_delimited.py::test_repeated_segments_are_distinct_doses_not_duplicates`
and `test_dose_attribution_is_impossible_for_most_visits`.

---

## 12. Contract terms hidden inside a cadence field

**Where** `customers.csv.service_frequency` for F-0008 reads
`"monthly (seasonal: closed mid-May to mid-Oct)"`.

**The trap** Powder Basin Lodge is **123 days** past its last visit and entirely
on schedule. Guidelines §7: *"A seasonal site showing no visits during its
documented closure window is on schedule, not neglected."* Jenn Fowler put it
plainly: *"That is the contract, not us forgetting them. It trips people up
every summer."*

**Defence** Cadence parsing takes the **leading token only**
(`features/chemistry/programs.py`, `cadence_for`); the closure window is
declared in `config/treatment_programs.toml`.

**Guard** `test_curated.py::test_no_seasonal_site_raises_a_coverage_alert`.

---

## 13. Coverage failures are invisible as records

**Where** `visit_status` reads `completed` on **321 of 324** visits. The other
three are `missed - rescheduled`.

**The trap** A site that was never serviced produces **no row at all**. There is
no flag to read. Kestrel's nine-week gap is an absence, not a record.

**Defence** Coverage is computed as days since last visit against contracted
cadence, per facility, evaluated as of the latest observation in the data —
never the system clock, so results stay reproducible.

**Guard** `test_curated.py::TestCoverage`.

---

## 14. Schema drift between batches

**Where** `service_visits_2026-09.csv` adds a `source_system` column that the
legacy export lacks; `systems_update_2026-09.csv` is a differently-named file
matching the same entity.

**Defence** The raw tier stores whole rows as JSON, so a new column needs no
migration. Drift is **detected and reported**, not silently absorbed — the
pipeline prints `[+source_system]`. Entity discovery is glob-based
(`config/sources.toml`), so a renamed file matches the existing pattern.

**Guard** `test_ingest.py::TestSchemaDrift`.

---

## 15. Programs govern, not observed chemistry

**Where** CT-HC2 towers intentionally run at 2,400–3,400 uS/cm; BP-HP boilers
run much tighter than BP-STD.

**The trap** Judged against CT-STD's 800–1,800 band, every CT-HC2 reading is an
exceedance. An early build produced **787 false exceedances** this way.
Guidelines §6.1 forbids reporting them: conductivity between 1,800 and 3,400 on
an enrolled HC2 system *"must not be reported to the customer"* as one.

**Defence** The band comes from the `treatment_program` field on the **system
record**, never inferred from a value. CT-HC2's conditional band carries
prerequisites (chloride < 300, inhibitor ≥ 12) evaluated against carried-forward
system state — and *unconfirmed* is distinguished from *failed*: an unmeasured
condition yields `not_evaluated`, never an exceedance.

Current false positives in that window: **0**.

**Guard** `test_curated.py::TestProgramAwareAssessment`.

---

## Verifying the defences

```bash
./.venv/bin/python -m pytest -q                    # all 305
./.venv/bin/python -m pytest tests/test_corpus.py -q   # every primitive over the real corpus
```

`test_corpus.py` runs each normalization primitive across all 1,702 readings and
324 visits, asserting that every timestamp parses, every declared unit is
recognised, every dose segment parses and every technician token resolves. It
catches regressions that hand-picked literals would miss.
