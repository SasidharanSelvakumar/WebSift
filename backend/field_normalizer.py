import re
from typing import Dict, List, Set, Tuple

# Baseline canonical field definitions and their verified conservative aliases
# All aliases must be lowercase and stripped of punctuation for matching
CANONICAL_FIELD_ALIASES: Dict[str, Set[str]] = {
    "Medicine Name": {
        "medicine name", "drug name", "product name", "item name", "brand name", "name", "title"
    },
    "Brand": {
        "brand", "brand name", "trade name", "trademark"
    },
    "Price": {
        "mrp", "maximum retail price", "price", "cost", "price inr", "mrp inr", "our price", "discounted price", "rate"
    },
    "Manufacturer": {
        "manufactured by", "manufacturer", "manufacturer name", "maker", "produced by", "producer"
    },
    "Marketer": {
        "marketed by", "marketer", "marketer name", "marketer details", "marketed & distributed by", "distributor"
    },
    "Active Ingredients": {
        "composition", "active ingredients", "active ingredient", "salt composition", "salts", "generic name", "salt", "active salt"
    },
    "Strength": {
        "strength", "potency", "dosage strength", "concentration"
    },
    "Dosage Form": {
        "dosage form", "form", "presentation", "product form", "type"
    },
    "Pack Size": {
        "pack size", "package size", "pack quantity", "packaging", "quantity", "unit", "pack"
    },
    "Storage Instructions": {
        "storage", "storage instructions", "how to store", "store", "storage conditions"
    },
    "Uses": {
        "uses", "uses of", "therapeutic uses", "indications", "what is it used for", "benefits", "benefits of", "indication"
    },
    "How to Use": {
        "how to use", "direction for use", "directions for use", "administration", "how to take", "dosage and administration", "dosage"
    },
    "How it Works": {
        "how it works", "mechanism of action", "pharmacology", "mode of action", "how does it work"
    },
    "Side Effects": {
        "side effects", "side effects of", "adverse reactions", "common side effects", "adverse effects"
    },
    "Warnings & Precautions": {
        "warnings", "precautions", "safety advice", "warnings & precautions", "safety warnings", "special precautions"
    },
    "Drug Interactions": {
        "drug interactions", "interactions", "drug-drug interactions", "contraindications"
    },
    "Prescription Required": {
        "prescription required", "rx required", "prescription", "schedule h", "schedule h drug", "rx"
    },
    "Country of Origin": {
        "country of origin", "origin", "made in"
    },
    "Product ID": {
        "product id", "sku", "item code", "item id", "drug id"
    },
    "Discounts": {
        "discount", "discounts", "offer", "savings"
    },
    "Packaging Details": {
        "packaging details", "packaging type", "package details", "container"
    },
}

# Inverted index for fast deterministic lookup: alias -> canonical name
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in CANONICAL_FIELD_ALIASES.items():
    ALIAS_TO_CANONICAL[canonical.lower()] = canonical
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias.lower()] = canonical

# Logical priority ordering for column headers
PRIORITY_HEADER_ORDER = [
    "Medicine Name",
    "Brand",
    "Strength",
    "Dosage Form",
    "Active Ingredients",
    "Manufacturer",
    "Marketer",
    "Price",
    "Pack Size",
    "Prescription Required",
    "Uses",
    "How to Use",
    "How it Works",
    "Side Effects",
    "Storage Instructions",
    "Warnings & Precautions",
    "Drug Interactions",
    "Discounts",
    "Country of Origin",
    "Product ID",
]


def clean_label_string(raw_label: str) -> str:
    """
    Cleans label string: removes colon/dashes, trims, normalizes whitespace.
    """
    if not raw_label:
        return ""
    clean = re.sub(r"[:\-_/]+", " ", raw_label)
    return " ".join(clean.split()).strip()


def normalize_field_name(raw_label: str) -> Tuple[str, str]:
    """
    Conservatively normalizes field labels using verified aliases.
    If no confident alias match is found, formats cleanly as a distinct dynamic column.
    Returns: (canonical_or_custom_field_name, original_raw_label)
    """
    cleaned = clean_label_string(raw_label)
    lookup_key = cleaned.lower()

    # Exact alias match
    if lookup_key in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[lookup_key], raw_label

    # Secondary fuzzy check for common prefixes like "uses of XYZ" or "benefits of XYZ"
    for prefix in ("uses of", "benefits of", "side effects of", "how to use", "how to take", "safety advice for"):
        if lookup_key.startswith(prefix):
            if "uses" in prefix or "benefits" in prefix:
                return "Uses", raw_label
            if "side effects" in prefix:
                return "Side Effects", raw_label
            if "how to" in prefix:
                return "How to Use", raw_label
            if "safety" in prefix:
                return "Warnings & Precautions", raw_label

    # If unmapped, preserve as dynamic attribute in Title Case
    # Do NOT merge with anything else to prevent data corruption
    words = cleaned.split()
    formatted = " ".join(w.capitalize() if not w.isupper() else w for w in words)
    return formatted or raw_label.strip(), raw_label


def compute_batch_field_union(records: List[Dict[str, any]]) -> Tuple[List[str], List[str]]:
    """
    Computes the ordered union of all distinct fields across all records in a batch.
    Returns: (all_discovered_fields, new_unmapped_fields)
    """
    all_fields_set: Set[str] = set()
    for rec in records:
        if rec.get("medicine_name"):
            all_fields_set.add("Medicine Name")
        if rec.get("brand"):
            all_fields_set.add("Brand")
        if rec.get("manufacturer"):
            all_fields_set.add("Manufacturer")
        if rec.get("marketer"):
            all_fields_set.add("Marketer")
        if rec.get("price"):
            all_fields_set.add("Price")
        if rec.get("strength"):
            all_fields_set.add("Strength")
        if rec.get("dosage_form"):
            all_fields_set.add("Dosage Form")
        if rec.get("active_ingredients"):
            all_fields_set.add("Active Ingredients")
        if rec.get("product_id"):
            all_fields_set.add("Product ID")

        attrs = rec.get("attributes", {})
        all_fields_set.update(attrs.keys())

    # Build ordered list:
    ordered_fields: List[str] = []
    
    # 1. Medicine Name is always the first column
    if "Medicine Name" in all_fields_set or any(r.get("medicine_name") for r in records):
        ordered_fields.append("Medicine Name")

    # 2. Standard priority headers present in the batch
    for header in PRIORITY_HEADER_ORDER:
        if header in all_fields_set and header not in ordered_fields:
            ordered_fields.append(header)

    # 3. Dynamic discovered fields sorted alphabetically
    remaining_fields = sorted(list(all_fields_set - set(ordered_fields) - {"Source URL", "Extracted At"}))
    new_unmapped_fields = [f for f in remaining_fields if f not in CANONICAL_FIELD_ALIASES]

    ordered_fields.extend(remaining_fields)

    # 4. Always append source tracking columns at the end
    if "Source URL" not in ordered_fields:
        ordered_fields.append("Source URL")
    if "Extracted At" not in ordered_fields:
        ordered_fields.append("Extracted At")

    return ordered_fields, new_unmapped_fields
