# SegoSight

An operational attention system for Sego Industrial Water.

## Quick start

**Prerequisites:** Python 3.11+, Node 20+, and pnpm (`npm install -g pnpm`).

#### macOS / Linux

```bash
./run.sh
```

#### Windows (PowerShell)

```powershell
.\run.ps1
```

Then open <http://127.0.0.1:8000>.

That one command creates the virtualenv, installs dependencies, builds the
warehouse from the source data, builds the UI and serves it. First run takes
about two minutes, almost all of it `pnpm install`; later runs take seconds.

**Check it worked.** The dashboard should show 41 active alerts, 2 of them
critical, and 24 items awaiting review. Click any alert to see the evidence
behind it.

#### Running tests

| Platform | Command |
| --- | --- |
| macOS / Linux | `./.venv/bin/python -m pytest -q` |
| Windows | `.\.venv\Scripts\python -m pytest -q` |

366 tests, ~9 s.

### If you would rather run the pieces

<details>
<summary>macOS / Linux (bash)</summary>

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m segosight.app.pipeline   # build the warehouse, ~2s
./.venv/bin/python -m pytest -q                # 366 tests, ~9s
cd ui && pnpm install && pnpm run build        # UI bundle
./.venv/bin/python -m uvicorn segosight.app.api:app --port 8000
```

</details>

<details>
<summary>Windows (PowerShell)</summary>

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m segosight.app.pipeline   # build the warehouse, ~2s
.\.venv\Scripts\python -m pytest -q                # 366 tests, ~9s
cd ui; pnpm install; pnpm run build; cd ..         # UI bundle
.\.venv\Scripts\python -m uvicorn segosight.app.api:app --port 8000
```

</details>

#### Dev mode (hot reload)

| Platform | Command | Result |
| --- | --- | --- |
| macOS / Linux | `./run.sh dev` | API on :8000, Vite dev server on :5173 |
| Windows | `.\run.ps1 dev` | API on :8000, Vite dev server on :5173 |

### Two things worth knowing

**DuckDB allows one writer, and the API holds it.** Running the pipeline in a
terminal while the server is up fails with a lock error. Use the **Upload
data** button in the UI, or stop the server first.

**To start completely fresh**, delete the warehouse and re-run. It rebuilds
from source in about two seconds:

```bash
# macOS / Linux
rm -rf warehouse && ./run.sh
```

```powershell
# Windows
Remove-Item -Recurse -Force warehouse; .\run.ps1
```

## Where to look first

| If you want to see | Go to |
| --- | --- |
| The headline finding | Alert `corrosion_trend:SYS-0006:iron` — iron climbed for five months inside its band before a $41,800 boiler failure |
| Human-in-the-loop AI | The **Pending insight review** tab; nothing from prose enters a governed table without a named approval |
| Ingesting a new batch | The **Upload data** button — upload a folder, review what would change, then confirm |
| What I built and why, in 500 words | [`WRITEUP.md`](WRITEUP.md) |
| How the work actually went, including what broke | [`FIELD_NOTES.md`](FIELD_NOTES.md) |
| Which AI tools I used, and what I rejected | [`AI_USAGE.md`](AI_USAGE.md) |
| Why the code is shaped this way | [`context/decisions.md`](context/decisions.md) |
| The traps in the source data | `context/data-quirks.md` — 15 of them, each with the test that guards it |

**Primary user:** Dana Whitlock, Operations Director. SegoSight answers her
Monday-morning question — which sites need attention, why, what it costs if we
sit on it, and who is doing what about it — from the company's existing
fragmented exports, without anyone hand-cleaning a spreadsheet first.

## Source data

Read in place from `data/`, never modified. Each batch is a directory named in
`segosight/config/sources.toml`. Point the pipeline at a different drop with:

```bash
export SEGOSIGHT_MATERIALS=/path/to/data
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

## Incorporating a new data batch

Append a `[[batches]]` entry to `config/sources.toml` pointing at the new
directory. Existing entity globs match renamed files (`service_visits.csv` and
`service_visits_2026-09.csv` share one pattern), new columns are absorbed into
the JSON payload and reported as drift, and `sequence` decides which version of
a re-issued record wins. Re-running the pipeline is idempotent.

## Design decisions and data quirks

Both moved out of this file to keep it short.

| Document | What is in it |
| --- | --- |
| [`context/decisions.md`](context/decisions.md) | ~30 architectural decisions with the alternatives rejected and why. Read before proposing a redesign |
| [`context/data-quirks.md`](context/data-quirks.md) | Every deliberate trap in the source data, each with the test that guards it. Read before simplifying a parser |
| [`context/ontology-design.md`](context/ontology-design.md) | The object model, the tier-by-tier table contracts, and where this build diverges from the supplied reference design |
| [`context/findings.md`](context/findings.md) | What the system concludes, with the evidence chain behind each one |
