/**
 * src/composables/useIngestionQueue.ts
 *
 * Application-lifetime shared ingestion queue composable.
 * Retains queued files, statuses, backend identifiers, and review destinations
 * across in-app router navigation while properly scoping to the active workspace.
 */

import { computed, ref, watch } from 'vue'
import { session } from '@/services/session'
import { api } from '@/services/api'
import { toast } from '@/services/toast'
import { useImportWorkflow } from '@/composables/useImportWorkflow'
import type { BatchImportDetail, SourceFileUploadResponse } from '@/types/api'

export type FileFormat = 'xlsx' | 'pdf' | 'jpeg' | 'png' | 'unknown'
export type DocType = 'spreadsheet' | 'invoice' | 'receipt' | 'unknown'
export type QueueStatus =
  | 'queued'
  | 'uploading'
  | 'processing'
  | 'ready'
  | 'needs_review'
  | 'imported'
  | 'failed'

export interface QueueEntry {
  id: string
  name: string
  size: number
  format: FileFormat
  suggestedType: DocType
  status: QueueStatus
  error?: string
  documentId?: number   // for PDF/image files after upload
  fileId?: number       // for XLSX files after upload
  batchId?: number      // for XLSX batch files after upload
  reviewPath?: string
  file?: File           // raw File retained only while queued/uploading or failed
}

export const ACCEPTED_MIME = new Set([
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/pdf',
  'image/jpeg',
  'image/png',
])
export const MAX_FILE_MB = 10
export const MAX_QUEUE = 25
export const UPLOAD_CONCURRENCY = 3

// Module-level reactive state: survives Vue router navigation
const queue = ref<QueueEntry[]>([])
const activeBatch = ref<BatchImportDetail | null>(null)
const scopedWorkspaceId = ref<number | null>(null)
let isProcessing = false

