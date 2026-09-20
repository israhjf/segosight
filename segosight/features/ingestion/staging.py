"""Staging area for uploaded data drops.

Uploads land on disk under an upload id and are profiled there, never in the
governed warehouse. Only `promote()` moves a drop into the corpus, and only
after Dana has confirmed the review.

The staging directory is deliberately shaped like a materials root, because
the pipeline already accepts one: `registry.all_files(root=...)`,
`documents.build(root=...)` and `pipeline.run(materials=...)` all take a base
path. Profiling therefore runs the real parsers rather than a second
implementation that would drift from them.

Everything arriving here is untrusted. Browsers send `webkitRelativePath` for
folder uploads, and that string is client-controlled: it is sanitised into a
relative path under the upload root before anything touches the filesystem.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from segosight.features.review.raw.documents import SUPPORTED_SUFFIXES
from segosight.shared.paths import REPO_ROOT

#: Suffixes an upload may contain: tabular sources plus the prose formats the
#: document reader understands. Anything else is refused by name.
ALLOWED_SUFFIXES = frozenset({".csv"}) | SUPPORTED_SUFFIXES

#: Caps. A drop is a monthly export of a small operator's records; the real
#: corpus is under a megabyte. These are generous, and exist so a runaway or
#: hostile upload cannot fill the disk.
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_FILES = 2000

#: How long an unconfirmed upload survives before it can be swept.
STAGING_TTL = dt.timedelta(hours=24)

_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")


def staging_root() -> Path:
    return REPO_ROOT / "warehouse" / "staging"


class UploadRejected(ValueError):
    """The upload cannot be staged, with a reason fit to show a user."""


def safe_relative_path(raw: str) -> Path:
    """Reduce a client-supplied path to a safe relative path.

    Browsers hand us `webkitRelativePath` for folder uploads, which is how the
    drop's own directory structure survives -- and it is also the obvious place
    to hide `../../etc/passwd`. Every segment is sanitised, and `.`/`..` are
    dropped rather than resolved, so the result can only ever land inside the
    upload directory.
    """
    parts: list[str] = []
    for segment in raw.replace("\\", "/").split("/"):
        segment = segment.strip()
        if not segment or segment in {".", ".."}:
            continue
        cleaned = _SAFE_SEGMENT.sub("_", segment).strip("._-") or "unnamed"
        parts.append(cleaned[:120])
    if not parts:
        raise UploadRejected("a file arrived with no usable name")
    # Guard against a drop that is one deep directory chain.
    return Path(*parts[-6:])


@dataclass
class StagedFile:
    """One file written into the staging area."""

    relative_path: Path
    size_bytes: int

    @property
    def suffix(self) -> str:
        return self.relative_path.suffix.lower()


@dataclass
class Upload:
    """A staged drop awaiting review."""

    upload_id: str
    root: Path
    created_at: dt.datetime
    files: list[StagedFile] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)

    def meta_path(self) -> Path:
        return self.root / ".upload.json"

    def save(self) -> None:
        self.meta_path().write_text(
            json.dumps(
                {
                    "upload_id": self.upload_id,
                    "created_at": self.created_at.isoformat(),
                    "files": [
                        {"path": str(f.relative_path), "size_bytes": f.size_bytes}
                        for f in self.files
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def create(files: list[tuple[str, bytes]]) -> Upload:
    """Write an upload into its own staging directory.

    `files` is a list of (client path, content). The client path may carry a
    folder structure; it is sanitised before use.
    """
    if not files:
        raise UploadRejected("no files were uploaded")
    if len(files) > MAX_FILES:
        raise UploadRejected(
            f"{len(files)} files exceeds the {MAX_FILES}-file limit for one upload"
        )

    total = 0
    prepared: list[tuple[Path, bytes]] = []
    for raw_path, content in files:
        relative = safe_relative_path(raw_path)
        suffix = relative.suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
            raise UploadRejected(
                f"{relative.name}: {suffix or 'no extension'} is not an accepted "
                f"file type. Accepted: {allowed}"
            )
        if len(content) > MAX_FILE_BYTES:
            raise UploadRejected(
                f"{relative.name} is {len(content) // (1024 * 1024)} MB, over the "
                f"{MAX_FILE_BYTES // (1024 * 1024)} MB per-file limit"
            )
        total += len(content)
        if total > MAX_UPLOAD_BYTES:
            raise UploadRejected(
                f"the upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
            )
        prepared.append((relative, content))

    upload_id = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    root = staging_root() / upload_id
    root.mkdir(parents=True, exist_ok=False)

    upload = Upload(
        upload_id=upload_id,
        root=root,
        created_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    )
    for relative, content in prepared:
        target = root / relative
        # Belt and braces: the sanitiser should make this impossible, but a
        # write outside the upload root is never acceptable.
        if not target.resolve().is_relative_to(root.resolve()):
            shutil.rmtree(root, ignore_errors=True)
            raise UploadRejected(f"{relative} resolves outside the staging area")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        upload.files.append(StagedFile(relative_path=relative, size_bytes=len(content)))

    upload.save()
    return upload


def load(upload_id: str) -> Upload:
    """Reopen a staged upload by id."""
    safe_id = _SAFE_SEGMENT.sub("", upload_id)
    root = staging_root() / safe_id
    meta = root / ".upload.json"
    if not meta.is_file():
        raise UploadRejected(f"no staged upload {upload_id!r}")
    data = json.loads(meta.read_text(encoding="utf-8"))
    return Upload(
        upload_id=data["upload_id"],
        root=root,
        created_at=dt.datetime.fromisoformat(data["created_at"]),
        files=[
            StagedFile(relative_path=Path(f["path"]), size_bytes=f["size_bytes"])
            for f in data["files"]
        ],
    )


def discard(upload_id: str) -> None:
    """Remove a staged upload and everything in it."""
    safe_id = _SAFE_SEGMENT.sub("", upload_id)
    root = staging_root() / safe_id
    if root.is_dir() and root.resolve().is_relative_to(staging_root().resolve()):
        shutil.rmtree(root, ignore_errors=True)


def sweep(ttl: dt.timedelta | None = None) -> int:
    """Delete staged uploads older than the TTL. Returns how many went."""
    root = staging_root()
    if not root.is_dir():
        return 0
    cutoff = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - (ttl or STAGING_TTL)
    removed = 0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            upload = load(child.name)
        except (UploadRejected, KeyError, ValueError):
            continue
        if upload.created_at < cutoff:
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed
