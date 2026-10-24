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
from backend.url_validator import SSRFProtectionError, validate_and_sanitize_url
from backend.category_scraper import (
    CategoryScraperRunner,
    active_jobs,
    start_category_scrape_job,
)
from backend.database import get_db
from backend.master_export import (
    generate_master_csv,
    generate_master_excel,
    generate_master_txt,
)
from backend.repair_service import repair_and_clean_database
from backend.models import (
    CategoryJobResponse,
    CategoryScrapeRequest,
    ExportRequest,
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
    ImageJobResponse,
    ImageScrapeRequest,
    ImageStorageStatusResponse,
    OpenFolderRequest,
    OpenFolderResponse,
)
from backend.image_downloader import (
    OUTPUT_IMAGES_DIR,
    active_image_jobs,
    open_output_folder,
    start_image_download_job,
)
from backend.spreadsheet_service import (
    get_default_destinations,
    get_spreadsheet_provider,
)


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


# ==========================================
# Category-Wide Scraping Endpoints
# ==========================================

@app.post("/api/category/start", response_model=CategoryJobResponse)
async def start_category_scrape(req: CategoryScrapeRequest):
    """
    Initiates category-wide scraping job in the background.
    Discovers listing pages and extracts all available products into persistent SQLite storage.
    """
    raw_url = str(req.category_url).strip()
    try:
        sanitized_url, _ = validate_and_sanitize_url(raw_url)
    except SSRFProtectionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Security Restriction: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}",
        )

    try:
        job_data = start_category_scrape_job(
            category_url=sanitized_url,
            max_pages=req.max_pages,
            max_products=req.max_products,
            delay_seconds=req.delay_seconds,
            product_selector=req.product_selector,
            next_page_selector=req.next_page_selector,
            force_browser=req.force_browser,
        )
        return CategoryJobResponse(**job_data)
    except Exception as e:
        logger.error(f"Failed to start category scrape job: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate category scrape: {str(e)}",
        )


@app.get("/api/category/jobs")
async def list_category_jobs():
    """
    Returns list of category scraping jobs.
    """
    db = get_db()
    return db.list_jobs(limit=25)


@app.get("/api/category/job/{job_id}", response_model=CategoryJobResponse)
async def get_category_job_status(job_id: str):
    """
    Retrieves live status, progress indicators, and tracked products for a category scraping job.
    """
    db = get_db()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    # Attach recent products for the live UI feed
    recent_products = db.get_job_products(job_id, limit=50)
    job["products"] = recent_products
    return CategoryJobResponse(**job)


@app.post("/api/category/job/{job_id}/pause")
async def pause_category_job(job_id: str):
    """
    Pauses an ongoing category scrape job.
    """
    runner = active_jobs.get(job_id)
    if runner:
        runner.pause()
    else:
        db = get_db()
        db.update_job_status(job_id, "paused")

    return {"success": True, "job_id": job_id, "status": "paused"}


@app.post("/api/category/job/{job_id}/resume")
async def resume_category_job(job_id: str):
    """
    Resumes a paused or interrupted category scrape job.
    """
    runner = active_jobs.get(job_id)
    if runner:
        runner.resume()
    else:
        # Re-instantiate runner for interrupted job
        db = get_db()
        job = db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        config = job.get("config", {})
        new_runner = CategoryScraperRunner(
            job_id=job_id,
            category_url=job["category_url"],
            db=db,
            max_pages=config.get("max_pages"),
            max_products=config.get("max_products"),
            delay_seconds=config.get("delay_seconds", 1.0),
            product_selector=config.get("product_selector"),
            next_page_selector=config.get("next_page_selector"),
            force_browser=config.get("force_browser", False),
        )
        active_jobs.register(job_id, new_runner)
        new_runner.start()

    return {"success": True, "job_id": job_id, "status": "running"}


@app.post("/api/category/job/{job_id}/stop")
async def stop_category_job(job_id: str):
    """
    Stops a running category scrape job.
    """
    runner = active_jobs.get(job_id)
    if runner:
        runner.stop()
    else:
        db = get_db()
        db.update_job_status(job_id, "stopped")

    return {"success": True, "job_id": job_id, "status": "stopped"}


@app.post("/api/category/job/{job_id}/retry-failed")
async def retry_category_failed(job_id: str):
    """
    Resets failed products and failed listing pages to pending and restarts scraper loop.
    """
    db = get_db()
    failed_prod_count = db.retry_failed_products(job_id)
    failed_page_count = db.retry_failed_listing_pages(job_id)
    count = failed_prod_count + failed_page_count
    if count > 0:
        runner = active_jobs.get(job_id)
        if not runner or (runner._task and runner._task.done()):
            job = db.get_job(job_id)
            if job:
                config = job.get("config", {})
                new_runner = CategoryScraperRunner(
                    job_id=job_id,
                    category_url=job["category_url"],
                    db=db,
                    max_pages=config.get("max_pages"),
                    max_products=config.get("max_products"),
                    delay_seconds=config.get("delay_seconds", 1.0),
                    product_selector=config.get("product_selector"),
                    next_page_selector=config.get("next_page_selector"),
                    force_browser=config.get("force_browser", False),
                )
                active_jobs.register(job_id, new_runner)
                new_runner.start()

    return {"success": True, "job_id": job_id, "retried_products_count": count}


# ==========================================
# Master Dataset Export Endpoints
# ==========================================

@app.get("/api/category/export/excel")
async def export_category_master_excel(job_id: Optional[str] = None):
    """
    Generates and returns the combined WebSift_Master.xlsx Excel workbook
    containing all accumulated products with dynamic column unions.
    """
    db = get_db()
    products = db.get_all_products(job_id=job_id)
    if not products and job_id:
        products = db.get_all_products()
    if not products:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed products found in the database for master export.",
        )

    try:
        xlsx_bytes, filename = generate_master_excel(products, filename="WebSift_Master.xlsx")
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
        logger.error(f"Master Excel export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Master Excel workbook: {str(e)}",
        )


