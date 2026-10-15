import pytest
from backend.field_normalizer import normalize_field_name, compute_batch_field_union
from backend.medicine_models import MedicineBatch, MedicineRecord


def test_field_normalization_and_alias_mapping():
    # MRP -> Price
    canon, raw = normalize_field_name("MRP")
    assert canon == "Price"
    assert raw == "MRP"

    # Maximum Retail Price -> Price
    canon, raw = normalize_field_name("Maximum Retail Price")
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

    # Active Ingredients / Composition
    canon, _ = normalize_field_name("Salt Composition")
    assert canon == "Active Ingredients"

    # Pack Size
    canon, _ = normalize_field_name("Pack Quantity")
    assert canon == "Pack Size"


def test_unseen_custom_field_discovery():
    # An unfamiliar attribute must NOT be merged with standard fields or discarded
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
    # Medicine C (introduces Active Ingredients and Drug Interactions)
    rec_c = {
        "Medicine Name": "Medicine Gamma",
        "attributes": {
            "Active Ingredients": "Amoxicillin",
            "Drug Interactions": "Avoid alcohol",
            "Manufacturer": "Pharma Corp C",
        }
    }

    all_fields, new_unmapped = compute_batch_field_union([rec_a, rec_b, rec_c])

    # Must contain the union of all attributes
    assert "Medicine Name" in all_fields or "Price" in all_fields
    assert "Price" in all_fields
    assert "Strength" in all_fields
    assert "Manufacturer" in all_fields
    assert "Side Effects" in all_fields
    assert "Storage Instructions" in all_fields
    assert "Active Ingredients" in all_fields
    assert "Drug Interactions" in all_fields

    # Source tracking columns present
    assert "Source URL" in all_fields
    assert "Extracted At" in all_fields


def test_deterministic_record_id():
    id1 = MedicineRecord.generate_id("https://example.com/drug-1", "Aspirin", "100 mg")
    id2 = MedicineRecord.generate_id("https://example.com/drug-1", "Aspirin", "100 mg")
    id3 = MedicineRecord.generate_id("https://example.com/drug-2", "Aspirin", "100 mg")
    
    assert id1 == id2  # Identical source and product generate identical ID
    assert id1 != id3  # Different source produces different ID
