# Operational findings

What SegoSight surfaces from Sego's own data, with the evidence behind each.
These are the conclusions the product exists to reach — and the regressions that
would matter most if a change silently lost them.

Every figure below was checked against the warehouse. Counts regenerate on each
pipeline run; the **evidence chain** is the durable part. Reproduce any of them
with the queries noted, or `./.venv/bin/python -m segosight.app.pipeline`.

As of the September 2026 corpus: **41 alerts** — 2 critical, 14 high, 25 medium.

---

## 1. A boiler failure that five months of data predicted

**SYS-0006, Bonneville Foods Ogden Plant · $96,000/yr · critical**

| | |
| --- | --- |
| Field iron, 26 readings | **0.19 → 1.50 ppm**, 2026-03-03 to 2026-08-25 |
| Action level (BP-STD) | **2.0 ppm — never reached** |
| Trend rule first satisfied | **2026-03-31**, iron at 0.40 ppm |
| First run recorded | 2026-03-17 → 2026-04-14 (5 services) |
| Boiler fails | **2026-09-02** — WO-0158, "oxygen pitting and thinning consistent with long-term corrosion" |
| Cost | **$41,800** |

Iron climbed monotonically for five months and never breached its limit. Any
threshold-based system stays silent for the entire run. The three-consecutive-
services trend rule is first satisfied **155 days before the failure**, with
iron at 0.40 ppm — comfortably inside the band.

This is the client's own complaint made concrete: *"A boiler we treat failed
this month, and our own records arguably saw it coming."* They did.

**Why the lab nearly hid it.** The contract lab read the same unit at
**0.14–0.51 ppm** across 6 samples — roughly a third of the field values, with
no visible trend. Pooling lab and field into one series flattens the signal
entirely. This single case is why measurement series are keyed on
`system × parameter × collection_method` ([decisions §2.3](decisions.md)).

**A human saw it too, in writing.** Marcus Webb, 2026-07-28, 36 days before the
failure: *"Recommending a proper condensate survey and an internal inspection at
the fall outage."* No work order followed. SegoSight surfaces the note as
evidence attached to the corrosion alert.

```sql
SELECT observed_at::DATE, normalized_value, collection_method
FROM canonical.reading_event
WHERE system_id = 'SYS-0006' AND parameter_code = 'iron' AND is_current
ORDER BY observed_at;
```

---

## 2. A three-month healthcare compliance gap

**SYS-0004, cooling tower CT-2, Maeser Ridge Regional Medical Center · $128,000/yr**

| | |
| --- | --- |
| Escalation triggers | **20**, 2026-05-25 to 2026-09-08 |
| Undocumented | **18 of 20** |
| First director notification due | **2026-06-15** |
| Longest gap without a work order | **109 days** |
| Breakdown | 13 director notification · 5 urgent offline clean · 2 corrective |

Guidelines §5.3 governs healthcare sites: two consecutive dipslides at or above
10⁴ require director notification within one business day, a written remediation
plan to the customer, and weekly re-tests until two consecutive results return
to 10³. A single 10⁵ requires an urgent offline clean recommendation.

That threshold was crossed on **2026-06-15**. The tower's only work order
(WO-0160) was raised **2026-09-09**, and it is a *proposal* awaiting customer
approval. The addendum is unambiguous: *"The escalation exists on paper or it
did not happen."*

**The mechanism is in the same data.** Free halogen across 28 readings spans
**0.05–0.99 ppm** against a 0.5–1.0 band — biocide control collapsed, and the
microbiological growth followed. SegoSight raises both and ranks the escalation
first; the halogen alert explains *why*.

> A bug worth remembering: an early build accepted **any** later work order as
> documentation, so WO-0160 retroactively "documented" escalations back to May,
> reporting this gap as fully closed. Evidence must land inside
> `documentation_window_days` ([decisions §4.7](decisions.md)).

```sql
SELECT observed_at::DATE, dipslide_log10, escalation_type, documented, days_undocumented
FROM curated.microbio_escalation WHERE system_id = 'SYS-0004' ORDER BY observed_at;
```

---

## 3. An A-tier account unserviced for nine weeks

**F-0004, Kestrel Aerospace Components · $84,000/yr · weekly contract**

| | |
| --- | --- |
| Last visit | **2026-07-10**, by **Kyle Bishop** |
| Days since | **63** — **9.0× the contracted cadence** |
| Status | critically overdue |

Kyle Bishop left the company in mid-July 2026. His routes were redistributed;
this account was not. The customer noticed before Sego did — Dave Pulsipher,
2026-08-21: *"We have not seen a Sego technician since Kyle's last visit in
early July. Six weeks, no calls, no explanation, on a weekly contract."*

**And the recovery promise was also missed.** Rosa replied the next day: *"I am
arranging coverage and will confirm a technician and a day for this coming week
by Monday."* Due **2026-08-24**. **18 days overdue** with still no visit.

That commitment exists nowhere in the structured data — no work order, no
scheduled visit, no flag. It lives in one sentence in an email, and SegoSight
finds it because coverage gaps and prose commitments are both first-class.

Coverage is detected as an **absence**: `visit_status` reads 'completed' on 321
of 324 visits, so an unserviced site produces no row at all.

---

## 4. A closed loop that is not closed

**SYS-0019, Pintura Polymers Springville Plant · $38,000/yr**

| | |
| --- | --- |
| Nitrite, 16 readings | **1050 → 410 ppm** |
| Band (CL-N) | **900–1,200 ppm** |
| Iron peak | **1.35 ppm** (limit 1.0) |
| CL-40 consumed at the facility | **131 gallons across 14 doses** |

Guidelines §8: *"after initial charge, a tight loop consumes almost nothing.
Recurring multi-gallon CL-40 dosing at one site means the loop is losing water,
and the chemical spend is the symptom, not the problem."* 131 gallons is not
maintenance dosing.

