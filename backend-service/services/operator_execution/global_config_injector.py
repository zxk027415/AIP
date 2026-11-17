# @AI_GENERATED
"""
Global Config Injector - Injects workflow-level global configuration into operator params.

Reads from EnhancedWorkflow.metadata.global_config and merges time_zone,
operate_status, nowtime into each operator's params without overwriting
existing operator-specific values.
"""
from typing import Dict, Any

from loguru import logger


class GlobalConfigInjector:
    """
    Injects workflow global configuration into operator parameters.

    Global config fields (time_zone, operate_status, nowtime) are stored in
    EnhancedWorkflow.metadata.global_config. Before each operator executes,
    this injector merges them into the operator's params dict.

    The injector uses setdefault semantics: operator-specific params take
    precedence over global config values.
    """

    # Fields that get promoted to top-level params for convenience
    _PROMOTED_FIELDS = (
        "time_zone",
        "nowtime",
        "operate_status",
        "slot",
        "dataset_id",
        "entity_keys",
        "time_field",
        "measure_fields",
        "label_field",
        "window_key",
        "dataset_contract",
        "source_workflow_id",
        "source_execution_id",
    )

    def __init__(self, global_config: Dict[str, Any]):
        """
        Args:
            global_config: The workflow global config dict, typically from
                           metadata.global_config. May contain time_zone,
                           operate_status, nowtime, etc.
        """
        self._global_config = dict(global_config) if global_config else {}

    @property
    def global_config(self) -> Dict[str, Any]:
        """Return a copy of the current global config."""
        return dict(self._global_config)

    def inject(self, params: dict) -> dict:
        """
        Merge global config into operator params.

        - Adds '_global_config' key containing the full global config dict
        - Promotes commonly used fields (time_zone, nowtime, operate_status)
          to top-level params using setdefault (won't overwrite existing values)

        Args:
            params: The operator's own parameters

        Returns:
            New dict with global config merged in
        """
        injected = dict(params)

        # Attach full global config under a namespaced key
        injected["_global_config"] = dict(self._global_config)

        # Promote commonly used fields to top-level for convenience
        for field_name in self._PROMOTED_FIELDS:
            if field_name in self._global_config:
                injected.setdefault(field_name, self._global_config[field_name])

        return injected
# @AI_GENERATED: end
