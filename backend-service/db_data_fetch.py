"""
Backward-compatible shim for legacy imports.

The original codebase imported ``offline_load_data`` from a module named
``db_data_fetch``. In this refactored repository, the implementation lives in
``data_fetch.fetcher``.
"""

from data_fetch.fetcher import offline_load_data  # re-export

