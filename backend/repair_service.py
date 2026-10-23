import asyncio
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.database import DEFAULT_DB_PATH, DatabaseManager, get_db
from backend.field_normalizer import normalize_field_name
from backend.master_export import generate_master_csv, generate_master_excel, generate_master_txt
from backend.medicine_extractor import (
    extract_medicine_batch_from_html,
    is_valid_company_name,
    validate_composition,
    validate_mrp_and_price,
    validate_storage_instructions,
)
from backend.medicine_models import MedicineRecord

logger = logging.getLogger("websift.repair")

# Non-medicine URL substrings that should never be in products table
NON_MEDICINE_URL_KEYWORDS = [
    "/cancer-care",
    "/subscription-plan",
    "/prescription-order",
    "/done-in-one",
    "/order-with-prescription",
    "/consult-doctor",
    "/care-plan",
    "/drugs-all-medicines",
    "/drugs-faq",
    "/all-diseases",
    "/articles",
]

# Promotional or irrelevant attribute patterns to purge
PURGE_ATTRIBUTE_PATTERNS = [
    re.compile(r"save\s*more|cashback|coupon|offer|discount|promo", re.IGNORECASE),
    re.compile(r"did\s*you\s*know|cancer\s*care|download\s*app|connect\s*with", re.IGNORECASE),
    re.compile(r"substitute|alternative\s*brand|people\s*also\s*viewed|similar\s*product", re.IGNORECASE),
    re.compile(r"customer\s*reviews?|faq|feedback|disclaimer", re.IGNORECASE),
]


def is_valid_medicine_product(url: str, name: str) -> bool:
    """
    Checks if a record is genuinely a medicine product and not a general site page.
    """
    url_lower = url.lower()
    for kw in NON_MEDICINE_URL_KEYWORDS:
        if kw in url_lower:
            return False

    name_lower = name.lower()
    if not name or name_lower in ("untitled page", "home", "undefined", "null"):
        return False

    if any(p in name_lower for p in ("cancer care", "subscription", "prescription order")):
        return False

    return True


