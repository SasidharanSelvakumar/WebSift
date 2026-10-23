import csv
import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from backend.config import FORMULA_PREFIXES
from backend.excel_formatter import FormattingConfig, format_workbook_by_content
from backend.field_normalizer import (
    JUNK_LABEL_PATTERNS,
    MEDICINE_NAME_LABEL_PATTERN,
    STANDARD_MASTER_COLUMNS,
    compute_batch_field_union,
    normalize_field_name,
)
from backend.medicine_models import MedicineRecord


def canonicalize_product_url(url: str) -> str:
    """
    Normalizes a product URL for deduplication:
    Strips query parameters and fragments, strips trailing slash, and converts to lowercase.
    """
    if not url:
        return ""
    clean = url.split("?")[0].split("#")[0].strip().rstrip("/").lower()
    return clean


def sanitize_excel_cell(value: Any) -> Any:
    """
    Sanitizes string values to prevent formula injection while preserving numbers/objects.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (dict, list)):
        import json
        return json.dumps(value, ensure_ascii=False)

    text = str(value).strip()
    if text.startswith(FORMULA_PREFIXES):
        return f"'{text}"
    return text


def escape_for_csv(value: Any) -> str:
    """
    Mitigates spreadsheet formula injection in CSV cells.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        import json
        value = json.dumps(value, ensure_ascii=False)
    else:
        value = str(value).strip()

    trimmed = value.lstrip()
    if trimmed.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


from backend.medicine_extractor import (
    is_valid_company_name,
    validate_composition,
    validate_mrp_and_price,
    validate_storage_instructions,
)


def extract_record_standard_values(record: MedicineRecord) -> Dict[str, Any]:
    """
    Resolves a MedicineRecord into the standard 21 medicine fields cleanly.
    Validates company names, composition, MRP/price, and storage instructions.
    Returns empty string for genuinely unavailable fields.
    """
    attrs = record.attributes or {}

    med_name = record.medicine_name or attrs.get("Medicine Name", "")
    brand = record.brand or attrs.get("Brand", "")
    composition = (
        record.active_ingredients
        or attrs.get("Active Ingredient / Composition")
        or attrs.get("Active Ingredients")
        or attrs.get("Composition")
        or ""
    )
    strength = record.strength or attrs.get("Strength", "")
    dosage_form = record.dosage_form or attrs.get("Dosage Form", "")
    pack_size = attrs.get("Pack Size") or attrs.get("Packaging Details") or ""
    pack_quantity = getattr(record, "pack_quantity", None) or attrs.get("Pack Quantity") or ""
    drug_schedule = getattr(record, "drug_schedule", None) or attrs.get("Drug Schedule") or ""
    safety_advice = getattr(record, "safety_advice", None) or attrs.get("Safety Advice") or ""
    tags = getattr(record, "tags", None) or attrs.get("Tags") or ""
    manufacturer = (
        record.manufacturer
        or attrs.get("Manufacturer")
        or attrs.get("Manufactured By")
        or ""
    )
    marketer = (
        record.marketer
        or attrs.get("Marketer")
        or attrs.get("Marketed By")
        or attrs.get("Marketer Details")
        or ""
    )
    price = record.price or attrs.get("Price") or ""
    mrp = attrs.get("MRP") or attrs.get("Maximum Retail Price") or ""
    availability = attrs.get("Availability") or attrs.get("Stock Status") or ""
    rx = attrs.get("Prescription Required") or attrs.get("Rx Required") or ""
    uses = attrs.get("Uses") or attrs.get("Therapeutic Uses") or ""
    benefits = attrs.get("Benefits") or attrs.get("Key Benefits") or ""
    side_effects = attrs.get("Side Effects") or attrs.get("Adverse Reactions") or ""
    how_to_use = (
        attrs.get("How to Use")
        or attrs.get("Direction for Use")
        or attrs.get("Directions for Use")
        or ""
    )
    how_it_works = (
        attrs.get("How It Works")
        or attrs.get("Mechanism of Action")
        or ""
    )
    storage = (
        attrs.get("Storage Instructions")
        or attrs.get("Storage")
        or attrs.get("How to Store")
        or ""
    )
    product_url = record.source_url or attrs.get("Product URL", "")
    extracted_at = record.extracted_at or attrs.get("Extracted At", "")
    scrape_status = attrs.get("Scrape Status", "Completed")

    # Sanitize and validate fields before export
    if manufacturer and not is_valid_company_name(str(manufacturer)):
        manufacturer = ""
    if marketer and not is_valid_company_name(str(marketer)):
        marketer = ""
    if composition:
        composition = validate_composition(str(composition)) or ""
    val_mrp, val_price = validate_mrp_and_price(mrp, price)
    mrp = val_mrp or ""
    price = val_price or ""
    if storage:
        storage = validate_storage_instructions(str(storage)) or ""
    if brand and (str(brand).strip().lower() == str(med_name).strip().lower() or not is_valid_company_name(str(brand))):
        brand = ""

    return {
        "Medicine Name": med_name,
        "Brand": brand,
        "Active Ingredient / Composition": composition,
        "Strength": strength,
        "Dosage Form": dosage_form,
        "Pack Size": pack_size,
        "Pack Quantity": pack_quantity,
        "Manufacturer": manufacturer,
        "Marketer": marketer,
        "Price": price,
        "MRP": mrp,
        "Availability": availability,
        "Prescription Required": rx,
        "Drug Schedule": drug_schedule,
        "Uses": uses,
        "Benefits": benefits,
        "Side Effects": side_effects,
        "How to Use": how_to_use,
        "How It Works": how_it_works,
        "Safety Advice": safety_advice,
        "Storage Instructions": storage,
        "Tags": tags,
        "Product URL": product_url,
        "Extracted At": extracted_at,
        "Scrape Status": scrape_status,
    }


