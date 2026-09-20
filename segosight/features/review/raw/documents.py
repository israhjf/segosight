"""Raw tier: landing of unstructured technician notes and customer email.

The office's own complaint is that "the office finds out about field concerns
late or never" -- technicians flag things in notes and verbally on site, and
some of those flags deserve work orders and customer conversations that never
happen. Those notes are therefore a first-class source, not an appendix.

Three formats appear: plain text, Word (.docx) and one Chromium-generated PDF.
Text and Word are handled with the standard library (a .docx is a zip of XML);
the PDF needs pypdf. A file whose text cannot be extracted is landed with
`extraction_status = 'failed'` rather than skipped, so a missing note is
visible in the review queue instead of silently absent.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from segosight.features.ingestion.registry import load_registry
from segosight.shared.paths import materials_root
from segosight.shared.warehouse import RAW, bulk_insert

TABLE = f"{RAW}.documents"

#: Directories are resolved from `config/sources.toml` rather than listed here.
#: They used to be a literal tuple, which meant the 2026-09 drop renaming
#: `customer_communications` to `communications` was absorbed by editing this
#: module -- a code change for what the registry calls a config change. The
#: alias list lives with the batches now, so the next rename is a TOML edit.

SUPPORTED_SUFFIXES = frozenset({".txt", ".docx", ".pdf", ".md"})

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: Filenames look like 2026-08-22_kestrel_reply.txt
_FILENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<slug>[a-z0-9-]+)_(?P<topic>.+)$"
)

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    document_id       VARCHAR NOT NULL,
    document_class    VARCHAR NOT NULL,
    batch_name        VARCHAR NOT NULL,
    source_file       VARCHAR NOT NULL,
    file_name         VARCHAR NOT NULL,
    file_suffix       VARCHAR NOT NULL,
    filename_date     DATE,
    filename_slug     VARCHAR,
    filename_topic    VARCHAR,
    body              VARCHAR,
    char_count        INTEGER NOT NULL,
    extraction_status VARCHAR NOT NULL,
    extraction_note   VARCHAR,
    content_hash      VARCHAR NOT NULL,
    ingested_at       TIMESTAMP NOT NULL
)
"""

_COLUMNS = [
    "document_id", "document_class", "batch_name", "source_file", "file_name",
    "file_suffix", "filename_date", "filename_slug", "filename_topic", "body",
    "char_count", "extraction_status", "extraction_note", "content_hash",
    "ingested_at",
]


@dataclass(frozen=True)
class Extraction:
    text: str
    status: str
    note: str | None = None


def _read_txt(path: Path) -> Extraction:
    return Extraction(path.read_text(encoding="utf-8", errors="replace"), "ok")


def _read_docx(path: Path) -> Extraction:
    """Extract paragraph text from a .docx without a third-party library."""
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs = []
    for para in root.iter(f"{_WORD_NS}p"):
        runs = [node.text or "" for node in para.iter(f"{_WORD_NS}t")]
        paragraphs.append("".join(runs))
    return Extraction("\n".join(paragraphs), "ok")


def _read_pdf(path: Path) -> Extraction:
    try:
        from pypdf import PdfReader
    except ImportError:
        return Extraction("", "failed", "pypdf not installed")
    try:
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as error:  # noqa: BLE001 - any parse failure is a review item
        return Extraction("", "failed", f"{type(error).__name__}: {error}")
    if not text.strip():
        return Extraction("", "failed", "no extractable text layer")
    return Extraction(text, "ok")


_READERS = {".txt": _read_txt, ".md": _read_txt, ".docx": _read_docx, ".pdf": _read_pdf}


def extract(path: Path) -> Extraction:
    """Read one document, never raising: failures become review items."""
    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        return Extraction("", "failed", f"unsupported suffix {path.suffix}")
    try:
        return reader(path)
    except Exception as error:  # noqa: BLE001
        return Extraction("", "failed", f"{type(error).__name__}: {error}")


def parse_filename(stem: str) -> tuple[dt.date | None, str | None, str | None]:
    """Pull the date, site slug and topic out of the naming convention."""
    match = _FILENAME_RE.match(stem)
    if not match:
        return None, None, None
    try:
        date = dt.date.fromisoformat(match.group("date"))
    except ValueError:
        date = None
    return date, match.group("slug"), match.group("topic")


def build(
    conn: duckdb.DuckDBPyConnection,
    root: Path | None = None,
    ingested_at: dt.datetime | None = None,
) -> dict[str, int]:
    """Land every document under the configured source directories."""
    base = root or materials_root()
    stamp = ingested_at or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    conn.execute(_DDL)

    registry = load_registry()
    rows = []
    seen: set[Path] = set()
    for source in registry.document_dirs(base):
        document_class, batch = source.document_class, source.batch.name
        for path in sorted(source.path.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            # An alias list can resolve two names onto the same directory; land
            # each document once regardless.
            if path in seen:
                continue
            seen.add(path)
            result = extract(path)
            date, slug, topic = parse_filename(path.stem)
            rows.append(
                (
                    f"{document_class}:{path.stem}",
                    document_class,
                    batch,
                    str(path),
                    path.name,
                    path.suffix.lower(),
                    date,
                    slug,
                    topic,
                    result.text,
                    len(result.text),
                    result.status,
                    result.note,
                    hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
                    stamp,
                )
            )

    bulk_insert(conn, TABLE, _COLUMNS, rows)
    return {
        "documents": len(rows),
        "failed": sum(1 for r in rows if r[11] != "ok"),
    }