def backup_database_and_exports(db: DatabaseManager) -> Tuple[Optional[Path], List[Path]]:
    """
    Safely backs up the SQLite database and any existing export files with a timestamp.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    db_path = Path(db.db_path)
    backed_up_files: List[Path] = []
    backup_db_path = None

    if db.db_path != ":memory:" and db_path.exists():
        backup_db_path = db_path.parent / f"websift_backup_{ts}.db"
        shutil.copy2(db_path, backup_db_path)
        logger.info(f"Database backed up to {backup_db_path}")

        export_dir = db_path.parent.parent if str(db_path.resolve()) == str(DEFAULT_DB_PATH.resolve()) else db_path.parent
        for fname in ["WebSift_Master.xlsx", "WebSift_Master.csv", "WebSift_Master.txt", "C1 medicines.xlsx"]:
            fpath = export_dir / fname
            if fpath.exists():
                b_path = export_dir / f"{fpath.stem}_backup_{ts}{fpath.suffix}"
                shutil.copy2(fpath, b_path)
                backed_up_files.append(b_path)

    return backup_db_path, backed_up_files


def reprocess_product_records(
    db: DatabaseManager,
    urls: Optional[List[str]] = None,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """
    Reprocesses products through the corrected extractor:
    1. Backs up SQLite database and existing export files.
    2. Identifies all canonical medicine URLs to reprocess.
    3. Fetches live HTML and runs corrected extraction + validation layer.
    4. Updates database records by canonical product URL, preserving valid existing values.
    5. Regenerates WebSift_Master.xlsx, WebSift_Master.csv, WebSift_Master.txt, and C1 medicines.xlsx.
    """
    backup_db, backed_up_exports = backup_database_and_exports(db)

    # If specific URLs are not provided, collect all products from products table and job_products
    with db._lock, db.get_connection() as conn:
        if urls:
            target_urls = list(urls)
        else:
            # Query existing product URLs
            p_rows = conn.execute("SELECT product_url, product_name FROM products;").fetchall()
            target_urls = [
                r["product_url"] for r in p_rows if is_valid_medicine_product(r["product_url"], r["product_name"])
            ]

            # Query job_products for job_dd83edd3dd3d or label=c
            jp_rows = conn.execute("SELECT product_url FROM job_products;").fetchall()
            for r in jp_rows:
                u = r["product_url"]
                if is_valid_medicine_product(u, "medicine") and u not in target_urls:
                    target_urls.append(u)

            # Ensure Concor COR 2.5 Tablet is explicitly included if label=c was scraped
            concor_url = "https://www.1mg.com/drugs/concor-cor-2.5-tablet-75326"
            has_c_job = conn.execute(
                "SELECT COUNT(*) as cnt FROM scrape_jobs WHERE category_url LIKE '%label=c%';"
            ).fetchone()["cnt"] > 0
            if has_c_job and concor_url not in target_urls:
                target_urls.append(concor_url)
                # Also track in job_dd83edd3dd3d if present
                conn.execute(
                    """
                    INSERT OR IGNORE INTO job_products (job_id, product_url, status, processing_timestamp)
                    VALUES ('job_dd83edd3dd3d', ?, 'pending', ?);
                    """,
                    (concor_url, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()

    http_client = client or httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        timeout=15.0,
        follow_redirects=True,
    )

    reprocessed_count = 0
    failed_count = 0
    field_completeness_report: Dict[str, Dict[str, Any]] = {}

    for prod_url in target_urls:
        try:
            resp = http_client.get(prod_url)
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} fetching {prod_url}")
                failed_count += 1
                continue

            html_content = resp.text
            title = resp.url.path.split("/")[-1].replace("-", " ").title()
            extracted_at = datetime.now(timezone.utc).isoformat()

            batch = extract_medicine_batch_from_html(
                raw_html=html_content,
                source_url=str(resp.url),
                page_title=title,
                extracted_at=extracted_at,
            )

            if batch.records:
                record = batch.records[0]
                db.save_product(record, status="completed")

                # Update job_products tracking
                with db._lock, db.get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE job_products
                        SET status = 'completed', processing_timestamp = ?
                        WHERE product_url = ?;
                        """,
                        (extracted_at, prod_url),
                    )
                    conn.commit()

                # Track field-level completeness
                present_fields = [k for k, v in record.attributes.items() if v]
                missing_fields = [k for k, v in record.attributes.items() if not v]
                field_completeness_report[record.medicine_name] = {
                    "url": prod_url,
                    "composition": record.active_ingredients,
                    "marketer": record.marketer,
                    "manufacturer": record.manufacturer,
                    "mrp": record.attributes.get("MRP"),
                    "price": record.price,
                    "storage": record.attributes.get("Storage Instructions"),
                    "warnings": record.warnings,
                }
                reprocessed_count += 1
                logger.info(f"Reprocessed: {record.medicine_name} ({prod_url})")
            else:
                failed_count += 1
        except Exception as e:
            logger.error(f"Error reprocessing {prod_url}: {str(e)}")
            failed_count += 1

    # Close client if created internally
    if not client:
        http_client.close()

    # Regenerate Master Exports
    db_path = Path(db.db_path)
    export_dir = db_path.parent.parent if str(db_path.resolve()) == str(DEFAULT_DB_PATH.resolve()) else db_path.parent
    master_xlsx = export_dir / "WebSift_Master.xlsx"
    master_csv = export_dir / "WebSift_Master.csv"
    master_txt = export_dir / "WebSift_Master.txt"
    c1_medicines_xlsx = export_dir / "C1 medicines.xlsx"

    all_cleaned = db.get_all_products()

    if all_cleaned:
        xlsx_bytes, _ = generate_master_excel(all_cleaned)
        with open(master_xlsx, "wb") as f:
            f.write(xlsx_bytes)

        # Also write C1 medicines.xlsx for verified user inspection
        with open(c1_medicines_xlsx, "wb") as f:
            f.write(xlsx_bytes)

        csv_bytes, _ = generate_master_csv(all_cleaned)
        with open(master_csv, "wb") as f:
            f.write(csv_bytes)

        txt_bytes, _ = generate_master_txt(all_cleaned)
        with open(master_txt, "wb") as f:
            f.write(txt_bytes)

    # Refresh job counts
    for j in db.list_jobs():
        db.refresh_job_counts(j["job_id"])

    return {
        "success": True,
        "backup_db": str(backup_db) if backup_db else None,
        "backed_up_exports": [str(p) for p in backed_up_exports],
        "total_targets": len(target_urls),
        "reprocessed_count": reprocessed_count,
        "failed_count": failed_count,
        "exported_excel": str(master_xlsx),
        "exported_c1_excel": str(c1_medicines_xlsx),
        "exported_csv": str(master_csv),
        "exported_txt": str(master_txt),
        "sample_completeness": dict(list(field_completeness_report.items())[:5]),
    }