def get_additional_specifications(record: MedicineRecord) -> List[Tuple[str, str]]:
    """
    Extracts valid extra clinical or technical specifications for the secondary worksheet.
    Purges junk, promotional headings, CSS/code strings, and product names.
    """
    extra = []
    attrs = record.attributes or {}
    standard_set = set(STANDARD_MASTER_COLUMNS) | {
        "Product ID", "raw_labels", "Source URL", "Active Ingredients",
        "Composition", "Manufactured By", "Marketed By", "Marketer Details",
    }

    css_code_tokens = ("{", "}", "width:", "height:", "background:", "module__", "<style", "display:")

    for k, v in attrs.items():
        if k in standard_set or not v:
            continue
        # Reject aliases representing standard columns to prevent duplicate specifications
        canon_name, _ = normalize_field_name(k)
        if canon_name and canon_name in standard_set:
            continue
        # Reject junk / promotional / medicine name keys
        if MEDICINE_NAME_LABEL_PATTERN.search(k) or any(p.search(k) for p in JUNK_LABEL_PATTERNS):
            continue
        val_str = str(v).strip()
        if not val_str:
            continue
        # Discard any attribute containing CSS or code tokens
        if any(tok in k.lower() or tok in val_str.lower() for tok in css_code_tokens):
            continue
        extra.append((k, val_str))

    return sorted(extra, key=lambda x: x[0])


def deduplicate_records(records: List[MedicineRecord]) -> List[MedicineRecord]:
    """
    Deduplicates records based on canonical product URL, preserving the first occurrence.
    """
    seen_urls: Set[str] = set()
    deduped: List[MedicineRecord] = []
    for rec in records:
        canon_url = canonicalize_product_url(rec.source_url)
        if canon_url and canon_url in seen_urls:
            continue
        if canon_url:
            seen_urls.add(canon_url)
        deduped.append(rec)
    return deduped


