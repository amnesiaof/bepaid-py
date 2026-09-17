from __future__ import annotations

from dataclasses import dataclass


class BepaidError(Exception):
    """Base exception for bepaid errors."""


@dataclass
class ApiError(BepaidError):
    """An error response returned by the bePaid API."""

    status: int
    message: str | dict
    errors: dict | None = None
    error_code: str | int | None = None
    code: str | None = None
    friendly_message: str | None = None

    def __str__(self) -> str:
        return f"API error {self.status}: {self.message}"