def clean_medicine_attributes(
    record: MedicineRecord,
    all_known_medicine_names: List[str],
) -> MedicineRecord:
    """
    Cleans a medicine record's attributes offline if live re-fetch is not needed:
    Normalizes headings, strips self-named attributes, validates company and composition fields.
    """
    attrs = dict(record.attributes)
    raw_labels = dict(record.raw_labels or {})

    # Extract Composition, Marketer, Pack Size from self-named or top summary attribute
    for k in list(attrs.keys()):
        val = str(attrs[k])
        if k.lower() == record.medicine_name.lower() or "composition:" in val.lower() or "marketer details:" in val.lower():
            comp_match = re.search(r"composition\s*[:\-]\s*([^\n\r]+)", val, re.IGNORECASE)
            if comp_match:
                comp_val = validate_composition(comp_match.group(1).strip())
                if comp_val:
                    attrs["Active Ingredient / Composition"] = comp_val
                    raw_labels["Active Ingredient / Composition"] = "Composition"
                    record.active_ingredients = comp_val

            mkt_match = re.search(r"(?:marketer details|marketer|marketed by)\s*[:\-]\s*([^\n\r]+)", val, re.IGNORECASE)
            if mkt_match:
                mkt_val = mkt_match.group(1).strip()
                if is_valid_company_name(mkt_val):
                    attrs["Marketer"] = mkt_val
                    raw_labels["Marketer"] = "Marketer"
                    record.marketer = mkt_val

            pack_match = re.search(r"(?:pack size|packaging)\s*[:\-]\s*([^\n\r]+)", val, re.IGNORECASE)
            if pack_match:
                attrs["Pack Size"] = pack_match.group(1).strip()
                raw_labels["Pack Size"] = "Pack Size"

    # Normalize 'How <Medicine> Works' -> 'How It Works'
    for k in list(attrs.keys()):
        if re.search(r"\bhow\s+.+\s+works?\b", k, re.IGNORECASE) or k.lower() == "how it works":
            val = attrs.pop(k)
            attrs["How It Works"] = val
            raw_labels["How It Works"] = k
            break

    # Normalize 'Uses of <Medicine>' -> 'Uses'
    for k in list(attrs.keys()):
        if re.search(r"\buses\s+of\b", k, re.IGNORECASE):
            val = attrs.pop(k)
            attrs["Uses"] = val
            raw_labels["Uses"] = k
            break

    # Normalize 'Side effects of <Medicine>' -> 'Side Effects'
    for k in list(attrs.keys()):
        if re.search(r"\bside\s*effects\s+of\b", k, re.IGNORECASE):
            val = attrs.pop(k)
            attrs["Side Effects"] = val
            raw_labels["Side Effects"] = k
            break

    # Remove self-named keys and other medicine names
    for k in list(attrs.keys()):
        if k.lower() == record.medicine_name.lower():
            del attrs[k]

    for other_name in all_known_medicine_names:
        if other_name.lower() != record.medicine_name.lower():
            for k in list(attrs.keys()):
                if k.lower() == other_name.lower():
                    del attrs[k]

    # Remove promotional and junk keys
    for k in list(attrs.keys()):
        for pat in PURGE_ATTRIBUTE_PATTERNS:
            if pat.search(k):
                attrs.pop(k, None)
                break

    # Validate company names
    mfg = attrs.get("Manufacturer") or record.manufacturer
    if mfg and not is_valid_company_name(str(mfg)):
        attrs["Manufacturer"] = ""
        record.manufacturer = None

    mkt = attrs.get("Marketer") or record.marketer
    if mkt and not is_valid_company_name(str(mkt)):
        attrs["Marketer"] = ""
        record.marketer = None

    # Validate composition
    comp = attrs.get("Active Ingredient / Composition") or record.active_ingredients
    if comp:
        clean_comp = validate_composition(str(comp))
        attrs["Active Ingredient / Composition"] = clean_comp or ""
        record.active_ingredients = clean_comp

    # Validate MRP & Price
    val_mrp, val_price = validate_mrp_and_price(attrs.get("MRP"), attrs.get("Price") or record.price)
    attrs["MRP"] = val_mrp or ""
    attrs["Price"] = val_price or ""
    record.price = val_price

    # Validate storage
    storage = attrs.get("Storage Instructions")
    if storage:
        attrs["Storage Instructions"] = validate_storage_instructions(str(storage)) or ""

    record.attributes = attrs
    record.raw_labels = raw_labels
    return record


