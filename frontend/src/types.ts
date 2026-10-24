export interface ExtractedItem {
  sequence_number: number;
  source_url: string;
  page_title: string;
  content_type: string;
  heading: string | null;
  text_content: string;
  extracted_at: string;
}

export interface ExtractionStats {
  block_count: number;
  word_count: number;
  character_count: number;
  reading_time_minutes: number;
  headings_count: number;
  paragraphs_count: number;
  lists_count: number;
  tables_count: number;
  duration_ms: number;
}

export interface MedicineRecord {
  record_id: string;
  medicine_name: string;
  source_url: string;
  extracted_at: string;
  attributes: Record<string, any>;
  raw_labels?: Record<string, string>;
  product_id?: string | null;
  brand?: string | null;
  manufacturer?: string | null;
  marketer?: string | null;
  price?: string | null;
  strength?: string | null;
  dosage_form?: string | null;
  active_ingredients?: string | null;
  drug_schedule?: string | null;
  pack_quantity?: string | null;
  tags?: string | null;
  safety_advice?: string | null;
  warnings?: string[];
  is_duplicate?: boolean;
}

export interface MedicineBatch {
  records: MedicineRecord[];
  all_discovered_fields: string[];
  new_fields: string[];
  total_records: number;
  unique_attributes_count: number;
  warnings?: string[];
}

export interface ExtractResponse {
  success: boolean;
  source_url: string;
  page_title: string;
  meta_description?: string | null;
  mode: 'main' | 'full';
  engine_used: string;
  stats: ExtractionStats;
  items: ExtractedItem[];
  full_text_preview: string;
  warnings: string[];
  extracted_at: string;
  medicine_batch?: MedicineBatch | null;
}

export interface HealthStatus {
  status: string;
  version: string;
  playwright_available: boolean;
}

export interface SpreadsheetDestinationInfo {
  id: string;
  name: string;
  provider: 'local' | 'google_sheets';
  path_or_id: string;
  worksheets: string[];
}

export interface SpreadsheetPushResponse {
  success: boolean;
  status: string;
  destination: string;
  total_records: number;
  inserted_records: number;
  skipped_records: number;
  failed_records: number;
  newly_created_columns: string[];
  existing_columns: string[];
  final_columns: string[];
  warnings?: string[];
  error_message?: string | null;
}

export type ScrapingMode = 'single' | 'category' | 'images';

export interface CategoryScrapeRequest {
  category_url: string;
  max_pages?: number;
  max_products?: number;
  delay_seconds?: number;
  product_selector?: string;
  next_page_selector?: string;
  force_browser?: boolean;
}

export interface CategoryJobProduct {
  product_url: string;
  status: 'pending' | 'completed' | 'failed' | 'skipped';
  attempt_count: number;
  last_error?: string | null;
  processing_timestamp?: string;
  product_name?: string;
  price?: string;
  strength?: string;
  dosage_form?: string;
  manufacturer?: string;
}

export interface CategoryJobResponse {
  job_id: string;
  category_url: string;
  job_status: 'running' | 'paused' | 'completed' | 'failed' | 'stopped' | 'incomplete';
  start_time: string;
  last_updated_time: string;
  completion_time?: string | null;
  pages_visited: number;
  total_discovered: number;
  total_completed: number;
  total_failed: number;
  total_skipped: number;
  current_page_url?: string | null;
  current_product_url?: string | null;
  error_message?: string | null;
  products?: CategoryJobProduct[];
}

export interface ImageScrapeRequest {
  listing_url: string;
  max_pages?: number | null;
  max_images?: number | null;
  delay_seconds?: number;
  product_selector?: string | null;
  next_page_selector?: string | null;
}

export interface ImageRecentDownload {
  medicine_name: string;
  filename: string;
  status: 'downloaded' | 'skipped_exists' | 'failed';
  size_bytes?: number;
  error?: string;
  timestamp: string;
}

export interface ImageJobResponse {
  job_id: string;
  listing_url: string;
  job_status: 'pending' | 'running' | 'completed' | 'failed' | 'stopped' | 'incomplete';
  start_time: string;
  last_updated_time: string;
  completion_time?: string | null;
  pages_visited: number;
  total_discovered: number;
  images_downloaded: number;
  images_skipped: number;
  images_failed: number;
  images_remaining: number;
  current_page_url?: string | null;
  current_product_url?: string | null;
  current_medicine_name?: string | null;
  output_dir: string;
  error_message?: string | null;
  recent_downloads: ImageRecentDownload[];
}

export interface ImageStorageStatus {
  folder_path: string;
  total_images: number;
  total_size_bytes: number;
}


