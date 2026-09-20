# Water Treatment Program Guidelines

**SEGO INDUSTRIAL WATER**
*Internal reference, Revision 6, February 2026*

> Markdown conversion of `treatment_guidelines.pdf`. Content is reproduced
> verbatim; only the page headers, footers and line wrapping of the original
> layout have been dropped. The tables below are the same tables as the source.

Sego Industrial Water internal reference. Revision 6, February 2026. Prepared by
D. Whitlock with field review by senior technicians.

## 1. Purpose and scope

This document defines control limits, interpretation rules, and escalation
requirements for the treatment programs Sego operates at customer sites. It
covers steam boilers, open recirculating cooling systems (towers and
evaporative condensers), closed loops, and pretreatment equipment.

These are operating guidelines, not a substitute for judgment. Two systems with
identical readings can deserve different responses depending on program,
equipment, and history. Where this document and a system-specific program sheet
disagree, the program sheet governs, and the technician should flag the
disagreement for reconciliation.

## 2. Sampling and data recording standards

Consistent recording matters as much as consistent treatment. Standard units for
Sego field records are:

| Parameter | Standard unit |
| --- | --- |
| Conductivity | microsiemens per centimeter (uS/cm) |
| Hardness, alkalinity | ppm as CaCO3 |
| Chloride, iron, nitrite, molybdate, sulfite, inhibitor | ppm |
| Microbiological activity | dipslide culture, reported as 10^x CFU/ml |

Field meters, controller displays, and laboratory instruments do not all use
these units. Conductivity in particular is commonly displayed in mS/cm on some
controllers and lab reports (1 mS/cm = 1,000 uS/cm), and some technicians
trained in other industries record hardness in grains per gallon
(1 gpg = 17.1 ppm as CaCO3). Values must be converted to standard units when
entered into customer-facing reports. **Where a record carries its own unit
notation, the notation governs over any assumption.**

Samples should be drawn from designated sample points after an adequate flush.
Samples from dead legs, stagnant branches, or pot feeder shells are not
representative and should be re-drawn; if an unrepresentative result has already
been recorded, it stays in the record and is annotated rather than deleted.

## 3. Control limits by treatment program

The limits below are the default bands for each program. Section 6 lists
exceptions that override this table for specific system classes. Applying this
table without checking Section 6 is the most common error new technicians make.

### 3.1 Steam boilers

| Parameter | BP-STD (up to 150 psig) | BP-HP (150 to 400 psig) |
| --- | --- | --- |
| Boiler water conductivity | 2,200 to 3,500 uS/cm | 800 to 1,500 uS/cm |
| Boiler water pH | 10.5 to 11.5 | 9.8 to 10.5 |
| M alkalinity | 500 to 800 ppm | 200 to 400 ppm |
| Sulfite residual | 20 to 40 ppm | 30 to 50 ppm |
| Feedwater hardness | below 2 ppm | below 1 ppm |
| Boiler water iron | below 2.0 ppm (action level, see 4.2) | below 1.0 ppm |

### 3.2 Open cooling systems (towers and evaporative condensers)

| Parameter | CT-STD | CT-HC2 (high cycles, see 6.1) |
| --- | --- | --- |
| Conductivity | 800 to 1,800 uS/cm | per 6.1 |
| pH | 8.0 to 9.0 | 8.2 to 9.0 |
| Total hardness | below 750 ppm | per 6.1 |
| Chloride | below 300 ppm | below 300 ppm |
| Free oxidizing biocide | 0.5 to 1.0 ppm | 0.5 to 1.0 ppm |
| Inhibitor residual (CT-770) | 8 to 14 ppm | n/a |
| Inhibitor residual (CT-785) | n/a | 12 to 18 ppm |
| Dipslide | below 10^4 CFU/ml (see 5) | below 10^4 CFU/ml (see 5) |

### 3.3 Closed loops

