"""Curated tier: deduplicated, ranked operational alerts.

This is Dana's Monday queue. Her framing, verbatim from the context document:
"Every Monday I want to know which sites need attention, why, what it costs us
or the customer if we sit on it, and who is doing what about it."

Every alert therefore answers four questions -- what, why, consequence, owner --
and carries its evidence rather than a bare flag.

Two design rules from the Ontology brief:

* A reading is not an alert. Raw observations and their assessments stay
  separate; an alert is a persistent work-management object built from them.
* Alerts are deduplicated on a stable fingerprint of risk class, subject and
  parameter, so a sawtooth trend updates one open alert instead of opening a
  new one per observation. Without this, SYS-0006's iron trend alone would
  produce five separate alerts.

Trend alerts are additionally gated on materiality. 278 concerning service-grain
trends exist in the corpus; almost none deserve Dana's attention on a Monday. A
trend is promoted only when it has travelled a meaningful fraction of the way to
its governing limit, or the equipment is critical. The aim is a queue a person
will actually read.
"""

from __future__ import annotations

import datetime as dt

import duckdb

from ..canonical.entities import CUSTOMER_TABLE, FACILITY_TABLE, SYSTEM_TABLE
from ..canonical.events import TABLE as EVENTS
from ..warehouse import CURATED, bulk_insert
from .assessments import TABLE as ASSESSMENTS
from .coverage import TABLE as COVERAGE
from .microbio import TABLE as MICROBIO
from .programs import Config, load_config
from .trends import TABLE as TRENDS

TABLE = f"{CURATED}.operational_alert"

#: Risk classes, ordered by how badly a missed one hurts this client.
CORROSION_TREND = "corrosion_trend"
MICROBIO_ESCALATION = "microbio_escalation"
COVERAGE_GAP = "coverage_gap"
TREATMENT_EXCEEDANCE = "treatment_exceedance"
RESIDUAL_LOSS = "residual_loss"
SCALING_RISK = "scaling_risk"

#: Risk class and consequence framing per trended parameter. Getting this
#: wrong produces alerts whose explanation contradicts their own evidence.
_TREND_RISK = {
    "iron": (
        CORROSION_TREND,
        "Guidelines section 4.2: the time to investigate a sustained trend is "
        "at the trend stage, not at the limit. Boiler or loop iron climbing "
        "from a stable baseline indicates active corrosion well before the "
        "action level, and waiting for the limit generally means the metal "
        "loss has already happened.",
    ),
    "conductivity": (
        SCALING_RISK,
        "Rising tower conductivity against a fixed bleed setpoint means cycles "
        "are climbing: scaling and fouling risk. Section 6.4 warns that a "
        "reuse-fed tower drifting above its band must be corrected by bleed "
        "control or a formal program change, not quietly tolerated.",
    ),
    "free_halogen": (
        RESIDUAL_LOSS,
        "A falling biocide residual at constant feed means demand is rising or "
        "feed is failing. Loss of oxidant control precedes microbiological "
        "growth.",
    ),
    "sulfite": (
        RESIDUAL_LOSS,
        "A falling sulfite residual means dissolved oxygen is not being "
        "scavenged. Oxygen ingress is the mechanism behind boiler pitting.",
    ),
    "nitrite": (
        RESIDUAL_LOSS,
        "A closed loop that repeatedly consumes inhibitor is telling you it is "
        "not closed. Section 3.3: look for water loss before adding more "
        "chemical.",
    ),
    "molybdate": (
        RESIDUAL_LOSS,
        "A closed loop that repeatedly consumes inhibitor is telling you it is "
        "not closed. Section 3.3: look for water loss before adding more "
        "chemical.",
    ),
    "inhibitor": (
        RESIDUAL_LOSS,
        "A falling inhibitor residual at constant feed means the demand "
        "changed. Find the mechanism before increasing dose.",
    ),
}

