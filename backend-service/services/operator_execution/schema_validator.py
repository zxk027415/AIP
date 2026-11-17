# @AI_GENERATED
"""
Schema Validator - Validates operator input/output data against DataContract definitions.

Provides DataContract dataclass for defining data format specifications,
ValidationResult for reporting validation outcomes, and SchemaValidator
for performing the actual validation checks.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class DataContract:
    """
    Formal specification for data passed between operators.

    Attributes:
        contract_id: Unique identifier for this contract
        data_type: Expected data type (MATRIX / ARRAY / NUMBER / OBJECT)
        required_columns: Column names that must be present (for MATRIX type)
        column_types: Mapping of column name -> expected dtype string
        constraints: List of constraint identifiers (e.g. "no_nan", "time_ordered")
        description: Human-readable description (Chinese)
    """
    contract_id: str
    data_type: str
    required_columns: List[str] = field(default_factory=list)
    column_types: Dict[str, str] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ValidationResult:
    """Result of a schema validation check."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SchemaValidator:
    """
    Validates operator output/input data against DataContract definitions.

    Checks required columns, column data types, and constraint conditions
    such as no_nan, time_ordered, continuous_index, etc.
    """

    # Mapping from contract dtype strings to pandas/numpy compatible checks
    _DTYPE_CHECKS = {
        "datetime64": lambda s: pd.api.types.is_datetime64_any_dtype(s),
        "float64": lambda s: pd.api.types.is_float_dtype(s) or pd.api.types.is_integer_dtype(s),
        "float": lambda s: pd.api.types.is_float_dtype(s) or pd.api.types.is_integer_dtype(s),
        "int": lambda s: pd.api.types.is_integer_dtype(s) or pd.api.types.is_float_dtype(s),
        "int64": lambda s: pd.api.types.is_integer_dtype(s) or pd.api.types.is_float_dtype(s),
        "str": lambda s: pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s),
        "string": lambda s: pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s),
        "bool": lambda s: pd.api.types.is_bool_dtype(s),
    }

    def validate_output(self, data: Any, contract: DataContract) -> ValidationResult:
        """
        Validate operator output data against a DataContract.

        Args:
            data: The output data to validate
            contract: The DataContract specification

        Returns:
            ValidationResult with valid flag, errors, and warnings
        """
        errors: List[str] = []
        warnings: List[str] = []

        # For OBJECT type that wraps multiple outputs, validate the dict structure
        if contract.data_type == "OBJECT":
            if not isinstance(data, dict):
                errors.append(
                    f"Expected OBJECT (dict), got {type(data).__name__}"
                )
            return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

        # For NUMBER type
        if contract.data_type == "NUMBER":
            if not isinstance(data, (int, float, np.integer, np.floating)):
                errors.append(
                    f"Expected NUMBER, got {type(data).__name__}"
                )
            else:
                self._check_number_constraints(data, contract.constraints, errors)
            return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

        # For ARRAY type
        if contract.data_type == "ARRAY":
            if not isinstance(data, (list, np.ndarray, pd.Series)):
                errors.append(
                    f"Expected ARRAY, got {type(data).__name__}"
                )
            return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

        # For MATRIX type (DataFrame)
        if contract.data_type == "MATRIX":
            if not isinstance(data, pd.DataFrame):
                errors.append(
                    f"Expected MATRIX (DataFrame), got {type(data).__name__}"
                )
                return ValidationResult(valid=False, errors=errors, warnings=warnings)

            # Check required columns
            for col in contract.required_columns:
                if col not in data.columns and col not in (data.index.name,):
                    errors.append(f"Missing required column: '{col}'")

            # Check column types
            for col, expected_dtype in contract.column_types.items():
                if col in data.columns:
                    checker = self._DTYPE_CHECKS.get(expected_dtype)
                    if checker and not checker(data[col]):
                        errors.append(
                            f"Column '{col}' type mismatch: expected {expected_dtype}, "
                            f"got {data[col].dtype}"
                        )
                elif col == data.index.name:
                    # Column might be the index
                    pass

            # Check constraints
            self._check_matrix_constraints(data, contract.constraints, errors, warnings)

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_input(self, data: Any, expected_type: str) -> ValidationResult:
        """
        Validate input data matches the expected type.

        Args:
            data: The input data
            expected_type: Expected type string (MATRIX/ARRAY/NUMBER/OBJECT/STRING)

        Returns:
            ValidationResult
        """
        errors: List[str] = []
        type_checks = {
            "MATRIX": lambda d: isinstance(d, pd.DataFrame),
            "ARRAY": lambda d: isinstance(d, (list, np.ndarray, pd.Series)),
            "NUMBER": lambda d: isinstance(d, (int, float, np.integer, np.floating)),
            "OBJECT": lambda d: isinstance(d, dict),
            "STRING": lambda d: isinstance(d, str),
        }

        checker = type_checks.get(expected_type)
        if checker and not checker(data):
            errors.append(
                f"Input type mismatch: expected {expected_type}, got {type(data).__name__}"
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def check_array_consistency(self, arr1: Any, arr2: Any) -> bool:
        """
        Check that two arrays have the same length.

        Args:
            arr1: First array-like
            arr2: Second array-like

        Returns:
            True if lengths match, False otherwise
        """
        len1 = len(arr1) if hasattr(arr1, "__len__") else 0
        len2 = len(arr2) if hasattr(arr2, "__len__") else 0
        return len1 == len2

    def _check_matrix_constraints(
        self,
        df: pd.DataFrame,
        constraints: List[str],
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Check DataFrame-level constraints."""
        for constraint in constraints:
            if constraint == "no_nan":
                numeric_cols = df.select_dtypes(include=[np.number]).columns
                for col in numeric_cols:
                    nan_count = df[col].isna().sum()
                    if nan_count > 0:
                        errors.append(
                            f"Constraint 'no_nan' violated: column '{col}' has {nan_count} NaN values"
                        )

            elif constraint == "time_ordered":
                time_col = None
                if "record_time" in df.columns:
                    time_col = "record_time"
                elif df.index.name and "time" in str(df.index.name).lower():
                    # Check index ordering
                    if not df.index.is_monotonic_increasing:
                        errors.append(
                            "Constraint 'time_ordered' violated: index is not monotonically increasing"
                        )
                    continue

                if time_col and len(df) > 1:
                    ts = pd.to_datetime(df[time_col], errors="coerce")
                    if not ts.is_monotonic_increasing:
                        errors.append(
                            f"Constraint 'time_ordered' violated: column '{time_col}' "
                            f"is not monotonically increasing"
                        )

            elif constraint == "no_duplicates":
                time_col = None
                if "record_time" in df.columns:
                    time_col = "record_time"
                if time_col and df[time_col].duplicated().any():
                    dup_count = df[time_col].duplicated().sum()
                    errors.append(
                        f"Constraint 'no_duplicates' violated: {dup_count} duplicate timestamps"
                    )

            elif constraint == "continuous_index":
                # Check that time index has consistent intervals
                if len(df) > 2:
                    time_col = None
                    if "record_time" in df.columns:
                        time_col = "record_time"
                    if time_col:
                        ts = pd.to_datetime(df[time_col], errors="coerce")
                        diffs = ts.diff().dropna()
                        if len(diffs) > 0:
                            mode_diff = diffs.mode()
                            if len(mode_diff) > 0:
                                expected = mode_diff.iloc[0]
                                inconsistent = (diffs != expected).sum()
                                if inconsistent > 0:
                                    warnings.append(
                                        f"Constraint 'continuous_index': {inconsistent} "
                                        f"gaps found in time index"
                                    )

            elif constraint == "features_merged":
                # Informational constraint - features should be merged into input
                pass

            elif constraint == "outliers_replaced_nan":
                # Informational - outlier positions replaced with NaN
                pass

            elif constraint in (
                "window_size_consistent",
                "step_aligned",
                "no_future_leak",
                "train_test_same_columns",
            ):
                # These are structural constraints checked at a higher level
                pass

    def _check_number_constraints(
        self, value: Any, constraints: List[str], errors: List[str]
    ) -> None:
        """Check number-level constraints."""
        for constraint in constraints:
            if constraint == "finite":
                if not np.isfinite(value):
                    errors.append(
                        f"Constraint 'finite' violated: value is {value}"
                    )
            elif constraint == "non_negative":
                if value < 0:
                    errors.append(
                        f"Constraint 'non_negative' violated: value is {value}"
                    )
            elif constraint == "range_0_200":
                if not (0 <= value <= 200):
                    errors.append(
                        f"Constraint 'range_0_200' violated: value is {value}"
                    )
# @AI_GENERATED: end
