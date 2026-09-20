# Foundry Ontology Design: Sego Industrial Water

> Markdown conversion of `Foundry Ontology Design_ Sego Industrial Water.pdf`
> (15 pages). Section order, tables, and wording follow the source.
>
> **Fidelity notes — so nothing below is mistaken for the original:**
>
> 1. **The rightmost column of the link-type table (§2) is clipped in the source
>    PDF itself.** That table is wider than the page, and the generator cut every
>    line at the page edge: "Primary physical hie", "Makes ownership vis",
>    "Chemical-dose evide". The lost characters are absent from the PDF's content
>    stream — no converter can recover them. Clipped lines are marked `…` and
>    nothing has been invented to complete them.
> 2. **Four dipslide powers in §4 "Example: healthcare tower escalation" did not
>    survive extraction** (superscripts dropped by the font mapping — the source
>    reads "dipslide of  at a healthcare facility"). They are restored from
>    `treatment_guidelines.md` §5.3, which that passage paraphrases sentence for
>    sentence, and every restored value is marked `10^N`†.
> 3. `ft` ligatures were dropped by the same font mapping ("a er", "dra ",
>    "dri ") and are restored silently to *after*, *draft*, *drift*. Page 1
>    carries a decorative banner image (3176 × 800) that is not content and is
>    not reproduced.
>
> Bracketed numerals `[n]` are the source's citation markers; the reference list
> is at the end.

The recommended Ontology should make a customer facility's operational state navigable in one place: equipment, treatment program, service coverage, chemistry, open risks, chemical consumption, and accountable follow-up. Model durable business entities as Object Types; model observations and operational occurrences as event Object Types; use links to preserve provenance and avoid embedding relational lists in properties. This is especially important here because the source data contains identifier changes, duplicate customers, lab sample aliases, mixed units, and multi-valued fields embedded in CSV strings. [1][2][3]

The primary operational user is Dana Whitlock, Operations Director, with Rosa Camacho, the service coordinator, as the main dispatch and follow-up user. The product surface should answer Dana's Monday-morning question: which sites need attention, why, the potential consequence, and the owner/action already in flight. [2]

## 1. Object Types

Foundry Object Types should represent either a real-world entity or a real-world event. Interfaces are abstract shapes/capabilities, not independently instantiated records; concrete Object Types implement them. [4][5]

### Canonical object model

