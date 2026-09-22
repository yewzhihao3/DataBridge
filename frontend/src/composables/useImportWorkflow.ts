
/**
 * src/composables/useImportWorkflow.ts
 *
 * Reactive state machine for the DataBridge ingestion workflow.
 */

import { computed, ref } from 'vue'
import { api } from '@/services/api'

import type {
  ApiError,
  ExtractionPreviewResponse,
  ImportBatchDetail,
  SourceFileUploadResponse,
  TemplateSummary,
} from '@/types/api'

export function useImportWorkflow() {
  // ── Step State ────────────────────────────────────────────────

  const currentStep = ref<1 | 2 | 3 | 4>(1)

  // ── Step 1: File Upload ──────────────────────────────────────

  const uploadedFile = ref<SourceFileUploadResponse | null>(
    null,
  )

  const isUploading = ref(false)
  const uploadError = ref<string | null>(null)

  // ── Step 2: Template Selection ───────────────────────────────

  const templates = ref<TemplateSummary[]>([])
  const selectedTemplateId = ref<number | null>(null)
  const isLoadingTemplates = ref(false)
  const templateError = ref<string | null>(null)

  // ── Step 3: Extraction Preview ───────────────────────────────

  const previewResult = ref<ExtractionPreviewResponse | null>(
    null,
  )

  const isExtracting = ref(false)
  const extractError = ref<string | null>(null)

  // ── Step 4: Import Confirmation ──────────────────────────────

  const isConfirming = ref(false)
  const confirmError = ref<string | null>(null)

  const confirmedBatch = ref<ImportBatchDetail | null>(null)

  const requiresWarningAcknowledgment = ref(false)
  const userAcknowledgedWarnings = ref(false)

  // ── Computed Properties ──────────────────────────────────────

  const hasValidationErrors = computed(() => {
    if (!previewResult.value) {
      return false
    }

    return Boolean(
      previewResult.value.has_errors ||
      !previewResult.value.validation_report
        ?.is_valid_for_import,
    )
  })

  const warningCount = computed(() => {
    if (!previewResult.value) {
      return 0
    }

    return previewResult.value.warning_count ?? 0
  })

  const canConfirm = computed(() => {
    if (!previewResult.value) {
      return false
    }

    if (hasValidationErrors.value) {
      return false
    }

    return !(
      warningCount.value > 0 &&
      !userAcknowledgedWarnings.value
    )
  })

  // ── Step 1: Upload File ──────────────────────────────────────

  async function handleFileUpload(file: File) {
    isUploading.value = true

    uploadError.value = null
    templateError.value = null
    extractError.value = null
    confirmError.value = null

    try {
      const response = await api.uploadFile(file)

      uploadedFile.value = response
      selectedTemplateId.value = null

      previewResult.value = null
      confirmedBatch.value = null

      currentStep.value = 2

      await loadTemplates()
    } catch (error: unknown) {
      uploadError.value = getErrorMessage(
        error,
        'File upload failed.',
      )
    } finally {
      isUploading.value = false
    }
  }

  // ── Step 2: Load Templates ───────────────────────────────────

  async function loadTemplates() {
    isLoadingTemplates.value = true
    templateError.value = null

    try {
      const loadedTemplates = await api.listTemplates()

      templates.value = Array.isArray(loadedTemplates)
        ? loadedTemplates
        : []

      if (templates.value.length === 0) {
        selectedTemplateId.value = null
        return
      }

      /*
       * Preserve the current selection if it still exists.
       */

      if (selectedTemplateId.value !== null) {
        const selectedStillExists = templates.value.some(
          (template) =>
            template.id === selectedTemplateId.value,
        )

        if (selectedStillExists) {
          return
        }
      }

      /*
       * Safely normalize worksheet names before using includes().
       */

      const sheetNames = Array.isArray(
        uploadedFile.value?.sheet_names,
      )
        ? uploadedFile.value.sheet_names
        : []

      const matchingTemplate = templates.value.find(
        (template) =>
          sheetNames.includes(template.worksheet),
      )

      selectedTemplateId.value =
        matchingTemplate?.id ?? templates.value[0].id
    } catch (error: unknown) {
      templateError.value = getErrorMessage(
        error,
        'Failed to load templates.',
      )
    } finally {
      isLoadingTemplates.value = false
    }
  }

  // ── Step 3: Run Extraction ───────────────────────────────────

  async function runExtraction() {
    extractError.value = null

    /*
     * Store validated values in local constants.
     * This prevents TypeScript from treating them as
     * undefined or null later in the function.
     */

    const fileId = uploadedFile.value?.id
    const templateId = selectedTemplateId.value

    if (typeof fileId !== 'number' || fileId <= 0) {
      extractError.value =
        'The uploaded file ID is missing. Please upload the file again.'
      return
    }

    if (typeof templateId !== 'number' || templateId <= 0) {
      extractError.value =
        'Please select an extraction template.'
      return
    }

    isExtracting.value = true
    confirmError.value = null
    requiresWarningAcknowledgment.value = false
    userAcknowledgedWarnings.value = false

    try {
      const response = await api.extractPreview(
        fileId,
        templateId,
      )

      previewResult.value = response
      currentStep.value = 3
    } catch (error: unknown) {
      extractError.value = getErrorMessage(
        error,
        'Extraction failed.',
      )
    } finally {
      isExtracting.value = false
    }
  }

  // ── Step 4: Confirm Import ───────────────────────────────────

  async function confirmImport() {
    confirmError.value = null

    /*
     * Validate and store IDs in local constants.
     */

    const fileId = uploadedFile.value?.id
    const templateId = selectedTemplateId.value

    if (typeof fileId !== 'number' || fileId <= 0) {
      confirmError.value =
        'The uploaded file ID is missing. Please upload the file again.'
      return
    }

    if (typeof templateId !== 'number' || templateId <= 0) {
      confirmError.value =
        'Please select an extraction template.'
      return
    }

    isConfirming.value = true

    try {
      const batch = await api.confirmImport({
        file_id: fileId,
        template_id: templateId,
        acknowledge_warnings:
          userAcknowledgedWarnings.value,
      })

      confirmedBatch.value = batch
      currentStep.value = 4
    } catch (error: unknown) {
      const apiError = error as Partial<ApiError>

      if (
        apiError.isWarningAcknowledgmentRequired ||
        apiError.status === 400
      ) {
        requiresWarningAcknowledgment.value = true
      }

      confirmError.value = getErrorMessage(
        error,
        'Failed to confirm import.',
      )
    } finally {
      isConfirming.value = false
    }
  }

  // ── Reset Workflow ───────────────────────────────────────────

  function resetWorkflow() {
    currentStep.value = 1

    uploadedFile.value = null
    uploadError.value = null
    isUploading.value = false

    templates.value = []
    selectedTemplateId.value = null
    templateError.value = null
    isLoadingTemplates.value = false

    previewResult.value = null
    extractError.value = null
    isExtracting.value = false

    confirmError.value = null
    isConfirming.value = false

    confirmedBatch.value = null
    requiresWarningAcknowledgment.value = false
    userAcknowledgedWarnings.value = false
  }

  return {
    currentStep,

    uploadedFile,
    isUploading,
    uploadError,

    templates,
    selectedTemplateId,
    isLoadingTemplates,
    templateError,

    previewResult,
    isExtracting,
    extractError,

    isConfirming,
    confirmError,
    confirmedBatch,

    requiresWarningAcknowledgment,
    userAcknowledgedWarnings,

    hasValidationErrors,
    warningCount,
    canConfirm,

    handleFileUpload,
    loadTemplates,
    runExtraction,
    confirmImport,
    resetWorkflow,
  }
}

// ── Error Helper ────────────────────────────────────────────────

function getErrorMessage(
  error: unknown,
  fallback: string,
): string {
  if (
    typeof error === 'object' &&
    error !== null &&
    'message' in error
  ) {
    const message = (error as { message?: unknown }).message

    if (
      typeof message === 'string' &&
      message.trim()
    ) {
      return message
    }
  }

  return fallback
}