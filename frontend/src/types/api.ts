/**
 * src/types/api.ts — Complete TypeScript interfaces mirroring backend Pydantic models.
 */

// ── File & Inspection Types ──────────────────────────────────────────────────
export type Confidence = 'high' | 'medium' | 'low'
export interface MappingSuggestion extends TemplateFieldMapping {
  confidence: Confidence
  reason: string
}
export interface WorkbookAnalysis {
  file_id: number
  suggested_worksheet: string
  selected_worksheet: string
  review_required: true
  profiles: { name: string; is_hidden: boolean; truncated: boolean; non_empty_count: number; used_range: string }[]
  analysis: {
    worksheet: string
    suggested_template_type: 'invoice' | 'dataset' | null
    confidence: Confidence
    reasons: string[]
    mappings: MappingSuggestion[]
    table: { header_row: number; data_start_row: number; data_end_row: number; confidence: Confidence; columns: MappingSuggestion[] } | null
  }
  template_matches: { template_id: number; name: string; confidence: Confidence; reasons: string[] }[]
  warnings: string[]
}

export interface WorksheetInfo {
  name: string
  state: 'visible' | 'hidden' | 'veryHidden'
  is_hidden: boolean
  has_formulas: boolean
  uncalculated_formula_count: number
  uncalculated_formula_cells: string[]
  preview_matrix: (string | null)[][]
}

export interface SourceFileUploadResponse {
  id: number
  stored_filename: string
  original_name: string
  file_size_bytes: number
  checksum_sha256: string
  sheet_names: string[]
  worksheet_info: WorksheetInfo[]
  uploaded_at: string
}

export interface WorksheetPreviewResponse {
  file_id: number
  sheet_name: string
  max_rows: number
  max_cols: number
  matrix: (string | null)[][]
  has_formulas: boolean
  formula_cells: string[]
}

// ── Template Types ───────────────────────────────────────────────────────────

export interface TemplateFieldMapping {
  id?: number
  field_name: string
  target_field?: string | null  // canonical or custom backend field to map to
  mapping_group?: 'header' | 'line_item'
  mapping_type: 'cell' | 'column' | 'fixed'
  cell_ref?: string
  column_ref?: string
  is_required: boolean
  data_type: 'text' | 'decimal' | 'date' | 'integer'
  date_format?: string
}

export interface TemplateSummary {
  id: number
  name: string
  description?: string | null
  template_type?: 'invoice' | 'dataset'
  file_type: string
  worksheet: string
  header_row?: number | null
  data_start_row?: number | null
  mapping_count: number
  created_at: string
  updated_at: string
}

export interface TemplateDetail {
  id: number
  name: string
  description?: string | null
  template_type?: 'invoice' | 'dataset'
  file_type: string
  worksheet: string
  header_row?: number | null
  data_start_row?: number | null
  field_mappings: TemplateFieldMapping[]
  created_at: string
  updated_at: string
}

export interface TemplateCreate {
  name: string
  description?: string
  template_type?: 'invoice' | 'dataset'
  file_type: string
  worksheet: string
  header_row?: number | null
  data_start_row?: number | null
  field_mappings: TemplateFieldMapping[]
}

// ── Extraction & Validation Preview Types ────────────────────────────────────

export interface ExtractedField {
  field_name: string
  mapping_type: string
  source_worksheet: string
  source_cell_ref: string
  raw_value: any
  data_type: string
  is_required: boolean
  is_empty_cell: boolean
  is_formula: boolean
  formula_expression?: string | null
  normalized_value: any
  status: 'success' | 'warning' | 'error' | 'empty_optional'
  error_message?: string | null
  warning_message?: string | null
}

export interface ExtractionError {
  field_name?: string | null
  message: string
  worksheet?: string | null
  cell_ref?: string | null
  error_type: string
}

export interface ValidationIssue {
  rule_id: string
  field_name?: string | null
  severity: 'error' | 'warning' | 'info'
  message: string
  cell_ref?: string | null
  worksheet?: string | null
  actual_value?: any
}

export interface ValidationReport {
  is_valid_for_import: boolean
  issues: ValidationIssue[]
  error_count: number
  warning_count: number
  info_count: number
  normalized_data: Record<string, any>
}

export interface RowExtractionPreview {
  source_row_number: number
  fields: ExtractedField[]
  has_errors: boolean
  error_count: number
  warning_count: number
  errors: ExtractionError[]
  warnings: string[]
  normalized_data: Record<string, any>
}

export interface ExtractionPreviewResponse {
  file_id: number
  template_id: number
  template_name: string
  template_type?: 'invoice' | 'dataset'
  target_worksheet: string
  is_multi_record?: boolean
  has_line_items?: boolean
  record_count?: number
  line_item_count?: number
  fields: ExtractedField[]
  records?: RowExtractionPreview[]
  line_items?: RowExtractionPreview[]
  has_errors: boolean
  error_count: number
  warning_count: number
  errors: ExtractionError[]
  warnings: string[]
  validation_report: ValidationReport
}

// ── Import Confirmation & Batch History Types ────────────────────────────────

export interface ImportConfirmRequest {
  file_id: number
  template_id: number
  acknowledge_warnings?: boolean
}

export interface InvoiceLineItemRead {
  id: number
  invoice_id: number
  source_row_number?: number | null
  description?: string | null
  quantity?: number | string | null
  unit_price?: number | string | null
  tax_rate?: number | string | null
  tax_amount?: number | string | null
  amount?: number | string | null
  custom_fields?: Record<string, any> | null
  created_at: string
}

