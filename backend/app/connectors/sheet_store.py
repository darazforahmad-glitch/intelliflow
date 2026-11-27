"""Row stores behind the Google Sheets connector in sandbox mode.

InMemorySheetStore backs unit tests and test runs (never persisted, SAF-5);
DbSheetStore persists the virtual sheet of a sandbox connection so the owner can see
the rows an automation wrote.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SandboxRecord


class SheetStore(Protocol):
    def append(self, sheet: str, values: dict[str, Any]) -> int: ...
    def rows(self, sheet: str) -> list[dict[str, Any]]: ...
    def update(self, sheet: str, row_number: int, values: dict[str, Any]) -> bool: ...


class InMemorySheetStore:
    def __init__(self, seed: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._sheets: dict[str, list[dict[str, Any]]] = copy.deepcopy(seed or {})

    def append(self, sheet: str, values: dict[str, Any]) -> int:
        rows = self._sheets.setdefault(sheet, [])
        row_number = len(rows) + 2  # row 1 is the header row, like a real sheet
        rows.append({**values, "row_number": row_number})
        return row_number

    def rows(self, sheet: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self._sheets.get(sheet, []))

    def update(self, sheet: str, row_number: int, values: dict[str, Any]) -> bool:
        for row in self._sheets.get(sheet, []):
            if row["row_number"] == row_number:
                row.update(values)
                return True
        return False

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return copy.deepcopy(self._sheets)


class DbSheetStore:
    def __init__(self, db: Session, connection_id: uuid.UUID) -> None:
        self.db = db
        self.connection_id = connection_id

    def _resource(self, sheet: str) -> str:
        return f"sheet:{sheet}"

    def append(self, sheet: str, values: dict[str, Any]) -> int:
        current = self.db.scalar(
            select(func.max(SandboxRecord.row_number)).where(
                SandboxRecord.connection_id == self.connection_id,
                SandboxRecord.resource == self._resource(sheet),
            )
        )
        row_number = (current or 1) + 1
        self.db.add(
            SandboxRecord(
                connection_id=self.connection_id,
                resource=self._resource(sheet),
                row_number=row_number,
                data_json=dict(values),
            )
        )
        self.db.flush()
        return row_number

    def rows(self, sheet: str) -> list[dict[str, Any]]:
        records = self.db.scalars(
            select(SandboxRecord)
            .where(
                SandboxRecord.connection_id == self.connection_id,
                SandboxRecord.resource == self._resource(sheet),
            )
            .order_by(SandboxRecord.row_number)
        ).all()
        return [{**r.data_json, "row_number": r.row_number} for r in records]

    def update(self, sheet: str, row_number: int, values: dict[str, Any]) -> bool:
        record = self.db.scalar(
            select(SandboxRecord).where(
                SandboxRecord.connection_id == self.connection_id,
                SandboxRecord.resource == self._resource(sheet),
                SandboxRecord.row_number == row_number,
            )
        )
        if record is None:
            return False
        record.data_json = {**record.data_json, **values}
        self.db.flush()
        return True

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        sheets: dict[str, list[dict[str, Any]]] = {}
        for record in self.db.scalars(
            select(SandboxRecord)
            .where(
                SandboxRecord.connection_id == self.connection_id,
                SandboxRecord.resource.like("sheet:%"),
            )
            .order_by(SandboxRecord.row_number)
        ):
            sheets.setdefault(record.resource.removeprefix("sheet:"), []).append(
                {**record.data_json, "row_number": record.row_number}
            )
        return sheets


def _norm(value: Any) -> str:
    text = str(value if value is not None else "").strip().lower()
    digits = re.sub(r"\D", "", text)
    if (
        len(digits) >= 10
        and len(digits) >= len(text.replace(" ", "").replace("+", "").replace("-", "")) - 1
    ):
        return digits[-10:]  # compare phone numbers by their last 10 digits
    return text


def row_matches(row: dict[str, Any], criteria: dict[str, Any]) -> bool:
    return all(_norm(row.get(column)) == _norm(expected) for column, expected in criteria.items())
