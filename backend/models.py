from typing import Any, Dict, List, Literal, Optional
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


class CategoryScrapeRequest(BaseModel):
    category_url: str = Field(..., description="Target category or listing page URL")
    max_pages: Optional[int] = Field(default=None, ge=1, le=10000, description="Maximum listing pages to traverse (None for all pages)")
    max_products: Optional[int] = Field(default=None, ge=1, le=50000, description="Maximum products to scrape (None for all products)")
    delay_seconds: float = Field(default=1.0, ge=0.0, le=10.0, description="Polite request delay in seconds")
    product_selector: Optional[str] = Field(default=None, description="Optional CSS selector for product links")
    next_page_selector: Optional[str] = Field(default=None, description="Optional CSS selector for Next page pagination")
    force_browser: bool = Field(default=False, description="Force headless browser rendering for JS pagination")


class CategoryJobResponse(BaseModel):
    job_id: str
    category_url: str
    job_status: str
    start_time: str
    last_updated_time: str
    completion_time: Optional[str] = None
    pages_visited: int = 0
    total_discovered: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    current_page_url: Optional[str] = None
    current_product_url: Optional[str] = None
    error_message: Optional[str] = None
    products: Optional[List[Dict[str, Any]]] = None


CategoryJobResponse.model_rebuild()

