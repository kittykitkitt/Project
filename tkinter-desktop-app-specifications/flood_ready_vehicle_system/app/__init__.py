"""Flood Ready Vehicle System - application package.

Shared exception types live here so business logic, services and the Tkinter
interface can raise/catch a single family of errors without circular imports.
"""
from __future__ import annotations


class AppError(Exception):
    """Base class for every expected, user presentable error."""


class ValidationError(AppError):
    """Raised when input data is missing or badly formatted."""


class AuthenticationError(AppError):
    """Raised when a login attempt fails."""


class NotFoundError(AppError):
    """Raised when a record does not exist."""


class DataConflictError(AppError):
    """Raised for unique/duplicate data problems such as plate numbers."""


class OperationError(AppError):
    """Raised when an action cannot be completed in the current state."""


__all__ = [
    "AppError",
    "ValidationError",
    "AuthenticationError",
    "NotFoundError",
    "DataConflictError",
    "OperationError",
]
