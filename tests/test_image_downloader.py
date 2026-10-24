import asyncio
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from starlette.testclient import TestClient

from backend.image_downloader import (
    ImageDownloaderRunner,
    detect_image_extension,
    download_image_file,
    extract_direct_images_from_listing,
    extract_medicine_name_and_image,
    open_output_folder,
    resolve_unique_filename,
    sanitize_medicine_filename,
    start_image_download_job,
)
from backend.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Unit Tests: Sanitization, Extension, Conflict Resolution
# ---------------------------------------------------------------------------


def test_sanitize_medicine_filename():
    """Verifies that medicine names are properly sanitized according to Mode C examples."""
    assert sanitize_medicine_filename("Dolo 650") == "Dolo_650"
    assert sanitize_medicine_filename("Zincovit Tablet") == "Zincovit_Tablet"
    assert sanitize_medicine_filename("Augmentin 625") == "Augmentin_625"
    assert sanitize_medicine_filename("Plamumab 40mg Injection (0.8ml Each)") == "Plamumab_40mg_Injection_0.8ml_Each"
    assert sanitize_medicine_filename("Pan-D / Capsule * [15's] <Special>?") == "Pan_D_Capsule_15_s_Special"
    assert sanitize_medicine_filename("   ...Candid-B Cream...   ") == "Candid_B_Cream"
    assert sanitize_medicine_filename("") == "medicine_product"
    assert sanitize_medicine_filename("   ") == "medicine_product"
    assert sanitize_medicine_filename(":::***???") == "medicine_product"


def test_detect_image_extension():
    """Verifies image extension detection from URLs, headers, and query parameters."""
    assert detect_image_extension("https://cdn.example.com/item.webp") == ".webp"
    assert detect_image_extension("https://cdn.example.com/item.png") == ".png"
    assert detect_image_extension("https://cdn.example.com/item.jpeg") == ".jpg"
    assert detect_image_extension("https://cdn.example.com/item.jpg") == ".jpg"
    assert detect_image_extension("https://cdn.example.com/item.avif") == ".avif"
    
    # Content-type header overrides or determines extension
    assert detect_image_extension("https://cdn.example.com/img?format=auto", content_type="image/webp") == ".webp"
    assert detect_image_extension("https://cdn.example.com/img?format=auto", content_type="image/png") == ".png"
    assert detect_image_extension("https://cdn.example.com/img?format=auto", content_type="image/jpeg; charset=utf-8") == ".jpg"
    
    # Query parameter format
    assert detect_image_extension("https://cdn.example.com/img?format=webp") == ".webp"
    assert detect_image_extension("https://cdn.example.com/img?f_png=1") == ".png"

    # Default fallback
    assert detect_image_extension("https://cdn.example.com/img_blob_unknown") == ".jpg"


def test_resolve_unique_filename(tmp_path):
    """
    Verifies that multiple products with the same medicine name do not overwrite each other,
    and identical product URLs reuse their existing destination file.
    """
    output_dir = tmp_path / "medicine_images"
    output_dir.mkdir(parents=True, exist_ok=True)
    known = {}

    url1 = "https://www.1mg.com/drugs/dolo-650-tablet-41565"
    url2 = "https://www.1mg.com/drugs/dolo-650-generic-98765"
    url3 = "https://www.1mg.com/drugs/dolo-650-alt-no-id"

    # Product 1 gets default sanitized name
    path1 = resolve_unique_filename(output_dir, "Dolo_650", ".webp", url1, known)
    assert path1.name == "Dolo_650.webp"
    # Create the file on disk to simulate successful download
    path1.write_bytes(b"dummy image 1")
    known[url1] = str(path1)

    # Calling again with Product 1 returns the SAME path (preserves duplicate check)
    path1_again = resolve_unique_filename(output_dir, "Dolo_650", ".webp", url1, known)
    assert path1_again == path1

    # Product 2 has SAME name but DIFFERENT product ID slug (98765)
    path2 = resolve_unique_filename(output_dir, "Dolo_650", ".webp", url2, known)
    assert path2.name == "Dolo_650_98765.webp"
    path2.write_bytes(b"dummy image 2")
    known[url2] = str(path2)

    # Product 3 has SAME name, no numeric slug ID -> uses numeric suffix _1
    path3 = resolve_unique_filename(output_dir, "Dolo_650", ".webp", url3, known)
    assert path3.name == "Dolo_650_1.webp"