| Parameter | CL-N (nitrite) | CL-M (molybdate) |
| --- | --- | --- |
| Nitrite residual | 900 to 1,200 ppm | n/a |
| Molybdate residual | n/a | 200 to 300 ppm |
| pH | 8.5 to 10.5 | 8.0 to 10.0 |
| Iron | below 1.0 ppm | below 1.0 ppm |
| Conductivity | record for trend; no fixed limit | record for trend; no fixed limit |

A closed loop holding its inhibitor residual between services is healthy. A loop
that repeatedly consumes inhibitor is telling you it is not closed: look for
water loss before adding more chemical.

## 4. Interpreting results: excursions versus trends

### 4.1 Single excursions

A single out-of-band reading is a prompt to verify, not an emergency. Re-test
where practical, check the sample point, check the unit notation, and check for
a site event (rain dilution of open towers, recent makeup, recent blowdown).
Physically impossible values (for example a pH outside the 0 to 14 scale, or a
negative concentration) are recording or instrument errors by definition and
must be corrected in the record, not acted on.

Open towers diluted by heavy weather will read low on conductivity and inhibitor
for several days and recover on their own. Do not chase setpoints after a storm.

### 4.2 Sustained trends

A parameter moving steadily in one direction across three or more consecutive
services indicates an active mechanism, and the time to investigate is at the
trend stage, not at the limit. This applies even when every individual reading
is inside its band. The canonical example: boiler or loop iron climbing month
over month from a stable baseline indicates active corrosion well before the
2.0 ppm action level is reached, and waiting for the limit generally means the
metal loss has already happened. Rising tower conductivity against a fixed bleed
setpoint, falling biocide residual at constant feed, and growing gaps between
chemical dose and residual all earn the same treatment: find the mechanism.

Trend judgments require consistent units across the series. Verify unit notation
before concluding a step change is real; a controller or lab scale change can
masquerade as a thousandfold excursion.

## 5. Microbiological control

### 5.1 Monitoring

Open recirculating systems receive a dipslide culture at every routine service.
Results are semi-quantitative powers of ten.

### 5.2 General sites

| Dipslide result | Response |
| --- | --- |
| 10^3 or below | Normal. Routine program. |
| 10^4 | Corrective: verify oxidant residual and feed equipment, supplemental biocide, re-test at next service. |
| 10^5 or above | Elevated: corrective actions plus physical inspection for fouling; consider offline cleaning if regrowth recurs. |

### 5.3 Healthcare and assisted-living sites (addendum)

Facilities serving patient or resident populations run a tighter ladder because
of aerosol exposure risk. For these sites:

Weekly dipslides are required on all open towers regardless of visit frequency
elsewhere in the contract. A result of 10^4 requires same-visit corrective
action and a re-test within one week. Two consecutive results at or above 10^4
require notification of the Sego operations director within one business day, a
documented remediation plan communicated to the customer in writing, and
continued weekly re-tests until two consecutive results return to 10^3 or below.
Any single result at 10^5 requires an urgent recommendation for offline cleaning
and disinfection of the affected tower.

**Verbal mentions to site staff do not satisfy the notification requirement in
this addendum. The escalation exists on paper or it did not happen.**

## 6. Program-specific exceptions and notes

### 6.1 CT-HC2 high-cycles cooling program

Systems formally enrolled in CT-HC2 (confirmed by the treatment_program field on
the system record, not by observed chemistry) intentionally operate far above
the standard conductivity band to reduce water consumption. For CT-HC2 systems
the conductivity band is 2,400 to 3,400 uS/cm, provided both of the following
hold: chloride remains below 300 ppm, and CT-785 inhibitor residual remains at
or above 12 ppm. If either condition fails, the system reverts to CT-STD limits
until restored. Conductivity between 1,800 and 3,400 on an HC2 system is not an
exceedance and must not be reported to the customer as one.

### 6.2 High-pressure boilers (BP-HP)

BP-HP units run much tighter conductivity than BP-STD. Readings that would be
comfortably normal on a standard boiler are serious exceedances on an HP unit.
Route coverage changes are the moment this mistake happens; check the program
before judging the number.

