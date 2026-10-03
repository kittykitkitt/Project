"""Data models and small shared helpers.

Related models are kept together in this single module on purpose - splitting
each record into its own file would add files without adding value.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Mapping


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_iso() -> str:
    return date.today().isoformat()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class User:
    id: int
    username: str
    full_name: str
    role: str
    password_salt: str = ""
    password_hash: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "User":
        return cls(
            id=as_int(row["id"]),
            username=str(row["username"]),
            full_name=str(row["full_name"]),
            role=str(row["role"]),
            password_salt=str(row["password_salt"]),
            password_hash=str(row["password_hash"]),
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def safe_dict(self) -> dict[str, Any]:
        """Representation without password material (for logs / dialogs)."""
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
        }


@dataclass
class Vehicle:
    id: int
    plate_number: str
    brand: str
    model: str
    category: str = "Sedan"
    year: int = 2020
    seats: int = 4
    rate_per_day: float = 0.0
    status: str = "available"
    is_archived: bool = False
    latitude: float = 0.0
    longitude: float = 0.0
    image_path: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, Any]) -> "Vehicle":
        return cls(
            id=as_int(row["id"]),
            plate_number=str(row["plate_number"]),
            brand=str(row["brand"]),
            model=str(row["model"]),
            category=str(row["category"]),
            year=as_int(row["year"], 2020),
            seats=as_int(row["seats"], 4),
            rate_per_day=as_float(row["rate_per_day"]),
            status=str(row["status"]),
            is_archived=bool(row["is_archived"]),
            latitude=as_float(row["latitude"]),
            longitude=as_float(row["longitude"]),
            image_path=str(row["image_path"] or ""),
            notes=str(row["notes"] or ""),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )


@dataclass
class ReportData:
    """Everything the PDF/CSV exporters need for one report."""
    title: str
    columns: list[str]
    rows: list[list[Any]]
    summary: list[str] = field(default_factory=list)
    subtitle: str = ""