| Domain category | Foundry Object Type | Grain / identity | Primary backing source(s) | Why it exists |
| --- | --- | --- | --- | --- |
| Commercial actor | `CustomerAccount` | One legal/commercial customer; canonical `customer_id` | Cleaned customers/master-data mapping | Holds account tier, ACV, contract risk, SLA, and canonical identity after duplicate resolution. |
| Physical location | `Facility` | One serviced physical location; `facility_id` | Cleaned customers | Separates a corporate account from a plant, campus, hotel, or hospital site. This is the key "account-at-a-glance" operating context. |
| Person / actor | `Contact` | One named customer contact at a facility | Customers, communications | Enables customer-facing commitments and escalation records to be tied to a named person rather than buried in email text. |
| Person / actor | `Employee` | One canonical employee/person | Employee identity reference built from technician names/initials | Resolves legacy full names and FieldFlow initials such as MW or TR to a stable person identity. |
| Physical asset | `WaterSystem` | One treated system; canonical `system_id` | Systems plus system-alias/crosswalk data | The common abstraction for boilers, cooling towers, evaporative condensers, and closed loops. Carries treatment program, criticality, status, capacity, and lifecycle. |
| Physical asset subtype | `SteamBoiler` | One boiler | Filtered system projection | Use only if boiler-specific characteristics require strongly typed properties, such as pressure class, boiler design, feedwater configuration, or condensate-return treatment. |
| Physical asset subtype | `CoolingSystem` | One cooling tower or evaporative condenser | Filtered system projection | Use when cooling-specific characteristics — tower type, cells, bleed controls, reuse-water makeup, biocide regime — matter in workflows. |
| Physical asset subtype | `ClosedLoop` | One closed loop | Filtered system projection | Use when loop-specific logic — nitrite versus molybdate program, estimated loop volume, tooling dependency, make-up events — requires a dedicated model. |
| Asset lineage | `AssetLineage` | One approved predecessor/successor relationship | System-update data, governed manual reconciliation | Represents equipment replacement or temporary-rental continuity without overwriting historical identity. Needed for the failed `SYS-0006` to rental `SYS-0101` scenario. [3] |
| Commercial agreement | `ServiceContract` | One contract version for a customer/facility | Customers plus contract normalization | Holds service cadence, effective dates, SLA, seasonal closure terms, and compliance obligations. A contract must be versioned rather than represented only as mutable fields on a facility. |
| Operational event | `ServiceVisit` | One scheduled or completed on-site/callout visit; canonical `visit_id` | ServiceTrak + FieldFlow normalized feeds | Captures date/time, assigned/completing technician, status, field observations, follow-up date, source system, and visit provenance. |
| Operational event | `SystemService` | One system serviced during one visit | Parsed/unnested `systems_serviced` | Junction event: resolves the source's semicolon-delimited list into a first-class record. This is more useful than an opaque N:M link because it can later hold per-system service details. [3] |
| Operational event | `ChemicalApplication` | One chemical product dose applied to one system during one visit | Parsed `chemicals_added`, technician notes, future mobile action | Captures product, quantity, unit, converted quantity, application purpose, operator, and timestamp. It drives consumption analytics and inventory decrement logic. |
| Measurement event | `WaterReading` | One reading/observation for one parameter, system, timestamp, and source | Normalized field, lab, and BMS readings | Recommended long/narrow event grain rather than one sparse wide row: `system_id`, `timestamp`, `parameter_code`, `raw_value`, `raw_unit`, `normalized_value`, `standard_unit`, `source`, quality flags. This enables consistent time-series treatment across parameters. |
| Measurement metadata | `MeasurementSeries` | One system × parameter × source/measurement context series | Time-series metadata backing dataset | Defines the series identity, unit, parameter semantics, expected sampling cadence, and source quality. It supports high-frequency BMS data without making every sample a heavyweight business object. |
| Measurement governance | `ReadingAssessment` | One evaluation of a reading or series window | Derived rule outputs | Stores validation and operational interpretation separately from raw evidence: `validity_status`, `out_of_band`, `trend_status`, severity, governing limit version, explanation, and human disposition. |
| Risk/event | `OperationalAlert` | One actionable, deduplicated concern | Derived from readings, visits, inventory, communications, work orders | A persistent work-management object for corrosion trends, missed coverage, microbiological escalation, stockout risk, or customer commitment risk. It should be distinct from raw anomaly rows. |
| Operational event | `WorkOrder` | One repair/remediation work order; `wo_id` | Work-order feeds | Holds status, priority, owner, cost, resolution, opened/resolved timestamps, and recurrence context. |
| Operational event | `CustomerCommunication` | One inbound/outbound email, request, complaint, or documented notice | Service inbox export | Preserves the original communication and lets operators connect it to the relevant account, facility, system, commitment, alert, or work order. |
| Operational commitment | `CustomerCommitment` | One promise requiring completion | Extracted from communications, created by operator actions | Examples: promised site visit, treatment plan, documentation packet, corrective-action update. The guidelines explicitly state that commitments made by email must be tracked to completion. [6] |
| Inventory master | `ChemicalProduct` | One chemical SKU/product code | Inventory feed / product master | Product identity, approved unit conversions, application class, and safety metadata. |
| Inventory state | `InventoryPosition` | One product at one storage location at one reported snapshot/current-state key | Chemical inventory | Recommended key: `location_id` + `product_code`; records on-hand quantity, reorder point, quantity on order, expected receipt, count timestamp, and confidence. |
| Inventory movement | `InventoryTransaction` | One receipt, transfer, count adjustment, or consumption movement | Actions plus inventory imports | Necessary for trustworthy write-back. A snapshot alone cannot support auditability or reconciled stock state. |
| Master-data governance | `IdentityResolution` | One source identifier to canonical identifier decision | Crosswalk datasets + approved curation | Governs aliases, duplicate mergers, lab sample-point codes, employee initials, and migrated FieldFlow IDs; includes effective dates, confidence, reviewer, and source evidence. |
| Policy/configuration | `TreatmentProgram` | One governed treatment program/version | Guidelines-to-configuration dataset | Examples: `BP-STD`, `BP-HP`, `CT-STD`, `CT-HC2`, `CL-N`, `CL-M`. Do not hard-code thresholds in applications. |
| Policy/configuration | `ControlLimit` | One program × parameter × effective-version rule | Treatment-program configuration | Stores lower/upper/action thresholds, standard unit, severity policy, exceptions, and applicability conditions. |
| Policy/configuration | `SamplingPlan` | One system/contract sampling requirement | Contract and treatment program rules | Represents routine cadence, weekly healthcare dipslide requirement, required re-test windows, seasonal exceptions, and reporting requirements. |

### Why WaterReading should be long-form

The candidate draft correctly identifies `Water_Reading` as an event, but its proposed wide schema becomes increasingly sparse and rigid as parameters, lab feeds, BMS tags, or new treatment programs are added. [3]

Use a normalized event model:

```
WaterReading
- reading_id
- system_id
- measurement_series_id
- observed_at
- parameter_code                 # conductivity, ph, iron, nitrite, dipslide, etc.
- raw_value
- raw_unit
- normalized_value
- standard_unit
- collection_method              # field | lab | BMS
- sample_point_id
- collected_by_actor_id
- source_record_id
- source_system
- quality_status                 # valid | suspect | invalid | unresolved
- quality_reason
- correction_of_reading_id
- ingestion_timestamp
```

This design directly supports the stated operating rules: normalize conductivity from mS/cm to uS/cm, normalize hardness from grains per gallon to ppm as CaCO3, preserve rather than delete nonrepresentative samples, and avoid interpreting trend changes before validating unit and sample-point consistency. [6]

### Object-Type design decisions

- Do not model "customer" and "facility" as one Object Type merely because the CSV is denormalized. A corporate account can own multiple facilities, whereas service, chemistry, equipment, and coverage failures occur at physical sites. [3]
- Do not delete or overwrite erroneous, superseded, or nonrepresentative chemistry observations. Retain raw evidence and use `ReadingAssessment`/correction relationships to express validity and replacement. The treatment guidelines explicitly require annotation rather than deletion for unrepresentative recorded samples. [6]
- Do not use `WaterReading` as the alert itself. A single out-of-band value generally requires verification, while three consecutive directional observations can represent an actionable mechanism even before any individual reading breaches a limit. [6]
- Do not use free-text fields as the sole system of record for commitments, crosswalks, root cause, remediation, or chemical doses. Preserve the original text, but promote the operational facts needed for action into governed objects.
- Keep individual reading events separate from a high-frequency time-series representation. Foundry supports time-series properties and a time-series sync backed by a dataset or stream; the time-series object backing dataset carries the stable per-series metadata and identifiers. [7][8]

## 2. Link Types and Cardinality

A Foundry link type is bidirectional: each relationship has two independently traversable sides with meaningful display and API names. Model link direction in operational language rather than database language — for example, *Facility has systems* / *WaterSystem is installed at facility*. [9]

