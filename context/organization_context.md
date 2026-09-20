# Company and Operations Context

**SEGO INDUSTRIAL WATER**
*Prepared September 2026 for an outside systems engagement*

> Markdown conversion of `organization_context.pdf`. Content is reproduced
> verbatim; only the page headers, footers and line wrapping of the original
> layout have been dropped.

Prepared September 2026 by D. Whitlock (Operations Director) for an outside
systems engagement. This document describes who we are, how we operate today,
and where the current process hurts. It deliberately does not prescribe a
solution.

## 1. The company

Sego Industrial Water is a water treatment service company based in Salt Lake
City, founded in 1998 and still owner-operated. We design and run chemical
treatment programs for steam boilers, cooling towers, evaporative condensers,
and closed loops at industrial and institutional facilities across Utah, from
Logan to St. George. Revenue comes from service contracts (most accounts) with
chemicals billed as consumed, plus project work like cleanings, layups, and
equipment repairs.

We currently serve roughly two dozen contracted facilities: hospitals and
senior living, food and beverage plants, a data center campus, aerospace and
electronics manufacturers, hospitality properties, a university campus, and
assorted smaller industrial accounts. Contracts range from weekly to monthly
service. A handful of accounts represent a disproportionate share of revenue
and reputation; losing one of them would be a bad year.

## 2. The team

Twelve employees. The people who show up in the operational records:

**Walt Neilsen**, owner and general manager. Sales, senior customer
relationships, pricing.

**Dana Whitlock**, operations director. Runs field operations, technical
standards, and escalations. The person most often blindsided by problems that
"someone knew about."

**Rosa Camacho**, service coordinator. Scheduling, dispatch, customer
communication, invoicing handoff to bookkeeping. Keeper of most institutional
knowledge about which account is which.

**Field technicians:** Dale Hardy (22 years, southern and central routes),
Marcus Webb (senior technician, northern industrial routes), Jenn Fowler
(healthcare and critical accounts), Tomas Rivera (northern routes), and Aaron
Silva (hired July 2026, still ramping). A sixth technician, Kyle Bishop, left
the company in mid-July 2026; his routes were redistributed.

There is no IT staff. The most technical system administration anyone does is
managing the shared drive.

## 3. How operations run today

Each technician runs a route of recurring visits (weekly, biweekly, or monthly
per contract). At each visit they test the water systems on site, dose
chemicals, handle small repairs, and record what they did. Bigger problems
become work orders, which Rosa tracks and assigns. Emergencies come in by phone
or email and get squeezed into routes as callouts.

Recording is the weak point, and everyone knows it. Test results go on paper log
sheets at the site, into a spreadsheet later, or both. Notes about what a
technician saw and worried about live in per-visit text files, in whatever style
each technician favors. Some sites send us their own building automation
exports. Our contract lab emails PDF and CSV reports in its own format with its
own sample point codes. Customer complaints and requests arrive in a shared
service inbox. Chemical inventory is a spreadsheet updated when someone
remembers.

In September 2026 we switched scheduling and visit logging from our old
ServiceTrak tool to a hosted product called FieldFlow. Data before the switch
was exported from ServiceTrak; data after arrives in FieldFlow's export format.
The migration also merged some duplicate records and renamed some identifiers;
Rosa circulated the details by email.

## 4. What management is worried about

The pattern that keeps repeating: information existed, in a spreadsheet or a
note or an email, and the company still got surprised. A boiler we treat failed
this month, and our own records arguably saw it coming. A major account went
unserviced for weeks after a staffing change and told us about it before we
noticed. A hospital has been asking for documentation we should be able to
produce in an afternoon and currently cannot.

Dana's framing of the problem, roughly verbatim:

> "Every Monday I want to know which sites need attention, why, what it costs us
> or the customer if we sit on it, and who is doing what about it. Today the only
> way to know that is to have read everything and remember all of it. Rosa and I
> are the database. That does not scale past about twenty accounts, and we are
> past twenty accounts."

Specific recurring pains, in management's own words:

- **The office finds out about field concerns late or never.** Technicians flag
  things in notes and verbally on site, and some of those flags deserve work
  orders and customer conversations that never happen.
- **Nobody can see a whole account at once.** Readings, visits, work orders,
  notes, lab reports, and emails about the same site live in five places.
  Answering "what is going on at this customer" is an archaeology project.
- **Trends hide.** A number that drifts a little every week never trips anyone's
  alarm on any single day.
- **Data quality is uneven.** Units vary by person and instrument, the same
  customer exists twice in the billing system, identifiers differ between our
  records and the lab's, and at least some readings are simply typos.
- **Inventory surprises.** We discover a chemical is short the week we need it.
- **Coverage fragility.** Routes live in people's heads. When staffing changes,
  things fall through cracks and we find out from customers.

## 5. Constraints and environment

Technicians carry phones and are not going to type essays in the field; whatever
they record has to be fast. Cell coverage at several rural sites is poor. The
office runs on ordinary business software: email, spreadsheets, the shared
drive, QuickBooks for accounting (not in scope of the data you have), and now
FieldFlow for scheduling. There is no budget appetite for enterprise platforms
or dedicated IT headcount; there is appetite for anything that demonstrably
prevents another month like this September.

Customer-facing sensitivity is real: several accounts are healthcare facilities
where water safety documentation is a compliance matter, and several are large
contracts where service lapses put renewals at risk. Anything that touches what
customers see needs to be right before it is fast.

## 6. About the data provided

The extract accompanying this document covers roughly six months of operations
(March through August 2026) plus a smaller batch from early September 2026 in
the new export formats. It includes the customer and system records, service
visits, water test readings, work orders, chemical inventory, technician notes,
the service inbox, and our internal treatment guidelines. It is the real working
data, warts and all: nobody has cleaned it, and it disagrees with itself in the
ways working data does. Treat the warts as part of the terrain, not as an
obstacle between you and some cleaner dataset that does not exist.
