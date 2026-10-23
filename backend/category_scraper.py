import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

from backend.browser_renderer import render_with_browser
from backend.content_cleaner import clean_html_document
from backend.crawler import (
    extract_listing_scope,
    extract_next_page_link,
    extract_product_links,
    get_fallback_next_page_url,
    is_explicit_last_page,
    is_product_url,
    is_url_in_scope,
    preserve_scope_in_url,
)
from backend.database import DatabaseManager, get_db
from backend.fetcher import FetchError, fetch_html
from backend.medicine_extractor import extract_medicine_batch_from_html
from backend.medicine_models import MedicineRecord
from backend.url_validator import SSRFProtectionError, validate_and_sanitize_url

logger = logging.getLogger("websift.category_scraper")


class CategoryScraperRunner:
    """
    Asynchronous category scraping runner.
    Traverses listing pages, discovers products, scrapes detail pages with retries,
    persists records immediately to SQLite, and supports pause/resume/stop controls.
    """

    def __init__(
        self,
        job_id: str,
        category_url: str,
        db: Optional[DatabaseManager] = None,
        max_pages: Optional[int] = None,
        max_products: Optional[int] = None,
        delay_seconds: float = 1.0,
        product_selector: Optional[str] = None,
        next_page_selector: Optional[str] = None,
        force_browser: bool = False,
    ):
        self.job_id = job_id
        self.category_url = category_url
        self.db = db or get_db()
        self.max_pages = max_pages
        self.max_products = max_products
        self.delay_seconds = max(delay_seconds, 0.1)
        self.product_selector = product_selector
        self.next_page_selector = next_page_selector
        self.force_browser = force_browser

        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._task: Optional[asyncio.Task] = None

    def start(self) -> asyncio.Task:
        """
        Launches the scraping workflow in the background.
        """
        self._task = asyncio.create_task(self.run())
        return self._task

    def pause(self) -> None:
        """
        Pauses the scraping process.
        """
        self._pause_event.clear()
        self.db.update_job_status(self.job_id, "paused")
        logger.info(f"Job {self.job_id} paused.")

    def resume(self) -> None:
        """
        Resumes a paused scraping process.
        """
        self._pause_event.set()
        self.db.update_job_status(self.job_id, "running")
        logger.info(f"Job {self.job_id} resumed.")

    def stop(self) -> None:
        """
        Signals the scraper to stop execution cleanly.
        """
        self._stop_event.set()
        self._pause_event.set()  # Unblock if paused so loop can terminate
        self.db.update_job_status(self.job_id, "stopped")
        logger.info(f"Job {self.job_id} stop requested.")

    async def _fetch_page(self, target_url: str, max_retries: int = 3) -> Tuple[str, str]:
        """
        Fetches webpage with exponential backoff retries.
        Returns: (html_content, final_url)
        """
        last_error = None
        for attempt in range(1, max_retries + 1):
            if self._stop_event.is_set():
                break

            try:
                # SSRF re-check per URL
                sanitized_url, _ = validate_and_sanitize_url(target_url)

                if self.force_browser:
                    return await render_with_browser(sanitized_url)

                html_content, final_url, needs_browser = await fetch_html(sanitized_url)
                if needs_browser:
                    return await render_with_browser(sanitized_url)
                return html_content, final_url

            except Exception as e:
                last_error = e
                logger.warning(f"Fetch attempt {attempt}/{max_retries} failed for {target_url}: {str(e)}")
                if attempt < max_retries:
                    backoff = min(1.5 ** attempt, 8.0)
                    await asyncio.sleep(backoff)

        raise last_error or Exception(f"Failed to fetch {target_url}")

    async def run(self) -> None:
        """
        Main execution loop for category scraping and product processing.
        """
        logger.info(f"Starting category scrape job {self.job_id} for URL: {self.category_url}")
        self.db.update_job_status(self.job_id, "running")

        try:
            # 1. URL validation & scope extraction
            sanitized_category_url, _ = validate_and_sanitize_url(self.category_url)
            scope = extract_listing_scope(sanitized_category_url)

            job_info = self.db.get_job(self.job_id)
            if not job_info:
                config = {
                    "max_pages": self.max_pages,
                    "max_products": self.max_products,
                    "delay_seconds": self.delay_seconds,
                    "product_selector": self.product_selector,
                    "next_page_selector": self.next_page_selector,
                    "force_browser": self.force_browser,
                }
                self.db.create_job(self.job_id, self.category_url, config)
                job_info = self.db.get_job(self.job_id) or {}

            listing_already_completed = job_info.get("listing_completed", False)

            # Visited listing pages from DB (preserves history on resume)
            visited_listing_pages: Set[str] = set(
                self.db.get_visited_listing_pages(self.job_id, status="completed")
            )
            failed_listing_pages = self.db.get_failed_listing_pages(self.job_id)
            pages_crawled = len(visited_listing_pages)
            failed_listing_pages_count = len(failed_listing_pages)

            current_listing_url: Optional[str] = None

            if not listing_already_completed:
                if not visited_listing_pages:
                    current_listing_url = sanitized_category_url
                else:
                    # Resuming an interrupted listing crawl
                    last_page_url = job_info.get("current_page_url")
                    failed_urls = {f["page_url"] for f in failed_listing_pages}
                    if last_page_url and last_page_url not in visited_listing_pages and last_page_url not in failed_urls:
                        current_listing_url = last_page_url
                    else:
                        # Find highest page number crawled and compute next
                        highest_page = 1
                        for v_url in visited_listing_pages:
                            try:
                                q = parse_qs(urlparse(v_url).query)
                                for p_param in ("page", "p", "pg", "page_number"):
                                    if p_param in q:
                                        highest_page = max(highest_page, int(q[p_param][0]))
                            except Exception:
                                pass
                        next_page_num = highest_page + 1
                        current_listing_url = preserve_scope_in_url(
                            sanitized_category_url, scope, page_num=next_page_num
                        )
                        logger.info(
                            f"Resuming listing crawl from page {next_page_num}: {current_listing_url}"
                        )
            else:
                logger.info("Listing discovery was completed in previous run. Proceeding to product scraping.")

            current_run_visited: Set[str] = set()
            listing_confirmed_end = False
            is_manually_capped = False
            consecutive_failed_pages = 0
            MAX_CONSECUTIVE_LISTING_FAILURES = 3

            # --- Phase 1: Listing Page Crawling & Product Discovery ---
            while current_listing_url and not self._stop_event.is_set():
                # Respect pause event
                await self._pause_event.wait()
                if self._stop_event.is_set():
                    break

                if self.max_pages and self.max_pages > 0 and pages_crawled >= self.max_pages:
                    logger.info(f"Reached max pages limit ({self.max_pages}). Stopping pagination.")
                    is_manually_capped = True
                    break

                # Scope isolation check
                if not is_url_in_scope(current_listing_url, scope):
                    logger.warning(
                        f"Candidate listing URL {current_listing_url} is outside requested listing scope {scope}. Halting pagination."
                    )
                    break

                # Pagination loop check (loop within current run)
                if current_listing_url in current_run_visited:
                    logger.info(f"Detected pagination loop at {current_listing_url}. Stopping pagination.")
                    break

                current_run_visited.add(current_listing_url)
                logger.info(f"Crawling listing page #{pages_crawled + 1}: {current_listing_url}")

                # Track listing page as pending before fetch
                self.db.record_listing_page_scheduled(self.job_id, current_listing_url)

                try:
                    listing_html, final_listing_url = await self._fetch_page(current_listing_url)
                    consecutive_failed_pages = 0
                except FetchError as fe:
                    if getattr(fe, "status_code", None) in (404, 410):
                        logger.info(
                            f"Listing page returned HTTP {fe.status_code} at {current_listing_url}. End of pagination reached."
                        )
                        listing_confirmed_end = True
                        break
                    logger.error(f"Failed to fetch listing page {current_listing_url}: {str(fe)}")
                    self.db.record_listing_page_visited(
                        self.job_id, current_listing_url, status="failed", error_message=str(fe)
                    )
                    failed_listing_pages_count += 1
                    consecutive_failed_pages += 1
                    if consecutive_failed_pages >= MAX_CONSECUTIVE_LISTING_FAILURES:
                        logger.warning(
                            f"Exceeded {MAX_CONSECUTIVE_LISTING_FAILURES} consecutive failed listing pages. Halting pagination."
                        )
                        break
                    fallback = get_fallback_next_page_url(current_listing_url, scope, visited_listing_pages)
                    if fallback and fallback not in current_run_visited:
                        current_listing_url = fallback
                        await asyncio.sleep(self.delay_seconds)
                        continue
                    else:
                        break
                except Exception as e:
                    logger.error(f"Failed to fetch listing page {current_listing_url}: {str(e)}")
                    self.db.record_listing_page_visited(
                        self.job_id, current_listing_url, status="failed", error_message=str(e)
                    )
                    failed_listing_pages_count += 1
                    consecutive_failed_pages += 1
                    if consecutive_failed_pages >= MAX_CONSECUTIVE_LISTING_FAILURES:
                        logger.warning(
                            f"Exceeded {MAX_CONSECUTIVE_LISTING_FAILURES} consecutive failed listing pages. Halting pagination."
                        )
                        break
                    fallback = get_fallback_next_page_url(current_listing_url, scope, visited_listing_pages)
                    if fallback and fallback not in current_run_visited:
                        current_listing_url = fallback
                        await asyncio.sleep(self.delay_seconds)
                        continue
                    else:
                        break

                # Validate redirect scope
                if not is_url_in_scope(final_listing_url, scope):
                    logger.warning(
                        f"Listing page redirected outside scope: {final_listing_url}. Halting pagination."
                    )
                    break

                # Record successful listing page visit
                visited_listing_pages.add(current_listing_url)
                self.db.record_listing_page_visited(self.job_id, current_listing_url, status="completed")
                pages_crawled += 1

                self.db.update_job_progress(
                    self.job_id,
                    pages_visited=pages_crawled,
                    current_page_url=current_listing_url,
                )

                # Discover product links
                discovered_urls = extract_product_links(
                    raw_html=listing_html,
                    base_url=final_listing_url,
                    custom_selector=self.product_selector,
                )

                # Reliable end-of-pagination condition: confirmed empty page
                if not discovered_urls:
                    logger.info(f"Listing page {current_listing_url} yielded 0 product URLs. Confirmed end of listing.")
                    listing_confirmed_end = True
                    break

                new_count, skipped_count = self.db.add_job_products(self.job_id, discovered_urls)
                logger.info(
                    f"Listing page #{pages_crawled} yielded {len(discovered_urls)} URLs "
                    f"({new_count} new pending, {skipped_count} already completed)"
                )

                # Check if website explicitly signals last page (e.g. disabled next button)
                if is_explicit_last_page(listing_html):
                    logger.info("Website explicitly indicated last page (disabled Next button). Pagination complete.")
                    listing_confirmed_end = True
                    break

                # Check if we've reached max_products discovery cap
                job_data = self.db.get_job(self.job_id)
                if self.max_products and self.max_products > 0 and job_data and job_data.get("total_discovered", 0) >= self.max_products:
                    logger.info(f"Reached max products limit ({self.max_products}). Ending pagination.")
                    is_manually_capped = True
                    break

                # Find next page
                next_page = extract_next_page_link(
                    raw_html=listing_html,
                    base_url=final_listing_url,
                    current_page_url=final_listing_url,
                    custom_selector=self.next_page_selector,
                    visited_urls=visited_listing_pages,
                )

                # If primary next page link is not discovered, use validated sequential fallback
                if not next_page:
                    fallback_page = get_fallback_next_page_url(
                        current_page_url=final_listing_url,
                        scope=scope,
                        visited_urls=visited_listing_pages,
                    )
                    if fallback_page and fallback_page not in current_run_visited:
                        logger.info(f"Using validated fallback next page: {fallback_page}")
                        next_page = fallback_page

                current_listing_url = next_page
                if next_page:
                    logger.info(f"Identified next page: {next_page}")
                    await asyncio.sleep(self.delay_seconds)
                else:
                    logger.info("No further pagination links discovered. Pagination complete.")
                    listing_confirmed_end = True

            # Mark listing completed only if genuinely reached the end without errors or user caps
            current_failed_pages = self.db.get_failed_listing_pages(self.job_id)
            if (
                not self._stop_event.is_set()
                and len(current_failed_pages) == 0
                and not is_manually_capped
                and listing_confirmed_end
            ):
                self.db.mark_listing_completed(self.job_id, True)

            # --- Phase 2: Product Scraping Loop ---
            while not self._stop_event.is_set():
                await self._pause_event.wait()
                if self._stop_event.is_set():
                    break

                pending_urls = self.db.get_pending_job_products(self.job_id, limit=50)
                if not pending_urls:
                    # All products processed
                    break

                for prod_url in pending_urls:
                    await self._pause_event.wait()
                    if self._stop_event.is_set():
                        break

                    self.db.update_job_progress(self.job_id, current_product_url=prod_url)
                    logger.info(f"Processing product: {prod_url}")

                    try:
                        # Polite delay
                        await asyncio.sleep(self.delay_seconds)

                        # Fetch product detail page with retries
                        prod_html, final_prod_url = await self._fetch_page(prod_url, max_retries=3)

                        # Clean document and extract title
                        soup, target_root, title, meta_desc, _ = clean_html_document(prod_html, mode="main")

                        # Extract dynamic medicine / product records
                        extracted_at = datetime.now(timezone.utc).isoformat()
                        batch = extract_medicine_batch_from_html(
                            raw_html=prod_html,
                            source_url=final_prod_url,
                            page_title=title,
                            extracted_at=extracted_at,
                        )

                        if batch.records:
                            # Save all discovered product records immediately to SQLite
                            for rec in batch.records:
                                self.db.save_product(rec, status="completed")
                            self.db.mark_job_product(self.job_id, prod_url, "completed")
                            logger.info(f"Successfully scraped & stored: {batch.records[0].medicine_name} ({prod_url})")
                        else:
                            # Verify if the final URL is a legitimate product page
                            if not is_product_url(final_prod_url, self.category_url):
                                self.db.mark_job_product(self.job_id, prod_url, "skipped", last_error="Excluded: Non-medicine page")
                                logger.info(f"Skipped non-medicine candidate URL: {final_prod_url}")
                            elif title and title.lower() not in ("untitled page", "home", "undefined", "null", "tata 1mg"):
                                fallback_rec = MedicineRecord(
                                    record_id=MedicineRecord.generate_id(final_prod_url, title),
                                    medicine_name=title,
                                    source_url=final_prod_url,
                                    extracted_at=extracted_at,
                                    attributes={"Medicine Name": title},
                                    raw_labels={},
                                )
                                self.db.save_product(fallback_rec, status="completed")
                                self.db.mark_job_product(self.job_id, prod_url, "completed")
                            else:
                                self.db.mark_job_product(self.job_id, prod_url, "failed", last_error="No product specifications or valid title found")

                    except Exception as err:
                        logger.error(f"Failed scraping product {prod_url}: {str(err)}")
                        # Mark as failed, record last error, but DO NOT stop overall job!
                        self.db.mark_job_product(self.job_id, prod_url, "failed", last_error=str(err))

            # Finalize Job Status
            final_job = self.db.get_job(self.job_id)
            failed_pages = self.db.get_failed_listing_pages(self.job_id)
            has_failed_listing_pages = len(failed_pages) > 0
            pending_products_count = self.db.count_pending_job_products(self.job_id)
            is_listing_done = final_job.get("listing_completed", False) if final_job else False

            if self._stop_event.is_set():
                status = "stopped"
            elif has_failed_listing_pages or not is_listing_done or pending_products_count > 0:
                status = "incomplete"
            elif final_job and final_job.get("total_failed", 0) > 0 and final_job.get("total_completed", 0) == 0:
                status = "failed"
            else:
                status = "completed"

            now = datetime.now(timezone.utc).isoformat()
            err_msg = None
            if has_failed_listing_pages:
                err_msg = f"Crawl incomplete: {len(failed_pages)} listing page(s) failed to load."
            elif not is_listing_done:
                err_msg = "Crawl incomplete: Listing page traversal was not fully completed."
            elif pending_products_count > 0:
                err_msg = f"Crawl incomplete: {pending_products_count} product(s) remain pending."

            self.db.update_job_status(self.job_id, status, error_message=err_msg, completion_time=now)
            self.db.refresh_job_counts(self.job_id)
            logger.info(f"Category scrape job {self.job_id} finished with status: {status}")

        except Exception as e:
            logger.exception(f"Unhandled error in job {self.job_id}: {str(e)}")
            self.db.update_job_status(self.job_id, "failed", error_message=str(e))