def generate_master_excel(
    records: List[MedicineRecord],
    filename: str = "WebSift_Master.xlsx",
) -> Tuple[bytes, str]:
    """
    Creates a clean master Excel (.xlsx) workbook containing:
    1. 'Products' Worksheet:
       - Strictly 21 standardized columns (STANDARD_MASTER_COLUMNS)
       - Deduplicated records (1 row per unique medicine)
       - No product names as column headers
       - No website sections / promotional banners
       - Clean blank cells for missing data
       - Professional styling: Dark slate header, frozen top row, autofilters, auto-sized columns
       - Unicode and Indian currency (₹) preservation
    2. 'Additional Specifications' Worksheet:
       - Relational secondary sheet with detailed clinical / safety specifications
       - Columns: Product URL | Medicine Name | Specification Name | Value
    """
    wb = openpyxl.Workbook()

    # Deduplicate records
    unique_records = deduplicate_records(records)

    # -------------------------------------------------------------
    # 1. Primary Sheet: 'Products'
    # -------------------------------------------------------------
    ws_products = wb.active
    ws_products.title = "Products"

    headers = list(STANDARD_MASTER_COLUMNS)

    # Write Header Row
    for col_idx, header in enumerate(headers, 1):
        ws_products.cell(row=1, column=col_idx, value=header)

    # Write Product Rows
    for row_idx, record in enumerate(unique_records, 2):
        field_values = extract_record_standard_values(record)
        for col_idx, header in enumerate(headers, 1):
            cell_value = field_values.get(header, "")
            ws_products.cell(row=row_idx, column=col_idx, value=sanitize_excel_cell(cell_value))

    # -------------------------------------------------------------
    # 2. Secondary Sheet: 'Additional Specifications'
    # -------------------------------------------------------------
    ws_specs = wb.create_sheet(title="Additional Specifications")
    spec_headers = ["Product URL", "Medicine Name", "Specification Name", "Specification Value"]

    for col_idx, header in enumerate(spec_headers, 1):
        ws_specs.cell(row=1, column=col_idx, value=header)

    spec_row_idx = 2
    for record in unique_records:
        extra_specs = get_additional_specifications(record)
        for spec_name, spec_val in extra_specs:
            vals = [record.source_url, record.medicine_name, spec_name, spec_val]
            for col_idx, val in enumerate(vals, 1):
                ws_specs.cell(row=spec_row_idx, column=col_idx, value=sanitize_excel_cell(val))
            spec_row_idx += 1

    # Apply content-aware dynamic formatting across every worksheet in the workbook
    format_workbook_by_content(wb)

    # Save to buffer
    buffer = io.BytesIO()
    wb.save(buffer)
    xlsx_bytes = buffer.getvalue()
    buffer.close()

    return xlsx_bytes, filename


def generate_master_csv(
    records: List[MedicineRecord],
    filename: str = "WebSift_Master.csv",
) -> Tuple[bytes, str]:
    """
    Generates a combined RFC-4180 CSV containing all accumulated products.
    Strictly outputs the 21 standard columns, deduplicated, and encoded in UTF-8 with BOM.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

    unique_records = deduplicate_records(records)
    headers = list(STANDARD_MASTER_COLUMNS)
    writer.writerow(headers)

    for record in unique_records:
        field_values = extract_record_standard_values(record)
        row = [escape_for_csv(field_values.get(h, "")) for h in headers]
        writer.writerow(row)

    csv_content = buffer.getvalue()
    csv_bytes = csv_content.encode("utf-8-sig")
    return csv_bytes, filename


def generate_master_txt(
    records: List[MedicineRecord],
    filename: str = "WebSift_Master.txt",
) -> Tuple[bytes, str]:
    """
    Generates a structured, human-readable plain text report of all accumulated products.
    """
    unique_records = deduplicate_records(records)
    lines = [
        "=" * 80,
        "WEBSIFT — MASTER DATASET EXPORT",
        "=" * 80,
        f"Export Timestamp : {datetime.now(timezone.utc).isoformat()}",
        f"Total Records    : {len(unique_records)} products",
        "=" * 80,
        "",
    ]

    for idx, rec in enumerate(unique_records, 1):
        fields = extract_record_standard_values(rec)
        lines.append("-" * 80)
        lines.append(f"PRODUCT #{idx}: {fields['Medicine Name']}")
        lines.append("-" * 80)
        for h in STANDARD_MASTER_COLUMNS:
            val = fields.get(h, "")
            if val:
                lines.append(f"{h.ljust(32)}: {val}")

        extra_specs = get_additional_specifications(rec)
        if extra_specs:
            lines.append("  [Additional Specifications]")
            for k, v in extra_specs:
                lines.append(f"  {k.ljust(30)}: {v}")

        lines.append("")

    lines.append("=" * 80)
    lines.append("End of WebSift Master Dataset Export")
    lines.append("=" * 80)

    txt_content = "\r\n".join(lines)
    return txt_content.encode("utf-8"), filename
