# SegoSight

An operational attention system for Sego Industrial Water.

**Primary user:** Dana Whitlock, Operations Director. SegoSight answers her
Monday-morning question — which sites need attention, why, what it costs if we
sit on it, and who is doing what about it — from the company's existing
fragmented exports, without anyone hand-cleaning a spreadsheet first.

## Setup

```bash
./run.sh            # venv, deps, warehouse, UI build, serve on :8000
```

Then open <http://127.0.0.1:8000>. Use `./run.sh dev` for the Vite dev server
with hot reload on :5173.

Running the pieces individually:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m pytest -q               # 302 tests, ~6s
./.venv/bin/python -m segosight.app.pipeline  # build the warehouse, ~2s
./.venv/bin/python -m segosight.features.review.cli list   # review queue (CLI)
cd ui && pnpm install && pnpm run build       # UI bundle
```

Requires Python 3.11+ and Node 20+. Python deps: `duckdb`, `pypdf`, `fastapi`,
`uvicorn`, `pydantic`, `pytest`, `httpx`.

Source data is read in place from `bedrock-fde-exercise-candidate/materials/`
and never modified. Point the pipeline at a different drop with:

```bash
export SEGOSIGHT_MATERIALS=/path/to/materials
```

## Layout

| Path | Purpose |
| --- | --- |
| `segosight/features/` | One vertical slice per domain; tier sub-layers inside |
| `segosight/features/ingestion/` | Source registry, immutable landing, supersede |
| `segosight/features/identity/` | Crosswalk, canonical master data, asset lineage |
| `segosight/features/chemistry/` | Readings, series, control limits, assessments, trends |
| `segosight/features/service/` | Visits, chemical applications, coverage |
| `segosight/features/compliance/` | Microbiological escalation ladder |
| `segosight/features/alerts/` | Alert aggregation, ranking, evidence, router |
| `segosight/features/review/` | Documents, extraction, LLM, promotion, router, CLI |
| `segosight/shared/` | Warehouse, paths, domain-agnostic normalization |
| `segosight/app/` | FastAPI factory, DuckDB lock, pipeline orchestrator |
| `segosight/config/` | Governed TOML: sources, identity, treatment programs |
| `ui/src/design-system/` | Material tokens, modes, validated chart colours |
| `ui/src/features/` | overview · alerts · review · pipeline |
| `tests/` | Unit tests plus corpus-wide validation against the real CSVs |

## Tiers

| Tier | Contents | Rule |
| --- | --- | --- |
| `raw.records` | Every source row as JSON + provenance, content-addressed | Never deduplicated, corrected or dropped |
| `clean.record_versions` | Which version of each business key is current | Append-and-supersede, never overwrite |
| `clean.water_readings_long` | One row per parameter, raw + normalized | Conversion only where the source declared a unit |
| `canonical.identity_resolution` | Source ID to canonical ID decisions | Every mapping carries evidence, confidence and authorization |
| `canonical.customer` / `.facility` / `.system` | Master data, merges applied | Surviving record's own attributes win |
| `canonical.reading_event` | Readings with identity and series resolved | `alert_eligible` gates uncertain identity out of alerting |
| `curated.reading_assessment` | Program-aware limit judgements | Thresholds come from config, never hard-coded |
| `curated.trend_signal` | Sustained-movement evidence | Evidence, not alerts |
| `curated.coverage_status` | Cadence vs actual, seasonal-aware | Absence is the signal |
| `curated.microbio_escalation` | §5 ladder plus documentation state | A late work order does not retroactively document |
| `curated.operational_alert` | Deduplicated, ranked queue | One alert per risk fingerprint |
| `raw.documents` | Notes and email, text extracted | Failures land visible, never skipped |
| `curated.extracted_insight` | Prose-derived candidates | Always `pending_review` with a confidence score |
| `curated.alert_evidence` | Prose attached to alerts | `primary` evidence gates the banner, `corroborating` does not |
| `curated.customer_commitment` | Promises promoted by a reviewer | Only written after a named human approves |

## Incorporating a new data batch

Append a `[[batches]]` entry to `config/sources.toml` pointing at the new
directory. Existing entity globs match renamed files (`service_visits.csv` and
`service_visits_2026-09.csv` share one pattern), new columns are absorbed into
the JSON payload and reported as drift, and `sequence` decides which version of
a re-issued record wins. Re-running the pipeline is idempotent.

## Design decisions

These are recorded here because each one is load-bearing and non-obvious.

**Timestamps are detected per value, not per file.** The supplied data
dictionary states that legacy files are ISO and only the FieldFlow batch is
American-format. That is not true: `water_readings.csv` carries `M/D/YY H:MM`
on BMS rows and `YYYY-MM-DD HH:MM` on field/lab rows *in the same file*.

**The `units` column governs, always.** Guidelines §2 require conversion only
when notation confirms the source unit, so we never infer a unit from a value's
magnitude. This matters: BMS conductivity for SYS-0014..0017 switches mS/cm to
uS/cm on 2026-07-14 mid-file, and magnitude-based guessing would manufacture a
1000× step change on four critical CT-HC2 towers.

**`inhibitor_ppm` is polymorphic.** With `moly` declared it carries molybdate
(188–311 ppm, CL-M loops); with `inhib` it carries corrosion inhibitor
(7.2–19 ppm, CT towers). Different control bands. The declaration is the only
discriminator, so parameter identity is resolved from it rather than from the
column name.

**Readings are stored long/narrow**, one row per parameter. Units are already
per-parameter in the source, so a wide row physically cannot carry the correct
`raw_unit` per column.

**Impossible values are quarantined on their own merits.** A pH outside 0–14 is
`invalid` whether or not a correction later arrives, so uncorrected typos are
caught too. Rows are retained and annotated, never deleted (§2, §4.1).

**Zero is read in context.** Zero conductivity is a BMS dropout (`suspect`).
Zero hardness is the *target* on boiler feedwater and zero sulfite is a real
depletion finding — both stay `valid` for the control-limit rules to judge.

**Trends run within a single collection method.** Lab and field disagree ~3:1
on the same system and date; pooling them flattens the corrosion signal that
preceded a $41,800 boiler failure.

**Identity confidence gates alerting, it does not gate visibility.** The lab
crosswalk exists only in a technician's note, and its author split it into what
he was "sure of" and "mostly sure of". That split is preserved: all six codes
resolve, but `CLPK-B1` and `MRMC-B1` are medium confidence and contribute zero
alert-eligible readings. Maeser Ridge has two fire-tube boilers, so "boiler 1"
is genuinely ambiguous — and it is a healthcare account, where a wrong join
would put another unit's chemistry into a compliance record.

**Two duplicate facilities were merged on equipment evidence.** `F-0022` and
`F-0021` each own zero systems, share a street address with a sibling facility,
and every visit booked against them services the sibling's equipment. Only the
Timpanogos duplicate is documented (Rosa's go-live email); the Bonneville one
appears in no email, note or data dictionary and is mapped at medium confidence
pending confirmation. Left unmerged, both would produce false coverage alerts.

**Equipment replacement is lineage, not a merge.** `SYS-0006` and `SYS-0101` are
distinct physical units and both records survive intact, per Rosa's explicit
instruction not to "fix" old records. The link records continuity of service
without stitching their trend series together.

**Control limits are configuration, and evaluation is program-aware.** All
thresholds live in `config/treatment_programs.toml` with a `rule_version`
stamped on every judgement. CT-HC2's conditional 2,400–3,400 band is evaluated
against carried-forward system state rather than per row, because a BMS point
measures conductivity alone and cannot re-prove chloride and inhibitor. A
condition that is *unconfirmed* is not a condition that *failed*: §6.1 says
1,800–3,400 on an enrolled HC2 tower "must not be reported to the customer" as
an exceedance, so unconfirmed yields `not_evaluated`. Treating those alike
produced 787 false exceedances in an early build; it is now 0.

**A late work order does not retroactively document an escalation.** §9 requires
the record within one business day. Maeser Ridge's CT-2 has exactly one work
order, raised 2026-09-09; accepting any later work order as evidence reported a
three-month compliance gap as fully documented. Evidence must land inside the
window, and later remediation is noted separately.

**Alerts are ranked by consequence, and promotion differs by risk class.**
Raw trend detection yields 589 signals — unusable as a queue. Corrosion is
promoted on distance travelled toward its action level; scaling only when a
tower actually leaves its band or drifts for 6+ services, because towers cycle
between bleeds by design; residual loss only when the *trough* is falling, since
every treated system consumes chemical between doses. Boiler conductivity is
excluded from scaling entirely — blowdown cycles it deliberately.

**Prose proposes; only a human disposes.** Every fact extracted from a note or
email lands in `curated.extracted_insight` with `status = 'pending_review'` and
an explicit `confidence_score`, quoting the sentence it came from. Nothing in
the pipeline writes an extraction into the identity crosswalk, a control limit
or a compliance record. Alerts that rest on an unreviewed extraction are
stamped `evidence_basis = 'prose_pending_review'` so a reader can tell.

**Fulfilment evidence must match the deliverable.** A service visit evidences a
promised visit. It evidences nothing about a promised accreditation packet, and
the system says so rather than guessing — Sego has no outbound-document store,
so those commitments stay `NULL` with the reason stated.

**AI is optional and additive.** The deterministic extractors are the product.
`--llm` routes the same text through a local open-weight model to propose extra
candidates at a capped confidence, through the identical review gate. Its main
failure mode — fabricated quotes — is contained by discarding any candidate
whose quote is not found verbatim in the source document.

**One process owns the warehouse, so ingestion is a product action.** DuckDB
permits a single writer. Rather than fight that, the API holds the connection
and exposes the pipeline as a button, with before/after counts. Re-running is
safe — the raw tier is content-addressed — and reviewer decisions are re-applied
after a rebuild rather than reset, because a human judgement is not a derived
value.

**Chart colours were validated, not chosen by eye.** The Material scheme is
deliberately monochromatic: its primary and tertiary sit at ΔE 7.9 in normal
vision, well under the 15 floor, so using them as two chart series would have
produced a chart most people cannot read. The series ramp in
`ui/src/theme/chart.ts` is a separate, verified pair for each mode, kept clear
of the reserved status colours.

**Chemical doses are mostly unattributable to a system.** 269 of 316
chemical-bearing visits serve multiple systems, and `chemicals_added` is a flat
concatenation with no per-system boundary. Attribution would be fabrication, so
it stays null for multi-system visits.
