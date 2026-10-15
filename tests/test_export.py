import csv
import io
from backend.export_service import generate_csv_bytes, generate_txt_bytes, escape_for_csv, generate_filename
from backend.models import ExtractedItem


def make_sample_items():
    return [
        ExtractedItem(
            sequence_number=1,
            source_url="https://example.com/test-page",
            page_title="WebSift Export Test",
            content_type="page_title",
            heading=None,
            text_content="WebSift Export Test",
            extracted_at="2026-10-15T12:00:00Z",
        ),
        ExtractedItem(
            sequence_number=2,
            source_url="https://example.com/test-page",
            page_title="WebSift Export Test",
            content_type="paragraph",
            heading="Section 1",
            text_content='A complex text with "double quotes", commas, and\nnewline characters.',
            extracted_at="2026-10-15T12:00:00Z",
        ),
        ExtractedItem(
            sequence_number=3,
            source_url="https://example.com/test-page",
            page_title="WebSift Export Test",
            content_type="paragraph",
            heading="Section 1",
            text_content="=SUM(A1:A10)",  # Formula injection attempt!
            extracted_at="2026-10-15T12:00:00Z",
        ),
        ExtractedItem(
            sequence_number=4,
            source_url="https://example.com/test-page",
            page_title="WebSift Export Test",
            content_type="paragraph",
            heading="Section 2",
            text_content="Unicode support: 東京 (Tokyo), € Euro, ₹ Rupee, 🚀 Rocket.",
            extracted_at="2026-10-15T12:00:00Z",
        ),
    ]


def test_formula_injection_escaping():
    assert escape_for_csv("=1+1") == "'=1+1"
    assert escape_for_csv("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert escape_for_csv("-danger") == "'-danger"
    assert escape_for_csv("@calc") == "'@calc"
    assert escape_for_csv("Normal paragraph") == "Normal paragraph"


def test_csv_generation():
    items = make_sample_items()
    csv_bytes, filename = generate_csv_bytes(
        items=items,
        source_url="https://example.com/test-page",
        page_title="WebSift Export Test",
    )

    # Must start with UTF-8 BOM
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert filename.startswith("websift_example_com_")
    assert filename.endswith(".csv")

    # Decode and parse with Python standard csv reader
    text_content = csv_bytes.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text_content)))

    # Check header
    header = reader[0]
    assert header == [
        "source_url",
        "page_title",
        "content_type",
        "heading",
        "text_content",
        "sequence_number",
        "extracted_at",
    ]

    # Check rows count (header + 4 items = 5 rows)
    assert len(reader) == 5

    # Check formula injection was escaped in row 3
    formula_row = reader[3]
    assert formula_row[4] == "'=SUM(A1:A10)"

    # Check quotes and commas row
    quotes_row = reader[2]
    assert 'A complex text with "double quotes", commas, and\nnewline characters.' in quotes_row[4]

    # Check Unicode row
    unicode_row = reader[4]
    assert "東京 (Tokyo)" in unicode_row[4]
    assert "🚀" in unicode_row[4]


def test_txt_generation():
    items = make_sample_items()
    txt_bytes, filename = generate_txt_bytes(
        items=items,
        source_url="https://example.com/test-page",
        page_title="WebSift Export Test",
        mode="main",
    )

    assert filename.startswith("websift_example_com_")
    assert filename.endswith(".txt")

    content = txt_bytes.decode("utf-8")
    assert "WEBSIFT — EXTRACTED CONTENT REPORT" in content
    assert "Page Title   : WebSift Export Test" in content
    assert "Source URL   : https://example.com/test-page" in content
    assert "Total Blocks : 4" in content
    assert "東京 (Tokyo)" in content
    assert "🚀 Rocket" in content