export interface InvoiceRecordRead {
  id: number
  batch_id: number
  company_name: string
  invoice_number: string
  invoice_date?: string | null
  total_amount?: number | string | null
  currency?: string | null
  source_worksheet: string
  source_row_number?: number | null
  custom_fields?: Record<string, any> | null
  created_at: string
  line_items?: InvoiceLineItemRead[]
}

/** Payload for PATCH /api/v1/imports/{batch_id}/records/{record_id} */
export interface InvoiceRecordUpdate {
  company_name?: string
  invoice_number?: string
  invoice_date?: string | null
  total_amount?: number | null
  currency?: string | null
}

export interface ValidationErrorRecordRead {
  id: number
  rule_id: string
  field_name?: string | null
  severity: 'warning' | 'info'
  message: string
  cell_ref?: string | null
  worksheet?: string | null
}

export interface ImportBatchListItem {
  id: number
  source_file_id: number
  original_filename: string
  template_id: number
  template_name: string
  status: string
  record_count: number
  warning_count: number
  imported_at: string
}

export interface ImportBatchDetail {
  id: number
  source_file_id: number
  original_filename: string
  template_id: number
  template_name: string
  status: string
  record_count: number
  warning_count: number
  imported_at: string
  invoice_records: InvoiceRecordRead[]
  validation_issues: ValidationErrorRecordRead[]
  raw_data?: Record<string, any> | null
}

export interface BatchImportFile {
  id: number; source_file_id: number; filename: string; status: string
  detected_type?: string | null; processing_method?: string | null
  template_id?: number | null; template_name?: string | null; import_batch_id?: number | null
  issues: { message: string }[]; error_message?: string | null
}
export interface BatchImportDetail {
  id: number; status: string; created_at: string; completed_at?: string | null
  summary: { total: number; ready: number; review: number; duplicate: number; failed: number; imported: number; skipped: number }
  files: BatchImportFile[]
}

// ── Standard API Error Payload ───────────────────────────────────────────────

export interface ApiError {
  status: number
  message: string
  detail?: any
  isWarningAcknowledgmentRequired?: boolean
  validationErrors?: string[]
}

// ── Data Explorer Types ──────────────────────────────────────────────────────

export interface InvoiceListItem {
  id: number
  batch_id: number
  company_name: string
  invoice_number: string
  invoice_date?: string | null
  total_amount?: number | string | null
  currency?: string | null
  source_worksheet: string
  source_row_number?: number | null
  line_item_count: number
  created_at: string
  source_filename?: string | null
}

export interface InvoiceDetailBatchInfo {
  id: number
  source_file_id: number
  source_filename: string
  template_id: number
  template_name: string
  status: string
  imported_at: string
}

export interface InvoiceDetailResponse {
  id: number
  batch_id: number
  company_name: string
  invoice_number: string
  invoice_date?: string | null
  total_amount?: number | string | null
  currency?: string | null
  source_worksheet: string
  source_row_number?: number | null
  custom_fields?: Record<string, any> | null
  created_at: string
  batch?: InvoiceDetailBatchInfo | null
  line_items: InvoiceLineItemRead[]
  raw_data?: Record<string, any> | null
}

export interface LineItemListItem {
  id: number
  invoice_id: number
  invoice_number: string
  company_name: string
  invoice_date?: string | null
  currency?: string | null
  source_row_number: number
  description?: string | null
  quantity?: number | string | null
  unit_price?: number | string | null
  tax_rate?: number | string | null
  tax_amount?: number | string | null
  amount?: number | string | null
  custom_fields?: Record<string, any> | null
  created_at: string
}

export interface PaginatedInvoicesResponse {
  items: InvoiceListItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PaginatedLineItemsResponse {
  items: LineItemListItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface DataExplorerFilterOptions {
  companies: string[]
  currencies: string[]
}

// ── Export Center Types ──────────────────────────────────────────────────────

export interface ExportSummaryResponse {
  dataset: 'invoices' | 'line-items'
  total_records: number
  column_count: number
  columns: string[]
}

export interface ExportFilterParams {
  search?: string
  company?: string
  currency?: string
  date_from?: string
  date_to?: string
  has_line_items?: boolean
}

// Analytics keeps authoritative Decimal values as strings.
export interface DashboardFilters {
  currency?: string | null
  date_from?: string | null
  date_to?: string | null
  company?: string | null
}

export interface AnalyticsFilterOptions {
  currencies: string[]
  has_unspecified_currency: boolean
  companies: string[]
  date_from: string | null
  date_to: string | null
}

export interface AnalyticsPeriod {
  period: string
  invoice_count: number
  invoices_with_total: number
  invoice_value: string | null
}

export interface DashboardResponse {
  filters: DashboardFilters
  monetary_values_available: boolean
  grouping: 'month'
  summary: {
    invoice_count: number
    invoices_with_total: number
    invoices_without_total: number
    invoices_without_date: number
    total_invoice_value: string | null
    average_invoice_value: string | null
    line_item_count: number
    line_items_with_amount: number
  }
  invoice_value_over_time: AnalyticsPeriod[]
  company_values: { company_name: string | null; invoice_count: number; invoices_with_total: number; invoice_value: string }[]
  line_item_values: { description: string | null; line_item_count: number; line_items_with_amount: number; amount: string }[]
}
