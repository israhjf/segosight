# Foundry ontology design (reference)

The object-model design that shaped SegoSight, reproduced here because it
existed only as a conversation attachment and several architectural decisions
cite it.

> **This is a reference design, not a description of the build.** SegoSight is
> a Python/DuckDB/FastAPI system, not a Palantir Foundry deployment. The object
> boundaries, link cardinalities and action semantics below informed the data
> model; the implementation diverges in the places recorded in
> [§ Divergences](#divergences) at the end. Where this document and the code
> disagree, **the code and [`decisions.md`](decisions.md) are authoritative.**

The design's stated goal: make a facility's operational state navigable in one
place — equipment, treatment program, service coverage, chemistry, open risks,
chemical consumption, accountable follow-up. Model durable business entities as
Object Types, observations and occurrences as event Object Types, and use links
to preserve provenance rather than embedding relational lists in properties.

Primary user: **Dana Whitlock**, Operations Director, with **Rosa Camacho** as
dispatch and follow-up.

---

## 1. Object types

### Commercial and location

| Object | Grain | Why it exists |
| --- | --- | --- |
| `CustomerAccount` | One legal customer; canonical `customer_id` | Account tier, ACV, contract risk, SLA, canonical identity after duplicate resolution |
| `Facility` | One serviced physical location; `facility_id` | Separates a corporate account from a plant, hotel or hospital site. The key account-at-a-glance context |
| `Contact` | One named customer contact at a facility | Ties commitments and escalations to a person rather than burying them in email |
| `Employee` | One canonical person | Resolves legacy full names and FieldFlow initials (`MW`, `TR`) to a stable identity |
| `ServiceContract` | One contract version per customer/facility | Cadence, effective dates, SLA, seasonal closure terms. Versioned, not mutable fields on a facility |

### Physical assets

| Object | Grain | Why it exists |
| --- | --- | --- |
| `WaterSystem` | One treated system; canonical `system_id` | Common abstraction for boilers, towers, evaporative condensers, closed loops. Carries program, criticality, status, capacity, lifecycle |
| `SteamBoiler` | One boiler | Only if boiler-specific typed properties are needed (pressure class, feedwater configuration, condensate return) |
| `CoolingSystem` | One tower or evaporative condenser | When tower type, cells, bleed control or biocide regime matter in workflows |
| `ClosedLoop` | One closed loop | When nitrite-vs-molybdate program, loop volume or make-up events need a dedicated model |
| `AssetLineage` | One approved predecessor/successor relationship | Equipment replacement or rental continuity **without overwriting historical identity**. Needed for SYS-0006 → SYS-0101 |

### Operational events

| Object | Grain | Why it exists |
| --- | --- | --- |
| `ServiceVisit` | One scheduled or completed visit; `visit_id` | Date/time, assigned and completing technician, status, observations, follow-up, source system, provenance |
| `SystemService` | One system serviced during one visit | Junction **event**, resolving the semicolon-delimited `systems_serviced` into a first-class record that can later hold per-system detail |
| `ChemicalApplication` | One product dose to one system during one visit | Product, quantity, unit, converted quantity, purpose, operator, timestamp. Drives consumption analytics and inventory decrement |
| `WorkOrder` | One repair/remediation; `wo_id` | Status, priority, owner, cost, resolution, opened/resolved timestamps, recurrence context |
| `CustomerCommunication` | One inbound/outbound email, request or notice | Preserves the original and connects it to account, facility, system, commitment, alert or work order |
| `CustomerCommitment` | One promise requiring completion | Promised visit, treatment plan, documentation packet. The guidelines require emailed commitments be tracked to completion |

### Measurement

| Object | Grain | Why it exists |
| --- | --- | --- |
| `WaterReading` | One observation of **one parameter**, system, timestamp and source | Long/narrow event grain rather than a sparse wide row |
| `MeasurementSeries` | One system × parameter × source context | Series identity, unit, parameter semantics, expected cadence, source quality. Supports high-frequency data without making every sample a heavyweight object |
| `ReadingAssessment` | One evaluation of a reading or window | Validity status, out-of-band, trend status, severity, governing limit version, explanation, human disposition — **separate from raw evidence** |

### Risk, inventory, governance

| Object | Grain | Why it exists |
| --- | --- | --- |
| `OperationalAlert` | One actionable, deduplicated concern | Persistent work-management object. **Distinct from raw anomaly rows** |
| `ChemicalProduct` | One SKU | Product identity, approved unit conversions, application class, safety metadata |
| `InventoryPosition` | `location_id` + `product_code` | On-hand, reorder point, on-order, expected receipt, count timestamp, confidence |
| `InventoryTransaction` | One receipt, transfer, adjustment or consumption | Necessary for trustworthy write-back; a snapshot alone cannot support auditability |
| `IdentityResolution` | One source-identifier → canonical decision | Aliases, duplicate mergers, lab sample points, employee initials, migrated IDs. Effective dates, confidence, reviewer, evidence |
| `TreatmentProgram` | One governed program version | BP-STD, BP-HP, CT-STD, CT-HC2, CL-N, CL-M. **Do not hard-code thresholds in applications** |
| `ControlLimit` | Program × parameter × effective version | Lower/upper/action thresholds, standard unit, severity policy, exceptions |
| `SamplingPlan` | One system/contract sampling requirement | Routine cadence, weekly healthcare dipslide requirement, re-test windows, seasonal exceptions |

### Why `WaterReading` is long-form

The recommended shape:

```
WaterReading
  reading_id · system_id · measurement_series_id · observed_at
  parameter_code            # conductivity, ph, iron, nitrite, dipslide…
  raw_value · raw_unit
  normalized_value · standard_unit
  collection_method         # field | lab | BMS
  sample_point_id · collected_by_actor_id
  source_record_id · source_system
  quality_status            # valid | suspect | invalid | unresolved
  quality_reason · correction_of_reading_id · ingestion_timestamp
```

A wide schema grows sparse and rigid as parameters, lab feeds and BMS tags are
added. The long form directly supports the operating rules: normalize mS/cm to
uS/cm, normalize gpg to ppm as CaCO₃, **preserve rather than delete**
non-representative samples, and validate unit and sample-point consistency
before interpreting a trend change.

### Object-type design principles

- **Do not model customer and facility as one object** merely because the CSV is
  denormalized. Service, chemistry, equipment and coverage failures occur at
  physical sites.
- **Do not delete or overwrite** erroneous, superseded or non-representative
  observations. Retain raw evidence; express validity through
  `ReadingAssessment` and correction relationships.
- **Do not use `WaterReading` as the alert itself.** A single out-of-band value
  usually needs verification; three consecutive directional observations can be
  actionable *before* any reading breaches a limit.
- **Do not use free text as the system of record** for commitments, crosswalks,
  root cause or doses. Preserve the original, promote the operational facts into
  governed objects.
- **Keep individual reading events separate from high-frequency time series.**

---

## 2. Link types and cardinality

A link type is bidirectional; name each side in operational language
(`Facility has systems` / `WaterSystem is installed at facility`).

**1:N direct links** — customer → facility · facility → system · system →
reading · facility → visit · system → work order · product → inventory position.

**N:M requires an association object when the relationship has facts:**

| Relationship | Becomes |
| --- | --- |
| visit ↔ system | `SystemService` |
| visit ↔ chemical product | `ChemicalApplication` |
| communication ↔ system | `CommunicationSystemReference` (if extraction finds several) |

**Selected links worth noting:**

| Link | From → To | Cardinality | Note |
| --- | --- | --- | --- |
| `SystemUsesProgram` | WaterSystem → TreatmentProgram | N:1 effective-dated | Thresholds selected by **formal program**, not inferred from a reading |
| `SystemPrecedesSystem` | WaterSystem → WaterSystem | via `AssetLineage` | Continuity between retired, rental and replacement equipment |
| `ApplicationTargetsSystem` | ChemicalApplication → WaterSystem | N:1, **nullable only for legitimate facility-wide use** | |
| `ReadingCollectedDuringVisit` | WaterReading → ServiceVisit | N:1, optional | Connects field readings to work performed |
| `ReadingAssessedBy` | WaterReading → ReadingAssessment | 1:N | Keeps raw measurement and rule/human assessment distinct |
| `AssessmentCreatesOrSupportsAlert` | ReadingAssessment → OperationalAlert | N:1 or N:M | Many observations can substantiate one ongoing alert |
| `CommunicationCreatesCommitment` | CustomerCommunication → CustomerCommitment | 1:N | Ensures emailed promises become tracked work |
| `LabSamplePointMapsToSystem` | SamplePointAlias → WaterSystem | N:1, effective-dated | Resolves codes like `BONF-OGD-B2` that otherwise orphan |

**1:1 is uncommon** and should be used sparingly; historical or changing facts
merit effective-dated assignments rather than overwriting.

**Avoid encoded N:M data** — parse `systems_serviced` and `chemicals_added`
upstream. Left as strings, operators cannot traverse systems served, doses
applied or inventory consumed.

---

## 3. Shared interfaces

Interfaces are abstract capabilities implemented by concrete object types —
used for recurring operational shapes, not merely because objects look similar.

| Interface | Implemented by | Purpose |
| --- | --- | --- |
| `Equipment` | SteamBoiler, CoolingSystem, ClosedLoop | Standard asset navigation, maintenance, risk scoring |
| `TreatableSystem` | All water-system subclasses | "Can be sampled, treated, evaluated, escalated" |
| `MonitoredAsset` | All TreatableSystem types | Dashboards for stale telemetry, quality flags, trends |
| `SchedulableEntity` | ServiceVisit, WorkOrder, CustomerCommitment | One uniform work queue for Rosa |
| `AssignableWork` | OperationalAlert, WorkOrder, CustomerCommitment, ServiceVisit | Common actions: assign, reprioritize, set due date, close/escalate |
| `RiskBearingItem` | OperationalAlert, high-risk WorkOrder, ReadingAssessment | Cross-domain attention queue without conflating lifecycles |
| `CustomerFacingRecord` | CustomerCommunication, CustomerCommitment, reports | Enforces review discipline for hospital documentation |
| `AuditableEvent` | ServiceVisit, WaterReading, ChemicalApplication, InventoryTransaction, WorkOrder, CustomerCommunication | Standardizes operational evidence and auditability |
| `EffectiveDatedRecord` | ServiceContract, SamplingPlan, IdentityResolution, ControlLimit | Prevents misleading historical reporting after program changes, ID merges or contract revisions |

**Constraints worth enforcing:** `TreatableSystem` requires stable criticality,
current program and status — an object missing these belongs in a data-quality
queue, not silently evaluated against generic thresholds. `AssignableWork`
requires owner, status and due date while non-terminal. `AuditableEvent`
requires source and source-record identity for imported records.

---

## 4. Action types and write-back

Use **Action Types** for explicit human decisions; use **pipelines** for
automated transformation. Normalization, control-limit evaluation and risk
scoring belong in pipelines. Acknowledgement, assignment, scheduling, inventory
adjustment and communication approval are operator decisions.

| Action | Core edits | Controls |
| --- | --- | --- |
| `ScheduleServiceVisit` | Creates visit and SystemService placeholders; links assignee, facility, systems, originating alert | Facility/system active; technician eligible; date respects cadence and seasonal closure |
| `RecordServiceCompletion` | Updates status; creates SystemService, chemical applications, inventory transactions, raw readings with provenance | Validates units, pH range, program applicability; **queues suspicious data rather than silently accepting it** |
| `TriageOperationalAlert` | Updates status, ownership, due date, rationale, disposition; may create a work order or verification commitment | Dismissal requires a reason; healthcare microbiological escalation cannot be closed without remediation evidence |
| `AdjustInventoryPosition` | Creates immutable transaction; recalculates position | Unit-conversion and negative-stock validation; count adjustments restricted and reasoned |
| `CreateCustomerCommitment` | Creates commitment; links source communication, owner, recipient, facility | Prohibits "completed" without completion evidence; healthcare documentation requires reviewer approval before send |
| `ResolveIdentityOrDataQualityException` *(optional sixth)* | Creates/updates an approved alias; marks assessment status; links superseded readings | Requires steward approval for customer merges, alias maps or unit reinterpretations |

**Action design principles**

1. **Pipelines are authoritative for derived state.** Do not expose an action
   that directly changes `out_of_band`, `trend_status`, limit values or risk
   scores. Operators record a disposition; the source assessment stays visible.
2. **Record intent, decision and evidence separately.** A technician creates a
   reading; a function creates an assessment; Dana triages the alert; a work
   order captures remediation; a follow-up reading supplies closure. More
   defensible than changing an anomaly flag in place.
3. **Use strict write-back selectively.** A writeback webhook when an external
   system must accept the change first; ordinary side-effect webhooks only for
   best-effort updates.
4. **Notifications for owned, actionable work** — recipients must have access to
   every object included, or the notification is not sent.
5. **Validate actions before release** with test runs.

---

## 5. Pipeline and architecture

| Tier | Responsibilities | Do **not** do here |
| --- | --- | --- |
| **Raw / Bronze** | Land payloads immutably with source path, ingestion timestamp, extract version, checksum. Preserve original timestamps, names, IDs, units, malformed values | Deduplicate, silently fix units, overwrite corrections, drop suspicious records |
| **Clean / Silver** | Parse schemas, normalize dates and units, standardize vocabulary, explode delimited fields, normalize technician identity, emit DQ exceptions | Treat unresolved records as canonical; embed business-priority rules |
| **Master-data** | Resolve aliases and duplicate IDs with effective dates, confidence, reviewer, evidence. Canonical keys while retaining source keys | Hard-delete retired/replaced systems or duplicate history |
| **Curated / Gold** | Business semantics, control-limit logic, trend detection, cadence checks, commitment tracking, state rollups | Ungoverned spreadsheet logic for customer-facing conclusions |
| **Serving** | Stable primary keys, display labels, link keys, security classifications | Raw text blobs or unsupported calculations in user-facing properties |
| **Action ledger** | User-originated changes with submitter, timestamp, pre/post state, reason, approval | Let user edits be overwritten invisibly by the next ingestion |

### Source-specific handling

| Source issue | Treatment | Ontology result |
| --- | --- | --- |
| ServiceTrak → FieldFlow migration | Source-specific raw tables; normalize to canonical visit schema; retain both IDs and source system | One visit history with evidence of origin |
| Full names vs initials | Effective-dated identity map; flag ambiguous initials for review rather than auto-guessing | Accurate assignment and coverage reporting |
| Duplicate CUST-0019 / CUST-0007 | Preserve source IDs in raw/clean; map both to one canonical ID | History traceable; UI does not split one customer's risk |
| Lab codes in `system_id` | Extract to `sample_point_alias`; resolve via governed crosswalk with confidence; quarantine unresolved | No false joins or fabricated trends |
| SYS-0006 → SYS-0101 | Keep distinct assets; lineage relationship with effective start/end and reason | Asset history accurate; continuity views only when business rules call for it |
| Per-row `units` key/value strings | Parse per parameter into long-form rows; retain raw unit and value; **convert only when notation is explicit** | Reliable control-limit checks |
| Delimited systems and chemicals | Explode to SystemService and ChemicalApplication; log parse failures | First-class associations |
| Corrections in a second batch | Identify business key + revision; represent as superseding records or `correction_of` links | Prior evidence not silently overwritten |

### Two-plane measurement design

Water chemistry has two access patterns that should not share one serving
construct:

1. **Operational event evidence** — field and lab measurements need source
   traceability, quality interpretation and workflow links. `WaterReading`
   event objects backed by the cleaned long-form table.
2. **High-frequency telemetry** — BMS/controller data needs scalable series
   storage, windowed aggregation and staleness monitoring. Time-series sync with
   stable series metadata.

Per-series identity should be
`canonical_system_id:parameter_code:sample_point:measurement_context` — never
display names or mutable source tags, which produce duplicate series after a
rename or migration.

**Trend detection** runs at service cadence with eligibility checks: same
parameter, compatible unit, valid sample point, same program context, valid
quality status. **Alert deduplication** uses a stable fingerprint from system,
risk class, parameter and governing limit — updating an open alert rather than
opening one per telemetry point.

### Data-quality gates

Implemented as first-class pipeline outputs rather than silent cleanup: schema
and freshness · identifier resolution coverage · referential integrity · unit
and range checks (pH outside 0–14 and negative concentrations are invalid **by
definition**) · conversion checks (only when notation confirms the source unit)
· program compatibility (CT-HC2 evaluated against CT-HC2, not CT-STD) ·
sampling validity · correction provenance (append/supersede, never destructive)
· business-rule transparency (expose rule version, applied threshold, program
and explanation).

---

## Divergences

Where SegoSight departs from this design, and why.

| Design | Implementation | Reason |
| --- | --- | --- |
| Foundry Object Types with links | DuckDB schemas with foreign keys; tiers as schemas | Client has no IT staff and no budget for enterprise platforms. Object semantics preserved as table contracts |
| Asset subtypes (`SteamBoiler`, `CoolingSystem`, `ClosedLoop`) | Single `canonical.system` with `system_type` | The design itself says "use only if subtype-specific typed properties are required". None are yet |
| Interfaces (`AssignableWork`, `RiskBearingItem`…) | Not implemented | Value is in a platform with interface-targeted actions. Here they would be documentation with no enforcement |
| `ApplicationTargetsSystem` nullable "only for legitimate facility-wide use" | **Null for 85% of doses** | 269 of 316 chemical-bearing visits serve multiple systems with no per-system boundary in the source. Attribution is not recoverable |
| `InventoryPosition` / `InventoryTransaction` | Landed but unused by alerting | Source is a snapshot with no transaction history; stockout projection would be guesswork |
| `SamplingPlan` as an object | Cadence and seasonal terms in `config/treatment_programs.toml` | Same governance, fewer moving parts at this scale |
| Six action types | Two implemented: review decision (promotion) and pipeline run | Scope. Alert triage and visit scheduling are the obvious next two |
| Time-series sync for BMS | Same long table, resampled to weekly median for trends | 740 BMS rows do not justify a separate serving plane. The design warns against over-engineering a small portfolio |
| `ReadingAssessment` separate from reading | **Implemented as designed** — `curated.reading_assessment` | One of the most load-bearing ideas here |
| Long-form `WaterReading` | **Implemented as designed** | The `units` column is per-parameter; a wide row cannot carry the right `raw_unit` |
| `IdentityResolution` with confidence and evidence | **Implemented as designed** — `canonical.identity_resolution` | Confidence gates alerting; see [findings §8](findings.md) |
| Append/supersede corrections | **Implemented as designed** | `clean.record_versions` |
| Alert fingerprint deduplication | **Implemented as designed** | 589 trend signals → 32 alerts |