#: Conductivity is actively controlled by blowdown on a boiler and cycles
#: between services by design, so a rising run there is normal operation. The
#: guidelines' conductivity-trend example is explicitly about towers:
#: "Rising tower conductivity against a fixed bleed setpoint".
_CONDUCTIVITY_TREND_SYSTEM_KINDS = frozenset(
    {"cooling_tower", "evaporative_condenser"}
)

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0}
_TIER_WEIGHT = {"A": 1.35, "B": 1.15, "C": 1.0}
_CRITICALITY_WEIGHT = {"critical": 1.4, "important": 1.15, "standard": 1.0}

#: Fraction of the distance to a governing limit a rising trend must travel
#: before it is worth an operator's Monday. Applied to corrosion trends.
TREND_PROMOTION_PROXIMITY = 0.5

#: A falling residual is promoted only when its *baseline* is collapsing, not
#: when it merely decays between doses. Every treated system consumes chemical
#: between services -- that is what dosing is for -- so a sawtooth that recovers
#: to the same trough is normal operation. The guidelines point at the opposite
#: case: a loop that "repeatedly consumes" inhibitor, and "growing gaps between
#: chemical dose and residual". We therefore compare the recent trough against
#: the earlier trough and ask how much of the headroom to the floor it ate.
RESIDUAL_COLLAPSE_FRACTION = 0.5
#: Services averaged at each end when measuring the trough.
TROUGH_WINDOW = 3

