import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup, Tag

from backend.field_normalizer import normalize_field_name, compute_batch_field_union
from backend.medicine_models import MedicineBatch, MedicineRecord

# Common medicine indicator terms on the page to confirm medicine context
MEDICINE_INDICATOR_KEYWORDS = [
    "medicine", "tablet", "injection", "capsule", "syrup", "dosage", "side effects",
    "mrp", "composition", "salt", "manufacturer", "uses", "indications", "rx", "prescription"
]


def extract_json_ld_medicine_data(raw_html: str) -> List[Dict[str, Any]]:
    """
    Extracts structured product/drug information from application/ld+json script tags.
    """
    records = []
    pattern = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
    
    for match in pattern.finditer(raw_html):
        content = match.group(1).strip()
        if not content:
            continue
        try:
            data = json.loads(content)
            # Normalize list vs single object
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Handle @graph
                if "@graph" in item and isinstance(item["@graph"], list):
                    items.extend(item["@graph"])
                    continue
                
                type_name = str(item.get("@type", "")).lower()
                if any(k in type_name for k in ("product", "drug", "medicalentity", "medicinalproduct")):
                    records.append(item)
        except Exception:
            continue

    return records


def parse_dosage_and_strength(name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts dosage form (Injection, Tablet, Syrup, etc.) and strength (e.g. 40 mcg, 500 mg) from medicine title.
    """
    strength = None
    form = None
    
    # Common strength patterns: 500mg, 40 mcg, 100 IU, 2.5 ml, 10% w/v
    strength_match = re.search(r'(\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|ml|iu|µg|%|w/v|w/w))', name, re.IGNORECASE)
    if strength_match:
        strength = strength_match.group(1)

    # Common dosage forms
    forms = ["Injection", "Tablet", "Capsule", "Syrup", "Ointment", "Cream", "Gel", "Suspension", "Drops", "Inhaler", "Spray", "Vial", "Ampoule", "Lotion", "Powder", "Patch"]
    for f in forms:
        if re.search(rf'\b{f}s?\b', name, re.IGNORECASE):
            form = f
            break

    return strength, form


def extract_key_value_pairs_from_dom(soup: BeautifulSoup) -> Dict[str, str]:
    """
    Extracts explicit label-value pairs from definition lists, tables, and property divs.
    """
    kv_pairs: Dict[str, str] = {}

    # 1. Definition lists (<dt> label -> <dd> value)
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            label = " ".join(dt.get_text().split())
            val = " ".join(dd.get_text().split())
            if label and val and len(label) < 60:
                kv_pairs[label] = val

    # 2. Key-value tables (2-column tables)
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) == 2:
            lbl = " ".join(cells[0].get_text().split()).rstrip(":")
            val = " ".join(cells[1].get_text().split())
            if lbl and val and len(lbl) < 60 and len(lbl) > 1:
                kv_pairs[lbl] = val

    # 3. Microdata and attribute rows with label/value class names
    for row in soup.find_all(True, class_=re.compile(r'(?:attr|prop|detail|spec|info|field)-row', re.IGNORECASE)):
        lbl_tag = row.find(class_=re.compile(r'(?:label|name|title|key)', re.IGNORECASE))
        val_tag = row.find(class_=re.compile(r'(?:val|desc|content|text)', re.IGNORECASE))
        if lbl_tag and val_tag:
            lbl = " ".join(lbl_tag.get_text().split()).rstrip(":")
            val = " ".join(val_tag.get_text().split())
            if lbl and val and len(lbl) < 60:
                kv_pairs[lbl] = val

    return kv_pairs


def extract_sections_under_headings(soup: BeautifulSoup) -> Dict[str, str]:
    """
    Extracts structured body content that appears directly under section headings.
    """
    sections: Dict[str, str] = {}
    heading_tags = soup.find_all(["h1", "h2", "h3", "h4"])

    for h in heading_tags:
        h_text = " ".join(h.get_text().split())
        if not h_text or len(h_text) > 80:
            continue

        collected_texts: List[str] = []
        # Find following sibling or container siblings
        container = h.parent if h.parent and h.parent.name in ("div", "section") and len(h.parent.get_text(strip=True)) < len(h_text) + 20 else h

        for sib in container.find_next_siblings():
            # Stop if we hit another heading of same or higher level
            if sib.name in ("h1", "h2", "h3", "h4") or sib.find(["h1", "h2", "h3", "h4"]):
                break

            # If it's a list (e.g. side effects, uses)
            if sib.name in ("ul", "ol"):
                items = [" ".join(li.get_text().split()) for li in sib.find_all("li")]
                if items:
                    collected_texts.append("; ".join(items))
            else:
                txt = " ".join(sib.get_text().split())
                if txt and len(txt) > 3:
                    collected_texts.append(txt)

            if len(collected_texts) >= 3:
                break

        if collected_texts:
            sections[h_text] = " \n\n".join(collected_texts)

    return sections


def extract_medicine_batch_from_html(
    raw_html: str,
    source_url: str,
    page_title: str,
    extracted_at: Optional[str] = None,
) -> MedicineBatch:
    """
    Extracts dynamic medicine records from raw HTML and structured DOM.
    Discovers all arbitrary attributes and computes batch field union.
    """
    if extracted_at is None:
        extracted_at = datetime.now(timezone.utc).isoformat()

    soup = BeautifulSoup(raw_html, "html.parser")
    records: List[MedicineRecord] = []
    seen_ids: Set[str] = set()
    warnings: List[str] = []

    # 1. Try Extracting from JSON-LD Schema
    json_ld_products = extract_json_ld_medicine_data(raw_html)

    # 2. Extract DOM sections and Key-Value pairs
    dom_kv = extract_key_value_pairs_from_dom(soup)
    heading_sections = extract_sections_under_headings(soup)

    # Base attributes dictionary for the primary product
    primary_attributes: Dict[str, Any] = {}
    primary_raw_labels: Dict[str, str] = {}

    # Seed medicine name from page title or H1
    h1 = soup.find("h1")
    primary_name = " ".join(h1.get_text().split()) if h1 else page_title.split("|")[0].split("-")[0].strip()
    primary_name = primary_name.replace("Buy ", "").replace(" Online", "").strip()

    # Ingest JSON-LD if present
    for jld in json_ld_products:
        jld_name = jld.get("name")
        if jld_name and isinstance(jld_name, str):
            primary_name = jld_name.strip()

        if "brand" in jld:
            brand_val = jld["brand"].get("name") if isinstance(jld["brand"], dict) else str(jld["brand"])
            if brand_val:
                canon, raw = normalize_field_name("Brand")
                primary_attributes[canon] = brand_val
                primary_raw_labels[canon] = "Brand"

        if "manufacturer" in jld:
            mfg_val = jld["manufacturer"].get("name") if isinstance(jld["manufacturer"], dict) else str(jld["manufacturer"])
            if mfg_val:
                canon, raw = normalize_field_name("Manufacturer")
                primary_attributes[canon] = mfg_val
                primary_raw_labels[canon] = "Manufacturer"

        if "offers" in jld:
            offers = jld["offers"] if isinstance(jld["offers"], list) else [jld["offers"]]
            for off in offers:
                if isinstance(off, dict) and "price" in off:
                    price_str = f"{off.get('priceCurrency', '₹')} {off['price']}".strip()
                    canon, raw = normalize_field_name("Price")
                    primary_attributes[canon] = price_str
                    primary_raw_labels[canon] = "Price"

        if "description" in jld and isinstance(jld["description"], str):
            canon, raw = normalize_field_name("Product Description")
            primary_attributes[canon] = jld["description"]
            primary_raw_labels[canon] = "Description"

        if "sku" in jld:
            canon, raw = normalize_field_name("Product ID")
            primary_attributes[canon] = str(jld["sku"])
            primary_raw_labels[canon] = "SKU"

    # Ingest DOM Key-Value pairs
    for raw_label, val in dom_kv.items():
        canon, raw = normalize_field_name(raw_label)
        if canon not in primary_attributes:
            primary_attributes[canon] = val
            primary_raw_labels[canon] = raw_label

    # Ingest Heading Sections (e.g. Uses, How to Use, Side Effects, Benefits)
    for h_label, content in heading_sections.items():
        canon, raw = normalize_field_name(h_label)
        if canon not in primary_attributes:
            primary_attributes[canon] = content
            primary_raw_labels[canon] = h_label

    # Derive Strength and Dosage Form if not explicitly extracted
    derived_strength, derived_form = parse_dosage_and_strength(primary_name)
    if "Strength" not in primary_attributes and derived_strength:
        primary_attributes["Strength"] = derived_strength
        primary_raw_labels["Strength"] = "Derived Strength"
    if "Dosage Form" not in primary_attributes and derived_form:
        primary_attributes["Dosage Form"] = derived_form
        primary_raw_labels["Dosage Form"] = "Derived Dosage Form"

    # Extract Price from text if not captured
    if "Price" not in primary_attributes:
        price_match = re.search(r'(?:₹|INR|Rs\.?)\s*(\d+(?:,\d+)*(?:\.\d{1,2})?)', raw_html)
        if price_match:
            primary_attributes["Price"] = f"₹{price_match.group(1)}"
            primary_raw_labels["Price"] = "Text MRP"

    # Extract Prescription indicator
    rx_flag = bool(re.search(r'\b(?:prescription required|schedule h|rx only)\b', raw_html, re.IGNORECASE))
    if rx_flag and "Prescription Required" not in primary_attributes:
        primary_attributes["Prescription Required"] = "Yes"
    # Ensure Medicine Name is in attributes for universal dynamic column mapping
    primary_attributes["Medicine Name"] = primary_name
    primary_raw_labels["Medicine Name"] = "Product Name"

    # Build Primary Record
    rec_id = MedicineRecord.generate_id(source_url, primary_name, primary_attributes.get("Strength", ""))
    
    primary_record = MedicineRecord(
        record_id=rec_id,
        medicine_name=primary_name,
        source_url=source_url,
        extracted_at=extracted_at,
        attributes=primary_attributes,
        raw_labels=primary_raw_labels,
        product_id=primary_attributes.get("Product ID"),
        brand=primary_attributes.get("Brand"),
        manufacturer=primary_attributes.get("Manufacturer"),
        marketer=primary_attributes.get("Marketer"),
        price=primary_attributes.get("Price"),
        strength=primary_attributes.get("Strength"),
        dosage_form=primary_attributes.get("Dosage Form"),
        active_ingredients=primary_attributes.get("Active Ingredients"),
        warnings=[],
        is_duplicate=False,
    )
    records.append(primary_record)
    seen_ids.add(rec_id)

    # Check for Product Variants (e.g. multiple pack sizes or strengths in DOM tables)
    # If variant tables exist, create distinct child records preserving relationships
    variant_tables = soup.find_all("table", class_=re.compile(r'(?:variant|substitute|strength|pack)', re.IGNORECASE))
    for v_table in variant_tables:
        for tr in v_table.find_all("tr")[1:]:
            cells = [ " ".join(c.get_text().split()) for c in tr.find_all(["td", "th"]) ]
            if len(cells) >= 2 and any(cells):
                v_name = f"{primary_name} ({cells[0]})"
                v_id = MedicineRecord.generate_id(source_url, v_name, cells[0])
                if v_id not in seen_ids:
                    seen_ids.add(v_id)
                    v_attrs = dict(primary_attributes)
                    v_attrs["Medicine Name"] = v_name
                    v_attrs["Variant Details"] = " | ".join(cells)
                    records.append(
                        MedicineRecord(
                            record_id=v_id,
                            medicine_name=v_name,
                            source_url=source_url,
                            extracted_at=extracted_at,
                            attributes=v_attrs,
                            raw_labels=dict(primary_raw_labels),
                            strength=cells[0] if re.search(r'\d+\s*(?:mg|mcg|ml)', cells[0]) else primary_attributes.get("Strength"),
                            dosage_form=primary_record.dosage_form,
                            active_ingredients=primary_record.active_ingredients,
                        )
                    )

    # Calculate Batch Union across all discovered records
    serialized_records = [r.model_dump() for r in records]
    all_fields, new_unmapped = compute_batch_field_union(serialized_records)

    # Ensure Medicine Name is first
    if "Medicine Name" in all_fields:
        all_fields.remove("Medicine Name")
        all_fields.insert(0, "Medicine Name")

    return MedicineBatch(
        records=records,
        all_discovered_fields=all_fields,
        new_fields=new_unmapped,
        total_records=len(records),
        unique_attributes_count=len(all_fields),
        warnings=warnings,
    )
