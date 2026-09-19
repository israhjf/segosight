"""Parameter identity and unit conversion for water chemistry readings.

Two source behaviours drive this module:

1. The per-row `units` column is authoritative. The treatment guidelines are
   explicit: "Where a record carries its own unit notation, the notation
   governs over any assumption", and conversions happen "only when unit
   notation confirms the source unit". We therefore never infer a unit from a
   value's magnitude, however tempting -- BMS conductivity for SYS-0014..0017
   switches mS/cm -> uS/cm on 2026-07-14 mid-file, and magnitude-based guessing
   would manufacture a 1000x step change on a critical CT-HC2 system.

2. `inhibitor_ppm` is polymorphic. With `moly` declared it carries molybdate
   (observed 188-311 ppm on CL-M loops); with `inhib` declared it carries
   corrosion inhibitor (observed 7.2-19 ppm on CT towers). Those map to
   different control bands, so parameter identity is resolved from the
   declaration, never from the column name alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from segosight.shared.normalize import codes
from segosight.shared.normalize.result import Normalized


@dataclass(frozen=True)
class Parameter:
    """A canonical measurable parameter and its standard unit."""

    code: str
    standard_unit: str
    #: raw unit -> multiplicative factor to reach `standard_unit`.
    conversions: dict[str, float]


def _ppm(code: str) -> Parameter:
    return Parameter(code, "ppm", {"ppm": 1.0})


#: Canonical parameter registry. Standard units follow treatment_guidelines.pdf
#: section 2.
PARAMETERS: dict[str, Parameter] = {
    "conductivity": Parameter(
        "conductivity", "uS/cm", {"uS/cm": 1.0, "mS/cm": 1000.0}
    ),
    # 1 gpg = 17.1 ppm as CaCO3 (guidelines section 2).
    "total_hardness": Parameter(
        "total_hardness", "ppm CaCO3", {"ppm CaCO3": 1.0, "gpg": 17.1}
    ),
    "m_alkalinity": Parameter("m_alkalinity", "ppm CaCO3", {"ppm CaCO3": 1.0}),
    "chloride": _ppm("chloride"),
    "inhibitor": _ppm("inhibitor"),
    "molybdate": _ppm("molybdate"),
    "sulfite": _ppm("sulfite"),
    "nitrite": _ppm("nitrite"),
    "iron": _ppm("iron"),
    "free_halogen": _ppm("free_halogen"),
    "ph": Parameter("ph", "pH", {"pH": 1.0}),
    "dipslide": Parameter("dipslide", "log10 CFU/ml", {"log10 CFU/ml": 1.0}),
}


@dataclass(frozen=True)
class ColumnSpec:
    """How one wide source column maps onto canonical parameters."""

    column: str
    #: Declaration key -> parameter code. Empty when the column is not
    #: unit-declared in the source.
    by_declaration: dict[str, str]
    #: Parameter used when the source declares nothing for this column.
    default_parameter: str
    #: True when the source is expected to declare a unit for this column.
    expects_declaration: bool


#: Column -> parameter mapping for water_readings.csv (both batches share the
#: same 18-column shape).
COLUMN_SPECS: tuple[ColumnSpec, ...] = (
    ColumnSpec("conductivity", {"cond": "conductivity"}, "conductivity", True),
    ColumnSpec("total_hardness", {"hard": "total_hardness"}, "total_hardness", True),
    ColumnSpec("m_alkalinity", {"alk": "m_alkalinity"}, "m_alkalinity", True),
    ColumnSpec("chloride", {"cl": "chloride"}, "chloride", True),
    # Polymorphic: identity depends on which key the row declares.
    ColumnSpec(
        "inhibitor_ppm",
        {"inhib": "inhibitor", "moly": "molybdate"},
        "inhibitor",
        True,
    ),
    ColumnSpec("sulfite", {"sulfite": "sulfite"}, "sulfite", True),
    ColumnSpec("nitrite", {"nitrite": "nitrite"}, "nitrite", True),
    # Never unit-declared in the source; units are fixed by definition.
    ColumnSpec("ph", {}, "ph", False),
    ColumnSpec("free_halogen", {}, "free_halogen", False),
    ColumnSpec("iron", {}, "iron", False),
)

COLUMN_SPECS_BY_NAME: dict[str, ColumnSpec] = {s.column: s for s in COLUMN_SPECS}


def parse_units_declaration(raw: str | None) -> dict[str, str]:
    """Parse a `units` cell such as `cond=uS/cm;hard=gpg;cl=ppm` into a dict.

    Malformed segments are skipped rather than raising: a broken declaration
    degrades one parameter to "unit not declared", it does not lose the row.
    """
    if not raw:
        return {}
    out: dict[str, str] = {}
    for segment in raw.split(";"):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        key, _, unit = segment.partition("=")
        key, unit = key.strip(), unit.strip()
        if key and unit:
            out[key] = unit
    return out


@dataclass(frozen=True)
class Resolution:
    """The parameter a column carries for one specific row."""

    parameter: Parameter
    raw_unit: str | None
    issues: tuple[str, ...]


def resolve_parameter(column: str, declaration: dict[str, str]) -> Resolution:
    """Determine which parameter a column carries, given the row's declaration.

    Returns the default parameter with `UNIT_NOT_DECLARED` when the source
    declared nothing for a column that normally carries a declaration. The
    caller decides whether to trust it; this primitive deliberately does not
    consult treatment programs or value magnitude to guess.
    """
    spec = COLUMN_SPECS_BY_NAME.get(column)
    if spec is None:
        raise KeyError(f"no parameter mapping for column {column!r}")

    if not spec.expects_declaration:
        param = PARAMETERS[spec.default_parameter]
        return Resolution(param, param.standard_unit, ())

    for key, parameter_code in spec.by_declaration.items():
        if key in declaration:
            return Resolution(
                PARAMETERS[parameter_code], declaration[key], ()
            )

    return Resolution(
        PARAMETERS[spec.default_parameter],
        None,
        (codes.UNIT_NOT_DECLARED,),
    )


def convert(
    parameter: Parameter, value: float | None, raw_unit: str | None
) -> Normalized[float]:
    """Convert `value` from `raw_unit` into the parameter's standard unit.

    An undeclared or unrecognized unit yields the value unconverted, flagged,
    so the reading survives for review instead of being silently rescaled.
    """
    if value is None:
        return Normalized(value=None, raw=value)

    if raw_unit is None:
        return Normalized(
            value=value,
            raw=value,
            detail={"standard_unit": parameter.standard_unit, "converted": False},
        ).with_issue(codes.UNIT_NOT_DECLARED)

    factor = parameter.conversions.get(raw_unit)
    if factor is None:
        return Normalized(
            value=value,
            raw=value,
            detail={
                "standard_unit": parameter.standard_unit,
                "raw_unit": raw_unit,
                "converted": False,
            },
        ).with_issue(codes.UNIT_UNRECOGNIZED, raw_unit=raw_unit)

    return Normalized(
        value=value * factor,
        raw=value,
        detail={
            "standard_unit": parameter.standard_unit,
            "raw_unit": raw_unit,
            "factor": factor,
            "converted": factor != 1.0,
        },
    )
