from backend.content_cleaner import clean_html_document


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>WebSift Test Article</title>
    <meta name="description" content="This is a test document for WebSift extraction.">
    <style>body { font-family: sans-serif; } .ad { display: block; }</style>
    <script>console.log("ignore me");</script>
</head>
<body>
    <header>
        <nav><a href="/home">Home</a> <a href="/about">About</a></nav>
    </header>
    <div class="cookie-banner">Please accept all tracking cookies.</div>
    <div style="display: none;">Secret hidden text that should never appear.</div>
    <span aria-hidden="true">Hidden icon text</span>
    <p hidden>Hidden attribute paragraph.</p>
    
    <main>
        <article>
            <h1>Understanding Web Scraping</h1>
            <p>Web scraping is the process of extracting content from websites automatically.</p>
            <div class="ad-container">Buy our product now!</div>
            <figure>
                <img src="diagram.png" alt="Architecture Diagram">
                <figcaption>Figure 1: Architectural pipeline of WebSift scraper.</figcaption>
            </figure>
            <svg height="100" width="100"><circle cx="50" cy="50" r="40" /></svg>
            <canvas id="myCanvas"></canvas>
            <p>Modern scrapers handle both static documents and client-side applications.</p>
        </article>
    </main>
    <footer>
        <p>Copyright 2026 WebSift Corp.</p>
    </footer>
</body>
</html>
"""


def test_cleaner_excludes_unwanted_elements():
    soup, root, title, meta_desc, warnings = clean_html_document(SAMPLE_HTML, mode="main")

    assert title == "WebSift Test Article"
    assert meta_desc == "This is a test document for WebSift extraction."

    text = root.get_text()

    # Scripts, styles, and SVG/canvas should be completely gone
    assert "console.log" not in text
    assert "font-family" not in text
    assert "circle cx" not in text

    # Hidden elements should be gone
    assert "Secret hidden text" not in text
    assert "Hidden icon text" not in text
    assert "Hidden attribute paragraph" not in text

    # Clutter/cookie/ad should be gone
    assert "Please accept all tracking cookies" not in text
    assert "Buy our product now" not in text

    # Figcaption text should be PRESERVED even though img was removed
    assert "Figure 1: Architectural pipeline of WebSift scraper" in text

    # Main content should be preserved
    assert "Understanding Web Scraping" in text
    assert "Web scraping is the process of extracting" in text


def test_cleaner_modes():
    # In main content mode, header/nav and footer are excluded
    _, main_root, _, _, _ = clean_html_document(SAMPLE_HTML, mode="main")
    main_text = main_root.get_text()
    assert "Copyright 2026 WebSift Corp" not in main_text

    # In full page mode, header and footer are retained
    _, full_root, _, _, _ = clean_html_document(SAMPLE_HTML, mode="full")
    full_text = full_root.get_text()
    assert "Copyright 2026 WebSift Corp" in full_text
    assert "Understanding Web Scraping" in full_text