@app.get("/api/category/export/csv")
async def export_category_master_csv(job_id: Optional[str] = None):
    """
    Generates and returns the combined Master CSV file encoded in UTF-8 with BOM.
    """
    db = get_db()
    products = db.get_all_products(job_id=job_id)
    if not products and job_id:
        products = db.get_all_products()
    if not products:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed products found in the database for master export.",
        )

    try:
        csv_bytes, filename = generate_master_csv(products, filename="WebSift_Master.csv")
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
        logger.error(f"Master CSV export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Master CSV file: {str(e)}",
        )


@app.get("/api/category/export/txt")
async def export_category_master_txt(job_id: Optional[str] = None):
    """
    Generates and returns the combined Master plain text document with formatted product cards.
    """
    db = get_db()
    products = db.get_all_products(job_id=job_id)
    if not products and job_id:
        products = db.get_all_products()
    if not products:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed products found in the database for master export.",
        )

    try:
        txt_bytes, filename = generate_master_txt(products, filename="WebSift_Master.txt")
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
        logger.error(f"Master TXT export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Master TXT file: {str(e)}",
        )


@app.post("/api/category/repair-database")
async def repair_database_endpoint():
    """
    Safely cleans existing database records:
    - Backs up the SQLite database with timestamp.
    - Purges non-medicine URLs (cancer care, prescriptions, subscriptions).
    - Cleans attributes and maps genuine medicine fields.
    - Regenerates WebSift_Master.xlsx, WebSift_Master.csv, and WebSift_Master.txt.
    """
    try:
        db = get_db()
        result = repair_and_clean_database(db)
        return result
    except Exception as e:
        logger.exception(f"Database repair failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database repair failed: {str(e)}",
        )


@app.post("/api/category/reprocess-database")
async def reprocess_database_endpoint():
    """
    Safely reprocesses existing product URLs through the corrected extractor:
    - Backs up the SQLite database and export files with timestamp.
    - Re-extracts clean product details using the corrected pipeline.
    - Validates company names, composition, MRP/price, and storage instructions.
    - Regenerates WebSift_Master.xlsx, WebSift_Master.csv, WebSift_Master.txt, and C1 medicines.xlsx.
    """
    try:
        from backend.repair_service import reprocess_product_records
        db = get_db()
        result = reprocess_product_records(db)
        return result
    except Exception as e:
        logger.exception(f"Database reprocess failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database reprocess failed: {str(e)}",
        )


# ============================================================================
# Mode C: Medicine Image Downloader Endpoints
# ============================================================================

@app.post("/api/images/start", response_model=ImageJobResponse)
async def start_image_scrape_endpoint(payload: ImageScrapeRequest):
    """
    Mode C: Initiates an incremental background image download job from a category or listing URL.
    Discovers medicine names and product images, saves directly to output/medicine_images/,
    and sanitizes filenames according to the actual medicine name.
    """
    try:
        sanitized_url, _ = validate_and_sanitize_url(payload.listing_url)
    except SSRFProtectionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"URL validation failed: {str(e)}",
        )

    try:
        runner = start_image_download_job(
            listing_url=sanitized_url,
            max_pages=payload.max_pages,
            max_images=payload.max_images,
            delay_seconds=payload.delay_seconds,
            product_selector=payload.product_selector,
            next_page_selector=payload.next_page_selector,
        )
        return ImageJobResponse(**runner.to_dict())
    except Exception as e:
        logger.exception(f"Failed to start Mode C image job: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start image download job: {str(e)}",
        )


@app.get("/api/images/job/{job_id}", response_model=ImageJobResponse)
async def get_image_job_status_endpoint(job_id: str):
    """
    Fetches real-time status and download counters for a Mode C image download job.
    """
    runner = active_image_jobs.get(job_id)
    if not runner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image download job {job_id} not found.",
        )
    return ImageJobResponse(**runner.to_dict())


@app.post("/api/images/job/{job_id}/stop", response_model=ImageJobResponse)
async def stop_image_job_endpoint(job_id: str):
    """
    Gracefully stops an in-progress Mode C image download job.
    """
    runner = active_image_jobs.get(job_id)
    if not runner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image download job {job_id} not found.",
        )
    runner.stop()
    return ImageJobResponse(**runner.to_dict())


@app.post("/api/images/open-folder", response_model=OpenFolderResponse)
async def open_images_folder_endpoint(payload: Optional[OpenFolderRequest] = None):
    """
    Conveniently opens the local output/medicine_images/ folder in the host OS desktop file explorer.
    """
    folder_path = Path(payload.folder_path) if payload and payload.folder_path else OUTPUT_IMAGES_DIR
    success, abs_path_str, err = open_output_folder(folder_path)
    return OpenFolderResponse(
        success=success,
        folder_path=abs_path_str,
        error_message=err,
    )


@app.get("/api/images/status", response_model=ImageStorageStatusResponse)
async def get_image_storage_status_endpoint():
    """
    Returns the total count and byte size of downloaded images currently stored in output/medicine_images/.
    """
    OUTPUT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    images = [
        f for f in OUTPUT_IMAGES_DIR.iterdir()
        if f.is_file() and not f.name.endswith(".tmp") and not f.name.startswith(".")
    ]
    total_size = sum(f.stat().st_size for f in images)
    return ImageStorageStatusResponse(
        folder_path=str(OUTPUT_IMAGES_DIR.resolve()),
        total_images=len(images),
        total_size_bytes=total_size,
    )


# Serve frontend if static dist folder exists
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