export function detectFormat(file: { name: string; type?: string }): FileFormat {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (ext === 'xlsx') return 'xlsx'
  if (ext === 'pdf') return 'pdf'
  if (ext === 'jpg' || ext === 'jpeg') return 'jpeg'
  if (ext === 'png') return 'png'
  const mt = file.type || ''
  if (mt === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') return 'xlsx'
  if (mt === 'application/pdf') return 'pdf'
  if (mt === 'image/jpeg') return 'jpeg'
  if (mt === 'image/png') return 'png'
  return 'unknown'
}

export function suggestType(format: FileFormat): DocType {
  if (format === 'xlsx') return 'spreadsheet'
  return 'unknown'
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
}

function enforceWorkspaceScope() {
  const currentId = session.value?.active_workspace_id ?? null
  if (!session.value || currentId === null) {
    queue.value = []
    activeBatch.value = null
    scopedWorkspaceId.value = null
    return
  }
  if (scopedWorkspaceId.value !== null && scopedWorkspaceId.value !== currentId) {
    // Switched workspace: reset queue
    queue.value = []
    activeBatch.value = null
  }
  scopedWorkspaceId.value = currentId
}

// Watch session to clean up on logout or workspace switch
if (typeof window !== 'undefined') {
  watch(
    () => session.value?.active_workspace_id,
    (newId, oldId) => {
      if (newId !== oldId) {
        queue.value = []
        activeBatch.value = null
        scopedWorkspaceId.value = newId ?? null
      }
    }
  )
}

function validateFile(file: File): string | null {
  const fmt = detectFormat(file)
  if (fmt === 'unknown' && !ACCEPTED_MIME.has(file.type)) {
    return `${file.name}: unsupported format. Accepted: XLSX, PDF, JPG, PNG.`
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return `${file.name}: exceeds ${MAX_FILE_MB} MB limit.`
  }
  return null
}

function isDuplicate(file: File): boolean {
  return queue.value.some(e => e.name === file.name && e.size === file.size)
}

function addFiles(files: FileList | File[]) {
  enforceWorkspaceScope()
  const arr = Array.from(files)
  const remaining = MAX_QUEUE - queue.value.length
  if (remaining <= 0) {
    toast.warning(`Queue is full (${MAX_QUEUE} files maximum).`)
    return
  }

  const accepted = arr.slice(0, remaining)
  const skipped = arr.length - accepted.length
  if (skipped > 0) toast.warning(`Only ${remaining} more file(s) can be added to the queue.`)

  let added = 0
  for (const file of accepted) {
    if (isDuplicate(file)) {
      toast.info(`${file.name} is already in the queue — skipped.`)
      continue
    }
    const err = validateFile(file)
    if (err) {
      toast.error(err)
      continue
    }
    const fmt = detectFormat(file)
    queue.value.push({
      id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      name: file.name,
      size: file.size,
      format: fmt,
      suggestedType: suggestType(fmt),
      status: 'queued',
      file,
    })
    added++
  }

  if (added > 0) {
    processQueue()
  }
}

async function processQueue() {
  if (isProcessing) return
  enforceWorkspaceScope()
  isProcessing = true
  try {
    while (true) {
      const pending = queue.value.filter(e => e.status === 'queued')
      if (!pending.length) break

      const pendingDocs = pending.filter(e => e.format !== 'xlsx')
      const pendingXlsx = pending.filter(e => e.format === 'xlsx')

      const promises: Promise<void>[] = []

      // 1. Process documents with concurrency
      if (pendingDocs.length > 0) {
        const docBatch = pendingDocs.slice(0, UPLOAD_CONCURRENCY)
        promises.push(...docBatch.map(processDocumentEntry))
      }

      // 2. Process XLSX files
      if (pendingXlsx.length > 0) {
        if (pendingXlsx.length >= 2) {
          // Batch flow for 2+ XLSX files
          promises.push(processXlsxBatch(pendingXlsx))
        } else {
          // Single-workbook flow for 1 XLSX file
          promises.push(processSingleXlsx(pendingXlsx[0]))
        }
      }

      await Promise.allSettled(promises)
    }
  } finally {
    isProcessing = false
  }
}

async function processDocumentEntry(entry: QueueEntry) {
  entry.status = 'uploading'
  try {
    if (!entry.file) throw new Error('File data unavailable.')
    const result = await api.uploadDocument(entry.file)
    entry.file = undefined // Release raw File buffer
    entry.documentId = result.document_id
    entry.status = 'needs_review'
    entry.reviewPath = `/documents/${result.document_id}/review`
  } catch (err: any) {
    entry.status = 'failed'
    entry.error = err?.message || 'Document upload failed.'
  }
}

async function processSingleXlsx(entry: QueueEntry) {
  entry.status = 'uploading'
  // Clear any previous batch view so the user immediately sees the single-workbook workflow
  activeBatch.value = null
  try {
    if (!entry.file) throw new Error('File data unavailable.')
    const file = entry.file
    const workflow = useImportWorkflow()
    await workflow.handleFileUpload(file)
    entry.file = undefined // Release raw File buffer
    if (workflow.uploadError.value) {
      entry.status = 'failed'
      entry.error = workflow.uploadError.value
    } else {
      entry.fileId = workflow.uploadedFile.value?.id
      entry.status = 'needs_review'
      entry.suggestedType = 'spreadsheet'
      entry.reviewPath = `/workbooks/${workflow.uploadedFile.value?.id}/review`
    }
  } catch (err: any) {
    entry.status = 'failed'
    entry.error = err?.message || 'Upload failed.'
  }
}

async function processXlsxBatch(entries: QueueEntry[]) {
  for (const entry of entries) {
    entry.status = 'uploading'
  }

  // Upload each file
  const uploadedResults = await Promise.allSettled(
    entries.map(async (entry) => {
      if (!entry.file) throw new Error('File data unavailable.')
      const res = await api.uploadFile(entry.file)
      entry.file = undefined // Release raw File buffer
      entry.fileId = res.id
      entry.status = 'processing'
      return { entry, res }
    })
  )

  const successful: Array<{ entry: QueueEntry; res: SourceFileUploadResponse }> = []
  for (let i = 0; i < uploadedResults.length; i++) {
    const res = uploadedResults[i]
    const entry = entries[i]
    if (res.status === 'fulfilled') {
      successful.push(res.value)
    } else {
      entry.status = 'failed'
      entry.error = res.reason?.message || 'Upload failed.'
    }
  }

  if (successful.length >= 2) {
    try {
      const fileIds = successful.map(s => s.res.id)
      const batch = await api.createBatchImport(fileIds)
      activeBatch.value = batch
      for (const { entry, res } of successful) {
        const batchFile = batch.files.find(f => f.source_file_id === res.id)
        entry.batchId = batch.id
        entry.reviewPath = `/history/batch/${batch.id}/file/${res.id}/review`
        if (batchFile?.status === 'ready') {
          entry.status = 'ready'
          entry.suggestedType = 'spreadsheet'
        } else if (batchFile?.status === 'failed') {
          entry.status = 'failed'
          entry.error = batchFile.error_message || 'Analysis failed.'
        } else {
          entry.status = 'needs_review'
          if (batchFile?.detected_type) {
            entry.suggestedType = batchFile.detected_type as DocType
          }
        }
      }
    } catch (batchErr: any) {
      for (const { entry } of successful) {
        entry.status = 'failed'
        entry.error = batchErr?.message || 'Batch analysis failed.'
      }
    }
  } else if (successful.length === 1) {
    // Fallback: only 1 XLSX succeeded uploading out of the batch
    const { entry, res } = successful[0]
    const workflow = useImportWorkflow()
    workflow.uploadedFile.value = res
    workflow.selectedTemplateId.value = null
    workflow.previewResult.value = null
    workflow.confirmedBatch.value = null
    workflow.currentStep.value = 2
    await workflow.loadTemplates()
    entry.status = 'needs_review'
    entry.suggestedType = 'spreadsheet'
  }
}

function retryEntry(id: string) {
  const entry = queue.value.find(e => e.id === id)
  if (!entry || entry.status !== 'failed') return
  if (!entry.file) {
    toast.error('File buffer is no longer available. Please drop the file again to re-upload.')
    return
  }
  entry.status = 'queued'
  entry.error = undefined
  processQueue()
}

function removeEntry(id: string) {
  const entry = queue.value.find(e => e.id === id)
  if (entry && (entry.status === 'uploading' || entry.status === 'processing')) return
  queue.value = queue.value.filter(e => e.id !== id)
}

function clearCompleted() {
  queue.value = queue.value.filter(e => e.status !== 'imported' && e.status !== 'failed')
}

function markDocumentConfirmed(documentId: number) {
  const entry = queue.value.find(e => e.documentId === documentId)
  if (entry) {
    entry.status = 'imported'
  }
}

function markFileImported(fileId: number) {
  const entry = queue.value.find(e => e.fileId === fileId)
  if (entry) {
    entry.status = 'imported'
  }
}

export function useIngestionQueue() {
  enforceWorkspaceScope()

  const queueSummary = computed(() => {
    enforceWorkspaceScope()
    return {
      total: queue.value.length,
      ready: queue.value.filter(e => e.status === 'ready').length,
      uploading: queue.value.filter(e => e.status === 'uploading' || e.status === 'processing').length,
      needsReview: queue.value.filter(e => e.status === 'needs_review').length,
      imported: queue.value.filter(e => e.status === 'imported').length,
      failed: queue.value.filter(e => e.status === 'failed').length,
    }
  })

  return {
    queue,
    activeBatch,
    queueSummary,
    addFiles,
    removeEntry,
    clearCompleted,
    retryEntry,
    markDocumentConfirmed,
    markFileImported,
    enforceWorkspaceScope,
  }
}
