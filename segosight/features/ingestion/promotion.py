"""Promote a reviewed upload into the governed corpus.

Confirmation does three things, in this order:

1. Copy the staged batch into the materials tree.
2. Append a `[[batches]]` entry to `config/sources.toml`, plus any directory
   aliases Dana mapped during review.
3. Rebuild the warehouse **beside** the live one and swap it in on success.

Step 2 is the one that matters. The registry's contract is that a new data drop
is a config change, never a code change; if uploads registered themselves
somewhere else, the corpus would stop being reproducible from config plus files
and you would need the database to know what the database was built from. The
entry is stamped with who uploaded it and when, so a batch can always be traced
to a person.

Step 3 exists because the API holds DuckDB's single write lock for its
lifetime. Rebuilding in place would leave a half-built warehouse serving a
compliance dashboard if anything threw; building aside means a failure leaves
the live warehouse untouched and Dana sees an error with nothing broken.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from segosight.features.ingestion.profile import Profile, resolve_batch_root
from segosight.features.ingestion.registry import (
    DEFAULT_CONFIG,
    Registry,
    load_registry,
)
from segosight.features.ingestion.staging import Upload
from segosight.shared.paths import materials_root

_SLUG = re.compile(r"[^a-z0-9_-]+")


@dataclass
class Mapping:
    """One decision Dana made about an unrecognised item during review."""

    path: str
    #: "document" maps a directory to a document class; "entity" maps a file to
    #: a registry entity; "exclude" leaves it out of the promoted batch.
    kind: str
    target: str | None = None


@dataclass
class PromotionResult:
    batch_name: str
    batch_root: str
    sequence: int
    files_promoted: int
    aliases_added: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)


def slugify(name: str) -> str:
    return _SLUG.sub("-", name.lower()).strip("-") or "upload"


def next_sequence(registry: Registry) -> int:
    return max((b.sequence for b in registry.batches), default=0) + 1


def batch_directory_name(
    profile: Profile,
    upload: Upload,
    registry: Registry | None = None,
    materials: Path | None = None,
) -> str:
    """Directory name for the promoted batch.

    Must be unique against *two* namespaces, not one. Checking only the
    filesystem is not enough: a drop whose folder is called `new_data_batch`
    would take a root already claimed by the 2026-09 batch, giving two config
    entries the same root. Both would then load the same files, and rolling
    one back would strip the other.
    """
    registry = registry or load_registry()
    base = slugify(profile.batch_root or f"upload-{upload.upload_id}")
    if base in {"materials", ".", ""}:
        base = f"upload-{upload.upload_id}"

    taken = {b.root for b in registry.batches} | {b.name for b in registry.batches}
    target_materials = materials or materials_root()

    candidate = base
    suffix = 2
    while candidate in taken or (target_materials / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def add_document_alias(config_text: str, document_class: str, alias: str) -> str:
    """Add a directory alias to a document class, in place, preserving comments.

    The file is edited as text rather than parsed and re-serialised because it
    is a governed, heavily commented artefact a steward reads. `tomllib` cannot
    write, and a round-trip through a writer would strip every comment
    explaining why the thresholds are what they are.
    """
    pattern = re.compile(
        rf"(\[documents\.{re.escape(document_class)}\]\s*\n"
        rf"directories\s*=\s*\[)([^\]]*)(\])",
        re.MULTILINE,
    )
    match = pattern.search(config_text)
    if not match:
        raise ValueError(f"no [documents.{document_class}] section to extend")
    existing = match.group(2)
    if f'"{alias}"' in existing:
        return config_text
    trimmed = existing.rstrip()
    separator = ", " if trimmed else ""
    return (
        config_text[: match.start(2)]
        + f"{trimmed}{separator}\"{alias}\""
        + config_text[match.end(2) :]
    )


def batch_entry(
    name: str, sequence: int, root: str, source_system: str, uploader: str
) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    return (
        f"\n# Uploaded by {uploader} on {stamp} through the ingestion review.\n"
        f"[[batches]]\n"
        f'name                  = "{name}"\n'
        f"sequence              = {sequence}\n"
        f'root                  = "{root}"\n'
        f'default_source_system = "{source_system}"\n'
    )


def promote(
    upload: Upload,
    profile: Profile,
    *,
    uploader: str,
    source_system: str = "Upload",
    mappings: list[Mapping] | None = None,
    config_path: Path | None = None,
    materials: Path | None = None,
) -> PromotionResult:
    """Copy the staged batch into the corpus and register it.

    Does not rebuild; the caller owns that, because it must happen under the
    write lock with the live connection closed.
    """
    registry = load_registry(config_path)
    config = config_path or DEFAULT_CONFIG
    target_materials = materials or materials_root()

    staged_root = resolve_batch_root(upload.root)
    directory = batch_directory_name(profile, upload, registry, target_materials)
    destination = target_materials / directory

    excluded = {m.path for m in (mappings or []) if m.kind == "exclude"}
    aliases_added: list[str] = []

    def skip(path: Path) -> bool:
        relative = str(path.relative_to(upload.root))
        return path.name.startswith(".") or relative in excluded

    # --- copy the batch -----------------------------------------------------
    destination.mkdir(parents=True, exist_ok=False)
    promoted = 0
    for source in sorted(staged_root.rglob("*")):
        if source.is_dir() or skip(source):
            continue
        relative = source.relative_to(staged_root)
        if str(source.relative_to(upload.root)) in excluded:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        promoted += 1

    # --- rename files Dana mapped onto an entity ---------------------------
    # The registry recognises a file by glob, so a file called visits_oct.csv
    # is made to match `service_visits*.csv` rather than the glob being widened
    # to accept anything. The original name is preserved in the batch entry's
    # comment, so the rename is never silent.
    renames: list[str] = []
    for mapping in mappings or []:
        if mapping.kind != "entity" or not mapping.target:
            continue
        entity = registry.entities.get(mapping.target)
        if entity is None:
            continue
        original = destination / Path(mapping.path).name
        if not original.is_file():
            continue
        stem = entity.glob.replace("*.csv", "").replace("*", "")
        renamed = destination / f"{stem}_{directory}{original.suffix}"
        original.rename(renamed)
        renames.append(f"{original.name} -> {renamed.name} ({mapping.target})")

    # --- register the batch and any new aliases ----------------------------
    text = config.read_text(encoding="utf-8")
    for mapping in mappings or []:
        if mapping.kind == "document" and mapping.target:
            alias = Path(mapping.path).name
            updated = add_document_alias(text, mapping.target, alias)
            if updated != text:
                aliases_added.append(f"{alias} -> {mapping.target}")
                text = updated

    sequence = next_sequence(registry)
    note = "".join(f"# renamed {r}\n" for r in renames)
    text = text.rstrip("\n") + "\n" + note + batch_entry(
        name=directory, sequence=sequence, root=directory,
        source_system=source_system, uploader=uploader,
    )
    config.write_text(text, encoding="utf-8")

    return PromotionResult(
        batch_name=directory,
        batch_root=directory,
        sequence=sequence,
        files_promoted=promoted,
        aliases_added=aliases_added,
        excluded=sorted(excluded),
    )


def rollback(batch_root: str, config_path: Path | None = None,
             materials: Path | None = None) -> None:
    """Undo a promotion: remove the copied batch and its config entry.

    Used when the rebuild fails after the files and config were already
    written, so a failed confirmation leaves no trace.
    """
    config = config_path or DEFAULT_CONFIG
    target = (materials or materials_root()) / batch_root
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)

    text = config.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\n(?:#[^\n]*\n)*\[\[batches\]\]\n"
        r"(?:[a-z_]+\s*=\s*[^\n]*\n)*?"
        rf'root\s*=\s*"{re.escape(batch_root)}"\n'
        r"(?:[a-z_]+\s*=\s*[^\n]*\n)*"
    )
    config.write_text(pattern.sub("\n", text), encoding="utf-8")