### Essential relationships

> The "Operational use" column below is clipped in the source PDF (see fidelity
> note 1). `…` marks a line the generator cut at the page edge.

| Link Type | From → To | Cardinality | Implementation | Operational us… |
| --- | --- | --- | --- | --- |
| `CustomerOwnsFacility` | `CustomerAccount` → `Facility` | 1:N | Direct link from canonical customer/facility mapping | Navigate a customer portfolio to all servic… locations. |
| `FacilityHasContact` | `Facility` → `Contact` | 1:N | Direct | Supports customer communication, escalation, and repo… delivery. |
| `CustomerHasContract` | `CustomerAccount` → `ServiceContract` | 1:N | Direct | Supports renewals, contractual exposure… customer-level term… |
| `ContractCoversFacility` | `ServiceContract` → `Facility` | 1:N, or N:M if a contract spans multiple facilities | Direct link / coverage junction when needed | Keeps contract term… separate from facility… master data. |
| `FacilityContainsSystem` | `Facility` → `WaterSystem` | 1:N | Direct | Primary physical hie… |
| `SystemUsesProgram` | `WaterSystem` → `TreatmentProgram` | N:1 for an effective-dated assignment; historical N:M over time | Current-state link plus `SystemProgramAssignment` if history is required | Ensures thresholds a… selected by formal… program, not inferre… a reading. |
| `SystemHasSamplingPlan` | `WaterSystem` → `SamplingPlan` | 1:N over time | Effective-dated direct/junction object | Enables expected vis… tests, healthcare wee… requirements, and c… window logic. |
| `SystemPrecedesSystem` | `WaterSystem` → `WaterSystem` | N:M over lifecycle, usually 1:1 per replacement event | Via `AssetLineage` object | Preserves continuity… between retired, ren… and replacement… equipment. |
| `FacilityHasVisit` | `Facility` → `ServiceVisit` | 1:N | Direct | Coverage and route… performance. |
| `EmployeeAssignedToVisit` | `Employee` → `ServiceVisit` | 1:N over time; N:M if multiple technicians participate | Assignment junction if needed | Separates planned… assignment from… completion. |
| `EmployeeCompletedVisit` | `Employee` → `ServiceVisit` | 1:N | Direct/current link | Accountability for fie… execution. |
| `VisitServicesSystem` | `ServiceVisit` → `WaterSystem` | N:M | Prefer `SystemService` junction object | Resolves… `systems_servi`… into auditable per-sy… activity. [3] |
| `SystemServiceOccursDuringVisit` | `SystemService` → `ServiceVisit` | N:1 | Direct | Gives the junction ev… visit context. |
| `SystemServiceTargetsSystem` | `SystemService` → `WaterSystem` | N:1 | Direct | Supports per-system… completion and late… measurements. |
| `VisitAppliesChemical` | `ServiceVisit` → `ChemicalApplication` | 1:N | Direct | Chemical-dose evide… |
| `ApplicationUsesProduct` | `ChemicalApplication` → `ChemicalProduct` | N:1 | Direct | Product consumptio… customer/system/pr… |
| `ApplicationTargetsSystem` | `ChemicalApplication` → `WaterSystem` | N:1 | Direct; nullable only for legitimate facility-wide use | Detects excess close… chemical consumpti… treatment gaps. |
| `ApplicationConsumesInventory` | `ChemicalApplication` → `InventoryTransaction` | 1:N or 1:1 depending on movement granularity | Direct | Preserves stock audi… |
| `InventoryPositionStoresProduct` | `InventoryPosition` → `ChemicalProduct` | N:1 | Direct | Supports warehouse… availability. |
| `InventoryTransactionAffectsPosition` | `InventoryTransaction` → `InventoryPosition` | N:1 | Direct | Current stock roll-up… immutable moveme… |
| `SystemHasReading` | `WaterSystem` → `WaterReading` | 1:N | Direct | Equipment chemistr… history. |
| `ReadingUsesSeries` | `WaterReading` → `MeasurementSeries` | N:1 | Direct | Links normalized… observations to time… metadata. |
| `ReadingCollectedDuringVisit` | `WaterReading` → `ServiceVisit` | N:1, optional | Direct when known | Connects field readin… work performed and… technician context. |
| `ReadingAssessedBy` | `WaterReading` → `ReadingAssessment` | 1:N | Direct | Keeps raw measurem… and rule/human… assessments distinct… |
| `AssessmentCreatesOrSupportsAlert` | `ReadingAssessment` → `OperationalAlert` | N:1 or N:M | Direct or evidence junction | Many observations c… substantiate one ong… alert. |
| `AlertConcernsSystem` | `OperationalAlert` → `WaterSystem` | N:1; nullable for facility-wide/inventory issues | Direct | Provides asset-level… prioritization. |
| `AlertConcernsFacility` | `OperationalAlert` → `Facility` | N:1 | Direct | Enables facility-leve… queueing, even whe… specific system is kn… |
| `AlertAssignedToEmployee` | `OperationalAlert` → `Employee` | N:1 | Direct | Makes ownership vis… |
| `AlertResultsInWorkOrder` | `OperationalAlert` → `WorkOrder` | 1:N | Direct | Shows whether iden… risk has a remediatio… path. |
| `WorkOrderTargetsSystem` | `WorkOrder` → `WaterSystem` | N:1, optional for site-wide work | Direct | System repair and… recurrence analysis. |
| `WorkOrderLocatedAtFacility` | `WorkOrder` → `Facility` | N:1 | Direct | Required for site-wid… unassigned-system w… |
| `WorkOrderOwnedByEmployee` | `WorkOrder` → `Employee` | N:1 | Direct | Accountability and… workload. |
| `CommunicationAboutCustomer` | `CustomerCommunication` → `CustomerAccount` | N:1 | Direct | Account history. |
| `CommunicationAboutFacility` | `CustomerCommunication` → `Facility` | N:1, optional | Direct | Site context. |
| `CommunicationConcernsSystem` | `CustomerCommunication` → `WaterSystem` | N:M, optional | Communication-to-system junction if multiple | Enables complaints… requests to surface o… asset views. |
| `CommunicationCreatesCommitment` | `CustomerCommunication` → `CustomerCommitment` | 1:N | Direct | Ensures emailed pro… become tracked wor… |
| `CommitmentOwnedByEmployee` | `CustomerCommitment` → `Employee` | N:1 | Direct | Dispatch responsibil… |
| `CommitmentSatisfiedByVisit` | `CustomerCommitment` → `ServiceVisit` | N:M | Junction if fulfillment is composite | Evidence for "promis… visit completed." |
| `CommitmentSatisfiedByDocument` | `CustomerCommitment` → `CustomerCommunication` or attachment/document object | N:M | Direct/junction | Evidence for custom… facing reporting… obligations. |
| `SourceAliasResolvesToCanonical` | `IdentityResolution` → any resolvable entity | N:1 | Prefer typed mappings: customer, system, employee, sample point | Makes entity reconci… inspectable and reve… |
| `LabSamplePointMapsToSystem` | `SamplePointAlias` → `WaterSystem` | N:1, effective-dated | Direct | Resolves lab codes s… `BONF-OGD-B2` th… otherwise orphan… chemistry readings. [3] |

