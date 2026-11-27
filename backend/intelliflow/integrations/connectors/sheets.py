"""Google Sheets connector: read, append and update rows (REQ-IN-3). No delete operations (SAF-3)."""

from __future__ import annotations

import json
import re
from typing import Any

from intelliflow.engine.errors import (
    ConnectionUnavailableError,
    PermanentBlockError,
    TransientBlockError,
)
from intelliflow.integrations.connectors.base import Connector, ConnectorContext, OperationSpec
from intelliflow.integrations.connectors.sheet_store import (
    InMemorySheetStore,
    SheetStore,
    row_matches,
)


class SheetsConnector(Connector):
    provider = "google_sheets"
    label = "Google Sheets"
    operations = {
        "append_row": OperationSpec(
            "append_row", "Add a row", writes=True, required=("sheet", "values")
        ),
        "find_rows": OperationSpec(
            "find_rows", "Find rows", writes=False, required=("sheet", "match")
        ),
        "update_row": OperationSpec(
            "update_row", "Update a row", writes=True, required=("sheet", "row_number", "values")
        ),
        "read_rows": OperationSpec("read_rows", "Read rows", writes=False, required=("sheet",)),
    }

    def __init__(self, ctx: ConnectorContext, store: SheetStore | None = None) -> None:
        super().__init__(ctx)
        self.store: SheetStore = store or InMemorySheetStore()

    # ------------------------------------------------------------------ operations
    def op_append_row(self, params: dict[str, Any]) -> dict[str, Any]:
        sheet, values = self._sheet(params), self._values(params)
        if self.sandbox:
            row_number = self.store.append(sheet, values)
            self.ctx.recorder.record(
                self.provider,
                "append_row",
                {"sheet": sheet, "values": values, "row_number": row_number},
            )
            return {"sheet": sheet, "row_number": row_number, "values": values, "status": "sandbox"}
        return self._live_append(sheet, values)

    def op_find_rows(self, params: dict[str, Any]) -> dict[str, Any]:
        sheet = self._sheet(params)
        criteria = {k: v for k, v in dict(params["match"]).items() if v not in (None, "")}
        rows = [r for r in self._all_rows(sheet) if row_matches(r, criteria)]
        rows.reverse()  # newest first
        return {
            "sheet": sheet,
            "count": len(rows),
            "rows": rows[:50],
            "first": rows[0] if rows else None,
        }

    def op_read_rows(self, params: dict[str, Any]) -> dict[str, Any]:
        sheet = self._sheet(params)
        criteria = {k: v for k, v in dict(params.get("match") or {}).items() if v not in (None, "")}
        limit = min(int(params.get("limit") or 200), 500)
        rows = [r for r in self._all_rows(sheet) if row_matches(r, criteria)][-limit:]
        return {
            "sheet": sheet,
            "count": len(rows),
            "rows": rows,
            "rows_json": json.dumps(rows, ensure_ascii=False, default=str),
        }

    def op_update_row(self, params: dict[str, Any]) -> dict[str, Any]:
        sheet, values = self._sheet(params), self._values(params)
        try:
            row_number = int(params["row_number"])
        except (TypeError, ValueError) as exc:
            raise PermanentBlockError(
                "No matching row was found to update.", code="row_not_found"
            ) from exc
        if self.sandbox:
            if not self.store.update(sheet, row_number, values):
                raise PermanentBlockError(
                    f"Row {row_number} does not exist in “{sheet}”.", code="row_not_found"
                )
            self.ctx.recorder.record(
                self.provider,
                "update_row",
                {"sheet": sheet, "row_number": row_number, "values": values},
            )
            return {
                "sheet": sheet,
                "row_number": row_number,
                "updated": sorted(values),
                "status": "sandbox",
            }
        return self._live_update(sheet, row_number, values)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _sheet(params: dict[str, Any]) -> str:
        sheet = str(params["sheet"]).strip()
        if not sheet or len(sheet) > 100 or re.search(r"[\[\]*?/\\:]", sheet):
            raise PermanentBlockError(
                f"“{sheet}” is not a valid sheet (tab) name.", code="invalid_sheet"
            )
        return sheet

    @staticmethod
    def _values(params: dict[str, Any]) -> dict[str, Any]:
        values = params.get("values")
        if not isinstance(values, dict) or not values:
            raise PermanentBlockError(
                "There are no values to write to the sheet.", code="no_values"
            )
        return {str(k): ("" if v is None else v) for k, v in values.items()}

    def _all_rows(self, sheet: str) -> list[dict[str, Any]]:
        if self.sandbox:
            return self.store.rows(sheet)
        header, rows = self._live_read(sheet)
        return [
            {**dict(zip(header, row, strict=False)), "row_number": index + 2}
            for index, row in enumerate(rows)
        ]

    # ------------------------------------------------------------------ live Google Sheets API
    def _service(self):  # type: ignore[no-untyped-def]
        from googleapiclient.discovery import build

        from intelliflow.integrations.connectors.google_auth import build_credentials

        if not self.ctx.credentials:
            raise ConnectionUnavailableError("Google Sheets is not connected.")
        creds = build_credentials(self.ctx.credentials, self.ctx.save_credentials)
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    def _spreadsheet_id(self) -> str:
        spreadsheet_id = (self.ctx.connection.config_json if self.ctx.connection else {}).get(
            "spreadsheet_id"
        )
        if not spreadsheet_id:
            raise ConnectionUnavailableError(
                "Choose a spreadsheet for Google Sheets on the Integrations page."
            )
        return str(spreadsheet_id)

    def _call(self, request):  # type: ignore[no-untyped-def]
        from googleapiclient.errors import HttpError

        try:
            return request.execute(num_retries=0)
        except HttpError as exc:
            status = exc.resp.status
            if status == 429 or status >= 500:
                raise TransientBlockError(
                    f"Google Sheets is temporarily unavailable ({status}). Will retry."
                ) from exc
            if status in {401, 403}:
                raise ConnectionUnavailableError(
                    "Google Sheets access was denied. Please reconnect Google."
                ) from exc
            raise PermanentBlockError(
                f"Google Sheets refused the request ({status}).", code="sheets_rejected"
            ) from exc
        except OSError as exc:
            raise TransientBlockError("Could not reach Google Sheets. Will retry.") from exc

    def _live_read(self, sheet: str) -> tuple[list[str], list[list[Any]]]:
        values = self._call(
            self._service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id(), range=f"'{sheet}'")
        ).get("values", [])
        return (values[0], values[1:]) if values else ([], [])

    def _ensure_header(self, service: Any, sheet: str, columns: list[str]) -> list[str]:
        header, _ = self._live_read(sheet)
        missing = [c for c in columns if c not in header]
        if missing:
            header = header + missing
            self._call(
                service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=self._spreadsheet_id(),
                    range=f"'{sheet}'!1:1",
                    valueInputOption="RAW",
                    body={"values": [header]},
                )
            )
        return header

    def _live_append(self, sheet: str, values: dict[str, Any]) -> dict[str, Any]:
        service = self._service()
        header = self._ensure_header(service, sheet, list(values))
        row = [values.get(column, "") for column in header]
        result = self._call(
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self._spreadsheet_id(),
                range=f"'{sheet}'!A1",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            )
        )
        match = re.search(r"![A-Z]+(\d+)", result.get("updates", {}).get("updatedRange", ""))
        return {
            "sheet": sheet,
            "row_number": int(match.group(1)) if match else None,
            "values": values,
            "status": "written",
        }

    def _live_update(self, sheet: str, row_number: int, values: dict[str, Any]) -> dict[str, Any]:
        service = self._service()
        header = self._ensure_header(service, sheet, list(values))
        data = []
        for column, value in values.items():
            index = header.index(column)
            letter = ""
            index += 1
            while index:
                index, remainder = divmod(index - 1, 26)
                letter = chr(65 + remainder) + letter
            data.append({"range": f"'{sheet}'!{letter}{row_number}", "values": [[value]]})
        self._call(
            service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self._spreadsheet_id(),
                body={"valueInputOption": "USER_ENTERED", "data": data},
            )
        )
        return {
            "sheet": sheet,
            "row_number": row_number,
            "updated": sorted(values),
            "status": "written",
        }
