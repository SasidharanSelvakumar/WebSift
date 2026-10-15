import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.browser_renderer import BrowserRenderError, render_with_browser
from backend.content_cleaner import clean_html_document
from backend.content_extractor import extract_structured_content
from backend.excel_service import generate_medicine_excel_workbook
from backend.export_service import (
    generate_csv_bytes,
    generate_medicine_csv_bytes,
    generate_medicine_txt_bytes,
    generate_txt_bytes,
)
from backend.fetcher import ContentTooLargeError, FetchError, fetch_html
from backend.medicine_extractor import extract_medicine_batch_from_html
from backend.medicine_models import (
    ExcelExportRequest,
    MedicineCsvExportRequest,
    MedicineTxtExportRequest,
    SpreadsheetPushRequest,
    SpreadsheetPushResponse,
)
from backend.models import (
    ExportRequest,
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
)
from backend.spreadsheet_service import (
    get_default_destinations,
    get_spreadsheet_provider,
)
from backend.url_validator import SSRFProtectionError, validate_and_sanitize_url

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("websift.api")

app = FastAPI(
    title="WebSift API",
    description="Intelligent Web Scraping & Structured Content Export Engine",
    version="1.0.0",
)

# Enable CORS for local Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint returning engine status and capabilities.
    """
    playwright_ready = True
    try:
        import playwright
    except ImportError:
        playwright_ready = False

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        playwright_available=playwright_ready,
    )


@app.post("/api/extract", response_model=ExtractResponse)
async def extract_content(req: ExtractRequest):
    """
    Extracts meaningful textual content from a user-provided webpage URL.
    Enforces SSRF controls, strips irrelevant visual elements, and structures records.
    """
    start_time = time.perf_counter()
    raw_url = str(req.url)

    # 1. URL and SSRF Validation
    try:
        sanitized_url, _ = validate_and_sanitize_url(raw_url)
    except SSRFProtectionError as e:
        logger.warning(f"Blocked unsafe target URL: {raw_url} - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Security Restriction: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}",
        )

    # 2. Fetch or Render Webpage
    engine_used = "HTTP Parser"
    html_content = ""
    final_url = sanitized_url
    warnings = []

    if req.force_browser:
        logger.info(f"Rendering {sanitized_url} with Playwright headless browser (forced)")
        try:
            html_content, final_url = await render_with_browser(sanitized_url)
            engine_used = "Playwright Browser"
        except BrowserRenderError as e:
            logger.warning(f"Browser rendering failed, falling back to HTTP: {str(e)}")
            warnings.append(f"Headless browser error: {str(e)}. Attempted HTTP fetch fallback.")
            try:
                html_content, final_url, _ = await fetch_html(sanitized_url)
            except Exception as fe:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(fe))
    else:
        # Standard fast HTTP fetch
        try:
            html_content, final_url, needs_browser = await fetch_html(sanitized_url)
            if needs_browser:
                logger.info(f"Page appears dynamic/SPA. Rendering with headless browser: {sanitized_url}")
                try:
                    html_content, final_url = await render_with_browser(sanitized_url)
                    engine_used = "Playwright Browser"
                except Exception as be:
                    logger.warning(f"Browser fallback failed: {str(be)}")
                    warnings.append("Dynamic page rendering had issues; parsed static HTML fallback.")
        except ContentTooLargeError as e:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=str(e),
            )
        except FetchError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch destination: {str(e)}",
            )
        except SSRFProtectionError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Security Restriction during redirect: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Unexpected fetch error for {sanitized_url}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An internal error occurred while retrieving the web page.",
            )

    # 3. Clean Content
    try:
        soup, target_root, title, meta_desc, clean_warnings = clean_html_document(
            html_content, mode=req.mode
        )
        warnings.extend(clean_warnings)
    except Exception as e:
        logger.error(f"HTML cleaning failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Failed to parse webpage content.",
        )

    # 4. Extract Structured Content Blocks
    extracted_at = datetime.now(timezone.utc).isoformat()
    try:
        items, stats, preview = extract_structured_content(
            root=target_root,
            source_url=final_url,
            page_title=title,
            extracted_at=extracted_at,
        )
    except Exception as e:
        logger.error(f"Content extraction error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to extract structured text: {str(e)}",
        )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    stats.duration_ms = duration_ms

    if not items or stats.word_count == 0:
        warnings.append("No accessible textual content could be extracted from this page.")

    # 5. Extract Dynamic Medicine Batch
    medicine_batch = None
    try:
        medicine_batch = extract_medicine_batch_from_html(
            raw_html=html_content,
            source_url=final_url,
            page_title=title,
            extracted_at=extracted_at,
        )
    except Exception as me:
        logger.warning(f"Medicine batch extraction note: {str(me)}")

    return ExtractResponse(
        success=True,
        source_url=final_url,
        page_title=title,
        meta_description=meta_desc,
        mode=req.mode,
        engine_used=engine_used,
        stats=stats,
        items=items,
        full_text_preview=preview,
        warnings=warnings,
        extracted_at=extracted_at,
        medicine_batch=medicine_batch,
    )


@app.post("/api/export/csv")
async def export_csv(req: ExportRequest):
    """
    Generates and returns an RFC-4180 compliant CSV file encoded in UTF-8 with BOM.
    Contains all extracted textual content with preserved reading order.
    """
    if not req.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extracted items provided for export.",
        )

    try:
        csv_bytes, filename = generate_csv_bytes(
            items=req.items,
            source_url=req.source_url,
            page_title=req.page_title,
        )

        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(csv_bytes)),
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as e:
        logger.error(f"CSV export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate CSV file.",
        )


@app.post("/api/export/txt")
async def export_txt(req: ExportRequest):
    """
    Generates and returns a clean, structured plain text file in original reading order.
    """
    if not req.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extracted items provided for export.",
        )

    try:
        txt_bytes, filename = generate_txt_bytes(
            items=req.items,
            source_url=req.source_url,
            page_title=req.page_title,
            mode=req.mode or "main",
        )

        return Response(
            content=txt_bytes,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(txt_bytes)),
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as e:
        logger.error(f"TXT export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate TXT file.",
        )


@app.post("/api/export/excel")
async def export_excel(req: ExcelExportRequest):
    """
    Generates and returns an authentic Excel (.xlsx) file with dynamic columns,
    styled frozen headers, autofilters, and cell wrapping.
    """
    if not req.batch or not req.batch.records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No medicine records provided for Excel export.",
        )

    try:
        xlsx_bytes, filename = generate_medicine_excel_workbook(
            batch=req.batch,
            source_url=req.source_url or "medicine_data",
        )

        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(xlsx_bytes)),
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as e:
        logger.error(f"Excel export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate Excel workbook.",
        )


@app.post("/api/export/medicine-csv")
async def export_medicine_csv(req: MedicineCsvExportRequest):
    """
    Generates and returns an RFC-4180 CSV file with dynamic columns for medicine records.
    """
    if not req.batch or not req.batch.records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No medicine records provided for CSV export.",
        )

    try:
        csv_bytes, filename = generate_medicine_csv_bytes(
            batch=req.batch,
            source_url=req.source_url or "medicine_data",
        )

        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(csv_bytes)),
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as e:
        logger.error(f"Medicine CSV export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate medicine CSV file.",
        )


@app.post("/api/export/medicine-txt")
async def export_medicine_txt(req: MedicineTxtExportRequest):
    """
    Generates structured, human-readable plain text cards for each medicine record.
    """
    if not req.batch or not req.batch.records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No medicine records provided for TXT export.",
        )

    try:
        txt_bytes, filename = generate_medicine_txt_bytes(
            batch=req.batch,
            source_url=req.source_url or "medicine_data",
        )

        return Response(
            content=txt_bytes,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(txt_bytes)),
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as e:
        logger.error(f"Medicine TXT export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate medicine TXT file.",
        )


@app.get("/api/spreadsheet/destinations")
async def get_spreadsheet_destinations():
    """
    Returns available spreadsheet destinations (local database file and cloud providers).
    """
    return get_default_destinations()


@app.post("/api/spreadsheet/push", response_model=SpreadsheetPushResponse)
async def push_to_spreadsheet(req: SpreadsheetPushRequest):
    """
    Non-destructively pushes medicine records into an existing local or cloud spreadsheet.
    Discovers columns, adds missing attributes, preserves historical rows, and prevents duplicates.
    """
    if not req.batch or not req.batch.records:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No medicine records provided to push into spreadsheet.",
        )

    try:
        provider = get_spreadsheet_provider(req.destination_type)
        return await provider.push_batch(req)
    except Exception as e:
        logger.error(f"Spreadsheet push error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Spreadsheet integration error: {str(e)}",
        )



# Serve frontend if static dist folder exists
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
