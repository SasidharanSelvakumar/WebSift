import re
from typing import Dict, List, Optional, Set, Tuple

# Baseline canonical field definitions and their verified conservative aliases
CANONICAL_FIELD_ALIASES: Dict[str, Set[str]] = {
    "Medicine Name": {
        "medicine name", "drug name", "product name", "item name", "brand name", "name", "title"
    },
    "Brand": {
        "brand", "brand name", "trade name", "trademark"
    },
    "Active Ingredient / Composition": {
        "composition", "active ingredients", "active ingredient", "salt composition",
        "salts", "generic name", "salt", "active salt", "active ingredient / composition"
    },
    "Strength": {
        "strength", "potency", "dosage strength", "concentration"
    },
    "Dosage Form": {
        "dosage form", "form", "presentation", "product form", "type"
    },
    "Pack Size": {
        "pack size", "package size", "packaging", "packaging details", "pack", "unit"
    },
    "Pack Quantity": {
        "pack quantity", "package quantity", "quantity", "net quantity", "pack count", "item count"
    },
    "Manufacturer": {
        "manufactured by", "manufacturer", "manufacturer name", "maker", "produced by", "producer"
    },
    "Marketer": {
        "marketed by", "marketer", "marketer name", "marketer details", "marketed & distributed by", "distributor"
    },
    "Price": {
        "price", "cost", "price inr", "our price", "discounted price", "rate", "selling price"
    },
    "MRP": {
        "mrp", "maximum retail price", "mrp inr", "retail price"
    },
    "Availability": {
        "availability", "in stock", "stock status", "item availability"
    },
    "Prescription Required": {
        "prescription required", "rx required", "prescription", "rx"
    },
    "Drug Schedule": {
        "drug schedule", "schedule", "prescription schedule", "medicine schedule"
    },
    "Uses": {
        "uses", "uses of", "therapeutic uses", "indications", "what is it used for", "indication"
    },
    "Benefits": {
        "benefits", "benefits of", "key benefits"
    },
    "Side Effects": {
        "side effects", "side effects of", "adverse reactions", "common side effects", "adverse effects"
    },
    "How to Use": {
        "how to use", "direction for use", "directions for use", "administration", "how to take",
        "dosage and administration", "dosage"
    },
    "How It Works": {
        "how it works", "mechanism of action", "pharmacology", "mode of action", "how does it work"
    },
    "Storage Instructions": {
        "storage", "storage instructions", "how to store", "store", "storage conditions"
    },
    "Safety Advice": {
        "safety advice", "warnings & precautions", "safety warnings", "safety precautions", "warnings", "precautions"
    },
    "Tags": {
        "tags", "product tags", "labels", "badges", "product badges", "categories tags"
    },
    "Drug Interactions": {
        "drug interactions", "interactions", "drug-drug interactions", "contraindications"
    },
    "Product Description": {
        "product description", "description", "product introduction", "overview", "about"
    },
    "Product ID": {
        "product id", "sku", "item code", "item id", "drug id"
    },
}

# Inverted index for fast deterministic lookup: alias -> canonical name
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in CANONICAL_FIELD_ALIASES.items():
    ALIAS_TO_CANONICAL[canonical.lower()] = canonical
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias.lower()] = canonical

# Standard columns for the clean master dataset
STANDARD_MASTER_COLUMNS = [
    "Medicine Name",
    "Brand",
    "Active Ingredient / Composition",
    "Strength",
    "Dosage Form",
    "Pack Size",
    "Pack Quantity",
    "Manufacturer",
    "Marketer",
    "Price",
    "MRP",
    "Availability",
    "Prescription Required",
    "Drug Schedule",
    "Uses",
    "Benefits",
    "Side Effects",
    "How to Use",
    "How It Works",
    "Safety Advice",
    "Storage Instructions",
    "Tags",
    "Product URL",
    "Extracted At",
    "Scrape Status",
]

# Patterns for labels that are promotional, navigation, or website junk and must be purged
JUNK_LABEL_PATTERNS = [
    re.compile(r"save\s*more|cashback|coupon|offer|discount|promo|deal", re.IGNORECASE),
    re.compile(r"did\s*you\s*know|cancer\s*care|download\s*app|connect\s*with", re.IGNORECASE),
    re.compile(r"substitute|alternative\s*brand|people\s*also\s*viewed|similar\s*product", re.IGNORECASE),
    re.compile(r"customer\s*reviews?|faq|feedback|disclaimer|quick\s*links|popular\s*categories", re.IGNORECASE),
    re.compile(r"editorial\s*policy|author|reviewed\s*by|our\s*services|about\s*us", re.IGNORECASE),
]

