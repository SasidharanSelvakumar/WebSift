from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field, HttpUrl


class ExtractRequest(BaseModel):
    url: str = Field(..., description="The HTTP or HTTPS URL to scrape")
    mode: Literal["full", "main"] = Field(
        default="main", description="Extraction mode: 'main' content or 'full' page"
    )
    force_browser: bool = Field(
        default=False, description="Force headless browser rendering instead of fast HTTP parsing"
    )


class ExtractedItem(BaseModel):
    sequence_number: int = Field(..., description="Preserved reading order index (1-based)")
    source_url: str = Field(..., description="The original URL of the page")
    page_title: str = Field(..., description="Extracted title of the webpage")
    content_type: str = Field(
        ...,
        description="Type: heading_1, heading_2, heading_3, heading_4, heading_5, heading_6, paragraph, list_item, table_row, link, blockquote, text_block",
    )
    heading: Optional[str] = Field(
        default=None, description="Closest active section heading in the document hierarchy"
    )
    text_content: str = Field(..., description="Cleaned, meaningful extracted text content")
    extracted_at: str = Field(..., description="ISO 8601 extraction timestamp")


class ExtractionStats(BaseModel):
    block_count: int = Field(default=0, description="Total number of structured content blocks")
    word_count: int = Field(default=0, description="Total word count of extracted text")
    character_count: int = Field(default=0, description="Total character count")
    reading_time_minutes: float = Field(default=0.0, description="Estimated reading time in minutes")
    headings_count: int = Field(default=0, description="Count of heading elements")
    paragraphs_count: int = Field(default=0, description="Count of paragraph blocks")
    lists_count: int = Field(default=0, description="Count of list items")
    tables_count: int = Field(default=0, description="Count of table rows")
    duration_ms: float = Field(default=0.0, description="Time taken to scrape and extract in milliseconds")


class ExtractResponse(BaseModel):
    success: bool
    source_url: str
    page_title: str
    meta_description: Optional[str] = None
    mode: str
    engine_used: str  # "HTTP Parser" or "Playwright Browser"
    stats: ExtractionStats
    items: List[ExtractedItem]
    full_text_preview: str
    warnings: List[str] = []
    extracted_at: str
    medicine_batch: Optional[Any] = None


class ExportRequest(BaseModel):
    items: List[ExtractedItem]
    source_url: str
    page_title: str
    mode: Optional[str] = "main"
    extracted_at: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    playwright_available: bool
