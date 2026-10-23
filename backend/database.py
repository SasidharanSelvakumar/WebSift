import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.medicine_models import MedicineRecord

DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "websift.db"


class DatabaseManager:
    """
    SQLite persistent storage manager for WebSift.
    Handles thread-safe parameterized queries, transactions, and immediate persistence
    for scraped products, jobs, and job-product tracking.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            self.db_path = str(DEFAULT_DB_PATH)
        else:
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.db_path = db_path

        self._lock = threading.Lock()
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        """
        Creates a connection with row factory and foreign keys enabled.
        """
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")  # High concurrency & crash resilience
        return conn

    def init_schema(self) -> None:
        """
        Initializes the products, scrape_jobs, and job_products tables.
        """
        with self._lock, self.get_connection() as conn:
            # 1. Products table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    product_url TEXT PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    specifications TEXT NOT NULL,
                    raw_labels TEXT,
                    brand TEXT,
                    manufacturer TEXT,
                    marketer TEXT,
                    price TEXT,
                    strength TEXT,
                    dosage_form TEXT,
                    active_ingredients TEXT,
                    scraping_status TEXT DEFAULT 'completed',
                    first_seen_at TEXT NOT NULL,
                    last_scraped_at TEXT NOT NULL,
                    content_hash TEXT
                );
                """
            )
            # 2. Scrape Jobs table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scrape_jobs (
                    job_id TEXT PRIMARY KEY,
                    category_url TEXT NOT NULL,
                    job_status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    last_updated_time TEXT NOT NULL,
                    completion_time TEXT,
                    pages_visited INTEGER DEFAULT 0,
                    total_discovered INTEGER DEFAULT 0,
                    total_completed INTEGER DEFAULT 0,
                    total_failed INTEGER DEFAULT 0,
                    total_skipped INTEGER DEFAULT 0,
                    current_page_url TEXT,
                    current_product_url TEXT,
                    error_message TEXT,
                    config_json TEXT,
                    listing_completed INTEGER DEFAULT 0
                );
                """
            )

            # 3. Job-Product Tracking table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_products (
                    job_id TEXT NOT NULL,
                    product_url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempt_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    processing_timestamp TEXT,
                    PRIMARY KEY (job_id, product_url),
                    FOREIGN KEY (job_id) REFERENCES scrape_jobs(job_id) ON DELETE CASCADE
                );
                """
            )

            # 4. Visited Listing Pages table (for pagination loop prevention across job resumes)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_listing_pages (
                    job_id TEXT NOT NULL,
                    page_url TEXT NOT NULL,
                    visited_at TEXT NOT NULL,
                    status TEXT DEFAULT 'completed',
                    error_message TEXT,
                    PRIMARY KEY (job_id, page_url),
                    FOREIGN KEY (job_id) REFERENCES scrape_jobs(job_id) ON DELETE CASCADE
                );
                """
            )

            # Safe backward-compatible schema migrations for existing databases
            for col in ("marketer", "drug_schedule", "pack_quantity", "tags", "safety_advice"):
                try:
                    conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT;")
                except sqlite3.OperationalError:
                    pass

            for col in ("listing_completed",):
                try:
                    conn.execute(f"ALTER TABLE scrape_jobs ADD COLUMN {col} INTEGER DEFAULT 0;")
                except sqlite3.OperationalError:
                    pass

            for col in ("status", "error_message"):
                try:
                    conn.execute(f"ALTER TABLE job_listing_pages ADD COLUMN {col} TEXT;")
                except sqlite3.OperationalError:
                    pass

            conn.commit()

    # --- Job Management ---

    def create_job(self, job_id: str, category_url: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Creates a new scrape job record.
        """
        now = datetime.now(timezone.utc).isoformat()
        config_json = json.dumps(config or {})

        with self._lock, self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO scrape_jobs (
                    job_id, category_url, job_status, start_time, last_updated_time,
                    pages_visited, total_discovered, total_completed, total_failed, total_skipped,
                    config_json
                ) VALUES (?, ?, 'running', ?, ?, 0, 0, 0, 0, 0, ?);
                """,
                (job_id, category_url, now, now, config_json),
            )
            conn.commit()

        return self.get_job(job_id)  # type: ignore

    def update_job_status(
        self,
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
        completion_time: Optional[str] = None,
    ) -> None:
        """
        Updates the status of a job.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.get_connection() as conn:
            conn.execute(
                """
                UPDATE scrape_jobs
                SET job_status = ?, last_updated_time = ?, error_message = COALESCE(?, error_message),
                    completion_time = COALESCE(?, completion_time)
                WHERE job_id = ?;
                """,
                (status, now, error_message, completion_time, job_id),
            )
            conn.commit()

    def update_job_progress(
        self,
        job_id: str,
        pages_visited: Optional[int] = None,
        current_page_url: Optional[str] = None,
        current_product_url: Optional[str] = None,
    ) -> None:
        """
        Updates live progress indicators for a job.
        """
        now = datetime.now(timezone.utc).isoformat()
        fields = ["last_updated_time = ?"]
        params: List[Any] = [now]

        if pages_visited is not None:
            fields.append("pages_visited = ?")
            params.append(pages_visited)
        if current_page_url is not None:
            fields.append("current_page_url = ?")
            params.append(current_page_url)
        if current_product_url is not None:
            fields.append("current_product_url = ?")
            params.append(current_product_url)

        params.append(job_id)
        sql = f"UPDATE scrape_jobs SET {', '.join(fields)} WHERE job_id = ?;"

        with self._lock, self.get_connection() as conn:
            conn.execute(sql, tuple(params))
            conn.commit()

    def refresh_job_counts(self, job_id: str) -> None:
        """
        Recalculates total_discovered, total_completed, total_failed, total_skipped from job_products.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.get_connection() as conn:
            conn.execute(
                """
                UPDATE scrape_jobs
                SET total_discovered = (SELECT COUNT(*) FROM job_products WHERE job_id = ?),
                    total_completed = (SELECT COUNT(*) FROM job_products WHERE job_id = ? AND status = 'completed'),
                    total_failed = (SELECT COUNT(*) FROM job_products WHERE job_id = ? AND status = 'failed'),
                    total_skipped = (SELECT COUNT(*) FROM job_products WHERE job_id = ? AND status = 'skipped'),
                    last_updated_time = ?
                WHERE job_id = ?;
                """,
                (job_id, job_id, job_id, job_id, now, job_id),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a job by ID.
        """
        with self._lock, self.get_connection() as conn:
            row = conn.execute("SELECT * FROM scrape_jobs WHERE job_id = ?;", (job_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("config_json"):
                try:
                    res["config"] = json.loads(res["config_json"])
                except Exception:
                    res["config"] = {}
            res["listing_completed"] = bool(res.get("listing_completed", 0))
            return res

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Lists recent jobs.
        """
        with self._lock, self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM scrape_jobs ORDER BY start_time DESC LIMIT ?;", (limit,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("config_json"):
                    try:
                        d["config"] = json.loads(d["config_json"])
                    except Exception:
                        d["config"] = {}
                d["listing_completed"] = bool(d.get("listing_completed", 0))
                result.append(d)
            return result

    # --- Listing Page Tracking (Pagination Loop Prevention & Failure Tracking) ---

    def record_listing_page_visited(
        self,
        job_id: str,
        page_url: str,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Records a visited listing page with status ('completed' or 'failed') and optional error message.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO job_listing_pages (job_id, page_url, visited_at, status, error_message)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, page_url) DO UPDATE SET
                        visited_at = excluded.visited_at,
                        status = excluded.status,
                        error_message = excluded.error_message;
                    """,
                    (job_id, page_url, now, status, error_message),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_visited_listing_pages(self, job_id: str, status: Optional[str] = None) -> List[str]:
        """
        Returns list of visited listing URLs for the job, optionally filtered by status ('completed', 'failed').
        """
        with self._lock, self.get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT page_url FROM job_listing_pages WHERE job_id = ? AND (status = ? OR (status IS NULL AND ? = 'completed'));",
                    (job_id, status, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT page_url FROM job_listing_pages WHERE job_id = ?;", (job_id,)
                ).fetchall()
            return [r["page_url"] for r in rows]

    def get_failed_listing_pages(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Returns list of failed listing pages and their error messages for the job.
        """
        with self._lock, self.get_connection() as conn:
            rows = conn.execute(
                "SELECT page_url, error_message, visited_at FROM job_listing_pages WHERE job_id = ? AND status = 'failed';",
                (job_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def record_listing_page_scheduled(self, job_id: str, page_url: str) -> bool:
        """
        Records a listing page as 'pending' before it is fetched.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO job_listing_pages (job_id, page_url, visited_at, status, error_message)
                    VALUES (?, ?, ?, 'pending', NULL)
                    ON CONFLICT(job_id, page_url) DO NOTHING;
                    """,
                    (job_id, page_url, now),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_listing_pages_summary(self, job_id: str) -> Dict[str, int]:
        """
        Returns a breakdown of listing pages by status (completed, failed, pending, total).
        """
        with self._lock, self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(status, 'completed') as st, COUNT(*) as cnt
                FROM job_listing_pages
                WHERE job_id = ?
                GROUP BY status;
                """,
                (job_id,),
            ).fetchall()
            summary = {"completed": 0, "failed": 0, "pending": 0, "total": 0}
            for r in rows:
                st = r["st"]
                cnt = r["cnt"]
                if st in summary:
                    summary[st] = cnt
                summary["total"] += cnt
            return summary

    def retry_failed_listing_pages(self, job_id: str) -> int:
        """
        Resets failed listing pages for a job back to 'pending'.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE job_listing_pages
                SET status = 'pending', error_message = NULL, visited_at = ?
                WHERE job_id = ? AND status = 'failed';
                """,
                (now, job_id),
            )
            count = cursor.rowcount
            conn.commit()
            return count

    def mark_listing_completed(self, job_id: str, completed: bool = True) -> None:
        """
        Marks whether the listing discovery phase has finished traversing all pages for the job.
        """
        with self._lock, self.get_connection() as conn:
            conn.execute(
                "UPDATE scrape_jobs SET listing_completed = ? WHERE job_id = ?;",
                (1 if completed else 0, job_id),
            )
            conn.commit()

    def count_pending_job_products(self, job_id: str) -> int:
        """
        Returns the count of products still pending for a job.
        """
        with self._lock, self.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM job_products WHERE job_id = ? AND status = 'pending';",
                (job_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    # --- Job-Product Tracking ---

    def add_job_products(self, job_id: str, product_urls: List[str]) -> Tuple[int, int]:
        """
        Inserts newly discovered product URLs into job_products as 'pending'.
        If product is already in the database and completed, marks it as 'skipped'.
        Returns: (newly_added_count, skipped_count)
        """
        newly_added = 0
        skipped = 0
        now = datetime.now(timezone.utc).isoformat()

        with self._lock, self.get_connection() as conn:
            for url in product_urls:
                # Check if product is already completed in products table
                existing = conn.execute(
                    "SELECT scraping_status FROM products WHERE product_url = ?;", (url,)
                ).fetchone()

                initial_status = "pending"
                if existing and existing["scraping_status"] == "completed":
                    initial_status = "skipped"
                    skipped += 1
                else:
                    newly_added += 1

                try:
                    conn.execute(
                        """
                        INSERT INTO job_products (job_id, product_url, status, processing_timestamp)
                        VALUES (?, ?, ?, ?);
                        """,
                        (job_id, url, initial_status, now),
                    )
                except sqlite3.IntegrityError:
                    # Already tracked in this job
                    pass

            conn.commit()

        self.refresh_job_counts(job_id)
        return newly_added, skipped

    def get_pending_job_products(self, job_id: str, limit: Optional[int] = None) -> List[str]:
        """
        Returns pending product URLs for a job.
        """
        sql = "SELECT product_url FROM job_products WHERE job_id = ? AND status = 'pending'"
        params: List[Any] = [job_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._lock, self.get_connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [r["product_url"] for r in rows]

    def mark_job_product(
        self,
        job_id: str,
        product_url: str,
        status: str,
        last_error: Optional[str] = None,
    ) -> None:
        """
        Updates product status in job_products ('completed', 'failed', 'skipped', 'pending').
        Increments attempt_count if status is 'failed' or 'completed'.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.get_connection() as conn:
            conn.execute(
                """
                UPDATE job_products
                SET status = ?, last_error = ?, processing_timestamp = ?,
                    attempt_count = attempt_count + 1
                WHERE job_id = ? AND product_url = ?;
                """,
                (status, last_error, now, job_id, product_url),
            )
            conn.commit()

        self.refresh_job_counts(job_id)

    def retry_failed_products(self, job_id: str) -> int:
        """
        Resets all 'failed' products for a job back to 'pending'.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE job_products
                SET status = 'pending', processing_timestamp = ?
                WHERE job_id = ? AND status = 'failed';
                """,
                (now, job_id),
            )
            count = cursor.rowcount
            conn.commit()

        self.refresh_job_counts(job_id)
        return count

    def get_job_products(self, job_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Gets list of tracked products for a job with status and errors.
        """
        with self._lock, self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT jp.product_url, jp.status, jp.attempt_count, jp.last_error, jp.processing_timestamp,
                       p.product_name, p.price, p.strength, p.dosage_form, p.manufacturer
                FROM job_products jp
                LEFT JOIN products p ON jp.product_url = p.product_url
                WHERE jp.job_id = ?
                ORDER BY jp.processing_timestamp DESC
                LIMIT ?;
                """,
                (job_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Master Product Persistence ---

    def save_product(
        self,
        record: MedicineRecord,
        status: str = "completed",
        content_hash: Optional[str] = None,
    ) -> bool:
        """
        Immediately saves a scraped product to the products table.
        Uses INSERT OR REPLACE with parameterized queries.
        Returns True if inserted/updated successfully.
        """
        now = datetime.now(timezone.utc).isoformat()
        # Canonicalize product URL (strip tracking params and trailing slash)
        canonical_url = record.source_url.split("?")[0].split("#")[0].strip().rstrip("/")
        record.source_url = canonical_url

        with self._lock, self.get_connection() as conn:
            # Check if record already exists to preserve first_seen_at and existing valid fields
            existing = conn.execute(
                "SELECT * FROM products WHERE product_url = ?;",
                (canonical_url,),
            ).fetchone()

            first_seen = existing["first_seen_at"] if existing else now

            if existing:
                from backend.medicine_extractor import is_valid_company_name, validate_composition
                # Check current fields on record or attributes before falling back to existing
                current_brand = record.brand or record.attributes.get("Brand")
                if not current_brand and existing["brand"] and is_valid_company_name(existing["brand"]):
                    record.brand = existing["brand"]
                    record.attributes["Brand"] = existing["brand"]
                elif current_brand and not record.brand:
                    record.brand = current_brand

                current_mfg = record.manufacturer or record.attributes.get("Manufacturer")
                if not current_mfg and existing["manufacturer"] and is_valid_company_name(existing["manufacturer"]):
                    record.manufacturer = existing["manufacturer"]
                    record.attributes["Manufacturer"] = existing["manufacturer"]
                elif current_mfg and not record.manufacturer:
                    record.manufacturer = current_mfg

                current_mkt = record.marketer or record.attributes.get("Marketer")
                if not current_mkt and existing["marketer"] and is_valid_company_name(existing["marketer"]):
                    record.marketer = existing["marketer"]
                    record.attributes["Marketer"] = existing["marketer"]
                elif current_mkt and not record.marketer:
                    record.marketer = current_mkt

                current_price = record.price or record.attributes.get("Price")
                if not current_price and existing["price"]:
                    record.price = existing["price"]
                    record.attributes["Price"] = existing["price"]
                elif current_price and not record.price:
                    record.price = current_price

                current_str = record.strength or record.attributes.get("Strength")
                if not current_str and existing["strength"]:
                    record.strength = existing["strength"]
                    record.attributes["Strength"] = existing["strength"]
                elif current_str and not record.strength:
                    record.strength = current_str

                current_form = record.dosage_form or record.attributes.get("Dosage Form")
                if not current_form and existing["dosage_form"]:
                    record.dosage_form = existing["dosage_form"]
                    record.attributes["Dosage Form"] = existing["dosage_form"]
                elif current_form and not record.dosage_form:
                    record.dosage_form = current_form

                current_ai = record.active_ingredients or record.attributes.get("Active Ingredient / Composition")
                if not current_ai and existing["active_ingredients"]:
                    comp_val = validate_composition(existing["active_ingredients"])
                    if comp_val:
                        record.active_ingredients = comp_val
                        record.attributes["Active Ingredient / Composition"] = comp_val
                elif current_ai and not record.active_ingredients:
                    record.active_ingredients = current_ai

                # Check and preserve new fields: drug_schedule, pack_quantity, tags, safety_advice
                for field_key, col_key in [
                    ("Drug Schedule", "drug_schedule"),
                    ("Pack Quantity", "pack_quantity"),
                    ("Tags", "tags"),
                    ("Safety Advice", "safety_advice"),
                ]:
                    curr_val = getattr(record, col_key, None) or record.attributes.get(field_key)
                    if not curr_val and col_key in existing.keys() and existing[col_key]:
                        setattr(record, col_key, existing[col_key])
                        record.attributes[field_key] = existing[col_key]
                    elif curr_val and not getattr(record, col_key, None):
                        setattr(record, col_key, curr_val)

                # Preserve existing valid non-CSS specifications
                if existing["specifications"]:
                    try:
                        old_specs = json.loads(existing["specifications"])
                        if isinstance(old_specs, dict):
                            for k, v in old_specs.items():
                                if v and not record.attributes.get(k):
                                    if not any(tok in str(v).lower() for tok in ("{", "}", "width:", "background:", "module__", "<style")):
                                        record.attributes[k] = v
                    except Exception:
                        pass

            specs_json = json.dumps(record.attributes, ensure_ascii=False)
            raw_labels_json = json.dumps(record.raw_labels or {}, ensure_ascii=False)

            conn.execute(
                """
                INSERT INTO products (
                    product_url, product_name, specifications, raw_labels,
                    brand, manufacturer, marketer, price, strength, dosage_form, active_ingredients,
                    drug_schedule, pack_quantity, tags, safety_advice,
                    scraping_status, first_seen_at, last_scraped_at, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_url) DO UPDATE SET
                    product_name = excluded.product_name,
                    specifications = excluded.specifications,
                    raw_labels = excluded.raw_labels,
                    brand = excluded.brand,
                    manufacturer = excluded.manufacturer,
                    marketer = excluded.marketer,
                    price = excluded.price,
                    strength = excluded.strength,
                    dosage_form = excluded.dosage_form,
                    active_ingredients = excluded.active_ingredients,
                    drug_schedule = excluded.drug_schedule,
                    pack_quantity = excluded.pack_quantity,
                    tags = excluded.tags,
                    safety_advice = excluded.safety_advice,
                    scraping_status = excluded.scraping_status,
                    last_scraped_at = excluded.last_scraped_at,
                    content_hash = excluded.content_hash;
                """,
                (
                    canonical_url,
                    record.medicine_name,
                    specs_json,
                    raw_labels_json,
                    record.brand or record.attributes.get("Brand"),
                    record.manufacturer or record.attributes.get("Manufacturer"),
                    record.marketer or record.attributes.get("Marketer"),
                    record.price or record.attributes.get("Price"),
                    record.strength or record.attributes.get("Strength"),
                    record.dosage_form or record.attributes.get("Dosage Form"),
                    record.active_ingredients or record.attributes.get("Active Ingredient / Composition") or record.attributes.get("Active Ingredients"),
                    record.drug_schedule or record.attributes.get("Drug Schedule"),
                    record.pack_quantity or record.attributes.get("Pack Quantity"),
                    record.tags or record.attributes.get("Tags"),
                    record.safety_advice or record.attributes.get("Safety Advice"),
                    status,
                    first_seen,
                    now,
                    content_hash,
                ),
            )
            conn.commit()
            return True

    def get_product(self, product_url: str) -> Optional[MedicineRecord]:
        """
        Retrieves a single product as a MedicineRecord.
        """
        with self._lock, self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE product_url = ?;", (product_url,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_all_products(self, job_id: Optional[str] = None) -> List[MedicineRecord]:
        """
        Retrieves all successfully saved products.
        If job_id is provided, filters to products discovered by that job.
        """
        with self._lock, self.get_connection() as conn:
            if job_id:
                rows = conn.execute(
                    """
                    SELECT p.* FROM products p
                    INNER JOIN job_products jp ON p.product_url = jp.product_url
                    WHERE jp.job_id = ? AND p.scraping_status = 'completed'
                    ORDER BY p.first_seen_at ASC;
                    """,
                    (job_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM products WHERE scraping_status = 'completed' ORDER BY first_seen_at ASC;"
                ).fetchall()

            return [self._row_to_record(r) for r in rows]

    def get_products_count(self) -> int:
        """
        Total count of completed products in database.
        """
        with self._lock, self.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM products WHERE scraping_status = 'completed';").fetchone()
            return row["cnt"] if row else 0

    def _row_to_record(self, row: sqlite3.Row) -> MedicineRecord:
        """
        Converts a SQLite row into a MedicineRecord.
        """
        attributes = {}
        if row["specifications"]:
            try:
                attributes = json.loads(row["specifications"])
            except Exception:
                attributes = {}

        raw_labels = {}
        if row["raw_labels"]:
            try:
                raw_labels = json.loads(row["raw_labels"])
            except Exception:
                raw_labels = {}

        def _get_row_or_attr(col_name: str, attr_name: str) -> Optional[str]:
            val = attributes.get(attr_name)
            if not val:
                try:
                    val = row[col_name]
                except (IndexError, KeyError):
                    pass
            return val or None

        return MedicineRecord(
            record_id=MedicineRecord.generate_id(row["product_url"], row["product_name"]),
            medicine_name=row["product_name"],
            source_url=row["product_url"],
            extracted_at=row["last_scraped_at"],
            attributes=attributes,
            raw_labels=raw_labels,
            brand=row["brand"],
            manufacturer=row["manufacturer"],
            marketer=_get_row_or_attr("marketer", "Marketer"),
            price=row["price"],
            strength=row["strength"],
            dosage_form=row["dosage_form"],
            active_ingredients=row["active_ingredients"],
            drug_schedule=_get_row_or_attr("drug_schedule", "Drug Schedule"),
            pack_quantity=_get_row_or_attr("pack_quantity", "Pack Quantity"),
            tags=_get_row_or_attr("tags", "Tags"),
            safety_advice=_get_row_or_attr("safety_advice", "Safety Advice"),
            warnings=[],
            is_duplicate=False,
        )


# Global default database instance
db_instance = DatabaseManager()


def get_db() -> DatabaseManager:
    return db_instance
