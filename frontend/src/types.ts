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
