# WebSift — Precision Web Scraping & Category-Wide Dataset Engine

WebSift is a high-performance web scraping and product data extraction platform designed for pharmacy websites and dynamic e-commerce catalogs. It extracts unstructured web content and dynamic specifications into a persistent SQLite database, generating standardized Master Excel (`.xlsx`), RFC-4180 CSV (with UTF-8 BOM), and TXT datasets.

---

## 🌟 Scraping Modes

### Mode A: Single Product Scraping
- Scrapes any individual product detail page via fast HTTP or headless Playwright Chromium.
- Extracts both core attributes (Composition, Strength, Dosage Form, Manufacturer, Marketer, MRP, Price, Prescription Requirements) and dynamic clinical specs (Uses, Side Effects, How to Use, Storage, Warnings).
- Supports instant downloads (Excel, CSV, TXT) and non-destructive appending to local or cloud spreadsheets.

### Mode B: Category & Alphabet-Wide Crawling
- **Single Starting URL**: Initiates full crawls from a single category or alphabet listing URL (e.g., `https://www.1mg.com/drugs-all-medicines?page=1&label=p`).
- **Alphabet Scope Isolation**: Automatically locks and preserves query parameters (such as `label=p`), ensuring crawls never unintentionally drift into other alphabets or sections.
- **Multi-Strategy Pagination**: Traverses pagination via standard HTML `rel="next"`, Next-page button heuristics, and an intelligent sequential fallback (`page=N+1`) when DOM controls are absent or unlinked.
- **Genuine Endpoint Discovery**: Detects true catalog endpoints through disabled pagination buttons, empty listing pages, or HTTP 404/410 status codes without imposing arbitrary page caps.
- **Fault-Tolerant Traversal**: Transient listing page failures are logged and bypassed using sequential fallback (up to 3 consecutive attempts) without aborting the entire job.
- **SQLite Persistence & Deduplication**: Discovered products are immediately queued into SQLite. Interrupted jobs resume from the highest completed page without re-fetching page 1, and duplicate URLs across pages are skipped.
- **Job Status Integrity**: Jobs are kept as `incomplete` if listing pages failed or products remain pending, ensuring runs are only marked `completed` once all data is verified.

---

## 📊 Master Dataset Export

WebSift consolidates records into clean, production-ready master export files:

1. **`WebSift_Master.xlsx`**:
   - **`Products` Sheet**: 21 standard columns:
     `Medicine Name` | `Brand` | `Active Ingredient / Composition` | `Strength` | `Dosage Form` | `Pack Size` | `Manufacturer` | `Marketer` | `Price` | `MRP` | `Availability` | `Prescription Required` | `Uses` | `Benefits` | `Side Effects` | `How to Use` | `How It Works` | `Storage Instructions` | `Product URL` | `Extracted At` | `Scrape Status`
   - **`Additional Specifications` Sheet**: Relational secondary sheet capturing unmapped clinical specifications (`Warnings`, `Interactions`, `Description`).
   - **Content-Aware Typography**: Auto-fitted column widths, text wrapping on multiline sections, dark frozen header row, autofilter enabled, and Indian Rupee (`₹`) symbol preservation.
2. **`WebSift_Master.csv`**: RFC-4180 compliant CSV encoded with UTF-8 BOM (`\xef\xbb\xbf`) for native Excel compatibility.
3. **`WebSift_Master.txt`**: Formatted structured text cards for readability and text processing.

---

## 🏗️ Architecture & Core Modules

