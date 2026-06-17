# @AI_GENERATED
"""
shift_features operator backend — Marks morning/afternoon/night shifts.

Classifies each timestamp into a work shift based on hour of day.
Default shift definitions: morning (6-14), afternoon (14-22), night (22-6).
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "shift_features"

# Default shift hour ranges
DEFAULT_SHIFT_RULES = {
    "morning": (6, 14),
    "afternoon": (14, 22),
    "night": (22, 6),
}


def execute(params: dict, inputs: dict) -> dict:
    """
    Mark morning/afternoon/night shifts based on hour of day.

    Args:
        params: Operator parameters including:
            - time_field (str, optional): Timestamp column name. Default "record_time".
            - shift_rules (dict, optional): Custom shift definitions.
              Format: {"morning": [6,14], "afternoon": [14,22], "night": [22,6]}.
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with shift_label (str) and shift_code (int) columns.
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # Parse options
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    time_field = params.get("time_field") or options.get("time_field") or "record_time"

    shift_rules_raw = params.get("shift_rules") or options.get("shift_rules")
    if isinstance(shift_rules_raw, str):
        try:
            shift_rules_raw = json.loads(shift_rules_raw)
        except json.JSONDecodeError:
            shift_rules_raw = None

    # Build shift ranges from rules or use defaults
    if isinstance(shift_rules_raw, dict):
        shift_ranges = {}
        for name, rng in shift_rules_raw.items():
            if isinstance(rng, (list, tuple)) and len(rng) == 2:
                shift_ranges[name] = (int(rng[0]), int(rng[1]))
            else:
                shift_ranges[name] = DEFAULT_SHIFT_RULES.get(name, (0, 0))
    else:
        shift_ranges = DEFAULT_SHIFT_RULES

    df = data.copy()

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning as-is")
        return {"data": df}

    # Determine hour source: use existing 'hour' column or extract from time_field
    if "hour" in df.columns:
        hours = df["hour"]
    elif time_field in df.columns:
        df[time_field] = pd.to_datetime(df[time_field], errors="coerce")
        hours = df[time_field].dt.hour
    else:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"Neither 'hour' column nor timestamp column '{time_field}' found. "
            f"Available columns: {list(df.columns)}",
        )

    # Assign shift codes: morning=0, afternoon=1, night=2
    shift_names = list(shift_ranges.keys())
    shift_code_map = {name: idx for idx, name in enumerate(shift_names)}

    def classify_shift(h):
        for name, (start, end) in shift_ranges.items():
            if start < end:
                # Normal range (e.g., 6-14)
                if start <= h < end:
                    return name
            else:
                # Wrapping range (e.g., 22-6 means 22-24 and 0-6)
                if h >= start or h < end:
                    return name
        # Fallback: assign to first shift
        return shift_names[0] if shift_names else "unknown"

    df["shift_label"] = hours.apply(classify_shift)
    df["shift_code"] = df["shift_label"].map(shift_code_map).fillna(0).astype(int)

    counts = df["shift_label"].value_counts().to_dict()
    logger.info(f"[{OPERATOR_ID}] Shift distribution: {counts}")

    return {"data": df}
# @AI_GENERATED: end