# ---------------------------------------------------------------------------
# HTML Extraction & Heuristic Tests
# ---------------------------------------------------------------------------

MOCK_PRODUCT_PAGE_SKU_HTML = """
<!DOCTYPE html>
<html>
<head><title>Augmentin 625 Duo Tablet | 1mg</title></head>
<body>
    <h1>Augmentin 625 Duo Tablet</h1>
    <div class="gallery">
        <img class="SkuImages-module__image___NCdK8" src="https://onemg.gumlet.io/cropped/augmentin_625.png" alt="Augmentin 625">
    </div>
</body>
</html>
"""

MOCK_PRODUCT_PAGE_JSONLD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Zincovit Tablet: Uses, Price, Benefits | 1mg</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Zincovit Tablet",
        "image": "https://res.cloudinary.com/pharmacy/image/upload/zincovit_tablet.jpg"
    }
    </script>
</head>
<body>
    <h1>Zincovit Tablet</h1>
</body>
</html>
"""

MOCK_LISTING_WITH_CARDS_HTML = """
<!DOCTYPE html>
<html>
<body>
    <div class="product-card">
        <a href="/drugs/dolo-650-41565">
            <img src="https://cdn.example.com/dolo_650.webp" alt="Dolo 650">
            <h3>Dolo 650</h3>
        </a>
    </div>
    <div class="product-card">
        <a href="/drugs/zincovit-9999">
            <img src="https://cdn.example.com/zincovit.jpg" alt="Zincovit Tablet">
            <h3>Zincovit Tablet</h3>
        </a>
    </div>
