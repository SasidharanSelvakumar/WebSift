import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class MedicineRecord(BaseModel):
    """
    Flexible medicine data record capable of preserving arbitrary dynamic attributes.
    """
    record_id: str = Field(..., description="Deterministic unique identifier for idempotency and duplicate checking")
    medicine_name: str = Field(..., description="The primary medicine or product name")
    source_url: str = Field(..., description="URL from which this medicine was extracted")
    extracted_at: str = Field(..., description="ISO-8601 extraction timestamp")
    
    # Dynamic attributes dictionary: maps attribute names to values (str, int, float, list, dict)
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dynamic key-value attributes discovered during extraction",
    )
    
    # Original raw labels preserved for traceability
    raw_labels: Dict[str, str] = Field(
        default_factory=dict,
        description="Original source labels prior to normalization",
    )
    
    # Optional metadata & identifiers
    product_id: Optional[str] = Field(default=None, description="Source SKU or product ID")
    brand: Optional[str] = Field(default=None, description="Brand name if distinct from medicine name")
    manufacturer: Optional[str] = Field(default=None, description="Manufacturing company")
    marketer: Optional[str] = Field(default=None, description="Marketing company")
    price: Optional[str] = Field(default=None, description="Price / MRP")
    strength: Optional[str] = Field(default=None, description="Potency / dosage strength (e.g. 500 mg, 40 mcg)")
    dosage_form: Optional[str] = Field(default=None, description="Dosage form (e.g. Tablet, Injection, Syrup)")
    active_ingredients: Optional[str] = Field(default=None, description="Active composition / salt")
    drug_schedule: Optional[str] = Field(default=None, description="Explicitly stated drug schedule (e.g. Schedule H, Schedule H1, Schedule X)")
    pack_quantity: Optional[str] = Field(default=None, description="Stated package size or quantity for the active variant")
    tags: Optional[str] = Field(default=None, description="Explicit product tags or labels")
    safety_advice: Optional[str] = Field(default=None, description="Medicine-specific safety advice and precautions by subsection")
    
    # Data quality & duplicate flags
    warnings: List[str] = Field(default_factory=list, description="Data quality or extraction warnings")
    is_duplicate: bool = Field(default=False, description="Flagged as a duplicate within the batch or target")

    @classmethod
    def generate_id(cls, source_url: str, medicine_name: str, variant: str = "") -> str:
        """
        Generates a deterministic unique ID based on source URL, medicine name, and variant.
        """
        payload = f"{source_url.strip().lower()}|{medicine_name.strip().lower()}|{variant.strip().lower()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class MedicineBatch(BaseModel):
    """
    A batch of extracted medicine records with dynamic field union calculation.
    """
    records: List[MedicineRecord] = Field(default_factory=list)
    all_discovered_fields: List[str] = Field(
        default_factory=list,
        description="The ordered union of all distinct fields across all records in the batch",
    )
    new_fields: List[str] = Field(
        default_factory=list,
        description="Fields discovered that are not in the standard baseline schema",
    )
    total_records: int = 0
    unique_attributes_count: int = 0
    warnings: List[str] = Field(default_factory=list)


class ExcelExportRequest(BaseModel):
    batch: MedicineBatch
    source_url: Optional[str] = None
    title: Optional[str] = "Medicine Data Export"


class MedicineCsvExportRequest(BaseModel):
    batch: MedicineBatch
    source_url: Optional[str] = None


class MedicineTxtExportRequest(BaseModel):
    batch: MedicineBatch
    source_url: Optional[str] = None


class SpreadsheetPushRequest(BaseModel):
    batch: MedicineBatch
    destination_type: Literal["local_excel", "google_sheets"] = "local_excel"
    target_file_path: Optional[str] = Field(
        default=None, description="Absolute or relative path to local .xlsx file"
    )
    spreadsheet_id: Optional[str] = Field(
        default=None, description="Google Sheets Spreadsheet ID"
    )
    worksheet_name: str = Field(
        default="Medicine Data", description="Target sheet/tab name"
    )
    prevent_duplicates: bool = Field(
        default=True, description="Skip records with matching record_id or composite key"
    )


class SpreadsheetPushResponse(BaseModel):
    success: bool
    status: str
    destination: str
    total_records: int
    inserted_records: int
    skipped_records: int
    failed_records: int
    newly_created_columns: List[str]
    existing_columns: List[str]
    final_columns: List[str]
    warnings: List[str] = []
    error_message: Optional[str] = None


class SpreadsheetDestinationInfo(BaseModel):
    id: str
    name: str
    provider: str  # "local" or "google_sheets"
    path_or_id: str
    worksheets: List[str]
