"""Pre-ingestion profiling of a staged upload.

Answers the question the review screen exists to ask: *what is about to
happen?* -- which files match known entities, which rows are new against which
supersede existing ones, what the schema drift is, what is unrecognised and
needs a human decision, and whether anything would land orphaned.

Nothing here writes to the warehouse. It reads the staged files with DuckDB's
own CSV reader and compares them against the governed tables, using the same
business-key expression the landing step uses, so the counts it reports are the
counts that will actually occur.

The registry, not this module, decides what a file *is*. Profiling asks the
registry and reports what it says; where the registry has no answer, the answer
is "ask Dana", never a guess written into a compliance record.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path

import duckdb

from segosight.features.identity.canonical.entities import (
    CUSTOMER_TABLE,
    FACILITY_TABLE,
    SYSTEM_TABLE,
)
from segosight.features.ingestion.raw.landing import (
    SCHEMA_TABLE,
    TABLE as RAW_RECORDS,
    _literal,
    _quote,
)
from segosight.features.ingestion.registry import Registry, load_registry
from segosight.features.ingestion.staging import Upload
from segosight.features.review.raw.documents import SUPPORTED_SUFFIXES

BLOCKING = "blocking"
ADVISORY = "advisory"


@dataclass
class EntityProfile:
    """One staged file matched to a registry entity."""

    entity: str
    file: str
    rows: int
    columns: list[str]
    added_columns: list[str]
    missing_columns: list[str]
    new_keys: int
    superseding_keys: int


@dataclass
class DocumentProfile:
    document_class: str
    directory: str
    documents: int


@dataclass
class Unmatched:
    """Something in the drop the registry does not recognise."""

    path: str
    kind: str  # "file" | "directory"
    #: Nearest known name, offered as a suggestion only. Never auto-applied.
    suggestion: str | None
    #: What the suggestion would map it to, if accepted.
    suggestion_target: str | None


@dataclass
class Finding:
    level: str
    code: str
    message: str


@dataclass
class Profile:
    upload_id: str
    batch_root: str
    entities: list[EntityProfile] = field(default_factory=list)
    documents: list[DocumentProfile] = field(default_factory=list)
    unmatched: list[Unmatched] = field(default_factory=list)
    absent_entities: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(e.rows for e in self.entities)

    @property
    def total_documents(self) -> int:
        return sum(d.documents for d in self.documents)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.level == BLOCKING]

    @property
    def can_confirm(self) -> bool:
        return not self.blocking and bool(self.entities or self.documents)


def resolve_batch_root(upload_root: Path) -> Path:
    """Find the directory that behaves as the batch root.

    A folder upload arrives as `new_data_batch/customers.csv`, so the real root
    is one level down. Descend only while there is exactly one directory and no
    data files beside it, which is the unambiguous case.
    """
    current = upload_root
    for _ in range(4):
        children = [c for c in current.iterdir() if not c.name.startswith(".")]
        dirs = [c for c in children if c.is_dir()]
        files = [c for c in children if c.is_file()]
        if len(dirs) == 1 and not files:
            current = dirs[0]
            continue
        break
    return current


def _row_count(path: Path) -> int:
    """Count data rows without loading the file."""
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def _columns(conn: duckdb.DuckDBPyConnection, path: Path) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            f"DESCRIBE SELECT * FROM read_csv({_literal(str(path))}, "
            f"all_varchar=true, header=true)"
        ).fetchall()
    ]


def _baseline_columns(conn: duckdb.DuckDBPyConnection, entity: str) -> set[str] | None:
    row = conn.execute(
        f"""SELECT columns FROM {SCHEMA_TABLE}
            WHERE entity = ? ORDER BY observed_at LIMIT 1""",
        [entity],
    ).fetchone()
    return set(row[0].split(",")) if row else None


def _key_overlap(
    conn: duckdb.DuckDBPyConnection,
    path: Path,
    entity_name: str,
    business_key: tuple[str, ...],
    columns: list[str],
) -> tuple[int, int]:
    """Split incoming business keys into (new, already-known).

    Uses the landing step's own key expression, so these are the rows that will
    actually be treated as supersedes rather than an approximation of them.
    """
    key_expr = ", ".join(
        f"coalesce(r.{_quote(col)}, '')" if col in columns else "''"
        for col in business_key
    )
    read = f"read_csv({_literal(str(path))}, all_varchar=true, header=true)"
    row = conn.execute(
        f"""
        WITH incoming AS (
            SELECT DISTINCT concat_ws('|', {key_expr}) AS business_key
            FROM {read} r
        ),
        known AS (
            SELECT DISTINCT business_key FROM {RAW_RECORDS} WHERE entity = ?
        )
        SELECT
            count(*) FILTER (WHERE k.business_key IS NULL) AS new_keys,
            count(*) FILTER (WHERE k.business_key IS NOT NULL) AS existing_keys
        FROM incoming i
        LEFT JOIN known k USING (business_key)
        """,
        [entity_name],
    ).fetchone()
    return int(row[0]), int(row[1])


#: Reference checks that indicate a genuinely broken drop rather than a delta.
#:
#: `water_readings.system_id` is deliberately absent: lab exports put sample
#: point codes such as BONF-OGD-B2 in that column, and those resolve through
#: the governed crosswalk rather than matching a system directly. Treating them
#: as orphans would block every drop containing a lab report.
_REFERENCE_CHECKS = (
    ("service_visits", "facility_id", FACILITY_TABLE, "facility_id", "facility"),
    ("service_visits", "customer_id", CUSTOMER_TABLE, "customer_id", "customer"),
    ("work_orders", "facility_id", FACILITY_TABLE, "facility_id", "facility"),
    ("systems", "facility_id", FACILITY_TABLE, "facility_id", "facility"),
)


def _orphan_references(
    conn: duckdb.DuckDBPyConnection,
    entity_name: str,
    path: Path,
    columns: list[str],
    incoming_entities: set[str],
) -> list[Finding]:
    """Find references that would land pointing at nothing.

    This is what separates "no customer updates this month" from "you forgot
    customers.csv". A delta load is normal; a delta that cites facilities the
    warehouse has never seen is not.
    """
    findings: list[Finding] = []
    read = f"read_csv({_literal(str(path))}, all_varchar=true, header=true)"
    for entity, column, table, target_column, label in _REFERENCE_CHECKS:
        if entity != entity_name or column not in columns:
            continue
        try:
            missing = conn.execute(
                f"""
                SELECT count(DISTINCT r.{_quote(column)})
                FROM {read} r
                LEFT JOIN {table} t
                       ON t.{target_column} = r.{_quote(column)}
                WHERE r.{_quote(column)} IS NOT NULL
                  AND r.{_quote(column)} <> ''
                  AND t.{target_column} IS NULL
                """
            ).fetchone()[0]
        except duckdb.Error:
            # The canonical tier may not exist yet on a first-ever load.
            continue
        if not missing:
            continue
        # If the drop also carries the master file, the reference will resolve
        # once both land together -- that is a complete drop, not a broken one.
        supplies_master = {
            "facility": "customers",
            "customer": "customers",
        }.get(label)
        if supplies_master and supplies_master in incoming_entities:
            findings.append(
                Finding(
                    ADVISORY,
                    "forward_reference",
                    f"{path.name}: {missing} {label} reference(s) are new, and "
                    f"will resolve from the {supplies_master} file in this drop.",
                )
            )
        else:
            findings.append(
                Finding(
                    BLOCKING,
                    "orphan_reference",
                    f"{path.name}: {missing} {label} reference(s) match no known "
                    f"{label}. Include the master file for {label}, or correct "
                    f"the identifiers, before ingesting.",
                )
            )
    return findings


def build(
    conn: duckdb.DuckDBPyConnection,
    upload: Upload,
    registry: Registry | None = None,
) -> Profile:
    """Profile a staged upload against the governed warehouse."""
    registry = registry or load_registry()
    root = resolve_batch_root(upload.root)
    profile = Profile(upload_id=upload.upload_id, batch_root=root.name)

    claimed: set[Path] = set()

    # --- tabular entities ---------------------------------------------------
    matched_files: list[tuple[str, Path]] = []
    for name, entity in registry.entities.items():
        for path in sorted(root.glob(entity.glob)):
            if path.is_file():
                matched_files.append((name, path))
                claimed.add(path)

    incoming_entities = {name for name, _ in matched_files}

    for name, path in matched_files:
        entity = registry.entities[name]
        columns = _columns(conn, path)
        baseline = _baseline_columns(conn, name)
        added = sorted(set(columns) - baseline) if baseline else []
        missing = sorted(baseline - set(columns)) if baseline else []
        # A column the registry already declares optional is absorbed drift,
        # not a surprise worth showing as a warning.
        added = [c for c in added if c not in entity.optional_columns]
        missing = [c for c in missing if c not in entity.optional_columns]

        new_keys, existing_keys = _key_overlap(
            conn, path, name, entity.business_key, columns
        )
        profile.entities.append(
            EntityProfile(
                entity=name,
                file=str(path.relative_to(upload.root)),
                rows=_row_count(path),
                columns=columns,
                added_columns=added,
                missing_columns=missing,
                new_keys=new_keys,
                superseding_keys=existing_keys,
            )
        )
        if added:
            profile.findings.append(
                Finding(
                    ADVISORY,
                    "schema_added",
                    f"{path.name}: new column(s) {', '.join(added)}. They will "
                    f"land in the payload and be available downstream.",
                )
            )
        if missing:
            profile.findings.append(
                Finding(
                    ADVISORY,
                    "schema_missing",
                    f"{path.name}: column(s) {', '.join(missing)} seen previously "
                    f"are absent. Existing rows keep their values.",
                )
            )
        profile.findings.extend(
            _orphan_references(conn, name, path, columns, incoming_entities)
        )

    # --- prose directories --------------------------------------------------
    known_dirs = registry.known_document_dirs()
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        aliases = {
            alias: cls
            for cls, names in registry.documents.items()
            for alias in names
        }
        document_class = aliases.get(directory.name)
        count = sum(
            1
            for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
        )
        if document_class:
            profile.documents.append(
                DocumentProfile(
                    document_class=document_class,
                    directory=directory.name,
                    documents=count,
                )
            )
        else:
            near = get_close_matches(directory.name, sorted(known_dirs), n=1, cutoff=0.4)
            suggestion = near[0] if near else None
            profile.unmatched.append(
                Unmatched(
                    path=str(directory.relative_to(upload.root)),
                    kind="directory",
                    suggestion=suggestion,
                    suggestion_target=aliases.get(suggestion) if suggestion else None,
                )
            )

    # --- files nothing claimed ---------------------------------------------
    for path in sorted(root.glob("*")):
        if path.is_file() and path not in claimed and not path.name.startswith("."):
            near = get_close_matches(
                path.name,
                [e.glob.replace("*", "") for e in registry.entities.values()],
                n=1,
                cutoff=0.3,
            )
            profile.unmatched.append(
                Unmatched(
                    path=str(path.relative_to(upload.root)),
                    kind="file",
                    suggestion=near[0] if near else None,
                    suggestion_target=None,
                )
            )

    # --- entities absent from the drop -------------------------------------
    profile.absent_entities = sorted(set(registry.entities) - incoming_entities)

    if profile.unmatched:
        profile.findings.append(
            Finding(
                BLOCKING,
                "unmapped",
                f"{len(profile.unmatched)} item(s) are not recognised. Map each "
                f"one to an entity, or exclude it, before ingesting.",
            )
        )
    if not profile.entities and not profile.documents:
        profile.findings.append(
            Finding(BLOCKING, "empty", "Nothing in this upload matches a known entity.")
        )

    return profile
