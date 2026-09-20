# AI usage

**Models and Development Tools Used**

*   **Gemini Pro:** I used Gemini Pro for the initial data analysis and schema
    profiling. Because it has a massive context window, I was able to upload the
    entire raw dataset (all CSVs, PDFs, and text notes) at once. I used it as a
    sounding board to understand the ontology, identify foreign keys, and map out
    the target audience's needs.
*   **Claude Opus:** I used Claude for the actual system architecture and modular
    code implementation. I treated Claude like a senior FDE (Forward Deployed
    Engineer), feeding it the ontology plan and having it write the pipeline in
    phases.
*   **Tech Stack:** DuckDB, FastAPI (Python), and React with Vite for the UI.

**Concrete Example of Rejected/Redesigned Output**

When we started handling the unstructured text (technician notes and emails),
the default approach on the table was a flow where the AI would extract
commitments (like a promised site visit) and write them directly into the active
"Governed Alerts" database table.

I rejected that and substantially redesigned the architecture. Sego deals with
strict healthcare compliance, so an AI guessing a date cannot be treated as a
hard operational fact. I required an intermediate "Pending Insight Review" queue.
In the redesigned system, every extraction lands in a holding area with a
confidence score and the verbatim quote it came from. It only becomes a governed
alert after a human explicitly clicks "Approve", and the approval is recorded
against their name.

I also had the model's own output constrained the same way: any candidate whose
quote does not appear verbatim in the source document is discarded, which is the
one failure mode that would otherwise put invented text in front of a customer.

**Parts of the System Needing Human/Production Validation**

The text extraction pipeline relies heavily on human validation. Since external
AI APIs were rejected to avoid shipping secrets, the local deterministic rules
(regex) are safe but rigid. Any AI-assisted extraction must be reviewed by Dana.

The identity resolution module needs the same treatment, but only in one place.
The customer merge of `CUST-0019` into `CUST-0007` is documented — Rosa Camacho's
FieldFlow go-live email states it explicitly — so it is recorded at high
confidence with her name against it. The facility merge of `F-0021` into `F-0003`
(Bonneville Foods Clearfield) is the one that needs checking: no email, note or
data dictionary mentions it, and it was inferred from the fact that the duplicate
owns zero systems and every visit booked against it services the surviving
facility's equipment. It is recorded at medium confidence with
`authorized_by = "unconfirmed"`, which stops it raising customer-facing alerts on
its own. In production the service coordinator should confirm or reject it before
it is trusted for billing.

**Approximate Personal Time Spent**

I spent roughly 14 hours on this exercise.

*   **Hours 1-3:** Understanding the problem, profiling the data with Gemini, and
    designing the Palantir-style ontology.
*   **Hours 4-9:** Building the backend pipeline with Claude (ingestion,
    cleaning, canonical mapping, and trend alerts).
*   **Hours 10-14:** Pausing to brainstorm wireframes, selecting accessible UI
    colour palettes, implementing the React dashboard, and performing manual
    testing to ensure the demo workflow functioned correctly.
