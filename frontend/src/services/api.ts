import { sessionHeaders, session } from "./session"

/**
 * src/services/api.ts — Typed API Client for DataBridge FastAPI backend.
 */

import type {
  WorkbookAnalysis,
  ApiError,
  AnalyticsFilterOptions,
  DashboardResponse,
  DashboardFilters,
  DataExplorerFilterOptions,
  ExportFilterParams,
  ExportSummaryResponse,
  ExtractionPreviewResponse,
  ImportBatchDetail,
  ImportBatchListItem,
  ImportConfirmRequest,
  InvoiceDetailResponse,
  InvoiceRecordRead,
  InvoiceRecordUpdate,
  PaginatedInvoicesResponse,
  PaginatedLineItemsResponse,
  SourceFileUploadResponse,
  TemplateCreate,
  TemplateDetail,
  TemplateSummary,
  WorksheetPreviewResponse,
  BatchImportDetail,
} from '@/types/api'

const API_BASE = '/api/v1'

async function request<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}${endpoint}`

  let res: Response

  try {
    res = await fetch(url, { ...options, credentials: "include", headers: { ...sessionHeaders(), ...options?.headers } })
  } catch (err: any) {
    throw {
      status: 0,
      message:
        'Failed to connect to DataBridge server. Is the backend running?',
      detail: err?.message,
    } as ApiError
  }

  if (res.status === 401) { session.value = null; window.location.assign("/login") }
  if (!res.ok) {
    let errorDetail: any = null
    let errorMsg = `Server error (${res.status})`

    try {
      errorDetail = await res.json()

      if (typeof errorDetail.detail === 'string') {
        errorMsg = errorDetail.detail
      } else if (Array.isArray(errorDetail.detail)) {
        errorMsg = errorDetail.detail
          .map((detail: any) => detail.msg || JSON.stringify(detail))
          .join('; ')
      }
    } catch {
      errorMsg = await res.text().catch(
        () => `Error status ${res.status}`,
      )
    }

    const isWarningAck =
      res.status === 400 &&
      typeof errorMsg === 'string' &&
      errorMsg.toLowerCase().includes('warning')

    const apiError: ApiError = {
      status: res.status,
      message: errorMsg,
      detail: errorDetail?.detail,
      isWarningAcknowledgmentRequired: isWarningAck,
      validationErrors: Array.isArray(errorDetail?.detail)
        ? errorDetail.detail.map(
          (error: any) =>
            `${error.loc?.join('.')} ${error.msg}`,
        )
        : undefined,
    }

    throw apiError
  }

  if (res.status === 204) {
    return {} as T
  }

  return (await res.json()) as T
}

export const api = {
  async createBatchImport(fileIds: number[]): Promise<BatchImportDetail> {
    return request('/batch-imports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_ids: fileIds }) })
  },
  async getBatchImport(id: number): Promise<BatchImportDetail> { return request(`/batch-imports/${id}`) },
  async listBatchImports(): Promise<BatchImportDetail[]> { return request('/batch-imports') },
  async importReadyFiles(id: number): Promise<BatchImportDetail> { return request(`/batch-imports/${id}/import-ready`, { method: 'POST' }) },
  async removeBatchFile(id: number, fileId: number): Promise<BatchImportDetail> { return request(`/batch-imports/${id}/files/${fileId}`, { method: 'DELETE' }) },
  async retryBatchAnalysis(id: number): Promise<BatchImportDetail> { return request(`/batch-imports/${id}/analyze`, { method: 'POST' }) },
  async getBatchReview(id: number, fileId: number): Promise<ExtractionPreviewResponse> { return request(`/batch-imports/${id}/files/${fileId}/review`) },
  async acceptBatchWarnings(id: number, fileId: number): Promise<BatchImportDetail> { return request(`/batch-imports/${id}/files/${fileId}/accept-warnings`, { method: 'POST' }) },
  getImportSummary() { return request<{ total_imports: number; total_records: number; total_warnings: number }>("/imports/summary") },
  async analyzeWorkbook(file_id: number, worksheet?: string): Promise<WorkbookAnalysis> {
    return request('/suggestions/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_id, worksheet }) })
  },
  async getAnalyticsFilterOptions(): Promise<AnalyticsFilterOptions> {
    return request<AnalyticsFilterOptions>('/analytics/filter-options')
  },
  async getDashboard(filters: DashboardFilters): Promise<DashboardResponse> {
    const params = new URLSearchParams()
    if (filters.currency) params.set('currency', filters.currency)
    if (filters.date_from) params.set('date_from', filters.date_from)
    if (filters.date_to) params.set('date_to', filters.date_to)
    if (filters.company) params.set('company', filters.company)
    return request<DashboardResponse>(`/analytics/dashboard?${params.toString()}`)
  },
  // ── Health Check ──────────────────────────────────────────────

  async checkHealth(): Promise<{
    status: string
    app: string
    version: string
  }> {
    const response = await fetch('/health')

    if (!response.ok) {
      throw new Error('Health check failed')
    }

    return response.json()
  },

  // ── Files & Workbook Inspection ──────────────────────────────

  async uploadFile(
    file: File,
  ): Promise<SourceFileUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await request<any>('/files/upload', {
      method: 'POST',
      body: formData,
    })

    /*
     * Normalize the backend response into the structure
     * expected by the frontend.
     *
     * Backend:
     *   file_id
     *   file_size
     *   checksum
     *   inspection.worksheets
     *
     * Frontend:
     *   id
     *   file_size_bytes
     *   checksum_sha256
     *   sheet_names
     */

    const worksheets = Array.isArray(
      response.inspection?.worksheets,
    )
      ? response.inspection.worksheets
      : []

    return {
      id: response.file_id,
      stored_filename:
        response.stored_filename ?? response.original_name,
      original_name: response.original_name,
      file_size_bytes: response.file_size,
      checksum_sha256: response.checksum,
      uploaded_at: response.uploaded_at,

      sheet_names: worksheets.map(
        (worksheet: { name: string }) => worksheet.name,
      ),

      worksheet_info: worksheets,
    }
  },

  async getFilePreview(
    fileId: number,
    sheetName: string,
    maxRows = 15,
    maxCols = 10,
  ): Promise<WorksheetPreviewResponse> {
    const params = new URLSearchParams({
      sheet_name: sheetName,
      max_rows: String(maxRows),
      max_cols: String(maxCols),
    })

    return request<WorksheetPreviewResponse>(
      `/files/${fileId}/preview?${params.toString()}`,
    )
  },

  // ── Templates ────────────────────────────────────────────────

  async listTemplates(): Promise<TemplateSummary[]> {
    return request<TemplateSummary[]>('/templates')
  },

  async getTemplate(
    templateId: number,
  ): Promise<TemplateDetail> {
    return request<TemplateDetail>(
      `/templates/${templateId}`,
    )
  },

  async createTemplate(
    payload: TemplateCreate,
  ): Promise<TemplateDetail> {
    return request<TemplateDetail>('/templates', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })
  },

  async updateTemplate(
    templateId: number,
    payload: Partial<TemplateCreate>,
  ): Promise<TemplateDetail> {
    return request<TemplateDetail>(
      `/templates/${templateId}`,
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      },
    )
  },

  async deleteTemplate(templateId: number): Promise<void> {
    return request<void>(`/templates/${templateId}`, {
      method: 'DELETE',
    })
  },

  // ── Extraction Preview ───────────────────────────────────────

  async extractPreview(
    fileId: number,
    templateId: number,
  ): Promise<ExtractionPreviewResponse> {
    return request<ExtractionPreviewResponse>(
      '/imports/extract',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          file_id: fileId,
          template_id: templateId,
        }),
      },
    )
  },

  // ── Import Confirmation ─────────────────────────────────────

  async confirmImport(
    payload: ImportConfirmRequest,
  ): Promise<ImportBatchDetail> {
    return request<ImportBatchDetail>(
      '/imports/confirm',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      },
    )
  },

  // ── Import History ──────────────────────────────────────────

  async listImportBatches(
    skip = 0,
    limit = 20,
  ): Promise<ImportBatchListItem[]> {
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
    })

    return request<ImportBatchListItem[]>(
      `/imports?${params.toString()}`,
    )
  },

  async getImportBatch(
    batchId: number,
  ): Promise<ImportBatchDetail> {
    return request<ImportBatchDetail>(
      `/imports/${batchId}`,
    )
  },

  /** Soft-delete an import batch. Returns 204 No Content on success. */
  async deleteImportBatch(batchId: number): Promise<void> {
    return request<void>(`/imports/${batchId}`, {
      method: 'DELETE',
    })
  },

  /** PATCH canonical fields on an invoice record. Preserves custom_fields. */
  async updateInvoiceRecord(
    batchId: number,
    recordId: number,
    payload: InvoiceRecordUpdate,
  ): Promise<InvoiceRecordRead> {
    return request<InvoiceRecordRead>(
      `/imports/${batchId}/records/${recordId}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
  },

  // ── Templates — Canonical Fields ────────────────────────────

  /** Returns the list of canonical target field names supported by InvoiceRecord. */
  async listCanonicalFields(): Promise<string[]> {
    return request<string[]>('/templates/canonical-fields')
  },

  /** Returns the list of canonical target field names supported by InvoiceLineItem. */
  async listCanonicalLineItemFields(): Promise<string[]> {
    return request<string[]>('/templates/canonical-line-item-fields')
  },

  // ── Data Explorer ───────────────────────────────────────────

  /** Browse paginated invoice records with server-side search, filtering, and sorting. */
  async listDataExplorerInvoices(params: {
    search?: string
    company?: string
    currency?: string
    date_from?: string
    date_to?: string
    has_line_items?: boolean
    sort_by?: string
    sort_order?: string
    page?: number
    page_size?: number
  } = {}): Promise<PaginatedInvoicesResponse> {
    const qp = new URLSearchParams()
    if (params.search) qp.set('search', params.search)
    if (params.company) qp.set('company', params.company)
    if (params.currency) qp.set('currency', params.currency)
    if (params.date_from) qp.set('date_from', params.date_from)
    if (params.date_to) qp.set('date_to', params.date_to)
    if (params.has_line_items !== undefined) qp.set('has_line_items', String(params.has_line_items))
    if (params.sort_by) qp.set('sort_by', params.sort_by)
    if (params.sort_order) qp.set('sort_order', params.sort_order)
    if (params.page !== undefined) qp.set('page', String(params.page))
    if (params.page_size !== undefined) qp.set('page_size', String(params.page_size))

    const queryString = qp.toString()
    return request<PaginatedInvoicesResponse>(
      `/data/invoices${queryString ? `?${queryString}` : ''}`,
    )
  },

  /** Get complete detail of an individual invoice record. */
  async getDataExplorerInvoice(invoiceId: number): Promise<InvoiceDetailResponse> {
    return request<InvoiceDetailResponse>(`/data/invoices/${invoiceId}`)
  },

  /** Update canonical fields on an invoice record. */
  async updateDataExplorerInvoice(
    invoiceId: number,
    payload: InvoiceRecordUpdate,
  ): Promise<InvoiceDetailResponse> {
    return request<InvoiceDetailResponse>(`/data/invoices/${invoiceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },

  /** Browse paginated flattened line items across all invoices with server-side filters. */
  async listDataExplorerLineItems(params: {
    search?: string
    company?: string
    currency?: string
    date_from?: string
    date_to?: string
    sort_by?: string
    sort_order?: string
    page?: number
    page_size?: number
  } = {}): Promise<PaginatedLineItemsResponse> {
    const qp = new URLSearchParams()
    if (params.search) qp.set('search', params.search)
    if (params.company) qp.set('company', params.company)
    if (params.currency) qp.set('currency', params.currency)
    if (params.date_from) qp.set('date_from', params.date_from)
    if (params.date_to) qp.set('date_to', params.date_to)
    if (params.sort_by) qp.set('sort_by', params.sort_by)
    if (params.sort_order) qp.set('sort_order', params.sort_order)
    if (params.page !== undefined) qp.set('page', String(params.page))
    if (params.page_size !== undefined) qp.set('page_size', String(params.page_size))

    const queryString = qp.toString()
    return request<PaginatedLineItemsResponse>(
      `/data/line-items${queryString ? `?${queryString}` : ''}`,
    )
  },

  /** Fetch unique filter options (companies, currencies) present in non-deleted records. */
  async getDataExplorerFilterOptions(): Promise<DataExplorerFilterOptions> {
    return request<DataExplorerFilterOptions>('/data/filter-options')
  },

  // ── Export Center ───────────────────────────────────────────

  /** Fetch export metadata (record count and discovered columns) for a dataset and filters. */
  async getExportSummary(
    dataset: 'invoices' | 'line-items',
    filters: ExportFilterParams = {},
  ): Promise<ExportSummaryResponse> {
    const qp = new URLSearchParams({ dataset })
    if (filters.search) qp.set('search', filters.search)
    if (filters.company) qp.set('company', filters.company)
    if (filters.currency) qp.set('currency', filters.currency)
    if (filters.date_from) qp.set('date_from', filters.date_from)
    if (filters.date_to) qp.set('date_to', filters.date_to)
    if (filters.has_line_items !== undefined) qp.set('has_line_items', String(filters.has_line_items))

    return request<ExportSummaryResponse>(`/exports/summary?${qp.toString()}`)
  },

  /**
   * Triggers browser file download for CSV or XLSX export.
   * Resolves when download initiation is complete.
   */
  async downloadExport(
    dataset: 'invoices' | 'line-items',
    format: 'csv' | 'xlsx',
    filters: ExportFilterParams = {},
  ): Promise<string> {
    const qp = new URLSearchParams()
    if (filters.search) qp.set('search', filters.search)
    if (filters.company) qp.set('company', filters.company)
    if (filters.currency) qp.set('currency', filters.currency)
    if (filters.date_from) qp.set('date_from', filters.date_from)
    if (filters.date_to) qp.set('date_to', filters.date_to)
    if (filters.has_line_items !== undefined) qp.set('has_line_items', String(filters.has_line_items))

    const queryString = qp.toString()
    const url = `/api/v1/exports/${dataset}.${format}${queryString ? `?${queryString}` : ''}`

    const res = await fetch(url, { credentials: "include", headers: sessionHeaders() })
    if (!res.ok) {
      let errMsg = `Export failed (${res.status})`
      try {
        const errJson = await res.json()
        errMsg = errJson.detail || errMsg
      } catch {
        // fallback
      }
      throw new Error(errMsg)
    }

    // Extract filename from Content-Disposition header if present
    let filename = `databridge_${dataset}_${new Date().toISOString().split('T')[0]}.${format}`
    const disposition = res.headers.get('Content-Disposition')
    if (disposition) {
      const match = disposition.match(/filename="?([^";]+)"?/i)
      if (match && match[1]) {
        filename = match[1].trim()
      }
    }

    const blob = await res.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = blobUrl
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    window.URL.revokeObjectURL(blobUrl)

    return filename
  },
}
