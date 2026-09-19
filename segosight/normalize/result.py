"""Container returned by every normalization primitive.

Every primitive preserves the raw input alongside the normalized value so the
Raw tier stays reconstructable from the Clean tier, and so a reviewer can see
what the source actually said when a value is quarantined.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Normalized(Generic[T]):
    """A normalized value plus its provenance and any data-quality issues."""

    value: T | None
    raw: Any
    issues: tuple[str, ...] = field(default=())
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when a value was produced and nothing was flagged."""
        return self.value is not None and not self.issues

    def with_issue(self, code: str, **detail: Any) -> "Normalized[T]":
        """Return a copy carrying one additional issue code."""
        if code in self.issues:
            return self
        return Normalized(
            value=self.value,
            raw=self.raw,
            issues=self.issues + (code,),
            detail={**self.detail, **detail},
        )