### Cardinality guidance

- **1:N direct links:** customer → facility; facility → system; system → reading; facility → visit; system → work order; product → inventory position.
- **N:M requires an association object when the relationship has facts:** visit ↔ system becomes `SystemService`; visit ↔ chemical product becomes `ChemicalApplication`; communication ↔ system can become `CommunicationSystemReference` if the extraction process finds multiple assets.
- **1:1 is uncommon and should be used sparingly:** for example, one active "current profile" may be linked to one system, but historical or changing facts nearly always merit effective-dated assignments rather than overwriting a 1:1 relation.
- **Avoid encoded N:M data:** parse the semicolon-separated `systems_serviced` and `chemicals_added` fields upstream. If these remain strings in ontology-backing datasets, downstream operators cannot reliably traverse systems served, doses applied, or inventory consumed. [3]

## 3. Shared Interfaces

Use interfaces for recurring operational shapes and capabilities — not merely because multiple objects look similar. Palantir recommends evaluating duplicate shapes, links, and actions for consolidation into either a single type or a shared interface; compose several focused interfaces rather than building a deep inheritance hierarchy. [10]

### Recommended interfaces

| Interface | Implementing Object Types | Required shared properties | Required links / capabilities | Purpose |
| --- | --- | --- | --- | --- |
| `Equipment` | `SteamBoiler`, `CoolingSystem`, `ClosedLoop`; optionally generic `WaterSystem` | `system_id`, name/description, status, criticality, install date, capacity, operating parameters | Installed at `Facility`; uses `TreatmentProgram`; has readings; has work orders | Standard asset navigation, maintenance, risk scoring, and shared applications. |
| `TreatableSystem` | All water-system subclasses | treatment program, active/inactive state, criticality, expected service cadence, last-service timestamp | Has `SamplingPlan`, `WaterReading`, `ChemicalApplication`, `OperationalAlert` | Defines the capability "can be sampled, treated, evaluated, and escalated." |
| `ServiceableAsset` | All equipment types, and potentially future pumps/feeders | asset status, criticality, maintenance state | Has service visits and work orders; can be targeted by scheduling/remediation actions | Future-proofs the Ontology beyond chemistry-bearing systems. |
| `MonitoredAsset` | All `TreatableSystem` types; potentially chemical-feed equipment later | latest-reading timestamp, monitoring health, data-quality status | Has `MeasurementSeries`, `WaterReading`, `ReadingAssessment` | Enables common dashboards for stale telemetry, quality flags, trends, and anomalies. |
| `SchedulableEntity` | `ServiceVisit`, `WorkOrder`, `CustomerCommitment`, possibly `SamplingPlan` execution instances | planned date/time, due date, status, priority, duration estimate | Assigned to `Employee`; associated with facility/system | Gives Rosa one uniform work queue for visits, follow-ups, repairs, and customer commitments. |
| `AssignableWork` | `OperationalAlert`, `WorkOrder`, `CustomerCommitment`, `ServiceVisit` | status, priority/severity, owner, due date, created timestamp | Assigned to employee; concerns facility/system | Common action set: assign, reprioritize, set due date, close/escalate. |
| `RiskBearingItem` | `OperationalAlert`, high-risk `WorkOrder`, potentially `ReadingAssessment` | risk category, severity, confidence, detected time, rationale, disposition | Concerns customer/facility/system; owned by employee | Enables a cross-domain "attention queue" without conflating alert and work-order lifecycles. |
| `CustomerFacingRecord` | `CustomerCommunication`, `CustomerCommitment`, customer-facing report/document | customer visibility, communication date, approval state, reviewer, sensitivity | Related to customer/facility/contact | Enforces additional review discipline for hospital documentation and other customer-visible content. |
| `InventoryTrackedItem` | `ChemicalProduct`, potentially service parts later | product code, unit of measure, reorder policy, safety/handling category | Has inventory positions and transactions | Makes inventory workflows extensible beyond chemicals. |
| `AuditableEvent` | `ServiceVisit`, `WaterReading`, `ChemicalApplication`, `InventoryTransaction`, `WorkOrder`, `CustomerCommunication` | event timestamp, source system, source record ID, entered by, ingestion time, provenance status | Related to originating entity/actor | Standardizes operational evidence and auditability. |
| `EffectiveDatedRecord` | `ServiceContract`, `SystemProgramAssignment`, `SamplingPlan`, `IdentityResolution`, `ControlLimit` | effective start/end, current flag, source, approval status | Links to governed parent entities | Prevents misleading historical reporting after program changes, ID merges, or contract revisions. |

