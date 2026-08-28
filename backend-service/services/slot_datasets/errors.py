"""Slot dataset errors (G5)."""

from __future__ import annotations


class SlotDatasetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