def repair_and_clean_database(db: DatabaseManager) -> Dict[str, Any]:
    """
    Offline database repair without network requests.
    Validates company fields, strips CSS and promotional junk, and regenerates exports.
    """
    backup_db, backed_up_exports = backup_database_and_exports(db)
    all_products = db.get_all_products()
    total_before = len(all_products)

    medicine_names = [p.medicine_name for p in all_products if is_valid_medicine_product(p.source_url, p.medicine_name)]

    removed_count = 0
    cleaned_records: List[MedicineRecord] = []

    with db._lock, db.get_connection() as conn:
        for prod in all_products:
            if not is_valid_medicine_product(prod.source_url, prod.medicine_name):
                conn.execute("DELETE FROM products WHERE product_url = ?;", (prod.source_url,))
                conn.execute(
                    "UPDATE job_products SET status = 'skipped', last_error = 'Excluded: Non-medicine page' WHERE product_url = ?;",
                    (prod.source_url,),
                )
                removed_count += 1
            else:
                cleaned_prod = clean_medicine_attributes(prod, medicine_names)
                cleaned_records.append(cleaned_prod)
                specs_json = json.dumps(cleaned_prod.attributes, ensure_ascii=False)
                raw_labels_json = json.dumps(cleaned_prod.raw_labels, ensure_ascii=False)
                conn.execute(
                    """
                    UPDATE products
                    SET specifications = ?, raw_labels = ?, brand = ?, manufacturer = ?,
                        price = ?, strength = ?, dosage_form = ?, active_ingredients = ?
                    WHERE product_url = ?;
                    """,
                    (
                        specs_json,
                        raw_labels_json,
                        cleaned_prod.brand,
                        cleaned_prod.manufacturer,
                        cleaned_prod.price,
                        cleaned_prod.strength,
                        cleaned_prod.dosage_form,
                        cleaned_prod.active_ingredients,
                        cleaned_prod.source_url,
                    ),
                )
        conn.commit()

    db_path = Path(db.db_path)
    export_dir = db_path.parent.parent if str(db_path.resolve()) == str(DEFAULT_DB_PATH.resolve()) else db_path.parent
    master_xlsx_path = export_dir / "WebSift_Master.xlsx"
    master_csv_path = export_dir / "WebSift_Master.csv"
    master_txt_path = export_dir / "WebSift_Master.txt"

    if cleaned_records:
        xlsx_bytes, _ = generate_master_excel(cleaned_records)
        with open(master_xlsx_path, "wb") as f:
            f.write(xlsx_bytes)

        csv_bytes, _ = generate_master_csv(cleaned_records)
        with open(master_csv_path, "wb") as f:
            f.write(csv_bytes)

        txt_bytes, _ = generate_master_txt(cleaned_records)
        with open(master_txt_path, "wb") as f:
            f.write(txt_bytes)

    for j in db.list_jobs():
        db.refresh_job_counts(j["job_id"])

    return {
        "success": True,
        "backup_path": str(backup_db) if backup_db else None,
        "total_records_before": total_before,
        "non_medicine_records_removed": removed_count,
        "cleaned_medicines_count": len(cleaned_records),
        "exported_excel": str(master_xlsx_path),
        "exported_csv": str(master_csv_path),
        "exported_txt": str(master_txt_path),
    }