### Interface constraints worth enforcing

- `Equipment` should require a link to exactly one active facility and at least one active or historical treatment-program assignment.
- `TreatableSystem` should require a stable criticality, current program, and status. An object missing these fields should be held in a data-quality queue, not silently evaluated against generic thresholds.
- `AssignableWork` should require owner, status, and due date when the item is non-terminal. This is the minimum data needed to answer "who is doing what about it?"
- `CustomerFacingRecord` should require reviewer/approval state before external delivery actions are available.
- `AuditableEvent` should require source and source-record identity for imported records, while operator-created records should include an action log reference and submitting user.

Interfaces can include property, link, and action constraints, allowing a shared workflow to target all conforming implementations. However, interfaces are abstract and must be implemented by concrete Object Types; their action and link constraints should be introduced selectively and tested in the target Foundry applications. [5][11]

## 4. Action Types and Write-Back

Use Action Types for explicit human or agent-assisted decisions and state changes; use pipelines for automated transformations. This distinction is particularly important here: normalization, control-limit evaluation, and risk scoring belong in pipelines/functions, while acknowledgement, assignment, scheduling, inventory adjustment, and communication approval are operator decisions. [12][10]

Each Action Type should be narrow, auditable, permissioned, and idempotent where feasible. Parameters are typed inputs used by rules, validation/submission criteria, object edits, and side effects. [13]

### Recommended Action Types

| Action Type | Target objects | Required parameters | Core object/link edits | Side effects and controls |
| --- | --- | --- | --- | --- |
| `ScheduleServiceVisit` | `Facility`, selected `TreatableSystem` objects, `ServiceVisit`, optionally `CustomerCommitment` | facility; one or more target systems; scheduled start/end; assigned technician; visit type; priority; reason; source alert/commitment if applicable | Creates `ServiceVisit`; creates `SystemService` placeholders/links; links assignee, facility, systems, originating alert/commitment; marks linked commitment as scheduled | Notify assigned technician and Rosa; optionally write back to FieldFlow through a writeback webhook if FieldFlow must be authoritative. Submission criteria: facility/system active; technician eligible; no conflicting assignment; date respects contractual cadence and seasonal closure. |
| `RecordServiceCompletion` | `ServiceVisit`, `SystemService`, `ChemicalApplication`, `WaterReading`, `OperationalAlert`, `WorkOrder` | visit; actual completion time; visit status; serviced systems; structured work performed; doses/product/unit; readings; follow-up date; observation; escalation decision | Updates visit status; creates completed `SystemService` events; creates chemical applications and inventory-consumption transactions; creates raw field readings with provenance; updates equipment last-serviced state; optionally creates/links alerts and work orders | Notify coordinator if missed, incomplete, or follow-up due; run a validation function for units, valid pH range, and treatment-program applicability; queue suspicious data rather than silently accepting it. Designed for mobile/offline capture with eventual synchronization. |
| `TriageOperationalAlert` | `OperationalAlert`, `WorkOrder`, `CustomerCommitment`, `Employee`, `Facility`, `WaterSystem` | alert; disposition (`acknowledge`, `monitor`, `verify`, `create work order`, `escalate`, `dismiss`); owner; due date; rationale; severity override reason; evidence references | Updates alert status, ownership, due date, rationale, and disposition; may create a linked work order or verification commitment; links supporting evidence | Notify Dana for critical/compliance/equipment-integrity escalation; notify assignee. Submission criteria: a dismiss/false-positive disposition requires reason; severity downgrade may require qualified approver; healthcare microbiological escalation cannot be closed without required remediation evidence. |
| `AdjustInventoryPosition` | `InventoryPosition`, `InventoryTransaction`, `ChemicalProduct` | location; product; transaction type (`receipt`, `transfer`, `count adjustment`, `waste`, `return`); quantity; unit; effective timestamp; reason; supporting reference; optional expected delivery | Creates immutable `InventoryTransaction`; recalculates/updates current position; links transaction to product/location and, when relevant, visit, supplier order, or correction record | Run unit-conversion and negative-stock validation; notify coordinator when projected availability crosses reorder threshold or when on-hand falls below planned route demand. Restrict count adjustments to authorized users and require a reason plus audit trail. |
| `CreateCustomerCommitment` | `CustomerCommunication`, `CustomerCommitment`, `CustomerAccount`, `Facility`, `Contact`, `Employee` | customer/facility; commitment type; exact promise; due date; owner; customer contact; source communication; review/approval requirement | Creates `CustomerCommitment`; links it to the source email/communication, owner, recipient, facility/customer, and related asset/work order if known | Notify owner and coordinator; create escalation reminder before SLA/due date; prohibit "completed" status without completion evidence. For healthcare documentation or remediation plans, require reviewer approval before a customer-facing send action. |

### Optional sixth action: `ResolveIdentityOrDataQualityException`

If the implementation needs a fifth action only, retain the preceding five. If data quality is the greatest adoption blocker, add a dedicated governed-curation action:

| Action Type | Target objects | Required parameters | Core edits | Side effects and controls |
| --- | --- | --- | --- | --- |
| `ResolveIdentityOrDataQualityException` | `IdentityResolution`, `WaterReading`, `Facility`, `WaterSystem`, `Employee` | exception record; resolution category; canonical target; effective date; evidence; reviewer; correction rationale | Creates or updates an approved alias/crosswalk; marks reading assessment status; links superseded/corrected readings; can create new canonical mapping records | Requires steward/operations approval for customer merges, system alias maps, lab sample-point mappings, or unit reinterpretations; triggers rebuild of affected downstream derived datasets. |

### Action design principles

1. **Make pipelines authoritative for derived state.** Do not expose a generic action that directly changes `out_of_band`, `trend_status`, treatment-program limit values, inventory risk, or account risk. Those are derived, reproducible outputs from governed pipeline logic. Operators may record a disposition or override, but the source assessment should remain visible.
2. **Record intent, decision, and evidence separately.** A technician can create a reading; an evaluation function creates a `ReadingAssessment`; Dana can triage the resulting alert; a work order captures remediation; a follow-up reading supplies closure evidence. This is more defensible than changing an anomaly flag in place.
3. **Use strict write-back semantics selectively.** Use a writeback webhook when an external system must accept the change before Foundry shows the action as successful — for example, creating a FieldFlow visit if FieldFlow remains the scheduling system of record. Writeback webhooks run before object edits and expose failure to the end user. Use ordinary side-effect webhooks only for best-effort downstream updates because they run after Foundry object changes and may complete after the UI reports success. [14]
4. **Use notifications for owned, actionable work.** Foundry notification recipients can be parameter-based or dynamically calculated by a function; notification content can be templated or function-generated. Ensure recipients have access to every object included in the notification, otherwise the notification will not be sent. [15][16]
5. **Validate actions before release.** Use Action Type test runs to inspect proposed edits, parameter validation, submission criteria, and notification previews without applying side effects. [17]

### Example: healthcare tower escalation

A `ReadingAssessment` detects a cooling-tower dipslide of 10^4† at a healthcare facility. It creates or updates an `OperationalAlert` with the relevant facility, tower, program, reading, and prior trend evidence. Dana uses `TriageOperationalAlert` to assign Jenn, require same-visit corrective action and a re-test due within one week, and create a documented customer-remediation commitment when the escalation threshold requires it. The system retains the evidence chain instead of merely marking the reading "red." This implements the guideline that two consecutive 10^4† results require director notification, written remediation communication, and weekly re-tests until two results return to 10^3† or below; a single 10^5† result requires urgent cleaning/disinfection recommendation. [6]

> † The four dipslide powers in this paragraph were superscripts that did not
> survive text extraction; they are restored from `treatment_guidelines.md` §5.3.

## 5. Pipeline and Architecture

Use a layered architecture that separates immutable source evidence, standardized/reconciled data, and consumer-ready Ontology backing datasets. In Foundry, datasets are the central representation of data from landing through ontology mapping, so the key architectural choice is to make every transformation, correction, and derived operational conclusion traceable. [18]

### Tiering convention

| Tier | Suggested dataset families | Responsibilities | Do not do here |
| --- | --- | --- | --- |
| Raw / Bronze | `raw_servicetrak_visits`, `raw_fieldflow_visits`, `raw_lab_reports`, `raw_bms_readings`, `raw_inventory_snapshots`, `raw_customer_inbox`, `raw_system_exports`, `raw_notes` | Land source payloads immutably with source file/path, ingestion timestamp, extract version, checksum, and raw rows/files. Preserve original timestamps, names, IDs, units, and malformed values. | Do not deduplicate, silently fix units, overwrite corrections, or drop suspicious records. |
| Standardized / Clean / Silver | `clean_service_visits`, `clean_water_readings_long`, `clean_work_orders`, `clean_inventory_snapshots`, `clean_customers`, `clean_systems`, `clean_communications`, `clean_notes` | Parse schemas, normalize dates/time zones and units, standardize controlled vocabulary, explode delimited fields, normalize technician identity, preserve raw and standardized values, and emit data-quality exceptions. | Do not treat unresolved records as valid canonical facts; do not embed business-priority rules in source normalization. |
| Master-data / Reconciliation | `canonical_customer`, `canonical_facility`, `canonical_system`, `employee_master`, `system_alias_crosswalk`, `lab_sample_point_crosswalk`, `customer_merge_map`, `asset_lineage`, `source_record_resolution` | Resolve aliases and duplicate IDs with effective dates, confidence, reviewer, and evidence. Produce canonical keys while retaining source keys. | Do not hard-delete retired/replaced systems or duplicate history. |
| Curated domain / Gold | `service_visit_system`, `chemical_application`, `chemical_usage_daily`, `inventory_position_current`, `reading_assessment`, `measurement_series`, `coverage_status`, `operational_alert`, `customer_commitment`, `work_order_current`, `facility_operational_snapshot` | Apply business semantics, control-limit logic, trend detection, service-cadence checks, inventory risk, commitment tracking, and state rollups. These are the primary sources for Ontology backing datasets. | Do not use ungoverned/manual spreadsheet logic for customer-facing or operationally consequential conclusions. |
| Ontology backing / Serving | Object- and link-specific backing datasets | Provide stable primary keys, display labels, properties, link keys, security classifications, and update cadence suitable for Foundry Ontology objects, links, applications, and actions. | Do not put raw text blobs, source-specific artifacts, or unsupported calculations into user-facing primary properties. |
| Action/write-back ledger | `action_log`, `inventory_transactions`, `manual_override_history`, `alert_dispositions`, `identity_resolution_requests` | Store user-originated changes separately from imported source data, including submitter, timestamp, pre/post state, reason, and approval. Feed approved state back into curated layers where appropriate. | Do not let user edits be overwritten invisibly by the next source ingestion. |

### Core ingestion and reconciliation pattern

```
Source exports, inboxes, BMS feeds, lab reports, mobile actions
                    │
                    ▼
          Raw / immutable landing
                    │
                    ▼
Standardization + parsing + profiling + DQ exceptions
                    │
                    ├──►  Master-data resolution and effective-dated crosswalks
                    │
                    ▼
Curated operational models, rules, trends, and state snapshots
                    │
                    ├──►  Ontology object/link backing datasets
                    ├──►  Time-series sync and measurement-series metadata
                    └──►  Operational applications / dashboards / alert queues
                                  │
                                  ▼
                    Action Types and governed write-back ledger
                                  │
                                  └──►  Optional FieldFlow / email / ERP webhooks
```

### Source-specific handling

| Source issue | Pipeline treatment | Ontology result |
| --- | --- | --- |
| ServiceTrak-to-FieldFlow schema and identifier migration | Maintain source-specific raw landing tables; normalize to canonical visit schema; use explicit ID/employee/facility resolution maps; retain both source IDs and source system. | Operators view one visit history while retaining evidence of origin and migration. |
| Full technician names versus initials | Map source identifier/name to canonical `Employee` through an effective-dated identity map. Flag ambiguous initials for review rather than auto-guessing. | Accurate assignment, workload, and coverage reporting. |
| Duplicate customer `CUST-0019` / `CUST-0007` | Preserve source customer IDs in raw/clean layers; map both to one `CustomerAccount` canonical ID through `IdentityResolution`. | Historical facts remain traceable; the UI does not split one customer's risk history. |
| Lab sample codes in `system_id` | Extract source code into `sample_point_alias`; resolve via a governed crosswalk with effective dates and confidence; quarantine unresolved lab observations. | No false joins or fabricated system trends. |
| Equipment replacement `SYS-0006` → `SYS-0101` | Keep distinct physical assets; create lineage relationship with effective start/end and reason. Build "continuity views" only when business rules call for it. | Asset history is accurate, while optional program-level trend analysis can be continuous and clearly labeled. |
| Wide readings with per-row units key/value strings | Parse units per parameter into long-form measurement rows; retain raw unit and raw value; convert only when conversion is explicit and approved. | Reliable control-limit checks and multi-source comparisons. |
| Delimited systems and chemicals in visit rows | Explode to `SystemService` and `ChemicalApplication` normalized datasets; parse quantity/unit; log parse failures. | First-class associations for system service coverage and consumption. |
| Corrections in second data batch | Identify source business key + revision/version when available; represent corrections as superseding records or `correction_of` links; recompute curated state incrementally. | Prior evidence is not silently overwritten; current state uses the latest valid record. |

### High-frequency time series

Water chemistry has two distinct access patterns:

1. **Operational event evidence:** field and lab measurements need source traceability, quality interpretation, workflow links, and audit context.
2. **High-frequency telemetry analytics:** BMS/controller data needs scalable series storage, charting, windowed aggregation, drift detection, and staleness monitoring.

Do not force both into exactly the same serving construct.

#### Recommended two-plane design

| Concern | Recommended design | Rationale |
| --- | --- | --- |
| Field/lab readings | `WaterReading` event Object Type backed by the cleaned long-form readings table. Link to system, visit, technician, sample point, and assessment. | Field and lab readings are infrequent, semantically rich, and routinely used as evidence for work and compliance decisions. |
| BMS/controller streams | Foundry time-series sync using a stable `MeasurementSeries`/time-series object metadata model plus the high-frequency values dataset or stream. | Foundry's time-series design separates metadata from values; a time-series object type and sync provide access to indexed values. [7] |
| Per-series identity | Stable ID such as `canonical_system_id:parameter_code:sample_point:measurement_context`; do not use display names or mutable source tags. | Prevents duplicate series after system rename, FieldFlow migration, or lab-code updates. |
| Time-series metadata | Store standard unit, raw unit/source, parameter code, sample point, expected cadence, interpolation choice, data-quality state, and effective time range. | Keeps units and interpretation rules centralized instead of scattered across raw samples. |
| Raw values | Preserve source timestamp, ingest timestamp, value, raw unit, quality bit/source status, and source event ID. | Allows late arrivals, replay, audit, and unit-validation investigation. |
| Aggregations | Build 5-minute/hourly/daily rollups as curated datasets where needed for user-facing views and alert rules; retain raw resolution for investigations. | Controls cost and application latency without losing diagnostic detail. |
| Trend detection | Run scheduled/windowed functions at the relevant service cadence, using normalized values and eligibility checks: same parameter, compatible unit, valid sample point, same program context, and quality status. | Meets the guideline that three or more consecutive readings moving in one direction warrant investigation, but units must be consistent before interpreting a step change. [6] |
| Alert deduplication | Generate a stable alert fingerprint from system, risk class, parameter, current governing program/limit, and active time window; update an existing open alert rather than opening one alert per telemetry point. | Avoids alert floods and gives Dana an actionable queue. |
| Freshness monitoring | Derive `last_valid_reading_at`, expected cadence, late/missing status, and source health by system/series. | Separates "system is unhealthy" from "we have no valid observation." |
| Security | Segment customer-facing data and potentially sensitive healthcare documentation using Ontology/data security boundaries; ensure notification recipients have access to included object data. | Customer and healthcare compliance records require controlled exposure. [2][16] |

Foundry supports both direct time-series properties on an object type and a separate time-series object-type configuration. When every object of one type owns the same time-series property pattern, direct properties are appropriate; when modeling many independently described sensors/series, separate series objects give more flexible metadata and row-level expansion. [7]

