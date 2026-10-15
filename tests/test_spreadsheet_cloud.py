import pytest
from backend.medicine_models import MedicineBatch, MedicineRecord, SpreadsheetPushRequest
from backend.spreadsheet_service import MockSpreadsheetProvider, get_spreadsheet_provider, get_default_destinations


def make_test_batch():
    rec = MedicineRecord(
        record_id="rec_cloud_1",
        medicine_name="Amoxicillin 500mg",
        source_url="https://example.com/amoxicillin",
        extracted_at="2026-10-15T12:00:00Z",
        attributes={
            "Medicine Name": "Amoxicillin 500mg",
            "Price": "₹75",
            "Strength": "500 mg",
            "Storage Instructions": "Store in dry place",
        },
    )
    return MedicineBatch(
        records=[rec],
        all_discovered_fields=["Medicine Name", "Price", "Strength", "Storage Instructions"],
        total_records=1,
    )


@pytest.mark.anyio
async def test_mock_cloud_push_success():
    provider = MockSpreadsheetProvider(existing_columns=["Medicine Name", "Price"])
    batch = make_test_batch()

    req = SpreadsheetPushRequest(
        batch=batch,
        destination_type="google_sheets",
        spreadsheet_id="sheet_xyz_123",
        worksheet_name="Medicine Data",
        prevent_duplicates=True,
    )

    res = await provider.push_batch(req)
    assert res.success is True
    assert res.status == "success"
    assert res.inserted_records == 1
    assert "Strength" in res.newly_created_columns
    assert "Storage Instructions" in res.newly_created_columns

    # Test idempotency (duplicate prevention)
    res2 = await provider.push_batch(req)
    assert res2.success is True
    assert res2.inserted_records == 0
    assert res2.skipped_records == 1


@pytest.mark.anyio
async def test_mock_cloud_push_auth_failure():
    provider = MockSpreadsheetProvider(fail_auth=True)
    batch = make_test_batch()

    req = SpreadsheetPushRequest(
        batch=batch,
        destination_type="google_sheets",
        spreadsheet_id="sheet_xyz_123",
    )

    res = await provider.push_batch(req)
    assert res.success is False
    assert res.status == "unauthorized"
    assert "Unauthorized" in res.error_message


def test_default_destinations():
    dests = get_default_destinations()
    assert len(dests) >= 2
    assert any(d.provider == "local" for d in dests)
    assert any(d.provider == "google_sheets" for d in dests)
