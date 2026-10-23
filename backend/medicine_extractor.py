import html
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from bs4 import BeautifulSoup, Tag

from backend.field_normalizer import (
    JUNK_LABEL_PATTERNS,
    MEDICINE_NAME_LABEL_PATTERN,
    STANDARD_MASTER_COLUMNS,
    compute_batch_field_union,
    normalize_field_name,
)
from backend.medicine_models import MedicineBatch, MedicineRecord

logger = logging.getLogger("websift.medicine_extractor")

# Allowed medical section heading patterns
ALLOWED_SECTION_HEADINGS = {
    "uses": "Uses",
    "indications": "Uses",
    "therapeutic uses": "Uses",
    "benefits": "Benefits",
    "key benefits": "Benefits",
    "side effects": "Side Effects",
    "adverse reactions": "Side Effects",
    "adverse effects": "Side Effects",
    "how to use": "How to Use",
    "direction for use": "How to Use",
    "directions for use": "How to Use",
    "how it works": "How It Works",
    "mechanism of action": "How It Works",
    "safety advice": "Safety Advice",
    "warnings": "Safety Advice",
    "precautions": "Safety Advice",
    "safety warnings": "Safety Advice",
    "warnings & precautions": "Safety Advice",
    "storage": "Storage Instructions",
    "how to store": "Storage Instructions",
    "storage conditions": "Storage Instructions",
    "drug interactions": "Drug Interactions",
    "interactions": "Drug Interactions",
    "contraindications": "Drug Interactions",
    "missed dose": "Safety Advice",
    "overdose": "Safety Advice",
    "product description": "Product Description",
    "description": "Product Description",
    "product introduction": "Product Description",
    "overview": "Product Description",
}


# ===========================================================================
# Validation Layer Functions
# ===========================================================================

def is_valid_company_name(name: Optional[str]) -> bool:
    """
    Validates whether a string is a plausible company name (Marketer/Manufacturer).
    Rejects CSS rules, code snippets, HTML tags, URLs, generic placeholders,
    and substitute-product labels.
    """
    if not name or not isinstance(name, str):
        return False

    clean = name.strip()
    if len(clean) < 2 or len(clean) > 100:
        return False

    clean_lower = clean.lower()

    # Reject CSS, code, or styling tokens
    css_code_tokens = (
        "{", "}", "width:", "height:", "background:", "module__",
        "display:", ";", "<", ">", "http", "var ", "px", "rgba",
        "margin:", "padding:", "color:", "font-", "border:", "class=",
        "href=", "javascript:", "function(", "style="
    )
    for tok in css_code_tokens:
        if tok in clean_lower:
            return False

    # Reject substitute or non-company text
    junk_terms = (
        "substitute", "alternative", "view all", "click here", "read more",
        "buy now", "disclaimer", "overview", "quick links", "add to cart",
        "rating", "reviews", "stars", "offer", "discount", "cashback"
    )
    for term in junk_terms:
        if term in clean_lower:
            return False

    # Must contain at least one alphabetical letter
    if not re.search(r"[a-zA-Z]", clean):
        return False

    return True


def clean_monetary_value(val: Any) -> Optional[str]:
    """
    Normalizes a price or MRP value into standard INR currency representation (₹XX or ₹XX.XX).
    Rejects invalid or negative values.
    """
    if val is None:
        return None

    val_str = str(val).strip()
    if not val_str:
        return None

    # Search for numeric amount
    m = re.search(r"(\d+(?:,\d+)*(?:\.\d+)?)", val_str)
    if not m:
        return None

    num_str = m.group(1).replace(",", "")
    try:
        num = float(num_str)
        if num <= 0:
            return None
        # If original text had decimals, preserve decimal precision
        if "." in num_str:
            dec = num_str.split(".")[1]
            if len(dec) == 2:
                return f"₹{num:.2f}"
            elif len(dec) == 1:
                return f"₹{num:.1f}"
            else:
                return f"₹{num:.2f}"
        if num.is_integer():
            return f"₹{int(num)}"
        return f"₹{num:.2f}"
    except (ValueError, TypeError):
        return None