### 6.3 Molybdate loops serving process tooling

For CL-M loops serving semiconductor or precision tooling, hold molybdate in the
upper portion of the band, 225 to 300 ppm, because tool warranties reference
that figure. The 200 ppm floor in Section 3.3 remains the contract minimum;
between 200 and 225 is compliant but should be topped up at the same visit.

### 6.4 Towers on reuse or reclaim makeup water

Towers fed partially with reuse water will drift upward in cycles and
conductivity as reuse fraction increases. This does not make them HC2 systems.
The HC2 band applies only to formally converted systems with the required
inhibitor and monitoring. For a reuse-fed tower drifting above the CT-STD band,
the correct paths are: tighten bleed control, reduce reuse fraction, or formally
convert the program after a chloride and scaling review. Quietly tolerating the
drift is not one of the paths.

## 7. Seasonal layup and shutdown procedures

Sites with seasonal operation (resort properties, schools on summer schedules,
seasonal agriculture) receive a documented layup at shutdown: boilers are laid up
wet with elevated sulfite and buffered alkalinity or dry with desiccant depending
on duration, loops are left circulating with inhibitor verified, and open towers
being idled are drained and cleaned. Layup and recommissioning are recorded as
service visits. A seasonal site showing no visits during its documented closure
window is on schedule, not neglected; the distinction lives in the contract
terms, and coverage reviews should read them before raising an alarm.

## 8. Products and typical consumption

Typical maintenance consumption for a healthy system, for budgeting and anomaly
detection. Sustained consumption well above these figures without a program
change is a finding, not a billing quirk.

| Product | Application | Typical consumption |
| --- | --- | --- |
| BW-210 sulfite blend | Boilers | 1 to 3 gal per service |
| BW-305 alkalinity builder | Boilers | 0 to 2 gal per service |
| AM-115 condensate amine | Boilers with condensate return | about 1 qt per service; do not skip |
| CT-770 inhibitor | CT-STD towers | 3 to 6 gal per service |
| CT-785 inhibitor | CT-HC2 towers | 3 to 6 gal per service |
| BIO-12 / BRM-40 biocides | Open systems, alternated | 1 gal / 5 lb per service |
| CL-40 nitrite/borate | CL-N loops | initial charge about 1 gal per 250 gal volume; maintenance near zero on a tight loop |
| CL-M40 molybdate | CL-M loops | maintenance near zero on a tight loop |

The closed-loop lines deserve emphasis: after initial charge, a tight loop
consumes almost nothing. Recurring multi-gallon CL-40 or CL-M40 dosing at one
site means the loop is losing water, and the chemical spend is the symptom, not
the problem.

## 9. Escalation and documentation requirements

Any condition presenting a safety, compliance, or equipment-integrity risk must
be captured as a work order within one business day of identification,
regardless of whether site staff were told in person. Verbal notification is a
courtesy; the work order is the record. Conditions that meet this bar include,
at minimum: microbiological escalations under Section 5.3, suspected active
corrosion under Section 4.2, treatment interruptions on critical systems, and
any repeated equipment failure after a completed repair.

A work order closed after a repair that later recurs is reopened or re-raised
with reference to the original; closing the paperwork does not close the problem.

Customer-facing commitments (a promised visit, a promised document, a promised
plan) are tracked to completion by the service coordinator. A commitment made in
email and not scheduled is a miss waiting to be discovered by the customer.

## 10. Outside laboratory reports

Central Analytical, Sego's contract laboratory, reports conductivity in mS/cm
and identifies sample points with its own codes rather than Sego system IDs. Both
conventions differ from Sego field records. Lab results must be converted to
standard units and mapped to the correct system before they are compared with
field data. The current code crosswalk is maintained informally by the senior
technician group; formalizing it is a known gap.

A lab result and a field result that disagree wildly usually differ by units,
sample point, or timing. Resolve the mundane explanations before concluding the
water changed.
