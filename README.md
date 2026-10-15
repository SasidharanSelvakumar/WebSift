# WebSift — Precision Web Scraping, Dynamic Medicine Data Extraction & Spreadsheet Integration

WebSift is a high-performance, security-hardened web scraping, dynamic medicine data extraction, and spreadsheet integration platform. It extracts structured textual content and arbitrary, unpredictable medicine attributes from user-provided URLs and provides instant downloads as genuine **Excel (.xlsx)** workbooks, RFC-4180 **CSV** files (with UTF-8 BOM), and structured **TXT** files, as well as direct non-destructive **push integration** to existing spreadsheets.

---

## 🌟 Key Features

### 1. Dynamic Medicine Data Extraction & Schema Discovery
- **No Rigid Medicine Schema**: Medicines exhibit unpredictable sets of attributes. WebSift captures arbitrary key-value pairs (e.g. Composition, Strength, Dosage Form, Uses, How to Use, Side Effects, Storage Instructions, Warnings, Interactions, Manufacturer vs. Marketer, Pack Size, Price, Prescription Requirements).
- **Batch Field Union**: Computes the union of all discovered fields across the entire extraction batch before export, ensuring no attribute is dropped.
- **Conservative Field Normalization**: Normalizes whitespace, casing, and verified aliases (e.g., `MRP` -> `Price`, `Composition` -> `Active Ingredients`), while strictly keeping distinct attributes separate (e.g., `Manufacturer` vs. `Marketed By`, different price types).
- **Variant Preservation**: Distinct packaging formats, strengths, and pack sizes are extracted as distinct records with preserved relationships.

### 2. Genuine Excel Workbook Export (.xlsx)
- Built with Python's `openpyxl` engine.
- Worksheet strictly named **`Medicine Data`**.
- Dynamic headers dynamically ordered with `Medicine Name` first, standard priority attributes, dynamic unmapped columns, and source metadata.
- **Header formatting**: Segoe UI bold white text on `#1E293B` background.
- **Freeze Panes**: Frozen header row at `A2` for seamless vertical scrolling.
- **Auto-Filter**: Enabled across the entire data range `A1:{last_col}{max_row}`.
- **Auto-Fit Column Widths**: Automatically padded to content width with min (14) and max (65) boundaries.
- **Formula Injection Defense**: Neutralizes leading `=`, `+`, `-`, `@` characters.

### 3. Non-Destructive Spreadsheet Push Integration
- **Existing Schema Adaptation**: Reads existing column headers from destination spreadsheets. Reuses matching columns and appends missing columns for newly discovered attributes.
- **Row Preservation**: Appends new medicine records without overwriting historical rows.
- **Duplicate Prevention**: Configurable deduplication using composite keys (`source_url|medicine_name|strength`) or record identifiers. Prevents accidental duplicates on retries.
- **Local & Cloud Architecture**: Built-in support for local workbooks (`medicines_database.xlsx`) and provider-agnostic cloud integrations (Google Sheets API architecture).

### 4. Dynamic CSV & Structured TXT Exports
- **Dynamic CSV**: Emits all discovered batch columns with UTF-8 BOM (`\xef\xbb\xbf`) and RFC-4180 escaping.
- **Dynamic TXT**: Generates human-readable medicine cards containing every discovered attribute in logical reading order.

### 5. Dual Scraping Engine & Security Guards
- **Fast Async HTTP Client (`httpx`)**: Automatic charset detection, stream size caps (10MB).
- **Headless Browser Fallback (`Playwright Chromium`)**: Renders client-side dynamic JavaScript Single Page Applications (SPAs).
- **Comprehensive SSRF Protection**: Blocks loopback (`127.0.0.0/8`, `::1`), private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), cloud metadata (`169.254.169.254`), and per-hop redirect verification.

---

## 🏗️ Architecture & Modules

The platform is designed with single-responsibility modular services:

| Component | File | Responsibility |
|---|---|---|
| **Medicine Data Models** | [`backend/medicine_models.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/medicine_models.py) | Flexible Pydantic schemas for `MedicineRecord`, `MedicineBatch`, and export/push requests |
| **Field Normalizer** | [`backend/field_normalizer.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/field_normalizer.py) | Conservative alias mapping, label sanitation, and batch field union calculations |
| **Medicine Extractor** | [`backend/medicine_extractor.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/medicine_extractor.py) | JSON-LD schema objects, DOM key-value tables, heading sections, dosage/strength parsing |
| **Excel Service** | [`backend/excel_service.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/excel_service.py) | `openpyxl` workbook generator, non-destructive schema adaptation, and safe Excel appending |
| **Spreadsheet Service** | [`backend/spreadsheet_service.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/spreadsheet_service.py) | Destination manager, Local Excel provider, Google Sheets API provider interface |
| **Content Extractor** | [`backend/content_extractor.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/content_extractor.py) | Text extraction, modern leaf container handling (How to Use, Benefits, Works) |
| **Export Service** | [`backend/export_service.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/export_service.py) | Dynamic CSV with UTF-8 BOM, plain text cards, formula escaping |
| **URL Validator** | [`backend/url_validator.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/url_validator.py) | DNS resolution and SSRF filtering for loopback, private IPs, and cloud metadata |
| **HTTP Fetcher** | [`backend/fetcher.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/fetcher.py) | Async HTTP client, redirect validation, and SPA detection |
| **Browser Renderer** | [`backend/browser_renderer.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/browser_renderer.py) | Playwright Chromium automation with media interception for JS pages |
| **Main API** | [`backend/main.py`](file:///c:/Users/SasidharanS/Desktop/Desktop/Web%20scrap/backend/main.py) | FastAPI application, CORS, static frontend mounting, and routing |

---

## 🚀 Quickstart & Execution

### 1. Requirements
- Python 3.10+ (tested on Python 3.15)
- Node.js LTS (v20+ recommended)

### 2. Install Dependencies

**Backend:**
```bash
pip install fastapi uvicorn httpx beautifulsoup4 pydantic pytest playwright openpyxl
playwright install chromium
```

**Frontend:**
```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Start the Server

Run the unified server (FastAPI serves both API and compiled React frontend):
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open your browser to:
👉 **`http://127.0.0.1:8000/`**

---

## 📡 API Endpoints

### 1. `GET /api/health`
Checks backend engine status and Playwright readiness.

### 2. `POST /api/extract`
Scrapes the specified URL, extracts both structured text blocks and flexible `medicine_batch` records.
- **Request Body**:
  ```json
  {
    "url": "https://www.1mg.com/drugs/actorise-40-injection-227647",
    "mode": "main",
    "force_browser": false
  }
  ```

### 3. `POST /api/export/excel`
Generates and downloads a genuine Excel workbook with dynamic headers and filters.
- **Request Body**:
  ```json
  {
    "batch": { ... },
    "source_url": "https://www.1mg.com/drugs/actorise-40-injection-227647"
  }
  ```
- **Returns**: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

### 4. `POST /api/export/medicine-csv`
Downloads dynamic medicine CSV with UTF-8 BOM (`\xef\xbb\xbf`).

### 5. `POST /api/export/medicine-txt`
Downloads structured medicine plain text cards.

### 6. `GET /api/spreadsheet/destinations`
Returns list of available destination spreadsheets and tabs.

### 7. `POST /api/spreadsheet/push`
Safely adapts destination schema, appends new columns, and appends records without overwriting historical rows.
- **Request Body**:
  ```json
  {
    "batch": { ... },
    "destination_type": "local_excel",
    "target_file_path": "medicines_database.xlsx",
    "worksheet_name": "Medicine Data",
    "prevent_duplicates": true
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "status": "success",
    "destination": "medicines_database.xlsx",
    "total_records": 1,
    "inserted_records": 1,
    "skipped_records": 0,
    "failed_records": 0,
    "newly_created_columns": ["Brand", "Pediatric Dosage"],
    "existing_columns": ["Medicine Name", "Price"],
    "final_columns": ["Medicine Name", "Price", "Brand", "Pediatric Dosage"]
  }
  ```

---

## 🧪 Automated Test Suite

WebSift includes 29 comprehensive automated tests across the entire extraction, normalization, export, and spreadsheet pipelines.

To run the automated tests:
```bash
python -m pytest tests/ -v
```

### Test Coverage Highlights:
- **`tests/test_medicine_schema.py`**: Flexible medicine models, dynamic field union, conservative alias normalization, Manufacturer vs. Marketer separation, and variant extraction.
- **`tests/test_excel_service.py`**: Valid `.xlsx` workbook structure, bold styled headers, frozen pane (`A2`), auto-filter range, and formula injection sanitization.
- **`tests/test_spreadsheet_cloud.py`**: Non-destructive spreadsheet adaptation, new column appending, row preservation, duplicate prevention, and provider interface.
- **`tests/test_validator.py`**: SSRF filtering, loopbacks, private RFC 1918 subnets, cloud metadata, and invalid schemes.
- **`tests/test_cleaner.py`**: DOM sanitation, image/SVG/script removal, hidden elements exclusion.
- **`tests/test_extractor.py`**: Structured text blocks, heading hierarchy context, reading order sequencing.
- **`tests/test_export.py`**: RFC-4180 CSV, UTF-8 BOM, plain text card exports.
- **`tests/test_api.py`**: Complete FastAPI endpoint tests including extract, Excel export, dynamic CSV/TXT, destination listing, and spreadsheet push.
