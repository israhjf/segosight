"""Declarative source registry.

Resolves the entities and file drops described in `config/sources.toml` against
the materials directory. The second data batch is incorporated by configuration
(a `[[batches]]` entry plus the existing glob), never by editing pipeline code,
which is what makes re-ingestion of a future drop a non-event.
"""

from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..paths import REPO_ROOT, materials_root

DEFAULT_CONFIG = REPO_ROOT / "segosight" / "config" / "sources.toml"


@dataclass(frozen=True)
class Batch:
    """One dated drop of source files."""

    name: str
    sequence: int
    root: str
    default_source_system: str


@dataclass(frozen=True)
class Entity:
    """A logical source entity and how to recognise its files."""

    name: str
    glob: str
    business_key: tuple[str, ...]
    date_columns: tuple[str, ...]
    optional_columns: tuple[str, ...]


@dataclass(frozen=True)
class SourceFile:
    """A concrete file resolved for one entity in one batch."""

    entity: Entity
    batch: Batch
    path: Path

    @property
    def source_system(self) -> str:
        return self.batch.default_source_system


@dataclass(frozen=True)
class Registry:
    corpus: tuple[dt.date, dt.date]
    batches: tuple[Batch, ...]
    entities: dict[str, Entity]

    def files_for(self, entity_name: str, root: Path | None = None) -> list[SourceFile]:
        """Resolve every file for one entity, ordered by batch sequence.

        Ordering matters: it is the precedence used when the same business key
        is re-issued in a later batch.
        """
        entity = self.entities[entity_name]
        base = root if root is not None else materials_root()
        found: list[SourceFile] = []
        for batch in sorted(self.batches, key=lambda b: b.sequence):
            batch_dir = (base / batch.root).resolve()
            if not batch_dir.is_dir():
                continue
            # Non-recursive: a nested batch directory must declare itself as a
            # batch rather than being swept up by the parent's glob.
            for path in sorted(batch_dir.glob(entity.glob)):
                if path.is_file():
                    found.append(SourceFile(entity=entity, batch=batch, path=path))
        return found

    def all_files(self, root: Path | None = None) -> list[SourceFile]:
        return [f for name in self.entities for f in self.files_for(name, root)]


def load_registry(config_path: Path | None = None) -> Registry:
    """Load and validate the source registry."""
    path = config_path or DEFAULT_CONFIG
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    batches = tuple(
        Batch(
            name=b["name"],
            sequence=int(b["sequence"]),
            root=b["root"],
            default_source_system=b["default_source_system"],
        )
        for b in raw["batches"]
    )
    sequences = [b.sequence for b in batches]
    if len(set(sequences)) != len(sequences):
        raise ValueError(
            "batch sequences must be unique; they decide supersede precedence"
        )

    entities = {
        name: Entity(
            name=name,
            glob=spec["glob"],
            business_key=tuple(spec["business_key"]),
            date_columns=tuple(spec.get("date_columns", ())),
            optional_columns=tuple(spec.get("optional_columns", ())),
        )
        for name, spec in raw["entities"].items()
    }

    return Registry(
        corpus=(raw["corpus"]["start"], raw["corpus"]["end"]),
        batches=batches,
        entities=entities,
    )
