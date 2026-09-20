# Field notes

**Initial Read of the Problem**
When I first looked at the Sego Industrial Water data, I was a bit overwhelmed by
how messy it was. There were typos, missing fields, and crucial information
hidden in plain text emails. However, after breaking it down, I realized the core
problem wasn't about building a massive enterprise system. It was about helping
Dana (the Operations Director) see exactly which accounts needed immediate
attention on Monday mornings so she wouldn't be blindsided by failing equipment
or angry clients.

**What I Prioritized and Why**
I heavily prioritized the data pipeline and backend ontology over a flashy UI. If
the system couldn't accurately link a messy lab report to the correct hospital
cooling tower, the dashboard would be useless. I focused on building a solid
foundation (Raw -> Clean -> Canonical -> Curated) before even touching the
front-end.

**Approaches Considered and Rejected**

*   **External AI APIs for Data Extraction:** I initially wanted to use an
    external AI API (like OpenAI or Gemini Flash) to parse the messy unstructured
    text notes. I rejected this because the challenge prohibits including secrets
    or paid API keys in the submission, and because an evaluator should be able
    to clone the repo and have it run. Instead I relied on deterministic
    rule-based extractors, with an optional local open-weight model that is off
    by default and runs through the same human review gate.
*   **Flutter Mobile App:** I briefly considered building a mobile app for the
    technicians. I rejected this because they already use a software called
    "FieldFlow". The real target audience is Dana in the office, so a web
    dashboard made much more sense.
*   **Heavy Postgres Database:** I thought about setting up a separate PostgreSQL
    database. I rejected this because the company has no IT staff. Sticking to a
    local DuckDB file made the system much easier to run and review locally
    without complex setups.

**Assumptions Made**
I assumed that the unstructured technician notes were just as important as the
numerical CSV data. I also assumed that the new September data batch needed to be
handled as a "delta update" rather than a full system wipe, meaning the pipeline
had to be smart enough to append new records without duplicating old ones.

**What Went Wrong / Failed**
While testing the alerting rules, my trend aggregation logic failed. I was using
a simple min/max calculation to track rising chemical levels. This worked fine
for rising trends, but it completely missed a massive *falling* trend (a nitrite
collapse at Pintura, 1050 down to 410 ppm) because my code dropped it. I had to
rewrite the aggregation logic to properly track consecutive falling troughs so
the system wouldn't silently ignore a massive leak.

**What I Learned from the Operational Data**
The operational data taught me that real-world transitions are messy. When Sego
switched to their new "FieldFlow" software in September, the date formats
completely changed, and technician names turned into initials. I learned that you
cannot hardcode schemas; the pipeline has to dynamically map and handle
variations.

**What I Would Change with Another Week**
I would build out the write-back capabilities, so that when Dana approves a
missing work order in SegoSight it automatically pushes that record back into the
technicians' FieldFlow system. I would also add alert triage — assign, snooze,
close with a reason — because right now Dana can see the queue but can't record
what she did about it, so the second week is as noisy as the first.
