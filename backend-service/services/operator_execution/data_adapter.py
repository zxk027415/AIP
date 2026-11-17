# @AI_GENERATED
"""
Data Adapter - Remaps column names between operators when source/target contracts differ.

When an upstream operator's output column names don't match the downstream operator's
expected column names, the DataAdapter automatically performs column name remapping
to avoid pipeline interruptions due to naming differences.
"""
from typing import Any, Dict, List, Tuple

import pandas as pd
from loguru import logger

from .schema_validator import DataContract


class DataAdapter:
    """
    Automatically remaps column names when upstream output doesn't match
    downstream input expectations.
    """

    def __init__(self):
        self._column_mappings: Dict[str, str] = {}

    def register_mapping(self, source: str, target: str) -> None:
        """
        Register a column name mapping from source to target.

        Args:
            source: Source column name (from upstream operator)
            target: Target column name (expected by downstream operator)
        """
        self._column_mappings[source] = target
        logger.debug(f"Registered column mapping: '{source}' -> '{target}'")

    def adapt(
        self,
        data: Any,
        source_contract: DataContract,
        target_contract: DataContract,
    ) -> Tuple[Any, List[str]]:
        """
        Adapt data from source contract format to target contract format.

        Performs column name remapping based on registered mappings and
        inferred mappings from the contracts.

        Args:
            data: The data to adapt (typically a DataFrame)
            source_contract: The contract of the upstream operator's output
            target_contract: The contract the downstream operator expects

        Returns:
            Tuple of (adapted_data, transformation_logs)
        """
        logs: List[str] = []

        if not isinstance(data, pd.DataFrame):
            return data, logs

        # Build effective mapping: registered mappings + inferred from contracts
        effective_mappings = dict(self._column_mappings)

        # Infer mappings from required columns that are missing
        existing_cols = set(data.columns)
        for target_col in target_contract.required_columns:
            if target_col not in existing_cols and target_col not in effective_mappings.values():
                # Try to find a matching source column in registered mappings
                for src, tgt in self._column_mappings.items():
                    if tgt == target_col and src in existing_cols:
                        effective_mappings[src] = tgt
                        break

        # Apply column renames
        rename_map = {}
        for source_col, target_col in effective_mappings.items():
            if source_col in data.columns and target_col not in data.columns:
                rename_map[source_col] = target_col
                log_entry = (
                    f"Column remapped: '{source_col}' -> '{target_col}' "
                    f"(source: {source_contract.contract_id}, "
                    f"target: {target_contract.contract_id})"
                )
                logs.append(log_entry)
                logger.info(log_entry)

        if rename_map:
            data = data.rename(columns=rename_map)

        return data, logs
# @AI_GENERATED: end
