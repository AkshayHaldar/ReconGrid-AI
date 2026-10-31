"""Standardized API response & error envelopes per CODE-STANDARDS.md §7."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: ErrorDetail | None = None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        return cls(success=True, data=data, error=None)

    @classmethod
    def fail(cls, code: str, message: str, details: Any | None = None) -> "ApiResponse[T]":
        return cls(
            success=False,
            data=None,
            error=ErrorDetail(code=code, message=message, details=details),
        )