def validate_mrp_and_price(
    mrp: Optional[str],
    price: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Validates MRP and selling Price. Ensures MRP is not confused with discounted price.
    If MRP is less than Price, corrects the inversion and logs a warning.
    """
    clean_mrp = clean_monetary_value(mrp)
    clean_price = clean_monetary_value(price)

    if clean_mrp and clean_price:
        try:
            mrp_val = float(re.sub(r"[^\d.]", "", clean_mrp))
            price_val = float(re.sub(r"[^\d.]", "", clean_price))
            if mrp_val < price_val:
                logger.warning(
                    f"Inverted MRP ({clean_mrp}) and Price ({clean_price}). Correcting order."
                )
                clean_mrp, clean_price = clean_price, clean_mrp
        except Exception:
            pass

    return clean_mrp, clean_price


def validate_composition(comp: Optional[str]) -> Optional[str]:
    """
    Validates active ingredient / composition text.
    Preserves combination ingredients and units (e.g. 'Beclometasone (0.025% w/w) + Clotrimazole (1% w/w)').
    Rejects HTML, CSS, or long product description paragraphs.
    """
    if not comp or not isinstance(comp, str):
        return None

    clean = re.sub(r"<[^>]+>", " ", comp)
    clean = " ".join(clean.split()).strip()

    if len(clean) < 3 or len(clean) > 250:
        return None

    clean_lower = clean.lower()
    if any(tok in clean_lower for tok in ("{", "}", "width:", "background:", "module__", "<style", "function()")):
        return None

    # Do not confuse description paragraphs with composition
    if any(phrase in clean_lower for phrase in ("is used for", "is an antibiotic", "treatment of", "consult your doctor", "disclaimer")):
        return None

    # Normalize combination plus spacing: 'A+ B' -> 'A + B'
    clean = re.sub(r"\s*\+\s*", " + ", clean)
    return clean


def validate_storage_instructions(storage: Optional[str]) -> Optional[str]:
    """
    Validates storage instructions text.
    Leaves blank (None) when not genuinely available on the page.
    """
    if not storage or not isinstance(storage, str):
        return None

    clean = re.sub(r"<[^>]+>", " ", storage)
    clean = " ".join(clean.split()).strip()

    if len(clean) < 4 or len(clean) > 200:
        return None

    clean_lower = clean.lower()
    if any(tok in clean_lower for tok in ("{", "}", "width:", "background:", "module__", "<style", "function()")):
        return None

    # Must contain relevant storage keywords
    if not any(k in clean_lower for k in ("store", "storage", "temperature", "cool", "dry", "freeze", "sunlight", "reach of children", "below", "moisture")):
        return None

    return clean


def clean_html_section(html_text: str) -> str:
    """
    Strips HTML tags cleanly from clinical/overview sections, converting <li> items
    to structured bullet points and preserving readable text.
    """
    if not html_text:
        return ""

    soup = BeautifulSoup(html_text, "html.parser")
    for li in soup.find_all("li"):
        li.insert_before("\n• ")
    for br in soup.find_all(["br", "p", "div"]):
        br.insert_before("\n")

    text = soup.get_text()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def extract_explicit_drug_schedule(text_or_obj: Any) -> Optional[str]:
    """
    Extracts an explicitly stated drug schedule (e.g. Schedule H, Schedule H1, Schedule X, Schedule G).
    Strictly avoids inferring from general prescription warnings, medicine names, or categories.
    Returns None if no explicit schedule is stated.
    """
    if not text_or_obj:
        return None
    raw_str = str(text_or_obj).strip()
    m = re.search(r'\b(Schedule\s+(?:H1|H|X|G|K|M|C1|C|[A-Z][0-9]?))\b', raw_str, re.IGNORECASE)
    if m:
        parts = m.group(1).split()
        if len(parts) == 2:
            return f"Schedule {parts[1].upper()}"
        return m.group(1).title()
    return None


def extract_and_sanitize_tags(candidate_tags: Any) -> Optional[str]:
    """
    Cleans, deduplicates, and validates explicit product tags/badges.
    Filters out CSS tokens, promotional text, navigation, and review ratings.
    Returns a comma-separated string or None.
    """
    if not candidate_tags:
        return None

    tag_list: List[str] = []
    if isinstance(candidate_tags, list):
        for item in candidate_tags:
            if isinstance(item, dict):
                tag_name = item.get("name") or item.get("title") or item.get("label") or item.get("text")
                if tag_name:
                    tag_list.append(str(tag_name))
            elif isinstance(item, str):
                tag_list.append(item)
    elif isinstance(candidate_tags, str):
        tag_list = candidate_tags.split(",")

    valid_tags: List[str] = []
    seen: Set[str] = set()

    junk_keywords = (
        "home", "cart", "buy", "overview", "substitute", "substitutes",
        "tata 1mg", "1mg", "review", "reviews", "star", "rating", "offer",
        "discount", "cashback", "coupon", "save", "download", "free", "promo", "deal"
    )

    for raw in tag_list:
        clean = " ".join(raw.strip().split())
        if not clean or len(clean) < 2 or len(clean) > 50:
            continue
        clean_lower = clean.lower()
        if any(tok in clean_lower for tok in ("{", "}", "width:", "background:", "<", ">", "http", "var ", "px")):
            continue
        if any(p.search(clean) for p in JUNK_LABEL_PATTERNS):
            continue
        if any(jk in clean_lower for jk in junk_keywords):
            continue
        if clean_lower not in seen:
            seen.add(clean_lower)
            valid_tags.append(clean)

    return ", ".join(valid_tags) if valid_tags else None


# ===========================================================================
# Structured Data Extraction
# ===========================================================================

def extract_json_ld_medicine_data(raw_html: str) -> List[Dict[str, Any]]:
    """
    Extracts structured product/drug information from application/ld+json script tags.
    """
    records = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(raw_html):
        content = match.group(1).strip()
        if not content:
            continue
        try:
            data = json.loads(content)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                if "@graph" in item and isinstance(item["@graph"], list):
                    items.extend(item["@graph"])
                    continue

                type_name = str(item.get("@type", "")).lower()
                if any(k in type_name for k in ("product", "drug", "medicalentity", "medicinalproduct", "medicalwebpage")):
                    records.append(item)
        except Exception:
            continue

    return records


def extract_1mg_embedded_state(raw_html: str) -> Optional[Dict[str, Any]]:
    """
    Extracts embedded JSON state from Tata 1mg pages (window.__INITIAL_STATE__ or productConfig).
    Uses json.JSONDecoder().raw_decode to reliably parse objects terminated before subsequent JS code.
    """
    # 1. Look for window.__INITIAL_STATE__ or window.__PRELOADED_STATE__
    for marker in ("window.__INITIAL_STATE__", "window.__PRELOADED_STATE__"):
        idx = raw_html.find(marker)
        if idx != -1:
            eq_idx = raw_html.find("=", idx)
            if eq_idx != -1:
                raw_substr = raw_html[eq_idx + 1:].lstrip()
                try:
                    data, _ = json.JSONDecoder().raw_decode(raw_substr)
                    if isinstance(data, dict):
                        return data
                except Exception as e:
                    logger.debug(f"JSON raw_decode failed for {marker}: {str(e)}")

    # 2. Regex fallback for productConfig
    config_match = re.search(r'productConfig["\']?\s*:\s*(\{.*?\})\s*,\s*["\']', raw_html, re.DOTALL)
    if config_match:
        try:
            return json.loads(config_match.group(1))
        except Exception:
            pass

    return None


def parse_dosage_and_strength(name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts dosage form (Injection, Tablet, Syrup, etc.) and strength (e.g. 40 mcg, 500 mg) from medicine title.
    """
    strength = None
    form = None

    strength_match = re.search(r'(\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|ml|iu|µg|%|w/v|w/w))', name, re.IGNORECASE)
    if strength_match:
        strength = strength_match.group(1).strip()

    forms = [
        "Injection", "Tablet", "Capsule", "Syrup", "Ointment", "Cream", "Gel",
        "Suspension", "Drops", "Inhaler", "Spray", "Vial", "Ampoule", "Lotion",
        "Powder", "Patch", "Solution", "Oral Solution"
    ]
    for f in forms:
        if re.search(rf'\b{f}s?\b', name, re.IGNORECASE):
            form = f
            break

    return strength, form


def is_junk_container(elem: Tag) -> bool:
    """
    Returns True if an element is part of navigation, footer, promotional banners,
    substitutes/alternatives, or recommendation carousels.
    """
    classes_and_id = " ".join(elem.get("class") or []) + " " + (elem.get("id") or "")
    classes_lower = classes_and_id.lower()
    for kw in (
        "substitute", "alternative", "recommend", "carousel", "related",
        "footer", "nav", "header", "banner", "promo", "sidebar", "ad",
        "download", "faq", "social", "offer", "discount", "coupon"
    ):
        if kw in classes_lower:
            return True
    return False


def extract_sections_under_headings(soup: BeautifulSoup, primary_name: str) -> Dict[str, str]:
    """
    Extracts structured body content under medical section headings from DOM.
    Excludes junk containers, header elements, and promotional sections.
    """
    sections: Dict[str, str] = {}
    primary_lower = primary_name.lower().strip()

    heading_tags = soup.find_all(["h2", "h3"])

    for h in heading_tags:
        parent = h.parent
        if parent and is_junk_container(parent):
            continue

        h_text = " ".join(h.get_text().split()).strip()
        if not h_text or len(h_text) > 75:
            continue

        h_lower = h_text.lower()
        if h_lower == primary_lower:
            continue

        target_field = None
        if re.search(r"\bhow\s+.+\s+works?\b", h_lower) or "mechanism of action" in h_lower:
            target_field = "How It Works"
        elif re.search(r"\buses\s+(?:of\s+)?", h_lower) or "indications" in h_lower:
            target_field = "Uses"
        elif re.search(r"\bside\s*effects\s+(?:of\s+)?", h_lower) or "adverse reactions" in h_lower:
            target_field = "Side Effects"
        elif re.search(r"\bhow\s+to\s+(?:use|take)\b", h_lower) or "directions for use" in h_lower or "direction for use" in h_lower:
            target_field = "How to Use"
        elif re.search(r"\bbenefits\s+(?:of\s+)?", h_lower):
            target_field = "Benefits"
        elif "storage" in h_lower or "how to store" in h_lower:
            target_field = "Storage Instructions"
        else:
            for key, canon in ALLOWED_SECTION_HEADINGS.items():
                if re.search(rf"\b{re.escape(key)}\b", h_lower):
                    target_field = canon
                    break

        if not target_field:
            continue

        collected_texts: List[str] = []
        container = h.parent if h.parent and h.parent.name in ("div", "section") and len(h.parent.get_text(strip=True)) < len(h_text) + 20 else h

        for sib in container.find_next_siblings():
            if sib.name in ("h1", "h2", "h3", "h4") or sib.find(["h1", "h2", "h3", "h4"]):
                break
            if is_junk_container(sib):
                break

            if sib.name in ("ul", "ol"):
                items = [" ".join(li.get_text().split()) for li in sib.find_all("li")]
                if items:
                    collected_texts.append("; ".join(items))
            else:
                txt = " ".join(sib.get_text().split())
                if txt and len(txt) > 3:
                    if not any(p.search(txt) for p in JUNK_LABEL_PATTERNS):
                        collected_texts.append(txt)

            if len(collected_texts) >= 3:
                break

        if collected_texts and target_field not in sections:
            sections[target_field] = " \n\n".join(collected_texts)

    return sections


# ===========================================================================
# Master Extraction Workflow
# ===========================================================================

def extract_medicine_batch_from_html(
    raw_html: str,
    source_url: str,
    page_title: str,
    extracted_at: Optional[str] = None,
) -> MedicineBatch:
    """
    Extracts dynamic medicine records from raw HTML and structured DOM.
    Maps fields into consistent, standardized schema without column explosion.
    Applies comprehensive validation layer before persisting records.
    """
    if extracted_at is None:
        extracted_at = datetime.now(timezone.utc).isoformat()

    warnings: List[str] = []

    # Clean non-medicine URLs immediately
    url_lower = source_url.lower()
    for kw in (
        "/cancer-care", "/subscription", "/prescription-order", "/done-in-one",
        "/order-with-prescription", "/consult-doctor", "/care-plan",
        "/drugs-all-medicines", "/drugs-faq", "/all-diseases", "/articles"
    ):
        if kw in url_lower:
            logger.info(f"Skipping non-medicine URL: {source_url}")
            return MedicineBatch(records=[], all_discovered_fields=STANDARD_MASTER_COLUMNS, total_records=0)

    # 1. Parse DOM and strip code/style/script tags to prevent CSS contamination
    soup = BeautifulSoup(raw_html, "html.parser")
    for script_tag in soup(["script", "style", "noscript", "svg"]):
        script_tag.decompose()

    # Seed medicine name from H1 or page title
    h1 = soup.find("h1")
    primary_name = " ".join(h1.get_text().split()) if h1 else page_title.split("|")[0].split("-")[0].strip()
    primary_name = primary_name.replace("Buy ", "").replace(" Online", "").strip()

    # 2. Extract Embedded JSON / State (Tata 1mg specific)
    embedded_data = extract_1mg_embedded_state(raw_html)

    # 3. Extract JSON-LD Schema
    json_ld_products = extract_json_ld_medicine_data(raw_html)

    # Candidate attributes storage
    cand_comp: Optional[str] = None
    cand_marketer: Optional[str] = None
    cand_manufacturer: Optional[str] = None
    cand_storage: Optional[str] = None
    cand_mrp: Optional[str] = None
    cand_price: Optional[str] = None
    cand_pack_size: Optional[str] = None
    cand_pack_quantity: Optional[str] = None
    cand_drug_schedule: Optional[str] = None
    cand_tags: Optional[str] = None
    cand_safety_advice: Optional[str] = None
    cand_rx: Optional[str] = None
    cand_brand: Optional[str] = None
    cand_sections: Dict[str, str] = {}
    extra_specs: Dict[str, str] = {}

    primary_raw_labels: Dict[str, str] = {}

    # Ingest from Tata 1mg embedded state
    if embedded_data:
        try:
            dpr = embedded_data.get("drugPageReducer") or embedded_data
            static_data = dpr.get("staticData") or {}
            dynamic_data = dpr.get("dynamicData") or {}

            # Name from pageTitleData
            title_data = static_data.get("pageTitleData") or {}
            if title_data.get("header"):
                primary_name = str(title_data["header"]).strip()

            # Composition from pageTitleData or generalInformation
            if isinstance(title_data.get("composition"), dict):
                cand_comp = title_data["composition"].get("displayText")
            if not cand_comp:
                for attr in static_data.get("generalInformation", {}).get("attributesData", []):
                    if attr.get("label") == "Contains":
                        cand_comp = attr.get("value")
                        break

            # Marketer from pageTitleData or generalInformation
            if isinstance(title_data.get("marketersDetails"), dict):
                cand_marketer = title_data["marketersDetails"].get("displayText")
            if not cand_marketer:
                for attr in static_data.get("generalInformation", {}).get("attributesData", []):
                    if attr.get("label") == "Marketer":
                        cand_marketer = attr.get("value")
                        break

            # Manufacturer: ONLY from explicit manufacturerInfo or sku.manufacturer
            mfg_info = static_data.get("manufacturerInfo")
            if isinstance(mfg_info, dict) and mfg_info.get("name"):
                cand_manufacturer = mfg_info.get("name")
            if not cand_manufacturer:
                sku_mfg = static_data.get("sku", {}).get("manufacturer")
                if isinstance(sku_mfg, dict) and sku_mfg.get("name"):
                    cand_manufacturer = sku_mfg.get("name")

            # Storage Instructions from generalInformation
            for attr in static_data.get("generalInformation", {}).get("attributesData", []):
                if attr.get("label") == "Storage":
                    cand_storage = attr.get("value")
                    break
            if not cand_storage and static_data.get("storageInstructions"):
                cand_storage = str(static_data["storageInstructions"])

            # MRP & Price from dynamic priceBox mixpanelData or priceList
            price_box = dynamic_data.get("priceBox") or {}
            mixpanel = price_box.get("mixpanelData") or {}
            if mixpanel.get("mrp") is not None:
                cand_mrp = str(mixpanel["mrp"])
            if mixpanel.get("list_price") is not None:
                cand_price = str(mixpanel["list_price"])

            if not cand_mrp or not cand_price:
                price_list = price_box.get("priceList") or []
                if price_list and isinstance(price_list, list):
                    first_p = price_list[0]
                    if not cand_mrp and isinstance(first_p.get("mrp"), dict):
                        cand_mrp = first_p["mrp"].get("price")
                    if not cand_price and isinstance(first_p.get("discount"), dict):
                        cand_price = first_p["discount"].get("price")

            # Pack Size & Pack Quantity (for the active selected variant)
            price_data = dynamic_data.get("priceData") or static_data.get("priceData") or dpr.get("priceData") or {}
            pack_sizes = price_data.get("packSizes")
            if isinstance(pack_sizes, list):
                for ps in pack_sizes:
                    if isinstance(ps, dict) and ps.get("active"):
                        cand_pack_size = str(ps.get("size") or ps.get("name") or "").strip()
                        cand_pack_quantity = cand_pack_size
                        break
                if not cand_pack_size and pack_sizes and isinstance(pack_sizes[0], dict):
                    cand_pack_size = str(pack_sizes[0].get("size") or pack_sizes[0].get("name") or "").strip()
                    cand_pack_quantity = cand_pack_size
            elif pack_sizes:
                cand_pack_size = str(pack_sizes).strip()
                cand_pack_quantity = cand_pack_size
            elif static_data.get("sku", {}).get("packSize") or dpr.get("sku", {}).get("packSize"):
                sku_ps = static_data.get("sku", {}).get("packSize") or dpr.get("sku", {}).get("packSize")
                cand_pack_size = str(sku_ps).strip()
                cand_pack_quantity = cand_pack_size

            # Prescription Required & Explicit Drug Schedule
            rx_obj = (
                static_data.get("sku", {}).get("summary", {}).get("prescription_required")
                or dpr.get("sku", {}).get("summary", {}).get("prescription_required")
            )
            schema_rx = static_data.get("metaData", {}).get("schema", {}).get("drug", {}).get("prescriptionStatus")
            if rx_obj or (schema_rx and "prescription" in str(schema_rx).lower()):
                cand_rx = "Yes"
            else:
                cand_rx = "No"

            # Explicit Drug Schedule (strictly extracted only when explicitly identified)
            if isinstance(rx_obj, dict):
                cand_drug_schedule = extract_explicit_drug_schedule(rx_obj.get("header")) or extract_explicit_drug_schedule(rx_obj.get("description"))
            elif rx_obj:
                cand_drug_schedule = extract_explicit_drug_schedule(rx_obj)

            # Product Tags
            raw_tags = (
                static_data.get("productTags")
                or dpr.get("productTags")
                or static_data.get("sku", {}).get("tags")
                or dpr.get("sku", {}).get("tags")
                or static_data.get("badges")
                or dpr.get("badges")
            )
            if raw_tags:
                cand_tags = extract_and_sanitize_tags(raw_tags)

            # Clinical sections
            for sec_key, target_name in [
                ("productUses", "Uses"),
                ("productBenefits", "Benefits"),
                ("sideEffect", "Side Effects"),
                ("howToUse", "How to Use"),
                ("howWorks", "How It Works"),
            ]:
                sec_obj = static_data.get(sec_key) or dpr.get(sec_key)
                if isinstance(sec_obj, dict) and sec_obj.get("content"):
                    clean_text = clean_html_section(sec_obj["content"])
                    if clean_text:
                        cand_sections[target_name] = clean_text

            # Additional Specifications from Fact Box
            for attr in (static_data.get("factBoxData") or dpr.get("factBoxData") or {}).get("attributesData", []):
                lbl = attr.get("label") or attr.get("ga_label")
                v = attr.get("value")
                if lbl and v:
                    extra_specs[lbl.strip()] = str(v).strip()
                    if not cand_drug_schedule and "schedule" in str(lbl).lower():
                        cand_drug_schedule = extract_explicit_drug_schedule(v)

            # Safety Advice: Extract structured warnings and preserve subsections
            safety_lines: List[str] = []
            safety_advice_obj = static_data.get("safetyAdvice") or dpr.get("safetyAdvice") or {}
            for w in safety_advice_obj.get("warnings", []):
                topic = w.get("topic")
                if not topic:
                    cap_html = w.get("imageCaption", "")
                    cap_soup = BeautifulSoup(cap_html, "html.parser")
                    topic = cap_soup.get_text().strip()
                else:
                    topic = str(topic).strip()
                desc = str(w.get("description", "")).strip()
                warn_label = str(w.get("warning", "")).strip()
                if topic and desc:
                    extra_specs[f"Safety Advice - {topic}"] = desc
                    entry = f"{topic}: {warn_label} - {desc}" if warn_label else f"{topic}: {desc}"
                    safety_lines.append(entry)
            if safety_lines:
                cand_safety_advice = "\n".join(safety_lines)

        except Exception as e:
            logger.debug(f"Embedded 1mg state parsing note: {str(e)}")

    # Ingest from JSON-LD Schema
    for jld in json_ld_products:
        if not cand_comp and "activeIngredient" in jld:
            cand_comp = str(jld["activeIngredient"]).strip()

        if not cand_brand and "brand" in jld:
            brand_val = jld["brand"].get("name") if isinstance(jld["brand"], dict) else str(jld["brand"])
            if brand_val and brand_val.strip().lower() != primary_name.lower():
                cand_brand = brand_val.strip()

        if not cand_marketer and "marketer" in jld:
            mkt_val = jld["marketer"].get("legalName") or jld["marketer"].get("name") if isinstance(jld["marketer"], dict) else str(jld["marketer"])
            if mkt_val:
                cand_marketer = mkt_val.strip()

        if not cand_price and "offers" in jld:
            offers = jld["offers"] if isinstance(jld["offers"], list) else [jld["offers"]]
            for off in offers:
                if isinstance(off, dict) and "price" in off:
                    cand_price = str(off["price"]).strip()
                    break

    # Ingest from Definition Lists (<dl><dt>...<dd>...) and Tables
    for dl in soup.find_all("dl"):
        if is_junk_container(dl):
            continue
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            raw_k = dt.get_text().strip()
            raw_v = dd.get_text().strip()
            norm_k, _ = normalize_field_name(raw_k)
            if not norm_k or not raw_v:
                continue
            if norm_k == "Brand" and not cand_brand:
                cand_brand = raw_v
            elif norm_k == "Manufacturer" and not cand_manufacturer:
                cand_manufacturer = raw_v
            elif norm_k == "Marketer" and not cand_marketer:
                cand_marketer = raw_v
            elif norm_k == "Active Ingredient / Composition" and not cand_comp:
                cand_comp = raw_v
            elif norm_k == "Pack Size" and not cand_pack_size:
                cand_pack_size = raw_v
            elif norm_k == "Pack Quantity" and not cand_pack_quantity:
                cand_pack_quantity = raw_v
            elif norm_k == "Drug Schedule" and not cand_drug_schedule:
                cand_drug_schedule = extract_explicit_drug_schedule(raw_v)
            elif norm_k == "Tags" and not cand_tags:
                cand_tags = extract_and_sanitize_tags(raw_v)
            elif norm_k == "Safety Advice" and not cand_safety_advice:
                cand_safety_advice = raw_v
            elif norm_k == "Price" and not cand_price:
                cand_price = raw_v
            elif norm_k == "MRP" and not cand_mrp:
                cand_mrp = raw_v
            else:
                extra_specs[norm_k] = raw_v

    for table in soup.find_all("table"):
        if is_junk_container(table):
            continue
        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if th and td:
                raw_k = th.get_text().strip()
                raw_v = td.get_text().strip()
                norm_k, _ = normalize_field_name(raw_k)
                if not norm_k or not raw_v:
                    continue
                if norm_k == "Brand" and not cand_brand:
                    cand_brand = raw_v
                elif norm_k == "Manufacturer" and not cand_manufacturer:
                    cand_manufacturer = raw_v
                elif norm_k == "Marketer" and not cand_marketer:
                    cand_marketer = raw_v
                elif norm_k == "Active Ingredient / Composition" and not cand_comp:
                    cand_comp = raw_v
                elif norm_k == "Pack Size" and not cand_pack_size:
                    cand_pack_size = raw_v
                elif norm_k == "Pack Quantity" and not cand_pack_quantity:
                    cand_pack_quantity = raw_v
                elif norm_k == "Drug Schedule" and not cand_drug_schedule:
                    cand_drug_schedule = extract_explicit_drug_schedule(raw_v)
                elif norm_k == "Tags" and not cand_tags:
                    cand_tags = extract_and_sanitize_tags(raw_v)
                elif norm_k == "Safety Advice" and not cand_safety_advice:
                    cand_safety_advice = raw_v
                elif norm_k == "Price" and not cand_price:
                    cand_price = raw_v
                elif norm_k == "MRP" and not cand_mrp:
                    cand_mrp = raw_v
                else:
                    extra_specs[norm_k] = raw_v

    # Clean DOM Fallback for missing fields (using cleaned soup)
    cleaned_text = soup.get_text("\n")

    # DOM Composition
    if not cand_comp:
        comp_m = re.search(r'(?:salt\s*composition|composition|active\s*ingredient)\s*[:\-]\s*([^\n\r]{3,120})', cleaned_text, re.IGNORECASE)
        if comp_m:
            cand_comp = comp_m.group(1).strip()

    # DOM Marketer
    if not cand_marketer:
        mkt_m = re.search(r'(?:marketer\s*details|marketed\s*by|marketer)\s*[:\-]\s*([^\n\r]{3,100})', cleaned_text, re.IGNORECASE)
        if mkt_m:
            cand_marketer = mkt_m.group(1).strip()

    # DOM Manufacturer
    if not cand_manufacturer:
        mfg_m = re.search(r'(?:manufactured\s*by|manufacturer\s*details|manufacturer)\s*[:\-]\s*([^\n\r]{3,100})', cleaned_text, re.IGNORECASE)
        if mfg_m:
            cand_manufacturer = mfg_m.group(1).strip()

    # DOM Pack Size
    if not cand_pack_size:
        pack_m = re.search(r'(?:pack\s*size|packaging)\s*[:\-]\s*([^\n\r]{3,60})', cleaned_text, re.IGNORECASE)
        if not pack_m:
            pack_m = re.search(r'\b((?:strip|bottle|box|vial|tube|pack)\s+of\s+\d+\s+[a-zA-Z]+|\d+\s+tablets|\d+\s+capsules|\d+\s+ml\s+syrup)\b', cleaned_text, re.IGNORECASE)
        if pack_m:
            cand_pack_size = pack_m.group(1).strip()

    # DOM MRP
    if not cand_mrp:
        mrp_m = re.search(r'MRP\s*[:\-₹]?\s*(?:₹|Rs\.?)?\s*(\d+(?:\.\d{1,2})?)', cleaned_text, re.IGNORECASE)
        if mrp_m:
            cand_mrp = mrp_m.group(1).strip()

    # DOM Price
    if not cand_price:
        price_m = re.search(r'(?:₹|INR|Rs\.?)\s*(\d+(?:,\d+)*(?:\.\d{1,2})?)', cleaned_text)
        if price_m:
            cand_price = price_m.group(1).strip()

    # DOM Headings for Medical Sections
    dom_sections = extract_sections_under_headings(soup, primary_name)
    for sec_name, sec_text in dom_sections.items():
        if sec_name not in cand_sections:
            cand_sections[sec_name] = sec_text

    # DOM Storage
    if not cand_storage and "Storage Instructions" in cand_sections:
        cand_storage = cand_sections["Storage Instructions"]

    # DOM Explicit Drug Schedule (strictly explicit; no guessing or inferring)
    if not cand_drug_schedule:
        for badge in soup.find_all(class_=re.compile(r"prescription|schedule|drug|badge|header|meta", re.IGNORECASE)):
            if not is_junk_container(badge):
                sched = extract_explicit_drug_schedule(badge.get_text())
                if sched:
                    cand_drug_schedule = sched
                    break

    # DOM Pack Quantity
    if not cand_pack_quantity:
        pq_m = re.search(r'(?:pack\s*quantity|package\s*quantity|net\s*quantity|quantity)\s*[:\-]\s*([^\n\r]{2,50})', cleaned_text, re.IGNORECASE)
        if pq_m:
            cand_pack_quantity = pq_m.group(1).strip()
        elif cand_pack_size:
            cand_pack_quantity = cand_pack_size

    # DOM Tags
    if not cand_tags:
        dom_tags = []
        for chip in soup.find_all(class_=re.compile(r"Chip__chip|DrugHeader__tag|product-tag|badge", re.IGNORECASE)):
            if not is_junk_container(chip):
                txt = chip.get_text().strip()
                if txt:
                    dom_tags.append(txt)
        if dom_tags:
            cand_tags = extract_and_sanitize_tags(dom_tags)

    # DOM Safety Advice fallback
    if not cand_safety_advice:
        dom_sa = dom_sections.get("Safety Advice") or dom_sections.get("Warnings & Precautions")
        if dom_sa:
            cand_safety_advice = dom_sa

    # 4. Apply Validation Layer
    val_comp = validate_composition(cand_comp)
    if not val_comp and cand_comp:
        warnings.append(f"Composition validation discarded value: '{cand_comp[:40]}'")

    val_marketer = cand_marketer if is_valid_company_name(cand_marketer) else None
    if not val_marketer and cand_marketer:
        warnings.append(f"Marketer validation discarded value: '{cand_marketer[:40]}'")

    val_manufacturer = cand_manufacturer if is_valid_company_name(cand_manufacturer) else None
    if not val_manufacturer and cand_manufacturer:
        warnings.append(f"Manufacturer validation discarded value: '{cand_manufacturer[:40]}'")

    val_mrp, val_price = validate_mrp_and_price(cand_mrp, cand_price)

    val_storage = validate_storage_instructions(cand_storage)
    if not val_storage and cand_storage:
        warnings.append(f"Storage instructions validation discarded value: '{cand_storage[:40]}'")

    # Strength & Dosage Form
    derived_strength, derived_form = parse_dosage_and_strength(primary_name)
    if not derived_strength and val_comp:
        comp_str, _ = parse_dosage_and_strength(str(val_comp))
        derived_strength = comp_str

    # Availability
    if re.search(r'\b(?:out of stock|currently unavailable|not for sale)\b', cleaned_text, re.IGNORECASE):
        availability = "Out of Stock"
    else:
        availability = "In Stock"

    # Prescription Required
    if cand_rx:
        rx_val = cand_rx
    else:
        rx_flag = bool(re.search(r'\b(?:prescription required|schedule h|rx only)\b', cleaned_text, re.IGNORECASE))
        rx_val = "Yes" if rx_flag else "No"

    # Assemble Primary Attributes Map
    primary_attributes: Dict[str, Any] = {
        "Medicine Name": primary_name,
        "Brand": cand_brand or "",
        "Active Ingredient / Composition": val_comp or "",
        "Strength": derived_strength or "",
        "Dosage Form": derived_form or "",
        "Pack Size": cand_pack_size or "",
        "Pack Quantity": cand_pack_quantity or "",
        "Manufacturer": val_manufacturer or "",
        "Marketer": val_marketer or "",
        "Price": val_price or "",
        "MRP": val_mrp or "",
        "Availability": availability,
        "Prescription Required": rx_val,
        "Drug Schedule": cand_drug_schedule or "",
        "Uses": cand_sections.get("Uses", ""),
        "Benefits": cand_sections.get("Benefits", ""),
        "Side Effects": cand_sections.get("Side Effects", ""),
        "How to Use": cand_sections.get("How to Use", ""),
        "How It Works": cand_sections.get("How It Works", ""),
        "Safety Advice": cand_safety_advice or "",
        "Storage Instructions": val_storage or "",
        "Tags": cand_tags or "",
        "Product URL": source_url,
        "Extracted At": extracted_at,
        "Scrape Status": "Completed",
    }

    # Add extra specifications for the secondary sheet
    for spec_k, spec_v in extra_specs.items():
        if spec_k not in primary_attributes and spec_v:
            # Validate extra spec does not contain CSS or code
            if not any(tok in str(spec_v).lower() for tok in ("{", "}", "width:", "background:", "module__", "<style")):
                primary_attributes[spec_k] = spec_v

    # Raw label tracking
    primary_raw_labels = {k: k for k in primary_attributes}

    # Build MedicineRecord
    rec_id = MedicineRecord.generate_id(source_url, primary_name, derived_strength or "")

    primary_record = MedicineRecord(
        record_id=rec_id,
        medicine_name=primary_name,
        source_url=source_url,
        extracted_at=extracted_at,
        attributes=primary_attributes,
        raw_labels=primary_raw_labels,
        product_id=primary_attributes.get("Product ID"),
        brand=primary_attributes.get("Brand") or None,
        manufacturer=val_manufacturer,
        marketer=val_marketer,
        price=val_price,
        strength=derived_strength,
        dosage_form=derived_form,
        active_ingredients=val_comp,
        drug_schedule=cand_drug_schedule or None,
        pack_quantity=cand_pack_quantity or None,
        tags=cand_tags or None,
        safety_advice=cand_safety_advice or None,
        warnings=warnings,
        is_duplicate=False,
    )

    records = [primary_record]
    all_fields, new_unmapped = compute_batch_field_union([primary_record.model_dump()])

    # Combine standard fields with any dynamically discovered specifications,
    # placing dynamic fields before the trailing tracking columns
    batch_fields = list(all_fields)
    for extra_field in new_unmapped:
        if extra_field not in batch_fields:
            tracking_cols = {"Product URL", "Extracted At", "Scrape Status"}
            insert_pos = next((i for i, f in enumerate(batch_fields) if f in tracking_cols), len(batch_fields))
            batch_fields.insert(insert_pos, extra_field)

    return MedicineBatch(
        records=records,
        all_discovered_fields=batch_fields,
        new_fields=new_unmapped,
        total_records=1,
        unique_attributes_count=len(batch_fields),
        warnings=warnings,
    )
