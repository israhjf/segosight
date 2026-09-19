"""Filesystem locations for the supplied source material.

The exercise data is read in place and never modified, per the requirement that
the system work against the data as it actually is.
"""

from __future__ import annotations

import os
from pathlib import Path

# segosight/shared/paths.py -> segosight/shared -> segosight -> repo root.
# Derived from this file's depth, so moving the module means updating this.
REPO_ROOT = Path(__file__).resolve().parents[2]


def materials_root() -> Path:
    """Directory holding the client's source files.

    Overridable via SEGOSIGHT_MATERIALS so the pipeline can be pointed at a new
    drop without code changes.
    """
    override = os.environ.get("SEGOSIGHT_MATERIALS")
    if override:
        return Path(override)
    return REPO_ROOT / "bedrock-fde-exercise-candidate" / "materials"


def config_dir() -> Path:
    """Governed configuration, kept central rather than per feature.

    These TOML files are operator-editable artefacts, not code:
    treatment_programs.toml transcribes the client's guidelines binder and
    identity.toml records approved account merges. A steward should find every
    tunable in one directory without navigating the source tree, so features
    own the loaders while the files stay here.
    """
    return REPO_ROOT / "segosight" / "config"


def new_batch_root() -> Path:
    return materials_root() / "new_data_batch"