The nitrite baseline falls continuously across 15 consecutive services and never
recovers between doses — the signature of make-up water diluting inhibitor, not
of normal consumption. Rising iron corroborates it. A technician recorded the
mechanism directly: *"Makeup meter 53,900. Loss continuing."*

> This finding was **lost twice** during development. The trough comparison used
> `min(first_value)`/`max(last_value)`, correct for rising series and wrong for
> falling ones; then a headroom guard dropped it again because the third reading
> already sat below the floor. Directional asymmetry is easy to get wrong
> ([decisions §4.5](decisions.md)).

---

## 5. A thousandfold excursion that never happened

**SYS-0014 – SYS-0017, Silver Sage Data Services · $110,000/yr · CT-HC2**

Not a finding — a **false alarm the system avoids**, and the clearest
demonstration of why unit handling is load-bearing.

On **2026-07-14** the BMS feed for four critical cooling towers switched from
mS/cm to uS/cm. The raw numbers jump from ~2.9 to ~2900 overnight. All four
series carry `distinct_raw_units = 2` across 197 observations.

Honouring the `units` column, the mean conductivity is **2861.0 before** the
switch and **2845.8 after** — a 0.5% difference. Continuity preserved. Ignoring
it manufactures a 1000× excursion on four critical systems simultaneously.

Jenn Fowler diagnosed it the next day and wrote it down: *"their vendor swapped
the tower controller on 7/14... whoever looks at that history later needs to
know about 7/14 or they will think the towers went crazy."*

A second trap sits on the same systems: CT-HC2 towers intentionally run at
2,400–3,400 uS/cm. Judged against CT-STD's 800–1,800 band, every reading is an
exceedance. An early build produced **787 false exceedances** here
([decisions §4.2](decisions.md)); guidelines §6.1 forbids reporting them.

---

## 6. A reuse-water tower drifting out of program

**SYS-0042, CleanPeak Linen Services · $36,000/yr**

Conductivity rising **1356 → 2110 uS/cm**, longest run **8 consecutive
services**, with **7 readings already outside the CT-STD band**.

This is guidelines §6.4: a reuse-fed tower drifting upward is not an HC2 system,
and *"quietly tolerating the drift is not one of the paths."* Jenn Fowler,
2026-08-14: *"Recommended: firm up the bleed setpoint and consider moving this
tower to the high-cycles product... Needs a decision, not just me poking the
valve every Friday."* Open **28 days**, no work order.

It is the only scaling-risk alert that survives promotion — boiler conductivity
is excluded (blowdown cycles it by design) and towers cycling inside their band
don't qualify.

---

## 7. Written concerns that never became work orders

Guidelines §9 makes the work order the record and verbal notification a
courtesy. These technician notes never produced one:

| Days open | Author | Note |
| --- | --- | --- |
| 148 | Webb, 2026-04-16 | *"Somebody should get the lab to just use our IDs."* |
| 114 | Bishop, 2026-05-20 | *"Flagged to Rosa to open a work order closer in."* |
| **95** | **Fowler, 2026-06-08** | ***"We should get this on paper."*** — at the hospital |
| **45** | **Webb, 2026-07-28** | ***"Recommending a proper condensate survey and an internal inspection"*** — SYS-0006, 45 days before it failed |
| 28 | Fowler, 2026-08-14 | *"Needs a decision, not just me poking the valve every Friday."* |

The hospital entry is the sharpest: a technician wrote that the escalation
needed to be on paper, and it never was — the exact requirement §5.3 states.

All of these land in the review queue as **pending**, never as fact. A human
approves or discards each one ([decisions §5.2](decisions.md)).

---

## 8. Data findings with operational consequences

**Three duplicate records**, all merged with recorded evidence:

| Source | Canonical | Confidence | Basis |
| --- | --- | --- | --- |
| CUST-0019 | CUST-0007 | high | Rosa's go-live email |
| F-0022 | F-0009 | high | Same address, zero systems, visits service F-0009's equipment |
| F-0021 | F-0003 | **medium** | Same evidence pattern — but documented **nowhere** |

The Bonneville duplicate (F-0021) appears in no email, note or data dictionary.
Its only corroboration is a `customers.csv` note: *"Entered during 2025 CRM
cleanup."* It is mapped at medium confidence pending Rosa's confirmation.

Left unmerged, these split Timpanogos' service history 11/3 and Bonneville
Clearfield's 12/2 — producing **false coverage alerts on A- and B-tier
accounts**, the opposite of the product's purpose.

**Seasonal closure prevents the inverse error.** Powder Basin Lodge is **123
days** past its last visit and entirely on schedule; its contract reads
"monthly (seasonal: closed mid-May to mid-Oct)". Jenn Fowler, in a note: *"That
is the contract, not us forgetting them. It trips people up every summer when
they see the gap in the visit log."* A test asserts no seasonally-closed site
ever raises a coverage alert.

---

## What is *not* found

Stated plainly, because absence of an alert is not evidence of absence.

- **Per-system chemical consumption.** 269 of 316 chemical-bearing visits serve
  multiple systems with no per-system boundary in the source. Facility grain
  only ([decisions §2.4](decisions.md)).
- **Inventory risk.** `chemical_inventory.csv` is landed but unused by alerting.
  It is a snapshot with no transaction history, so stockout projection would be
  guesswork — despite "inventory surprises" being a stated pain.
- **Anything in the two medium-confidence lab mappings.** `CLPK-B1` and
  `MRMC-B1` resolve for display but contribute zero alert-eligible readings.
  Maeser Ridge has two fire-tube boilers, so "boiler 1" is genuinely ambiguous —
  and it is a healthcare account.
