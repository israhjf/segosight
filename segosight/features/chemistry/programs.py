"""Treatment-program configuration: limits, exceptions and classifications.

Thresholds are never hard-coded in evaluation logic. Every judgement records
the `rule_version` and the exact band applied, so an operator can see which
guideline revision produced it and why.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from segosight.shared.paths import config_dir

DEFAULT_CONFIG = config_dir() / "treatment_programs.toml"


@dataclass(frozen=True)
class Limit:
    parameter: str
    lower: float | None
    upper: float | None
    unit: str | None
    #: "band" (normal operating range) | "action_level" | "trend_only"
    kind: str = "band"
    product: str | None = None
    #: Conditions that must hold for this limit to apply at all.
    requires: tuple[dict, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class Program:
    name: str
    label: str
    system_kind: str
    limits: dict[str, Limit]
    conditional: tuple[Limit, ...] = ()
    fallback_program: str | None = None


@dataclass(frozen=True)
class Exception_:
    """A per-system override of a program limit (guidelines section 6.3)."""

    system_id: str
    parameter: str
    target_lower: float
    contract_lower: float
    upper: float
    reason: str
    rationale: str


@dataclass(frozen=True)
class SeasonalClosure:
    facility_id: str
    closed_from: str  # MM-DD
    closed_to: str    # MM-DD
    rationale: str


@dataclass(frozen=True)
class Config:
    rule_version: str
    cadence_days: dict[str, int]
    thresholds: dict[str, float]
    programs: dict[str, Program]
    exceptions: dict[tuple[str, str], Exception_]
    seasonal: dict[str, SeasonalClosure]
    healthcare_facilities: frozenset[str]
    microbio: dict[str, dict]
    raw: dict = field(default_factory=dict, repr=False)

    def limit_for(
        self, program: str, parameter: str, system_id: str | None = None
    ) -> Limit | None:
        """Resolve the governing limit, applying any per-system exception."""
        override = self.exceptions.get((system_id or "", parameter))
        if override is not None:
            return Limit(
                parameter=parameter,
                lower=override.contract_lower,
                upper=override.upper,
                unit=None,
                kind="band_with_target",
                note=override.reason,
            )
        prog = self.programs.get(program)
        if prog is None:
            return None
        return prog.limits.get(parameter)

    def is_healthcare(self, facility_id: str | None) -> bool:
        return facility_id in self.healthcare_facilities

    def cadence_for(self, service_frequency: str | None) -> int | None:
        """Contracted interval in days from a `service_frequency` cell.

        The field carries contract terms alongside the cadence, e.g.
        "monthly (seasonal: closed mid-May to mid-Oct)", so only the leading
        token is the cadence.
        """
        if not service_frequency:
            return None
        return self.cadence_days.get(service_frequency.split()[0].strip().lower())


def _limit(entry: dict) -> Limit:
    return Limit(
        parameter=entry["parameter"],
        lower=entry.get("lower"),
        upper=entry.get("upper"),
        unit=entry.get("unit"),
        kind=entry.get("kind", "band"),
        product=entry.get("product"),
        requires=tuple(entry.get("requires", ())),
        note=" ".join(entry["note"].split()) if entry.get("note") else None,
    )


def load_config(path: Path | None = None) -> Config:
    raw = tomllib.loads((path or DEFAULT_CONFIG).read_text(encoding="utf-8"))

    programs = {}
    for name, spec in raw["programs"].items():
        programs[name] = Program(
            name=name,
            label=spec["label"],
            system_kind=spec["system_kind"],
            limits={e["parameter"]: _limit(e) for e in spec["limits"]},
            conditional=tuple(_limit(e) for e in spec.get("conditional", ())),
            fallback_program=spec.get("fallback_program"),
        )

    exceptions = {
        (e["system_id"], e["parameter"]): Exception_(
            system_id=e["system_id"],
            parameter=e["parameter"],
            target_lower=e["target_lower"],
            contract_lower=e["contract_lower"],
            upper=e["upper"],
            reason=e["reason"],
            rationale=" ".join(e["rationale"].split()),
        )
        for e in raw.get("program_exceptions", ())
    }

    seasonal = {
        s["facility_id"]: SeasonalClosure(
            facility_id=s["facility_id"],
            closed_from=s["closed_from"],
            closed_to=s["closed_to"],
            rationale=" ".join(s["rationale"].split()),
        )
        for s in raw.get("seasonal_closure", ())
    }

    return Config(
        rule_version=raw["rule_version"],
        cadence_days={k: int(v) for k, v in raw["cadence"].items()},
        thresholds=raw["thresholds"],
        programs=programs,
        exceptions=exceptions,
        seasonal=seasonal,
        healthcare_facilities=frozenset(raw["facility_class"]["healthcare"]),
        microbio=raw["microbio"],
        raw=raw,
    )
