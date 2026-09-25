/**
 * src/types/api.ts — Complete TypeScript interfaces mirroring backend Pydantic models.
 */

// ── File & Inspection Types ──────────────────────────────────────────────────

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
  invoice_record_id: number
  source_row_number?: number | null
  description?: string | null
  quantity?: number | null
  unit_price?: number | null
  tax_rate?: number | null
  tax_amount?: number | null
  amount?: number | null
  custom_fields?: Record<string, any> | null
  created_at: string
}

export interface InvoiceRecordRead {
  id: number
  batch_id: number
  company_name: string
  invoice_number: string
  invoice_date?: string | null
  total_amount?: number | null
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

// ── Standard API Error Payload ───────────────────────────────────────────────

export interface ApiError {
  status: number
  message: string
  detail?: any
  isWarningAcknowledgmentRequired?: boolean
  validationErrors?: string[]
}
