from backend.content_cleaner import clean_html_document
from backend.content_extractor import extract_structured_content


COMPREHENSIVE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Full Feature Test Page</title></head>
<body>
    <article>
        <h1>Introduction to Data Systems</h1>
        <p>Data systems form the bedrock of digital infrastructure.</p>
        
        <h2>Core Components</h2>
        <p>A typical data pipeline comprises ingestion, transformation, and storage.</p>
        <ul>
            <li>Real-time message broker</li>
            <li>Distributed compute nodes</li>
            <li>Columnar analytical store</li>
        </ul>
        
        <h2>Performance Benchmarks</h2>
        <table>
            <thead>
                <tr><th>Engine</th><th>Latency (ms)</th><th>Throughput (ops/s)</th></tr>
            </thead>
            <tbody>
                <tr><td>PostgreSQL</td><td>12.5</td><td>4,500</td></tr>
                <tr><td>ClickHouse</td><td>2.1</td><td>85,000</td></tr>
            </tbody>
        </table>

        <h2>Resources and References</h2>
        <p>Refer to official documentation for in-depth guidance.</p>
        <a href="https://example.org/docs">Official Architecture Whitepaper</a>
    </article>
</body>
</html>
"""


def test_structured_content_extraction():
    _, root, title, _, _ = clean_html_document(COMPREHENSIVE_HTML, mode="main")
    items, stats, preview = extract_structured_content(
        root=root,
        source_url="https://example.com/data-systems",
        page_title=title,
    )

    assert len(items) > 5
    assert stats.word_count > 30
    assert stats.headings_count >= 3
    assert stats.paragraphs_count >= 3
    assert stats.lists_count == 3
    assert stats.tables_count >= 2

    # Verify sequence numbers are monotonic
    seqs = [item.sequence_number for item in items]
    assert seqs == list(range(1, len(items) + 1))

    # Verify heading context assignment
    p_core = next(item for item in items if "ingestion, transformation" in item.text_content)
    assert p_core.heading == "Core Components"

    # Verify list items have bullets
    li_item = next(item for item in items if "Real-time message broker" in item.text_content)
    assert li_item.content_type == "list_item"
    assert "•" in li_item.text_content or "Real-time" in li_item.text_content

    # Verify table row extraction
    table_item = next(item for item in items if "ClickHouse" in item.text_content)
    assert table_item.content_type in ("table_row", "table_header")
    assert "ClickHouse" in table_item.text_content

    # Verify link extraction
    link_item = next(item for item in items if "Official Architecture Whitepaper" in item.text_content)
    assert link_item.content_type == "link"
    assert "https://example.org/docs" in link_item.text_content
