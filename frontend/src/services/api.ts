
/**
 * src/services/api.ts — Typed API Client for DataBridge FastAPI backend.
 */

import type {
  ApiError,
  ExtractionPreviewResponse,
  ImportBatchDetail,
  ImportBatchListItem,
  ImportConfirmRequest,
  InvoiceRecordRead,
  InvoiceRecordUpdate,
  SourceFileUploadResponse,
  TemplateCreate,
  TemplateDetail,
  TemplateSummary,
  WorksheetPreviewResponse,
} from '@/types/api'

const API_BASE = '/api/v1'

async function request<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}${endpoint}`

  let res: Response

  try {
    res = await fetch(url, options)
  } catch (err: any) {
    throw {
      status: 0,
      message:
        'Failed to connect to DataBridge server. Is the backend running?',
      detail: err?.message,
    } as ApiError
  }

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
}