### Relational state versus time-series state

Keep the following as **current relational state** in curated ontology-backing datasets:

- Customer account tier, ACV, active contract, SLA, contact and facility metadata.
- System treatment program, criticality, lifecycle status, and system lineage.
- Current open work orders, current alert owner/severity/due date, next service due, missed-service state.
- Current inventory position, on-order quantities, projected days of supply, and reorder state.
- Current customer commitments, owner, due date, completion evidence, and approval status.
- Latest valid reading and compact derived indicators such as `latest_conductivity`, `latest_reading_at`, `trend_status`, and `active_alert_count`.

Keep the following in **event/time-series stores**:

- Every raw/normalized chemistry reading.
- BMS/controller streams.
- Inventory transactions.
- Chemical application events.
- Service visits and per-system service events.
- Communication and commitment lifecycle events.
- Assessment history and alert disposition history.

This hybrid model lets Workshop/Object Views render fast "current operational state" while still allowing users to drill from a risk flag into the measurement series, service events, notes, and original source evidence.

### Data-quality gates

Implement data-quality checks as first-class pipeline outputs rather than silent cleanup:

- **Schema and freshness:** expected columns, source extract date, file format, volume anomalies, late BMS data.
- **Identifier resolution:** canonical customer/facility/system/employee map coverage; unresolved aliases held in a review queue.
- **Referential integrity:** no chemistry record should be promoted into system-level analytics without either a resolved system or an explicitly visible unresolved status.
- **Unit and range checks:** pH outside 0–14 and negative concentrations are invalid by definition; do not trigger operational treatment response from them. [6]
- **Conversion checks:** mS/cm to uS/cm and grains-per-gallon to ppm as CaCO3 conversions must occur only when unit notation confirms the source unit. [6]
- **Program compatibility:** evaluate CT-HC2 systems against CT-HC2 conditions, not CT-STD thresholds; BP-HP systems must not inherit standard-boiler limits. [6]
- **Sampling validity:** flag unrepresentative sample points, unflushed samples, and suspicious lab-to-field mismatches for review while retaining the original observation. [6]
- **Correction provenance:** use append/supersede semantics, not destructive updates.
- **Business-rule transparency:** expose rule version, applied threshold, source program, and explanation on `ReadingAssessment` and `OperationalAlert`.

### Delivery sequence

A pragmatic FDSE delivery order would be:

1. Build Raw, Clean, and reconciliation datasets for customer/facility/system/employee identity, service visits, readings, work orders, and inventory.
2. Create the `CustomerAccount` → `Facility` → `WaterSystem` backbone and the visit/work-order links.
3. Normalize readings and implement treatment-program-aware assessments for the highest-value risks: missed service, critical system treatment interruption, sustained iron/inhibitor/biocide trends, healthcare dipslide escalation, and inventory below reorder/projected demand.
4. Create `OperationalAlert`, `CustomerCommitment`, and unified ownership/due-date workflow.
5. Implement the first three actions: schedule visit, triage alert, and record service completion.
6. Add high-frequency time-series sync and rollups only for BMS assets that genuinely produce enough data to justify it; do not over-engineer a small operational portfolio.
7. Add FieldFlow and customer-communication write-backs after object and action behavior has been validated with real operators.

This sequencing aligns the Ontology to the client's actual operational failure modes — late recognition, invisible account context, hidden trends, missed coverage, fragile routing knowledge, and inventory surprises — rather than building a generic asset registry. [2][6]

---

## References

1. `candidate-brief.pdf`
2. `organization_context.pdf`
3. `data_dictionary_relational_mapping.md`
4. https://palantir.com/docs/foundry/object-link-types/object-types-overview/
5. https://palantir.com/docs/foundry/interfaces/interface-overview/
6. `treatment_guidelines.pdf`
7. https://palantir.com/docs/foundry/time-series/time-series-overview/
8. https://palantir.com/docs/foundry/time-series/time-series-concepts-glossary/
9. https://palantir.com/docs/foundry/object-link-types/link-types-overview/
10. https://palantir.com/docs/foundry/ontology/ontology-best-practices/
11. https://palantir.com/docs/foundry/interfaces/implement-interface/
12. https://palantir.com/docs/foundry/ontology/overview/
13. https://palantir.com/docs/foundry/action-types/parameter-overview/
14. https://palantir.com/docs/foundry/action-types/webhooks/
15. https://palantir.com/docs/foundry/action-types/notifications/
16. https://palantir.com/docs/foundry/action-types/permissions/
17. https://www.palantir.com/docs/foundry/action-types/test-run/
18. https://palantir.com/docs/foundry/data-integration/datasets/
19. `candidate-brief.pdf`
20. `organization_context.pdf`
21. `treatment_guidelines.pdf`
22. https://palantir.com/docs/foundry/functions/ontology-imports/
23. https://palantir.com/docs/foundry/interfaces/interface-link-types-overview/
24. https://palantir.com/docs/foundry/object-link-types/base-types/
25. https://palantir.com/docs/foundry/object-link-types/type-groups/
26. https://palantir.com/docs/foundry/action-types/rules/
27. https://palantir.com/docs/foundry/ontology/core-concepts/
28. https://palantir.com/docs/foundry/action-types/getting-started/
29. https://palantir.com/docs/foundry/action-types/overview/
30. https://palantir.com/docs/foundry/time-series/faqs/
31. https://www.palantir.com/docs/foundry/action-types/explore-action-types
32. https://palantir.com/docs/foundry/action-types/side-effects-overview/
33. https://palantir.com/docs/foundry/object-edits/materializations/