| Module | File | Responsibility |
|---|---|---|
| **Category Scraper** | [`backend/category_scraper.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/category_scraper.py) | Background crawler orchestrator, listing pagination loop, product extraction loop, pause/resume/stop |
| **URL Crawler & Pagination** | [`backend/crawler.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/crawler.py) | Link discovery, scope preservation, pagination discovery, loop defense, and sequential fallback |
| **SQLite Persistence** | [`backend/database.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/database.py) | Thread-safe database manager for `products`, `scrape_jobs`, `job_products`, and `job_listing_pages` |
| **Master Dataset Exporter** | [`backend/master_export.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/master_export.py) | Generates `WebSift_Master.xlsx`, master CSV with BOM, and master TXT reports |
| **Excel Formatter** | [`backend/excel_formatter.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/excel_formatter.py) | Content-aware visual width measurement, dynamic row heights, and openpyxl styling |
| **Medicine Extractor** | [`backend/medicine_extractor.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/medicine_extractor.py) | Hybrid JSON-LD schema parser, DOM table extractor, company validation, and attribute normalization |
| **HTTP Fetcher & Browser** | [`backend/fetcher.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/fetcher.py) / [`browser_renderer.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/browser_renderer.py) | Async HTTP client with SSRF protection and Playwright Chromium headless fallback |
| **Main API Engine** | [`backend/main.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/main.py) | FastAPI application serving REST endpoints and hosting the compiled React dashboard |

---

## 🗄️ Database Schema (`data/websift.db`)

SQLite (WAL mode enabled) serves as the persistent data store across restarts:

- **`products`**: Canonical product URL (PRIMARY KEY), title, normalized core columns (`brand`, `manufacturer`, `marketer`, `price`, `strength`, `dosage_form`, `active_ingredients`, `drug_schedule`, `pack_quantity`, `tags`, `safety_advice`), raw labels, and full JSON specifications.
- **`scrape_jobs`**: Job status (`running`, `paused`, `completed`, `incomplete`, `stopped`), listing traversal status, visited counts, discovered counts, error messages, and configuration.
- **`job_products`**: Product progress tracker per job (`pending`, `completed`, `failed`, `skipped`), attempt counts, and error logs.
- **`job_listing_pages`**: Page URLs traversed per job with status (`completed`, `failed`, `pending`) to prevent duplicate crawling and enable instant resumption.

---

## 🚀 Quickstart & Setup

### 1. Requirements
- Python 3.10+
- Node.js LTS (v18+)

### 2. Installation

**Backend Dependencies:**
```bash
pip install fastapi uvicorn httpx beautifulsoup4 pydantic pytest playwright openpyxl
playwright install chromium
```

**Frontend Build:**
```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Launch WebSift
Start the application launcher:
```bash
python run.py
```
Or run directly via Uvicorn:
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open your browser to: **`http://127.0.0.1:8000/`**

---

## 📡 API Reference

### Category & Alphabet Crawling
- **`POST /api/category/start`**: Launch a background scraping job with optional `max_pages`, `max_products`, or `delay_seconds`.
- **`GET /api/category/job/{job_id}`**: Retrieve real-time progress metrics (pages visited, discovered, completed, failed, pending) and live ticker.
- **`POST /api/category/job/{job_id}/pause`**: Pause an active crawl.
- **`POST /api/category/job/{job_id}/resume`**: Resume an interrupted or paused crawl from its highest completed page.
- **`POST /api/category/job/{job_id}/stop`**: Terminate a crawl cleanly.
- **`POST /api/category/job/{job_id}/retry-failed`**: Reset failed listing pages and failed products to `pending` and resume processing.
- **`GET /api/category/export/{excel|csv|txt}?job_id={job_id}`**: Export master datasets for a specific job or all completed records.

### Single Product Scraping
- **`POST /api/extract`**: Extract structured data and specifications from an individual product URL.
- **`POST /api/export/{excel|csv|txt}`**: Download extracted single batch data.
- **`POST /api/spreadsheet/push`**: Push extracted batch into local or cloud spreadsheets.

---

## 🧪 Automated Testing

WebSift includes **93 automated tests** verifying crawling, schema validation, pagination fallback, and export formatting:

```bash
python -m pytest tests/ -v
```

Tests cover:
- Multi-page alphabet traversal past high page boundaries (pages 17, 20, 25+).
- Alphabet query parameter isolation and preservation (`label=p`).
- Fallback sequential pagination when Next button tags are missing from HTML.
- Fault tolerance and recovery from temporary listing page errors.
- SQLite state tracking, duplicate avoidance, and seamless resume without repeating page 1.
- RFC-4180 CSV with UTF-8 BOM, content-aware Excel styling, and single-product extraction endpoints.
