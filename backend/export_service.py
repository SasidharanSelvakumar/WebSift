import csv
import io
import re
from datetime import datetime, timezone
from typing import List, Tuple
from urllib.parse import urlparse

from backend.config import FORMULA_PREFIXES
from backend.models import ExtractedItem

CSV_COLUMNS = [
    "source_url",
    "page_title",
    "content_type",
    "heading",
    "text_content",
    "sequence_number",
    "extracted_at",
]


def sanitize_filename_part(text: str) -> str:
    """
    Sanitizes domain or text for use in filenames.
    """
    clean = re.sub(r'[^a-zA-Z0-9_-]', '_', text)
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean[:40] or "extracted"


def generate_filename(source_url: str, extension: str, timestamp_str: str = None) -> str:
    """
    Generates a meaningful filename, e.g. websift_example_com_20261015_143000.csv
    """
    try:
        domain = urlparse(source_url).netloc.split(":")[0]
    except Exception:
        domain = "page"

    clean_domain = sanitize_filename_part(domain)

    if not timestamp_str:
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d_%H%M%S")
    else:
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            ts = dt.strftime("%Y%m%d_%H%M%S")
        except Exception:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    return f"websift_{clean_domain}_{ts}.{extension}"


def escape_for_csv(value: str) -> str:
    """
    Mitigate CSV / Spreadsheet Formula Injection (CWE-1236).
    If a cell value starts with '=', '+', '-', '@', tab, or carriage return,
    prefix it with a single quote to prevent automatic formula execution in Excel/Calc.
    """
    if not value or not isinstance(value, str):
        return value or ""

    trimmed = value.lstrip()
    if trimmed.startswith(FORMULA_PREFIXES):
        return f"'{value}"

    return value


def generate_csv_bytes(
    items: List[ExtractedItem],
    source_url: str,
    page_title: str,
) -> Tuple[bytes, str]:
    """
    Generates a valid RFC 4180 CSV encoded with UTF-8 BOM (utf-8-sig).
    Returns (csv_bytes, filename).
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

    # Write CSV Header
    writer.writerow(CSV_COLUMNS)

    # Sort items by sequence_number to guarantee strict reading order
    sorted_items = sorted(items, key=lambda x: x.sequence_number)

    for item in sorted_items:
        row = [
            escape_for_csv(item.source_url or source_url),
            escape_for_csv(item.page_title or page_title),
            escape_for_csv(item.content_type),
            escape_for_csv(item.heading or ""),
            escape_for_csv(item.text_content),
            str(item.sequence_number),
            escape_for_csv(item.extracted_at),
        ]
        writer.writerow(row)

    csv_content = buffer.getvalue()
    # Encode with UTF-8 BOM so Microsoft Excel correctly displays Unicode characters
    csv_bytes = csv_content.encode("utf-8-sig")

    first_item_ts = sorted_items[0].extracted_at if sorted_items else None
    filename = generate_filename(source_url, "csv", first_item_ts)

    return csv_bytes, filename


def generate_txt_bytes(
    items: List[ExtractedItem],
    source_url: str,
    page_title: str,
    mode: str = "main",
) -> Tuple[bytes, str]:
    """
    Generates a structured, highly readable plain text document in reading order.
    Returns (txt_bytes, filename).
    """
    sorted_items = sorted(items, key=lambda x: x.sequence_number)
    first_item_ts = sorted_items[0].extracted_at if sorted_items else datetime.now(timezone.utc).isoformat()

    total_words = sum(len(item.text_content.split()) for item in sorted_items)
    total_chars = sum(len(item.text_content) for item in sorted_items)

    lines = [
        "=" * 80,
        "WEBSIFT — EXTRACTED CONTENT REPORT",
        "=" * 80,
        f"Page Title   : {page_title}",
        f"Source URL   : {source_url}",
        f"Extracted At : {first_item_ts}",
        f"Mode         : {mode.title()}",
        f"Total Blocks : {len(sorted_items)}",
        f"Word Count   : {total_words}",
        f"Char Count   : {total_chars}",
        "=" * 80,
        "",
    ]

    current_section = None

    for item in sorted_items:
        ctype = item.content_type
        text = item.text_content

        if ctype == "page_title":
            # Already in header; print top title banner
            lines.append(f"# {text}")
            lines.append("-" * len(text))
            lines.append("")
        elif ctype == "heading_1":
            lines.append("")
            lines.append(f"# {text}")
            lines.append("-" * len(text))
            lines.append("")
            current_section = text
        elif ctype == "heading_2":
            lines.append("")
            lines.append(f"## {text}")
            lines.append("")
            current_section = text
        elif ctype.startswith("heading_"):
            level = ctype.split("_")[1]
            hashes = "#" * int(level)
            lines.append("")
            lines.append(f"{hashes} {text}")
            lines.append("")
            current_section = text
        elif ctype == "list_item":
            # List items already contain bullet or number prefix
            lines.append(f"  {text}")
        elif ctype in ("table_row", "table_header"):
            lines.append(f"  | {text} |")
        elif ctype == "blockquote":
            lines.append(f"  > {text}")
            lines.append("")
        elif ctype == "code_block":
            lines.append("  ```")
            lines.append(f"  {text}")
            lines.append("  ```")
            lines.append("")
        elif ctype == "link":
            lines.append(f"  * {text}")
        else:
            # Paragraph or general text block
            lines.append(text)
            lines.append("")

    lines.append("")
    lines.append("=" * 80)
    lines.append("End of WebSift Scraped Content Export")
    lines.append("=" * 80)

    txt_content = "\r\n".join(lines)
    txt_bytes = txt_content.encode("utf-8")
    filename = generate_filename(source_url, "txt", first_item_ts)

    return txt_bytes, filename


def generate_medicine_csv_bytes(
    batch: any,
    source_url: str,
) -> Tuple[bytes, str]:
    """
    Generates an RFC-4180 CSV encoded with UTF-8 BOM containing all dynamic medicine fields.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

    headers = batch.all_discovered_fields
    if not headers:
        headers = ["Medicine Name", "Source URL", "Extracted At"]

    writer.writerow(headers)

    for record in batch.records:
        row = []
        for h in headers:
            val = ""
            if h == "Medicine Name":
                val = record.medicine_name
            elif h == "Source URL":
                val = record.source_url
            elif h == "Extracted At":
                val = record.extracted_at
            elif h in record.attributes:
                val = record.attributes[h]

            if isinstance(val, (dict, list)):
                import json
                val = json.dumps(val, ensure_ascii=False)
            else:
                val = str(val or "")

            row.append(escape_for_csv(val))
        writer.writerow(row)

    csv_content = buffer.getvalue()
    csv_bytes = csv_content.encode("utf-8-sig")
    filename = generate_filename(source_url, "csv")

    return csv_bytes, filename