#: A rising conductivity run on a tower is promoted only when it has actually
#: left the band, or run long enough to be a drift rather than a cycle. Towers
#: cycle up between bleeds by design.
SCALING_MIN_RUN = 6

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    alert_id        VARCHAR NOT NULL,
    fingerprint     VARCHAR NOT NULL,
    risk_class      VARCHAR NOT NULL,
    severity        VARCHAR NOT NULL,
    priority_score  DOUBLE NOT NULL,
    customer_id     VARCHAR,
    customer_name   VARCHAR,
    account_tier    VARCHAR,
    acv_usd         DOUBLE,
    facility_id     VARCHAR,
    facility_name   VARCHAR,
    system_id       VARCHAR,
    system_label    VARCHAR,
    criticality     VARCHAR,
    parameter_code  VARCHAR,
    title           VARCHAR NOT NULL,
    why             VARCHAR NOT NULL,
    consequence     VARCHAR NOT NULL,
    owner           VARCHAR,
    owner_source    VARCHAR,
    evidence_count  INTEGER NOT NULL,
    first_observed  TIMESTAMP,
    last_observed   TIMESTAMP,
    as_of_date      DATE NOT NULL,
    rule_version    VARCHAR NOT NULL
)
"""

_COLUMNS = [
    "alert_id", "fingerprint", "risk_class", "severity", "priority_score",
    "customer_id", "customer_name", "account_tier", "acv_usd", "facility_id",
    "facility_name", "system_id", "system_label", "criticality",
    "parameter_code", "title", "why", "consequence", "owner", "owner_source",
    "evidence_count", "first_observed", "last_observed", "as_of_date",
    "rule_version",
]


def _score(severity: str, tier: str | None, criticality: str | None) -> float:
    """Rank an alert by severity, weighted by what it threatens."""
    base = _SEVERITY_RANK.get(severity, 1)
    return round(
        base
        * _TIER_WEIGHT.get(tier or "C", 1.0)
        * _CRITICALITY_WEIGHT.get(criticality or "standard", 1.0),
        3,
    )


def build(
    conn: duckdb.DuckDBPyConnection,
    config: Config | None = None,
    as_of: dt.date | None = None,
) -> int:
    """Collapse assessments, trends, escalations and coverage into alerts."""
    cfg = config or load_config()
    conn.execute(_DDL)
    reference = as_of or conn.execute(
        f"SELECT max(as_of_date) FROM {COVERAGE}"
    ).fetchone()[0]

    context = {
        row[0]: row
        for row in conn.execute(
            f"""SELECT s.system_id, s.facility_id, s.description, s.criticality,
                       f.facility_name, f.customer_id, c.customer_name,
                       c.account_tier, c.acv_usd
                FROM {SYSTEM_TABLE} s
                LEFT JOIN {FACILITY_TABLE} f USING (facility_id)
                LEFT JOIN {CUSTOMER_TABLE} c ON c.customer_id = f.customer_id"""
        ).fetchall()
    }

    out: list[tuple] = []

    def emit(
        risk_class, severity, system_id, facility_id, parameter, title, why,
        consequence, owner, owner_source, count, first, last,
    ):
        ctx = context.get(system_id)
        if ctx:
            (_, facility_id, label, criticality, facility_name, customer_id,
             customer_name, tier, acv) = ctx
        else:
            label = criticality = None
            row = conn.execute(
                f"""SELECT f.facility_name, f.customer_id, c.customer_name,
                           c.account_tier, c.acv_usd
                    FROM {FACILITY_TABLE} f
                    LEFT JOIN {CUSTOMER_TABLE} c USING (customer_id)
                    WHERE f.facility_id = ?""",
                [facility_id],
            ).fetchone()
            facility_name, customer_id, customer_name, tier, acv = row or (
                None, None, None, None, None
            )

        fingerprint = ":".join(
            str(p) for p in (risk_class, system_id or facility_id, parameter or "-")
        )
        out.append(
            (
                fingerprint, fingerprint, risk_class, severity,
                _score(severity, tier, criticality), customer_id, customer_name,
                tier, acv, facility_id, facility_name, system_id, label,
                criticality, parameter, title, why, consequence, owner,
                owner_source, count, first, last, reference, cfg.rule_version,
            )
        )

    # --- Microbiological escalations -------------------------------------
    for row in conn.execute(
        f"""SELECT system_id, facility_id, count(*) AS n,
                   min(observed_at), max(observed_at),
                   max(dipslide_log10) AS peak,
                   count(*) FILTER (WHERE NOT documented) AS undocumented,
                   any_value(ladder) AS ladder
            FROM {MICROBIO}
            WHERE escalation_type IN ('director_notification','urgent_offline_clean')
            GROUP BY 1,2"""
    ).fetchall():
        system_id, facility_id, n, first, last, peak, undocumented, ladder = row
        severity = "critical" if ladder == "healthcare" else "high"
        emit(
            MICROBIO_ESCALATION, severity, system_id, facility_id, "dipslide",
            f"Microbiological escalation unresolved on {system_id}",
            f"{n} escalation triggers since {first:%Y-%m-%d}, peaking at "
            f"10^{peak:.0f} CFU/ml; {undocumented} lack a work order within the "
            f"required window",
            "Section 5.3 requires director notification, a written remediation "
            "plan and weekly re-tests. Undocumented escalations at a healthcare "
            "site are a compliance exposure, not just a water-quality issue."
            if ladder == "healthcare"
            else "Sustained microbiological growth risks fouling and an "
            "escalating biocide spend.",
            None, "unassigned", n, first, last,
        )

    # --- Coverage gaps ----------------------------------------------------
    for row in conn.execute(
        f"""SELECT facility_id, status, days_since_visit, cadence_ratio,
                   service_frequency, last_technician, technician_departed,
                   acv_usd, explanation, last_visit_date
            FROM {COVERAGE} WHERE status IN ('overdue','critically_overdue')"""
    ).fetchall():
        (facility_id, status, days, ratio, frequency, technician, departed,
         acv, explanation, last_visit) = row
        severity = "critical" if status == "critically_overdue" else "medium"
        consequence = (
            f"Contract value at risk: ${acv:,.0f}/yr. " if acv else ""
        ) + (
            "Routes held in departed staff's knowledge are how accounts go "
            "silently unserviced."
            if departed
            else "Unserviced systems drift out of program between visits."
        )
        emit(
            COVERAGE_GAP, severity, None, facility_id, None,
            f"No service visit in {days} days on a {frequency} contract",
            explanation, consequence,
            technician if departed else None,
            "last_technician_departed" if departed else "unassigned",
            1, last_visit, last_visit,
        )

    # --- Residual baselines ----------------------------------------------
    # Trough per system x parameter at each end of the observation window.
    troughs: dict[tuple[str, str], tuple[float, float, int]] = {}
    residual_rows = conn.execute(
        f"""SELECT system_id, parameter_code, observed_at, normalized_value
            FROM {EVENTS}
            WHERE alert_eligible AND normalized_value IS NOT NULL
              AND collection_method <> 'bms'
            ORDER BY system_id, parameter_code, observed_at"""
    ).fetchall()
    grouped: dict[tuple[str, str], list[float]] = {}
    for system_id, parameter, _, value in residual_rows:
        grouped.setdefault((system_id, parameter), []).append(value)
    for key, values in grouped.items():
        if len(values) >= TROUGH_WINDOW * 2:
            troughs[key] = (
                min(values[:TROUGH_WINDOW]),
                min(values[-TROUGH_WINDOW:]),
                len(values),
            )

    # --- Sustained trends -------------------------------------------------
    for row in conn.execute(
        f"""WITH limits AS (
                SELECT system_id, parameter_code,
                       any_value(applied_upper) AS upper_limit,
                       any_value(applied_lower) AS lower_limit
                FROM {ASSESSMENTS}
                WHERE applied_upper IS NOT NULL OR applied_lower IS NOT NULL
                GROUP BY 1,2
            )
            SELECT t.system_id, t.facility_id, t.parameter_code,
                   count(*) AS runs, max(t.run_length) AS longest,
                   min(t.started_at) AS first_at, max(t.ended_at) AS last_at,
                   least(min(t.first_value), min(t.last_value))   AS series_min,
                   greatest(max(t.first_value), max(t.last_value)) AS series_max,
                   any_value(t.standard_unit) AS unit,
                   bool_and(t.all_within_band) AS all_in_band,
                   any_value(t.direction) AS direction,
                   any_value(l.upper_limit) AS upper_limit,
                   any_value(l.lower_limit) AS lower_limit,
                   any_value(s.criticality) AS criticality,
                   any_value(s.system_type) AS system_type
            FROM {TRENDS} t
            LEFT JOIN limits l
              ON l.system_id = t.system_id AND l.parameter_code = t.parameter_code
            LEFT JOIN {SYSTEM_TABLE} s ON s.system_id = t.system_id
            WHERE t.is_concerning AND t.sample_grain = 'service'
            GROUP BY 1,2,3"""
    ).fetchall():
        (system_id, facility_id, parameter, runs, longest, first, last,
         series_min, series_max, unit, all_in_band, direction, upper_limit,
         lower_limit, criticality, system_type) = row

        if (
            parameter == "conductivity"
            and system_type not in _CONDUCTIVITY_TREND_SYSTEM_KINDS
        ):
            continue

        # Materiality gate: what fraction of the headroom to the governing
        # limit did this movement consume? Symmetric for rising and falling,
        # and >1 means the limit was crossed.
        # `series_min`/`series_max` bracket the whole movement regardless of
        # direction; using min(first)/max(last) silently mis-measures a falling
        # series, which is how a 1050 -> 410 ppm nitrite collapse went missing.
        proximity = None
        span = series_max - series_min
        if direction == "rising" and upper_limit and upper_limit > series_min:
            proximity = span / (upper_limit - series_min)
        elif (
            direction == "falling"
            and lower_limit is not None
            and series_max > lower_limit
        ):
            proximity = span / (series_max - lower_limit)

        travelled_from, travelled_to = (
            (series_min, series_max) if direction == "rising" else (series_max, series_min)
        )

        risk_class, consequence = _TREND_RISK.get(
            parameter, (RESIDUAL_LOSS, "Sustained movement warrants investigation.")
        )

        # Promotion is per risk class: the question "is this worth a Monday?"
        # has a different answer for corrosion, scaling and residual loss.
        collapse = None
        collapse_detail = ""
        if risk_class == RESIDUAL_LOSS:
            entry = troughs.get((system_id, parameter))
            if entry is None or lower_limit is None:
                continue
            early_trough, late_trough, _ = entry
            drop = early_trough - late_trough
            if drop <= 0:
                continue
            headroom = early_trough - lower_limit
            # Two readings of the same collapse. The headroom fraction asks how
            # much of the margin to the floor was consumed; the relative drop
            # asks how far the baseline fell in its own terms. A series whose
            # early trough is already at or below the floor has no headroom to
            # measure -- Pintura's nitrite third reading is 890 against a 900
            # floor -- yet it then falls a further 480 ppm, so the relative drop
            # has to be able to carry the judgement on its own.
            by_headroom = (drop / headroom) if headroom > 0 else 0.0
            by_relative = drop / early_trough
            collapse = max(by_headroom, by_relative)
            if collapse < RESIDUAL_COLLAPSE_FRACTION:
                continue
            severity = "high" if (by_relative >= 0.4 or by_headroom >= 1.0) else "medium"
            collapse_detail = (
                f"trough fell from {early_trough:g} to {late_trough:g} {unit} "
                f"({by_relative * 100:.0f}% decline) against a {lower_limit:g} "
                f"{unit} floor, and is not recovering between doses"
            )
        elif risk_class == SCALING_RISK:
            breached = (upper_limit is not None) and (series_max > upper_limit)
            if not (breached or longest >= SCALING_MIN_RUN):
                continue
            severity = "high" if breached else "medium"
        else:
            promoted = (
                proximity is not None and proximity >= TREND_PROMOTION_PROXIMITY
            ) or (criticality == "critical" and longest >= 5)
            if not promoted:
                continue
            severity = "high" if (proximity or 0) >= 0.7 else "medium"
        band_note = (
            " Every reading stayed inside its band, so no single test would "
            "have raised an alarm."
            if all_in_band
            else ""
        )
        emit(
            risk_class, severity, system_id, facility_id, parameter,
            f"{parameter.replace('_',' ').capitalize()} {direction} steadily on {system_id}",
            f"{runs} sustained runs since {first:%Y-%m-%d}, longest {longest} "
            f"consecutive services; {travelled_from:g} to {travelled_to:g} {unit}"
            + (
                f". Baseline: {collapse_detail}"
                if collapse is not None
                else f" ({(proximity or 0) * 100:.0f}% of the headroom to its limit)"
            )
            + "."
            + band_note,
            consequence,
            None, "unassigned", runs, first, last,
        )

    # --- Persistent exceedances -------------------------------------------
    for row in conn.execute(
        f"""SELECT system_id, facility_id, parameter_code, count(*) AS n,
                   min(observed_at) AS first_at, max(observed_at) AS last_at,
                   any_value(governing_program) AS program,
                   max(severity) AS severity
            FROM {ASSESSMENTS}
            WHERE out_of_band AND status <> 'action_level_exceeded'
            GROUP BY 1,2,3 HAVING count(*) >= 5"""
    ).fetchall():
        system_id, facility_id, parameter, n, first, last, program, severity = row
        emit(
            TREATMENT_EXCEEDANCE, "medium", system_id, facility_id, parameter,
            f"{parameter.replace('_',' ').capitalize()} persistently out of band on {system_id}",
            f"{n} readings outside the {program} band between {first:%Y-%m-%d} "
            f"and {last:%Y-%m-%d}",
            "Persistent out-of-band operation means the program is not holding; "
            "the treatment or the equipment needs review.",
            None, "unassigned", n, first, last,
        )

    bulk_insert(conn, TABLE, _COLUMNS, out)
    return len(out)
