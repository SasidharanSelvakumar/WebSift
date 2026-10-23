from unittest.mock import patch
import pytest
from starlette.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "playwright_available" in data


def test_extract_ssrf_blocked():
    # Loopback IP attempt
    response = client.post("/api/extract", json={"url": "http://127.0.0.1:8080/data", "mode": "main"})
    assert response.status_code == 403
    assert "Security Restriction" in response.json()["detail"]

    # Localhost attempt
    response = client.post("/api/extract", json={"url": "http://localhost:3000/api", "mode": "main"})
    assert response.status_code == 403


def test_extract_invalid_scheme():
    response = client.post("/api/extract", json={"url": "ftp://example.com/file", "mode": "main"})
    assert response.status_code == 400


@patch("backend.main.fetch_html")
def test_extract_successful_mock(mock_fetch):
    sample_html = """
    <html>
        <head><title>Mocked Article</title></head>
        <body>
            <article>
                <h1>Scraping Success</h1>
                <p>WebSift extracts high quality structured content.</p>
                <ul><li>Bullet one</li><li>Bullet two</li></ul>
            </article>
        </body>
    </html>
    """
    mock_fetch.return_value = (sample_html, "https://example.com/test", False)

    response = client.post(
        "/api/extract",
        json={"url": "https://example.com/test", "mode": "main"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["page_title"] == "Mocked Article"
    assert len(data["items"]) >= 3
    assert data["stats"]["word_count"] > 5


def test_export_csv_endpoint():
    items = [
        {
            "sequence_number": 1,
            "source_url": "https://example.com",
            "page_title": "Test Title",
            "content_type": "paragraph",
            "heading": "Intro",
            "text_content": "Extracted text content for export testing.",
            "extracted_at": "2026-10-15T10:00:00Z"
        }
    ]
    response = client.post(
        "/api/export/csv",
        json={
            "items": items,
            "source_url": "https://example.com",
            "page_title": "Test Title"
        }
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM


def test_export_txt_endpoint():
    items = [
        {
            "sequence_number": 1,
            "source_url": "https://example.com",
            "page_title": "Test Title",
            "content_type": "paragraph",
            "heading": "Intro",
            "text_content": "Extracted text content for export testing.",
            "extracted_at": "2026-10-15T10:00:00Z"
        }
    ]
    response = client.post(
        "/api/export/txt",
        json={
            "items": items,
            "source_url": "https://example.com",
            "page_title": "Test Title",
            "mode": "main"
        }
    )
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    assert "WEBSIFT — EXTRACTED CONTENT REPORT" in text
    assert "Extracted text content for export testing." in text


def test_export_excel_endpoint():
    batch = {
        "records": [
            {
                "record_id": "rec_api_1",
                "medicine_name": "Test Medicine",
                "source_url": "https://example.com/test",
                "extracted_at": "2026-10-15T12:00:00Z",
                "attributes": {
                    "Medicine Name": "Test Medicine",
                    "Price": "₹199",
                    "Strength": "100 mg",
                }
            }
        ],
        "all_discovered_fields": ["Medicine Name", "Price", "Strength"],
        "total_records": 1,
    }

    res = client.post("/api/export/excel", json={"batch": batch, "source_url": "https://example.com/test"})
    assert res.status_code == 200
    assert "spreadsheetml.sheet" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]
    assert len(res.content) > 1000


def test_export_medicine_csv_and_txt_endpoints():
    batch = {
        "records": [
            {
                "record_id": "rec_api_2",
                "medicine_name": "Test Medicine 2",
                "source_url": "https://example.com/test2",
                "extracted_at": "2026-10-15T12:00:00Z",
                "attributes": {
                    "Medicine Name": "Test Medicine 2",
                    "Active Ingredients": "Ibuprofen",
                }
            }
        ],
        "all_discovered_fields": ["Medicine Name", "Active Ingredients"],
        "total_records": 1,
    }

    # CSV
    csv_res = client.post("/api/export/medicine-csv", json={"batch": batch, "source_url": "https://example.com/test2"})
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert csv_res.content.startswith(b"\xef\xbb\xbf")

    # TXT
    txt_res = client.post("/api/export/medicine-txt", json={"batch": batch, "source_url": "https://example.com/test2"})
    assert txt_res.status_code == 200
    assert "text/plain" in txt_res.headers["content-type"]
    assert "MEDICINE DATA EXPORT" in txt_res.text
    assert "RECORD #1" in txt_res.text


def test_spreadsheet_destinations_and_push(tmp_path):
    dest_res = client.get("/api/spreadsheet/destinations")
    assert dest_res.status_code == 200
    dests = dest_res.json()
    assert len(dests) >= 2

    # Test push
    target_path = str(tmp_path / "push_test.xlsx")
    batch = {
        "records": [
            {
                "record_id": "rec_push_1",
                "medicine_name": "Push Drug",
                "source_url": "https://example.com/push",
                "extracted_at": "2026-10-15T12:00:00Z",
                "attributes": {"Medicine Name": "Push Drug", "Price": "₹50"}
            }
        ],
        "all_discovered_fields": ["Medicine Name", "Price"],
        "total_records": 1,
    }

    push_res = client.post(
        "/api/spreadsheet/push",
        json={
            "batch": batch,
            "destination_type": "local_excel",
            "target_file_path": target_path,
            "worksheet_name": "Medicine Data",
        }
    )
    assert push_res.status_code == 200
    data = push_res.json()
    assert data["success"] is True
    assert data["inserted_records"] == 1
    assert data["skipped_records"] == 0

    # Test duplicate prevention on same batch
    push_dup = client.post(
        "/api/spreadsheet/push",
        json={
            "batch": batch,
            "destination_type": "local_excel",
            "target_file_path": target_path,
            "worksheet_name": "Medicine Data",
            "prevent_duplicates": True,
        }
    )
    assert push_dup.status_code == 200
    dup_data = push_dup.json()
    assert dup_data["inserted_records"] == 0
    assert dup_data["skipped_records"] == 1

    # Test dynamic schema expansion with batch 2
    batch2 = {
        "records": [
            {
                "record_id": "rec_push_2",
                "medicine_name": "Push Drug B",
                "source_url": "https://example.com/push-b",
                "extracted_at": "2026-10-15T12:05:00Z",
                "attributes": {
                    "Medicine Name": "Push Drug B",
                    "Price": "₹120",
                    "Pediatric Dosage": "10mg",
                    "Storage Condition": "Keep dry",
                }
            }
        ],
        "all_discovered_fields": ["Medicine Name", "Price", "Pediatric Dosage", "Storage Condition"],
        "total_records": 1,
    }
    push2_res = client.post(
        "/api/spreadsheet/push",
        json={
            "batch": batch2,
            "destination_type": "local_excel",
            "target_file_path": target_path,
            "worksheet_name": "Medicine Data",
            "prevent_duplicates": True,
        }
    )
    assert push2_res.status_code == 200
    push2_data = push2_res.json()
    assert push2_data["inserted_records"] == 1
    assert "Pediatric Dosage" in push2_data["newly_created_columns"]
    assert "Storage Condition" in push2_data["newly_created_columns"]


def test_category_api_workflow():
    start_res = client.post(
        "/api/category/start",
        json={
            "category_url": "https://example.com/drugs-all-medicines",
            "max_pages": 2,
            "max_products": 10,
            "delay_seconds": 0.1,
        }
    )
    assert start_res.status_code == 200
    data = start_res.json()
    assert "job_id" in data
    assert data["job_status"] == "running"

    job_id = data["job_id"]
    status_res = client.get(f"/api/category/job/{job_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["job_id"] == job_id

    pause_res = client.post(f"/api/category/job/{job_id}/pause")
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"

