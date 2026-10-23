import pytest
from backend.field_normalizer import normalize_field_name, compute_batch_field_union, STANDARD_MASTER_COLUMNS
from backend.medicine_models import MedicineBatch, MedicineRecord


def test_field_normalization_and_alias_mapping():
    # MRP is kept as distinct MRP field
    canon, raw = normalize_field_name("MRP")
    assert canon == "MRP"
    assert raw == "MRP"

    # Maximum Retail Price -> MRP
    canon, raw = normalize_field_name("Maximum Retail Price")
    assert canon == "MRP"

    # Price / Our Price -> Price
    canon, raw = normalize_field_name("Our Price")
    assert canon == "Price"

    # Manufactured By -> Manufacturer
    canon, raw = normalize_field_name("Manufactured By")
    assert canon == "Manufacturer"

    # Marketed By -> Marketer (MUST BE KEPT SEPARATE FROM MANUFACTURER)
    canon_mkt, _ = normalize_field_name("Marketed By")
    canon_mfg, _ = normalize_field_name("Manufactured By")
    assert canon_mkt == "Marketer"
    assert canon_mfg == "Manufacturer"
    assert canon_mkt != canon_mfg

    # Active Ingredients / Composition -> Active Ingredient / Composition
    canon, _ = normalize_field_name("Salt Composition")
    assert canon == "Active Ingredient / Composition"

    # Pack Size & Pack Quantity
    canon_size, _ = normalize_field_name("Package Size")
    assert canon_size == "Pack Size"

    canon_qty, _ = normalize_field_name("Pack Quantity")
    assert canon_qty == "Pack Quantity"

    # Product names masquerading as headers are rejected
    rejected_name, _ = normalize_field_name("Aciloc 150 Tablet")
    assert rejected_name is None

    # Promotional junk is rejected
    rejected_promo, _ = normalize_field_name("Save More With Additional Offers")
    assert rejected_promo is None


def test_unseen_custom_field_discovery():
    # Legitimate non-standard clinical/storage attribute is normalized to Title Case
    canon, raw = normalize_field_name("Special Bioavailability Ratio")
    assert canon == "Special Bioavailability Ratio"
    assert raw == "Special Bioavailability Ratio"

    canon2, raw2 = normalize_field_name("refrigeration_requirements")
    assert canon2 == "Refrigeration Requirements"


def test_batch_union_calculation():
    # Medicine A
    rec_a = {
        "Medicine Name": "Medicine Alpha",
        "attributes": {
            "Price": "₹150",
            "Strength": "500 mg",
            "Manufacturer": "Pharma Corp A",
        }
    }
    # Medicine B (introduces Side Effects and Storage Instructions)
    rec_b = {
        "Medicine Name": "Medicine Beta",
        "attributes": {
            "Price": "₹320",
            "Side Effects": "Nausea, Dizziness",
            "Storage Instructions": "Store below 25°C",
        }
    }
    # Medicine C (introduces Active Ingredient / Composition and unmapped clinical attribute)
    rec_c = {
        "Medicine Name": "Medicine Gamma",
        "attributes": {
            "Active Ingredient / Composition": "Amoxicillin",
            "Drug Interactions": "Avoid alcohol",
            "Manufacturer": "Pharma Corp C",
        }
    }

    all_fields, new_unmapped = compute_batch_field_union([rec_a, rec_b, rec_c])

    # Must contain standard 21 columns
    assert all_fields == STANDARD_MASTER_COLUMNS
    assert "Medicine Name" in all_fields
    assert "Price" in all_fields
    assert "Strength" in all_fields
    assert "Manufacturer" in all_fields
    assert "Side Effects" in all_fields
    assert "Storage Instructions" in all_fields
    assert "Active Ingredient / Composition" in all_fields

    # Extra legitimate specifications are routed to new_unmapped
    assert "Drug Interactions" in new_unmapped


def test_deterministic_record_id():
    id1 = MedicineRecord.generate_id("https://example.com/drug-1", "Aspirin", "100 mg")
    id2 = MedicineRecord.generate_id("https://example.com/drug-1", "Aspirin", "100 mg")
    id3 = MedicineRecord.generate_id("https://example.com/drug-2", "Aspirin", "100 mg")
    
    assert id1 == id2  # Identical source and product generate identical ID
    assert id1 != id3  # Different source produces different ID
