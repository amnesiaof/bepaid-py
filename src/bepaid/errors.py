from __future__ import annotations

from dataclasses import dataclass


class BepaidError(Exception):
    """Base exception for bepaid errors."""


@dataclass
class ApiError(BepaidError):
    """An error response returned by the bePaid API."""

    status: int
    message: str
    errors: dict | None = None

    def __str__(self) -> str:
        return f"API error {self.status}: {self.message}"
