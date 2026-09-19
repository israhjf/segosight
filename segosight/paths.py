"""Filesystem locations for the supplied source material.

The exercise data is read in place and never modified, per the requirement that
the system work against the data as it actually is.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def materials_root() -> Path:
    """Directory holding the client's source files.

    Overridable via SEGOSIGHT_MATERIALS so the pipeline can be pointed at a new
    drop without code changes.
    """
    override = os.environ.get("SEGOSIGHT_MATERIALS")
    if override:
        return Path(override)
    return REPO_ROOT / "bedrock-fde-exercise-candidate" / "materials"


def new_batch_root() -> Path:
    return materials_root() / "new_data_batch"
