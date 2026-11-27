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

from django.db.models import Max

from intelliflow.integrations.models import SandboxRecord


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
    def __init__(self, connection_id: uuid.UUID) -> None:
        self.connection_id = connection_id

    def _resource(self, sheet: str) -> str:
        return f"sheet:{sheet}"

    def _records(self, sheet: str):  # type: ignore[no-untyped-def]
        return SandboxRecord.objects.filter(
            connection_id=self.connection_id, resource=self._resource(sheet)
        )

    def append(self, sheet: str, values: dict[str, Any]) -> int:
        current = self._records(sheet).aggregate(top=Max("row_number"))["top"]
        row_number = (current or 1) + 1
        SandboxRecord.objects.create(
            connection_id=self.connection_id,
            resource=self._resource(sheet),
            row_number=row_number,
            data_json=dict(values),
        )
        return row_number

    def rows(self, sheet: str) -> list[dict[str, Any]]:
        return [
            {**r.data_json, "row_number": r.row_number}
            for r in self._records(sheet).order_by("row_number")
        ]

    def update(self, sheet: str, row_number: int, values: dict[str, Any]) -> bool:
        record = self._records(sheet).filter(row_number=row_number).first()
        if record is None:
            return False
        record.data_json = {**record.data_json, **values}
        record.save(update_fields=["data_json", "updated_at"])
        return True

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        sheets: dict[str, list[dict[str, Any]]] = {}
        records = SandboxRecord.objects.filter(
            connection_id=self.connection_id, resource__startswith="sheet:"
        ).order_by("row_number")
        for record in records:
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
