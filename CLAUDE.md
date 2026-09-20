# SegoSight — working notes for an AI assistant

Operational attention system for Sego Industrial Water, a fictional water
treatment company. It reads their messy exports and answers the operations
director's Monday question: which sites need attention, why, what it costs to
wait, and who owns it.

Background lives in [`context/`](context/) — read those before changing domain
logic, not before a mechanical edit.

| File | When you need it |
| --- | --- |
| `context/candidate-brief.md` | What this project is and how it's judged |
| `context/organization_context.md` | The client, the people, the pain |
| `context/treatment_guidelines.md` | **Control limits and escalation rules.** The domain authority |
| `context/decisions.md` | Why the architecture is the way it is; read before proposing a redesign |
| `context/data-quirks.md` | **Every deliberate trap in the data.** Read before simplifying a parser |
| `context/findings.md` | What the system concludes, and the evidence chain for each |
| `context/Foundry Ontology Design_ Sego Industrial Water.md` | **Theirs.** The supplied Foundry reference design, converted from the PDF beside it |
| `context/ontology-design.md` | **Ours.** How this build maps to that design, and where it diverges |
| `context/data_dictionary_relational_mapping.md` | Field-level source-to-target mapping for the raw corpus |

## Commands

```bash
./run.sh                                       # venv, deps, warehouse, UI build, serve :8000
./run.sh dev                                   # API :8000 + Vite dev server :5173
./.venv/bin/python -m pytest -q                # 307 tests, ~7s
./.venv/bin/python -m segosight.app.pipeline   # rebuild the warehouse (~2s)
./.venv/bin/python -m segosight.features.review.cli list   # review queue in the terminal
cd ui && pnpm run build                        # UI bundle
cd ui && pnpm run tokens                       # regenerate theme tokens from the palette CSS
```

Always use `./.venv/bin/python`, never bare `python3` — the deps are in the venv.

## Things that will bite you

**DuckDB allows one writer.** The API holds it. Running
`python -m segosight.app.pipeline` while the server is up fails with a lock
error. Use the **Ingest data** button in the UI, or stop the server first.

**Never hand out the shared connection.** `dependencies.get_connection()`
returns a *per-request cursor*. Sharing one connection across FastAPI's
threadpool made concurrent requests read each other's result sets — a real bug
that produced a 500 on `/api/overview`. `TestConcurrency` guards it.

**Tests are green while the server is broken.** `run.sh` and `README.md`
reference module paths that pytest never executes. After moving modules, grep
shell scripts and docs too.

**The corpus is full of deliberate traps.** Code that looks over-defensive
usually isn't — see `context/decisions.md` § Data quirks. Before "simplifying"
a parser, check whether it's handling a documented anomaly.

## Layout

```
segosight/
├── app/          FastAPI factory, DuckDB lock, pipeline orchestrator
├── features/     one vertical slice per domain, tier sub-folders inside
│   ├── ingestion/    registry · raw landing · supersede
│   ├── identity/     crosswalk · canonical master data
│   ├── chemistry/    readings · series · limits · assessments · trends
│   ├── service/      visits · chemical applications · coverage
│   ├── compliance/   microbiological escalation ladder
│   ├── alerts/       aggregation · ranking · evidence · router
│   └── review/       documents · extraction · LLM · promotion · router · CLI
├── shared/       warehouse · paths · domain-agnostic normalization
└── config/       governed TOML: sources · identity · treatment_programs

ui/src/
├── app/            shell + routing
├── features/       overview · alerts · review · pipeline
├── design-system/  Material tokens, modes, validated chart colours
└── shared/         api client · formatters · types
```

**Tiers are DuckDB schemas, not folders.** `raw` is immutable and
content-addressed. `clean` parses and supersedes. `canonical` resolves identity.
`curated` applies business rules. A module's docstring names its tier; it writes
to the matching schema.

## Rules this system is built on

**Thresholds live in config, never in code.** All control limits are in
`segosight/config/treatment_programs.toml` with a `rule_version` stamped onto
every judgement. A guideline revision is a config change.

**Programs govern, not chemistry.** A reading is judged against the program on
the *system record*. 2,900 µS/cm is normal on a CT-HC2 tower and a serious
exceedance on a BP-HP boiler. Never infer a program from a value.

**The `units` column governs.** Never infer a unit from a value's magnitude.
Conductivity switches mS/cm→uS/cm mid-file; magnitude-guessing manufactures a
1000× excursion.

**Trends matter more than limits.** Guidelines §4.2: a parameter moving one
direction across 3+ consecutive services is actionable *even inside its band*.
This is the product's whole thesis — SYS-0006 iron climbed for five months,
never reached its action level, and the boiler failed.

**Nothing derived from prose is fact until a human approves it.** Every
extraction lands `status = 'pending_review'` with a confidence score and a
verbatim quote. Approval is attributable and promotes into governed tables.
Never write an extraction straight into a crosswalk, a limit or a compliance
record.

**Never delete evidence.** Corrections supersede; rejections detach. A
superseded reading keeps its row.

## Testing

`pytest` with a session-scoped warehouse built from the real corpus. Tests that
write use `writable_warehouse` (an isolated file copy) — never mutate the shared
`warehouse` fixture, it makes the suite order-dependent.

Many tests assert *operational conclusions*, not just plumbing: that the
SYS-0006 corrosion trend is detected within band, that the seasonal site never
raises a coverage alert, that a late work order cannot retroactively document an
escalation. If one fails, suspect the change before the test.

## AI inside the product

Optional and off by default. `features/review/llm.py` proposes extra candidates
via a local Ollama model, capped at 0.55 confidence, through the same review
gate. Its quote must appear verbatim in the source or the candidate is
discarded. The deterministic extractors are the product; the model is additive.