</body>
</html>
"""


def test_extract_medicine_name_and_image():
    """Verifies extraction of medicine name and image across SkuImages and JSON-LD markup."""
    name1, img1 = extract_medicine_name_and_image(
        MOCK_PRODUCT_PAGE_SKU_HTML,
        "https://www.1mg.com/drugs/augmentin-625-duo-tablet-138629",
    )
    assert name1 == "Augmentin 625 Duo Tablet"
    assert img1 == "https://onemg.gumlet.io/cropped/augmentin_625.png"

    name2, img2 = extract_medicine_name_and_image(
        MOCK_PRODUCT_PAGE_JSONLD_HTML,
        "https://www.1mg.com/drugs/zincovit-tablet-12345",
    )
    assert name2 == "Zincovit Tablet"
    assert img2 == "https://res.cloudinary.com/pharmacy/image/upload/zincovit_tablet.jpg"


def test_extract_direct_images_from_listing():
    """Verifies that direct image cards on rich listing pages are recognized."""
    items = extract_direct_images_from_listing(
        MOCK_LISTING_WITH_CARDS_HTML,
        "https://example.com/pharmacy",
    )
    assert len(items) == 2
    assert items[0]["name"] == "Dolo 650"
    assert items[0]["image_url"] == "https://cdn.example.com/dolo_650.webp"
    assert items[1]["name"] == "Zincovit Tablet"
    assert items[1]["image_url"] == "https://cdn.example.com/zincovit.jpg"


# ---------------------------------------------------------------------------
# Streaming Download & Duplicate Handling
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_download_image_file_incremental(tmp_path):
    """Verifies that download_image_file streams chunks to disk safely."""
    dest = tmp_path / "output" / "medicine_images" / "test_med.png"
    fake_png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048

    class MockAsyncTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(200, content=fake_png_bytes, request=request)

    async with httpx.AsyncClient(transport=MockAsyncTransport()) as client:
        success, size, err = await download_image_file(client, "https://example.com/image.png", dest)

    assert success is True
    assert size == len(fake_png_bytes)
    assert err is None
    assert dest.exists()
    assert dest.stat().st_size == len(fake_png_bytes)
    # Ensure temporary file is cleanly removed
    assert not dest.with_suffix(".png.tmp").exists()


@pytest.mark.anyio
async def test_download_image_file_handles_failure(tmp_path):
    """Verifies that download failures (e.g. 404) return clean error status without crashing."""
    dest = tmp_path / "output" / "medicine_images" / "missing.jpg"

    class MockAsyncTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(404, request=request)

    async with httpx.AsyncClient(transport=MockAsyncTransport()) as client:
        success, size, err = await download_image_file(client, "https://example.com/missing.jpg", dest)

    assert success is False
    assert size == 0
    assert "404" in str(err)
    assert not dest.exists()


# ---------------------------------------------------------------------------
# End-to-End Runner Workflow: Multi-Page Traversal and Image Archival
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_image_downloader_runner_full_workflow(tmp_path):
    """
    Mode C End-to-End Verification:
    - Page 1: contains 2 medicine links + Next button.
    - Page 2: contains 1 medicine link, disabled Next button (last page).
    - Downloads all 3 images with sanitized medicine names directly into output/medicine_images/.
    - Verifies duplicate download avoidance when run a second time.
    """
    output_dir = tmp_path / "output" / "medicine_images"

    page_1_html = """
    <html>
    <body>
        <div class="drug-item"><a href="/drugs/dolo-650-tablet-41565">Dolo 650</a></div>
        <div class="drug-item"><a href="/drugs/zincovit-tablet-12345">Zincovit Tablet</a></div>
        <div class="pagination">
            <a class="active" href="/drugs-all-medicines?page=1&label=d">1</a>
            <a class="next" href="/drugs-all-medicines?page=2&label=d">Next</a>
        </div>
    </body>
    </html>
    """

    page_2_html = """
    <html>
    <body>
        <div class="drug-item"><a href="/drugs/augmentin-625-tablet-99999">Augmentin 625</a></div>
        <div class="pagination">
            <a class="active" href="/drugs-all-medicines?page=2&label=d">2</a>
            <button class="next disabled" disabled>Next</button>
        </div>
    </body>
    </html>
    """

    product_responses = {
        "https://www.1mg.com/drugs/dolo-650-tablet-41565": """
            <html><body><h1>Dolo 650</h1><img class="SkuImages-module__image" src="https://cdn.example.com/dolo.webp"></body></html>
        """,
        "https://www.1mg.com/drugs/zincovit-tablet-12345": """
            <html><body><h1>Zincovit Tablet</h1><img class="SkuImages-module__image" src="https://cdn.example.com/zincovit.jpg"></body></html>
        """,
        "https://www.1mg.com/drugs/augmentin-625-tablet-99999": """
            <html><body><h1>Augmentin 625</h1><img class="SkuImages-module__image" src="https://cdn.example.com/augmentin.png"></body></html>
        """,
    }

    dummy_image_payload = b"RIFF\x24\x00\x00\x00WEBPVP8 "

    class MockAsyncTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            url_str = str(request.url)
            if "page=1" in url_str:
                return httpx.Response(200, text=page_1_html, request=request)
            elif "page=2" in url_str:
                return httpx.Response(200, text=page_2_html, request=request)
            elif url_str in product_responses:
                return httpx.Response(200, text=product_responses[url_str], request=request)
            elif any(u in url_str for u in ["dolo.webp", "zincovit.jpg", "augmentin.png"]):
                return httpx.Response(200, content=dummy_image_payload, request=request)
            return httpx.Response(404, request=request)

    mock_transport = MockAsyncTransport()
    original_client_cls = httpx.AsyncClient

    def make_client(**kwargs):
        kwargs["transport"] = mock_transport
        return original_client_cls(**kwargs)

    with patch("backend.fetcher.httpx.AsyncClient", side_effect=make_client), \
         patch("backend.image_downloader.httpx.AsyncClient", side_effect=make_client), \
         patch("backend.image_downloader.validate_and_sanitize_url", side_effect=lambda u: (u, "104.18.2.1")):

        runner = ImageDownloaderRunner(
            listing_url="https://www.1mg.com/drugs-all-medicines?page=1&label=d",
            output_dir=output_dir,
            delay_seconds=0.0,
        )
        await runner._run_job()

        assert runner.job_status == "completed"
        assert runner.pages_visited == 2
        assert runner.total_discovered == 3
        assert runner.images_downloaded == 3
        assert runner.images_failed == 0
        assert runner.images_skipped == 0

        # Verify exact filenames created in output directory
        assert (output_dir / "Dolo_650.webp").exists()
        assert (output_dir / "Zincovit_Tablet.jpg").exists()
        assert (output_dir / "Augmentin_625.png").exists()

        # Re-running the job should detect existing files and skip downloads
        runner2 = ImageDownloaderRunner(
            listing_url="https://www.1mg.com/drugs-all-medicines?page=1&label=d",
            output_dir=output_dir,
            delay_seconds=0.0,
        )
        await runner2._run_job()
        assert runner2.job_status == "completed"
        assert runner2.images_downloaded == 0
@pytest.mark.anyio
async def test_image_downloader_duplicate_names_in_same_crawl(tmp_path):
    """
    Verifies that when two distinct products share the exact same medicine name,
    Mode C prevents overwriting by appending a unique slug identifier or numeric suffix.
    """
    output_dir = tmp_path / "output" / "medicine_images"
    page_html = """
    <html>
    <body>
        <div class="drug-item"><a href="/drugs/paracetamol-500mg-tablet-1111">Paracetamol 500mg</a></div>
        <div class="drug-item"><a href="/drugs/paracetamol-500mg-tablet-2222">Paracetamol 500mg</a></div>
        <button class="next disabled" disabled>Next</button>
    </body>
    </html>
    """
    product_responses = {
        "https://www.1mg.com/drugs/paracetamol-500mg-tablet-1111": """
            <html><body><h1>Paracetamol 500mg</h1><img class="SkuImages-module__image" src="https://cdn.example.com/p1.jpg"></body></html>
        """,
        "https://www.1mg.com/drugs/paracetamol-500mg-tablet-2222": """
            <html><body><h1>Paracetamol 500mg</h1><img class="SkuImages-module__image" src="https://cdn.example.com/p2.jpg"></body></html>
        """,
    }

    class MockAsyncTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            url_str = str(request.url)
            if "label=p" in url_str:
                return httpx.Response(200, text=page_html, request=request)
            elif url_str in product_responses:
                return httpx.Response(200, text=product_responses[url_str], request=request)
            elif "p1.jpg" in url_str:
                return httpx.Response(200, content=b"IMAGE_CONTENT_1", request=request)
            elif "p2.jpg" in url_str:
                return httpx.Response(200, content=b"IMAGE_CONTENT_2", request=request)
            return httpx.Response(404, request=request)

    mock_transport = MockAsyncTransport()
    original_client_cls = httpx.AsyncClient

    def make_client(**kwargs):
        kwargs["transport"] = mock_transport
        return original_client_cls(**kwargs)

    with patch("backend.fetcher.httpx.AsyncClient", side_effect=make_client), \
         patch("backend.image_downloader.httpx.AsyncClient", side_effect=make_client), \
         patch("backend.image_downloader.validate_and_sanitize_url", side_effect=lambda u: (u, "104.18.2.1")):

        runner = ImageDownloaderRunner(
            listing_url="https://www.1mg.com/drugs-all-medicines?label=p",
            output_dir=output_dir,
            max_pages=1,
            delay_seconds=0.0,
        )
        await runner._run_job()

        assert runner.job_status == "completed"
        assert runner.images_downloaded == 2
        assert runner.images_failed == 0

        # Verify that two distinct files exist and neither overwrote the other
        file1 = output_dir / "Paracetamol_500mg.jpg"
        file2 = output_dir / "Paracetamol_500mg_2222.jpg"
        assert file1.exists()
        assert file2.exists()
        assert file1.read_bytes() == b"IMAGE_CONTENT_1"
        assert file2.read_bytes() == b"IMAGE_CONTENT_2"


# ---------------------------------------------------------------------------
# API Route Endpoint Tests
# ---------------------------------------------------------------------------


def test_api_mode_c_endpoints(tmp_path):
    """Tests Mode C FastAPI endpoints: start, status, stop, open folder, storage status."""
    # 1. Start Image Job
    resp = client.post(
        "/api/images/start",
        json={
            "listing_url": "https://www.1mg.com/drugs-all-medicines?label=p",
            "max_pages": 1,
            "max_images": 2,
            "delay_seconds": 0.0,
        },
    )
    assert resp.status_code == 200
    job_data = resp.json()
    job_id = job_data["job_id"]
    assert job_id.startswith("img_job_")
    assert job_data["job_status"] in ("pending", "running", "completed")

    # 2. Get Job Status
    status_resp = client.get(f"/api/images/job/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["job_id"] == job_id

    # 3. Stop Job
    stop_resp = client.post(f"/api/images/job/{job_id}/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["job_status"] in ("stopped", "completed")

    # 4. Storage Status
    storage_resp = client.get("/api/images/status")
    assert storage_resp.status_code == 200
    assert "total_images" in storage_resp.json()
    assert "folder_path" in storage_resp.json()

    # 5. Open Folder
    folder_resp = client.post(
        "/api/images/open-folder",
        json={"folder_path": str(tmp_path)},
    )
    assert folder_resp.status_code == 200
    assert folder_resp.json()["success"] is True