def generate_medicine_txt_bytes(
    batch: any,
    source_url: str,
) -> Tuple[bytes, str]:
    """
    Generates structured, human-readable plain text cards for each medicine record.
    """
    lines = [
        "=" * 80,
        "WEBSIFT — MEDICINE DATA EXPORT",
        "=" * 80,
        f"Source URL   : {source_url}",
        f"Total Records: {len(batch.records)}",
        f"Attributes   : {len(batch.all_discovered_fields)} unique discovered fields",
        "=" * 80,
        "",
    ]

    for idx, rec in enumerate(batch.records, 1):
        lines.append("-" * 80)
        lines.append(f"RECORD #{idx}: {rec.medicine_name}")
        lines.append("-" * 80)
        lines.append(f"Medicine Name        : {rec.medicine_name}")
        if rec.brand:
            lines.append(f"Brand                : {rec.brand}")
        if rec.strength:
            lines.append(f"Strength             : {rec.strength}")
        if rec.dosage_form:
            lines.append(f"Dosage Form          : {rec.dosage_form}")
        if rec.active_ingredients:
            lines.append(f"Active Ingredients   : {rec.active_ingredients}")
        if rec.manufacturer:
            lines.append(f"Manufacturer         : {rec.manufacturer}")
        if rec.marketer:
            lines.append(f"Marketer             : {rec.marketer}")
        if rec.price:
            lines.append(f"Price                : {rec.price}")

        standard_keys = {
            "Medicine Name", "Brand", "Strength", "Dosage Form", "Active Ingredients",
            "Manufacturer", "Marketer", "Price", "Source URL", "Extracted At"
        }
        dynamic_keys = [k for k in rec.attributes.keys() if k not in standard_keys]
        for k in sorted(dynamic_keys):
            v = rec.attributes[k]
            lines.append(f"{k.ljust(21)}: {v}")

        lines.append(f"Source URL           : {rec.source_url}")
        lines.append(f"Extracted At         : {rec.extracted_at}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("End of WebSift Medicine Data Export")
    lines.append("=" * 80)

    txt_content = "\r\n".join(lines)
    txt_bytes = txt_content.encode("utf-8")
    filename = generate_filename(source_url, "txt")

    return txt_bytes, filename