# Patterns detecting that a label is actually a medicine title / formulation (not a valid column)
MEDICINE_NAME_LABEL_PATTERN = re.compile(
    r"\b(?:tablet|capsule|syrup|injection|ointment|gel|suspension|drops|inhaler|spray|cream|solution)\b",
    re.IGNORECASE,
)


def clean_label_string(raw_label: str) -> str:
    """
    Cleans label string: removes colon/dashes, trims, normalizes whitespace.
    """
    if not raw_label:
        return ""
    clean = re.sub(r"[:\-_/]+", " ", raw_label)
    return " ".join(clean.split()).strip()


def normalize_field_name(raw_label: str) -> Tuple[Optional[str], str]:
    """
    Conservatively normalizes field labels using verified aliases.
    Filters out promotional banners, footer sections, and medicine titles masquerading as headers.
    Returns: (canonical_field_name_or_None, original_raw_label)
    """
    cleaned = clean_label_string(raw_label)
    lookup_key = cleaned.lower()

    if not lookup_key:
        return None, raw_label

    # Reject junk / promotional / footer labels
    for pat in JUNK_LABEL_PATTERNS:
        if pat.search(lookup_key):
            return None, raw_label

    # Exact alias match
    if lookup_key in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[lookup_key], raw_label

    # Regex checks for variations like "How Aciloc 150 Tablet Works"
    if re.search(r"\bhow\s+.+\s+works?\b", lookup_key) or lookup_key.startswith("mechanism of action"):
        return "How It Works", raw_label

    if re.search(r"\buses\s+of\b", lookup_key):
        return "Uses", raw_label

    if re.search(r"\bbenefits\s+of\b", lookup_key):
        return "Benefits", raw_label

    if re.search(r"\bside\s*effects\s+of\b", lookup_key):
        return "Side Effects", raw_label

    if re.search(r"\bhow\s+to\s+(?:use|take)\b", lookup_key):
        return "How to Use", raw_label

    if lookup_key.startswith("safety advice for") or lookup_key.startswith("precautions for") or lookup_key.startswith("warnings for"):
        return "Safety Advice", raw_label

    if lookup_key.startswith("storage of") or lookup_key.startswith("how to store"):
        return "Storage Instructions", raw_label

    if lookup_key.startswith("composition of") or lookup_key.startswith("salt composition of"):
        return "Active Ingredient / Composition", raw_label

    if lookup_key.startswith("pack size of") or lookup_key.startswith("packaging of"):
        return "Pack Size", raw_label

    if lookup_key.startswith("schedule of") or lookup_key.startswith("drug schedule of"):
        return "Drug Schedule", raw_label

    if lookup_key.startswith("pack quantity of") or lookup_key.startswith("quantity of"):
        return "Pack Quantity", raw_label

    if lookup_key.startswith("tags of") or lookup_key.startswith("product tags of"):
        return "Tags", raw_label

    # If the label looks like a medicine name (e.g. contains dosage form or is too long), reject it
    if MEDICINE_NAME_LABEL_PATTERN.search(lookup_key) or len(cleaned) > 50:
        return None, raw_label

    # Format remaining unmapped label in Title Case
    words = cleaned.split()
    formatted = " ".join(w.capitalize() if not w.isupper() else w for w in words)
    return formatted or raw_label.strip(), raw_label


def compute_batch_field_union(records: List[Dict[str, any]]) -> Tuple[List[str], List[str]]:
    """
    Computes standard headers for the master products dataset and dynamically discovered specifications.
    Standardizes known field aliases to prevent duplicate columns when a standard field
    and a dynamic specification represent the same information.
    Preserves genuine dynamic specifications present across products.
    Returns: (ordered_fields, extra_unmapped_fields)
    """
    # Base set of standard columns
    ordered_fields = list(STANDARD_MASTER_COLUMNS)
    standard_set = set(ordered_fields)

    # Check for legitimate extra clinical/safety specifications
    all_extra: Set[str] = set()
    for rec in records:
        attrs = rec.get("attributes", {})
        for k in list(attrs.keys()):
            if k in standard_set or k in ("Source URL", "Extracted At", "Scrape Status"):
                continue

            # Check if this dynamic attribute represents a standard field alias
            canon_name, _ = normalize_field_name(k)
            if canon_name and canon_name in standard_set:
                # Same information as standard field: populate standard field if missing/empty
                if attrs.get(k) and not attrs.get(canon_name):
                    attrs[canon_name] = attrs[k]
                # Avoid duplicate columns
                continue

            # Genuine unmapped dynamic specification (e.g. Therapeutic Class, Bioavailability)
            candidate_key = canon_name or k
            if not MEDICINE_NAME_LABEL_PATTERN.search(candidate_key) and not any(p.search(candidate_key) for p in JUNK_LABEL_PATTERNS):
                all_extra.add(candidate_key)

    extra_sorted = sorted(list(all_extra))
    return ordered_fields, extra_sorted