class JobRegistry:
    """
    In-memory registry to manage active background CategoryScraperRunner instances.
    """

    def __init__(self):
        self._runners: Dict[str, CategoryScraperRunner] = {}

    def register(self, job_id: str, runner: CategoryScraperRunner) -> None:
        self._runners[job_id] = runner

    def get(self, job_id: str) -> Optional[CategoryScraperRunner]:
        return self._runners.get(job_id)

    def remove(self, job_id: str) -> None:
        if job_id in self._runners:
            del self._runners[job_id]


active_jobs = JobRegistry()


def start_category_scrape_job(
    category_url: str,
    max_pages: Optional[int] = None,
    max_products: Optional[int] = None,
    delay_seconds: float = 1.0,
    product_selector: Optional[str] = None,
    next_page_selector: Optional[str] = None,
    force_browser: bool = False,
    db: Optional[DatabaseManager] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates and initiates a category scraping job.
    Returns initial job status.
    """
    db_mgr = db or get_db()
    if not job_id:
        job_id = f"job_{uuid.uuid4().hex[:12]}"

    config = {
        "max_pages": max_pages,
        "max_products": max_products,
        "delay_seconds": delay_seconds,
        "product_selector": product_selector,
        "next_page_selector": next_page_selector,
        "force_browser": force_browser,
    }

    job_data = db_mgr.create_job(job_id, category_url, config)

    runner = CategoryScraperRunner(
        job_id=job_id,
        category_url=category_url,
        db=db_mgr,
        max_pages=max_pages,
        max_products=max_products,
        delay_seconds=delay_seconds,
        product_selector=product_selector,
        next_page_selector=next_page_selector,
        force_browser=force_browser,
    )
    active_jobs.register(job_id, runner)
    runner.start()

    return job_data
