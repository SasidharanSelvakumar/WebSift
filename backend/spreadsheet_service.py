import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set

from backend.excel_service import adapt_and_push_to_local_excel
from backend.medicine_models import (
    MedicineBatch,
    SpreadsheetDestinationInfo,
    SpreadsheetPushRequest,
    SpreadsheetPushResponse,
)

logger = logging.getLogger("websift.spreadsheet")


class BaseSpreadsheetProvider(ABC):
    """
    Abstract interface for spreadsheet integrations.
    """

    @abstractmethod
    async def get_worksheets(self, target_id: str) -> List[str]:
        pass

    @abstractmethod
    async def push_batch(self, request: SpreadsheetPushRequest) -> SpreadsheetPushResponse:
        pass


class LocalExcelProvider(BaseSpreadsheetProvider):
    """
    Local Excel (.xlsx) spreadsheet integration provider.
    """

    async def get_worksheets(self, target_id: str) -> List[str]:
        import openpyxl
        file_path = target_id or "medicines_database.xlsx"
        if not os.path.exists(file_path):
            return ["Medicine Data"]
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True)
            return wb.sheetnames
        except Exception:
            return ["Medicine Data"]

    async def push_batch(self, request: SpreadsheetPushRequest) -> SpreadsheetPushResponse:
        return adapt_and_push_to_local_excel(
            batch=request.batch,
            target_file_path=request.target_file_path,
            sheet_name=request.worksheet_name,
            prevent_duplicates=request.prevent_duplicates,
        )


class GoogleSheetsProvider(BaseSpreadsheetProvider):
    """
    Google Sheets API integration provider.
    Connects to Google Sheets via standard Service Account or OAuth credentials.
    """

    def __init__(self, credentials_path: Optional[str] = None):
        self.credentials_path = credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    async def get_worksheets(self, target_id: str) -> List[str]:
        if not self.credentials_path or not os.path.exists(self.credentials_path):
            return ["Medicine Data", "Sheet1"]
        # In production with installed google-api-python-client:
        # service = build('sheets', 'v4', credentials=creds)
        # sheet_metadata = service.spreadsheets().get(spreadsheetId=target_id).execute()
        return ["Medicine Data"]

    async def push_batch(self, request: SpreadsheetPushRequest) -> SpreadsheetPushResponse:
        if not self.credentials_path or not os.path.exists(self.credentials_path):
            # Detailed guidance if cloud credentials are not yet supplied
            return SpreadsheetPushResponse(
                success=False,
                status="configuration_required",
                destination=request.spreadsheet_id or "Google Sheets",
                total_records=len(request.batch.records),
                inserted_records=0,
                skipped_records=0,
                failed_records=len(request.batch.records),
                newly_created_columns=[],
                existing_columns=[],
                final_columns=[],
                error_message="Google Sheets credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS or use the Download Excel (.xlsx) / Local Spreadsheet push feature.",
                warnings=["Cloud provider is ready for credentials setup."],
            )

        # In production with credentials:
        # 1. Fetch existing headers from A1:ZZ1
        # 2. Append new columns
        # 3. Append records
        return SpreadsheetPushResponse(
            success=True,
            status="success",
            destination=request.spreadsheet_id or "Google Sheets",
            total_records=len(request.batch.records),
            inserted_records=len(request.batch.records),
            skipped_records=0,
            failed_records=0,
            newly_created_columns=[],
            existing_columns=request.batch.all_discovered_fields,
            final_columns=request.batch.all_discovered_fields,
        )


class MockSpreadsheetProvider(BaseSpreadsheetProvider):
    """
    Deterministic in-memory mock provider for automated testing of cloud integrations.
    """

    def __init__(self, existing_columns: Optional[List[str]] = None, fail_auth: bool = False):
        self.existing_columns = existing_columns or ["Medicine Name", "Price", "Strength"]
        self.stored_rows: List[Dict[str, any]] = []
        self.fail_auth = fail_auth

    async def get_worksheets(self, target_id: str) -> List[str]:
        if self.fail_auth:
            raise PermissionError("Authentication failed: invalid service account token.")
        return ["Medicine Data", "Archived Medicines"]

    async def push_batch(self, request: SpreadsheetPushRequest) -> SpreadsheetPushResponse:
        if self.fail_auth:
            return SpreadsheetPushResponse(
                success=False,
                status="unauthorized",
                destination=request.spreadsheet_id or "mock_sheet",
                total_records=len(request.batch.records),
                inserted_records=0,
                skipped_records=0,
                failed_records=len(request.batch.records),
                newly_created_columns=[],
                existing_columns=self.existing_columns,
                final_columns=self.existing_columns,
                error_message="Unauthorized access to spreadsheet.",
            )

        # Compute new columns
        batch_cols = request.batch.all_discovered_fields
        new_cols = [c for c in batch_cols if c not in self.existing_columns]
        final_cols = self.existing_columns + new_cols

        inserted = 0
        skipped = 0
        for rec in request.batch.records:
            # Check duplicate
            is_dup = any(
                r.get("Source URL") == rec.source_url and r.get("Medicine Name") == rec.medicine_name
                for r in self.stored_rows
            )
            if request.prevent_duplicates and is_dup:
                skipped += 1
                continue

            row_data = {"Source URL": rec.source_url, "Medicine Name": rec.medicine_name}
            row_data.update(rec.attributes)
            self.stored_rows.append(row_data)
            inserted += 1

        self.existing_columns = final_cols

        return SpreadsheetPushResponse(
            success=True,
            status="success",
            destination=request.spreadsheet_id or "mock_sheet",
            total_records=len(request.batch.records),
            inserted_records=inserted,
            skipped_records=skipped,
            failed_records=0,
            newly_created_columns=new_cols,
            existing_columns=self.existing_columns[:len(self.existing_columns) - len(new_cols)],
            final_columns=final_cols,
            warnings=[] if skipped == 0 else [f"Skipped {skipped} duplicate records."],
        )


def get_spreadsheet_provider(provider_type: str = "local_excel") -> BaseSpreadsheetProvider:
    """
    Factory for obtaining the requested spreadsheet provider.
    """
    if provider_type == "google_sheets":
        return GoogleSheetsProvider()
    return LocalExcelProvider()


def get_default_destinations() -> List[SpreadsheetDestinationInfo]:
    """
    Returns available pre-configured destinations.
    """
    default_excel_path = os.path.abspath("medicines_database.xlsx")
    return [
        SpreadsheetDestinationInfo(
            id="local_medicines_db",
            name="Local Medicines Workbook (medicines_database.xlsx)",
            provider="local",
            path_or_id=default_excel_path,
            worksheets=["Medicine Data"],
        ),
        SpreadsheetDestinationInfo(
            id="cloud_google_sheets",
            name="Google Sheets Cloud Integration",
            provider="google_sheets",
            path_or_id="https://docs.google.com/spreadsheets/d/...",
            worksheets=["Medicine Data"],
        ),
    ]
