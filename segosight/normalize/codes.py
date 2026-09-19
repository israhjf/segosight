"""Data-quality issue codes emitted by the normalization primitives.

Codes are stable strings because they are persisted into the DQ exception
tables and surfaced in the UI. Renaming one is a breaking change; add a new
code instead.
"""

# --- temporal -------------------------------------------------------------
UNPARSEABLE_TIMESTAMP = "unparseable_timestamp"
AMBIGUOUS_DATE_ORDER = "ambiguous_date_order"
TIMESTAMP_OUT_OF_CORPUS = "timestamp_out_of_corpus"

# --- numeric --------------------------------------------------------------
UNPARSEABLE_NUMBER = "unparseable_number"

# --- units ----------------------------------------------------------------
UNIT_NOT_DECLARED = "unit_not_declared"
UNIT_UNRECOGNIZED = "unit_unrecognized"
UNIT_NOT_CONVERTIBLE = "unit_not_convertible"

# --- physical plausibility ------------------------------------------------
PH_OUT_OF_SCALE = "ph_out_of_scale"
NEGATIVE_CONCENTRATION = "negative_concentration"
ZERO_CONDUCTIVITY = "zero_conductivity"
MALFORMED_DIPSLIDE = "malformed_dipslide"

# --- identity -------------------------------------------------------------
UNKNOWN_ACTOR = "unknown_actor"
AMBIGUOUS_ACTOR = "ambiguous_actor"

# --- delimited fields -----------------------------------------------------
UNPARSEABLE_DOSE = "unparseable_dose"
UNKNOWN_DOSE_UNIT = "unknown_dose_unit"

# --- quality_status values (not issues; the resulting disposition) --------
VALID = "valid"
SUSPECT = "suspect"
INVALID = "invalid"
UNRESOLVED = "unresolved"
