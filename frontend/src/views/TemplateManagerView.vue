<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api } from '@/services/api'
import type {
  TemplateCreate,
  TemplateDetail,
  TemplateFieldMapping,
  TemplateSummary,
} from '@/types/api'

const templates = ref<TemplateSummary[]>([])
const canonicalFields = ref<string[]>([])
const canonicalLineItemFields = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const deleting = ref<number | null>(null)

const errorMessage = ref('')
const successMessage = ref('')

const isFormOpen = ref(false)
const editingTemplateId = ref<number | null>(null)

// Mode tab: 'invoice' (Invoice Template: Header + optional Line Items) or 'dataset' (Multi-Record Dataset)
const templateType = ref<'invoice' | 'dataset'>('invoice')

const form = reactive({
  name: '',
  description: '',
  file_type: 'xlsx',
  worksheet: '',
  header_row: 1 as number | null,
  data_start_row: 2 as number | null,
  header_mappings: [] as TemplateFieldMapping[],
  line_item_mappings: [] as TemplateFieldMapping[],
})

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.file_type = 'xlsx'
  form.worksheet = ''
  form.header_row = 1
  form.data_start_row = 2
  form.header_mappings = []
  form.line_item_mappings = []
  editingTemplateId.value = null
  templateType.value = 'invoice'
}

const openCreateForm = () => {
  resetForm()
  errorMessage.value = ''
  successMessage.value = ''
  isFormOpen.value = true
}

const closeForm = () => {
  isFormOpen.value = false
  resetForm()
}

const customHeaderTargetActive = reactive<Record<number, boolean>>({})
const customLineItemTargetActive = reactive<Record<number, boolean>>({})

const isCanonicalHeaderOrEmpty = (field: string | null | undefined): boolean => {
  if (!field) return true
  return canonicalFields.value.includes(field)
}

const isCanonicalLineItemOrEmpty = (field: string | null | undefined): boolean => {
  if (!field) return true
  return canonicalLineItemFields.value.includes(field)
}

const handleHeaderTargetChange = (
  event: Event,
  index: number,
  mapping: TemplateFieldMapping,
) => {
  const value = (event.target as HTMLSelectElement).value
  if (value === '__custom__') {
    customHeaderTargetActive[index] = true
    if (isCanonicalHeaderOrEmpty(mapping.target_field)) {
      mapping.target_field = ''
    }
  } else {
    customHeaderTargetActive[index] = false
    mapping.target_field = value
  }
}

const handleLineItemTargetChange = (
  event: Event,
  index: number,
  mapping: TemplateFieldMapping,
) => {
  const value = (event.target as HTMLSelectElement).value
  if (value === '__custom__') {
    customLineItemTargetActive[index] = true
    if (isCanonicalLineItemOrEmpty(mapping.target_field)) {
      mapping.target_field = ''
    }
  } else {
    customLineItemTargetActive[index] = false
    mapping.target_field = value
  }
}

const switchTemplateType = (targetType: 'invoice' | 'dataset') => {
  if (templateType.value === targetType) return

  const hasData = form.header_mappings.length > 0 || form.line_item_mappings.length > 0
  if (hasData) {
    const fromName = templateType.value === 'invoice' ? 'Invoice Template' : 'Dataset Template'
    const toName = targetType === 'invoice' ? 'Invoice Template' : 'Dataset Template'
    const confirmMessage = `Switching from ${fromName} to ${toName} will reconfigure your field mapping layout. Do you want to switch?`
    if (!window.confirm(confirmMessage)) {
      return
    }
  }

  templateType.value = targetType

  if (targetType === 'dataset') {
    // For dataset templates, all header mappings use columns
    form.header_mappings.forEach((m) => {
      m.mapping_type = 'column'
      m.mapping_group = 'header'
    })
    form.line_item_mappings = []
  } else {
    // For invoice templates, header mappings use cell references
    form.header_mappings.forEach((m) => {
      m.mapping_type = 'cell'
      m.mapping_group = 'header'
    })
  }
}

const addHeaderMapping = () => {
  form.header_mappings.push({
    field_name: '',
    target_field: '',
    mapping_group: 'header',
    mapping_type: templateType.value === 'invoice' ? 'cell' : 'column',
    cell_ref: '',
    column_ref: '',
    is_required: false,
    data_type: 'text',
    date_format: '',
  })
}

const removeHeaderMapping = (index: number) => {
  delete customHeaderTargetActive[index]
  form.header_mappings.splice(index, 1)
}

const addLineItemMapping = () => {
  form.line_item_mappings.push({
    field_name: '',
    target_field: '',
    mapping_group: 'line_item',
    mapping_type: 'column',
    column_ref: '',
    is_required: false,
    data_type: 'text',
    date_format: '',
  })
}

const removeLineItemMapping = (index: number) => {
  delete customLineItemTargetActive[index]
  form.line_item_mappings.splice(index, 1)
}

const loadCanonicalFields = async () => {
  try {
    const [headerFields, lineFields] = await Promise.all([
      api.listCanonicalFields(),
      api.listCanonicalLineItemFields(),
    ])
    canonicalFields.value = headerFields
    canonicalLineItemFields.value = lineFields
  } catch (error) {
    console.error('Failed to load canonical fields:', error)
  }
}

const loadTemplates = async () => {
  loading.value = true
  errorMessage.value = ''

  try {
    templates.value = await api.listTemplates()
  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to load templates.'
  } finally {
    loading.value = false
  }
}

const editTemplate = async (template: TemplateSummary) => {
  loading.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    const detail: TemplateDetail = await api.getTemplate(template.id)

    form.name = detail.name
    form.description = detail.description || ''
    form.file_type = detail.file_type
    form.worksheet = detail.worksheet || ''
    form.header_row = detail.header_row || 1
    form.data_start_row = detail.data_start_row || 2

    const detectedType = detail.template_type ||
      (detail.field_mappings.every((m) => m.mapping_type === 'column') ? 'dataset' : 'invoice')
    templateType.value = detectedType

    const headers: TemplateFieldMapping[] = []
    const lineItems: TemplateFieldMapping[] = []

    for (const m of detail.field_mappings) {
      const mappingGroup = m.mapping_group || 'header'
      const item: TemplateFieldMapping = {
        id: m.id,
        field_name: m.field_name,
        target_field: m.target_field || '',
        mapping_group: mappingGroup,
        mapping_type: m.mapping_type,
        cell_ref: m.cell_ref || '',
        column_ref: m.column_ref || '',
        is_required: m.is_required,
        data_type: m.data_type,
        date_format: m.date_format || '',
      }
      if (mappingGroup === 'line_item') {
        lineItems.push(item)
      } else {
        headers.push(item)
      }
    }

    form.header_mappings = headers
    form.line_item_mappings = lineItems
    editingTemplateId.value = detail.id
    isFormOpen.value = true
  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to load template details.'
  } finally {
    loading.value = false
  }
}

const validateForm = (): boolean => {
  if (!form.name.trim()) {
    errorMessage.value = 'Template name is required.'
    return false
  }

  if (!form.worksheet.trim()) {
    errorMessage.value = 'Worksheet name is required.'
    return false
  }

  if (templateType.value === 'dataset' || form.line_item_mappings.length > 0) {
    if (!form.header_row || form.header_row < 1) {
      errorMessage.value = 'Header row must be at least 1.'
      return false
    }
    if (!form.data_start_row || form.data_start_row < 1) {
      errorMessage.value = 'Data start row must be at least 1.'
      return false
    }
  }

  if (form.header_mappings.length === 0 && form.line_item_mappings.length === 0) {
    errorMessage.value = 'Add at least one field mapping.'
    return false
  }

  for (const mapping of form.header_mappings) {
    if (!mapping.field_name.trim()) {
      errorMessage.value = 'Every mapping must have a field name.'
      return false
    }
    if (templateType.value === 'invoice' && !mapping.cell_ref?.trim()) {
      errorMessage.value = `Cell reference (e.g. B2) is required for header field "${mapping.field_name}".`
      return false
    }
    if (templateType.value === 'dataset' && !mapping.column_ref?.trim()) {
      errorMessage.value = `Column reference (e.g. A) is required for field "${mapping.field_name}".`
      return false
    }
  }

  for (const mapping of form.line_item_mappings) {
    if (!mapping.field_name.trim()) {
      errorMessage.value = 'Every line item mapping must have a field name.'
      return false
    }
    if (!mapping.column_ref?.trim()) {
      errorMessage.value = `Column reference (e.g. A) is required for line item "${mapping.field_name}".`
      return false
    }
  }

  return true
}

const saveTemplate = async () => {
  errorMessage.value = ''
  successMessage.value = ''

  if (!validateForm()) {
    return
  }

  saving.value = true

  try {
    const combinedMappings: TemplateFieldMapping[] = []

    // Header mappings
    form.header_mappings.forEach((m) => {
      combinedMappings.push({
        field_name: m.field_name.trim(),
        target_field: m.target_field?.trim() || undefined,
        mapping_group: 'header',
        mapping_type: templateType.value === 'invoice' ? 'cell' : 'column',
        cell_ref: templateType.value === 'invoice' ? m.cell_ref?.trim() || undefined : undefined,
        column_ref: templateType.value === 'dataset' ? m.column_ref?.trim() || undefined : undefined,
        is_required: m.is_required,
        data_type: m.data_type,
        date_format: m.date_format?.trim() || undefined,
      })
    })

    // Line item mappings (Invoice mode only)
    if (templateType.value === 'invoice') {
      form.line_item_mappings.forEach((m) => {
        combinedMappings.push({
          field_name: m.field_name.trim(),
          target_field: m.target_field?.trim() || undefined,
          mapping_group: 'line_item',
          mapping_type: 'column',
          column_ref: m.column_ref?.trim() || undefined,
          is_required: m.is_required,
          data_type: m.data_type,
          date_format: m.date_format?.trim() || undefined,
        })
      })
    }

    const payload: TemplateCreate = {
      name: form.name.trim(),
      description: form.description?.trim() || '',
      template_type: templateType.value,
      file_type: form.file_type,
      worksheet: form.worksheet.trim(),
      header_row:
        templateType.value === 'dataset' || form.line_item_mappings.length > 0
          ? form.header_row ? Number(form.header_row) : 1
          : undefined,
      data_start_row:
        templateType.value === 'dataset' || form.line_item_mappings.length > 0
          ? form.data_start_row ? Number(form.data_start_row) : 2
          : undefined,
      field_mappings: combinedMappings,
    }

    if (editingTemplateId.value !== null) {
      await api.updateTemplate(editingTemplateId.value, payload)
      successMessage.value = 'Template updated successfully.'
    } else {
      await api.createTemplate(payload)
      successMessage.value = 'Template created successfully.'
    }

    closeForm()
    await loadTemplates()
  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to save template.'
  } finally {
    saving.value = false
  }
}

const deleteTemplate = async (template: TemplateSummary) => {
  const confirmed = window.confirm(
    `Are you sure you want to delete "${template.name}"?`,
  )

  if (!confirmed) {
    return
  }

  deleting.value = template.id
  errorMessage.value = ''
  successMessage.value = ''

  try {
    await api.deleteTemplate(template.id)
    successMessage.value = 'Template deleted successfully.'
    await loadTemplates()
  } catch (error: any) {
    errorMessage.value = error.message || 'Failed to delete template.'
  } finally {
    deleting.value = null
  }
}

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleString()
}

onMounted(async () => {
  await Promise.all([loadTemplates(), loadCanonicalFields()])
})
</script>

<template>
  <section class="template-manager container">
    <!-- Page Header -->
    <div class="page-header">
      <div>
        <div class="eyebrow">CONFIGURATION</div>
        <h1>Template Manager</h1>
        <p class="page-description">
          Create and manage templates for single invoices with line items or multi-record datasets.
        </p>
      </div>

      <button
        v-if="!isFormOpen"
        class="btn btn-primary"
        @click="openCreateForm"
      >
        <span>+</span>
        New Template
      </button>
    </div>

    <!-- Messages -->
    <div v-if="errorMessage" class="message message-error">
      <strong>Error</strong>
      <span>{{ errorMessage }}</span>
    </div>

    <div v-if="successMessage" class="message message-success">
      <strong>Success</strong>
      <span>{{ successMessage }}</span>
    </div>

    <!-- Template Form -->
    <div v-if="isFormOpen" class="glass-card template-form">
      <div class="form-header">
        <div>
          <div class="eyebrow">
            {{ editingTemplateId !== null ? 'EDITING' : 'NEW TEMPLATE' }}
          </div>
          <h2>
            {{ editingTemplateId !== null ? 'Edit Template' : 'Create Template' }}
          </h2>
        </div>

        <button
          class="btn btn-secondary"
          :disabled="saving"
          @click="closeForm"
        >
          Cancel
        </button>
      </div>

      <!-- General Information -->
      <div class="section-heading">
        <h3>General Information</h3>
        <p>Configure basic metadata and target spreadsheet worksheet.</p>
      </div>

      <div class="form-grid">
        <label class="form-field">
          <span>Template Name</span>
          <input
            v-model="form.name"
            type="text"
            placeholder="Standard Invoice Template"
          />
        </label>

        <label class="form-field">
          <span>File Type</span>
          <select v-model="form.file_type">
            <option value="xlsx">XLSX</option>
            <option value="xls">XLS</option>
            <option value="csv">CSV</option>
          </select>
        </label>

        <label class="form-field">
          <span>Worksheet Name</span>
          <input
            v-model="form.worksheet"
            type="text"
            placeholder="Invoice"
          />
        </label>

        <label class="form-field form-field-wide">
          <span>Description</span>
          <textarea
            v-model="form.description"
            rows="2"
            placeholder="Describe this template..."
          />
        </label>
      </div>

      <!-- Template Type Selection Tabs -->
      <div class="mode-section">
        <div class="mode-tabs-header">
          <h3>Template Type</h3>
          <p>Choose whether this template extracts a single invoice or imports a multi-row dataset.</p>
        </div>

        <div class="mode-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            :aria-selected="templateType === 'invoice'"
            class="mode-tab"
            :class="{ active: templateType === 'invoice' }"
            @click="switchTemplateType('invoice')"
          >
            <div class="tab-icon">📄</div>
            <div class="tab-label-group">
              <span class="tab-title">Invoice Template</span>
              <span class="tab-sub">Extract invoice information and optional product/service line items</span>
            </div>
          </button>

          <button
            type="button"
            role="tab"
            :aria-selected="templateType === 'dataset'"
            class="mode-tab"
            :class="{ active: templateType === 'dataset' }"
            @click="switchTemplateType('dataset')"
          >
            <div class="tab-icon">📊</div>
            <div class="tab-label-group">
              <span class="tab-title">Dataset Template</span>
              <span class="tab-sub">Import structured spreadsheets containing multiple independent records</span>
            </div>
          </button>
        </div>

        <!-- Banner for Selected Mode -->
        <div class="mode-banner glass-card">
          <div v-if="templateType === 'invoice'" class="mode-info">
            <div class="mode-title-row">
              <h4>Invoice Template</h4>
            </div>
            <p class="mode-description">
              Extracts high-level invoice details (supplier, invoice number, totals) from exact Excel cell coordinates, with optional repeating product/service line items extracted from table columns.
            </p>

            <!-- Line Items Table Parameters -->
            <div v-if="form.line_item_mappings.length > 0" class="form-grid spreadsheet-options">
              <label class="form-field">
                <div class="field-label-row">
                  <span>Line Items Header Row</span>
                </div>
                <input
                  v-model.number="form.header_row"
                  type="number"
                  min="1"
                  placeholder="7"
                />
              </label>

              <label class="form-field">
                <div class="field-label-row">
                  <span>Line Items Data Start Row</span>
                </div>
                <input
                  v-model.number="form.data_start_row"
                  type="number"
                  min="1"
                  placeholder="8"
                />
              </label>
            </div>
          </div>

          <div v-else class="mode-info">
            <div class="mode-title-row">
              <h4>Dataset Template</h4>
            </div>
            <p class="mode-description">
              Imports multiple independent invoice records from rows in a structured spreadsheet dataset.
            </p>

            <div class="form-grid spreadsheet-options">
              <label class="form-field">
                <div class="field-label-row">
                  <span>Header Row</span>
                </div>
                <input
                  v-model.number="form.header_row"
                  type="number"
                  min="1"
                  placeholder="1"
                />
              </label>

              <label class="form-field">
                <div class="field-label-row">
                  <span>Data Start Row</span>
                </div>
                <input
                  v-model.number="form.data_start_row"
                  type="number"
                  min="1"
                  placeholder="2"
                />
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- Section 1: Header / Dataset Fields -->
      <div class="section-heading mapping-heading">
        <div>
          <h3>{{ templateType === 'invoice' ? 'Invoice Header Fields' : 'Dataset Record Fields' }}</h3>
          <p v-if="templateType === 'invoice'">
            Map invoice fields to specific cell coordinates (e.g. B2, F4, E17).
          </p>
          <p v-else>
            Map record fields to spreadsheet column letters (e.g. A, B, C).
          </p>
        </div>

        <button type="button" class="btn btn-secondary" @click="addHeaderMapping">
          <span>+</span>
          Add Field
        </button>
      </div>

      <div v-if="form.header_mappings.length === 0" class="empty-state compact">
        <p>No header field mappings configured.</p>
        <button type="button" class="btn btn-secondary" @click="addHeaderMapping">
          Add First Header Field
        </button>
      </div>

      <div
        v-for="(mapping, index) in form.header_mappings"
        :key="`header-${index}`"
        class="mapping-card"
      >
        <div class="mapping-card-header">
          <div class="mapping-title">
            <span class="mapping-number">{{ String(index + 1).padStart(2, '0') }}</span>
            <strong>Field Mapping {{ index + 1 }}</strong>
          </div>

          <button
            type="button"
            class="btn btn-danger btn-small"
            @click="removeHeaderMapping(index)"
          >
            Remove
          </button>
        </div>

        <div class="mapping-grid">
          <label class="form-field">
            <span>Field Name</span>
            <input
              v-model="mapping.field_name"
              type="text"
              placeholder="invoice_number"
            />
          </label>

          <label class="form-field">
            <span>Target Canonical Field</span>
            <select
              :value="
                isCanonicalHeaderOrEmpty(mapping.target_field) &&
                !customHeaderTargetActive[index]
                  ? mapping.target_field || ''
                  : '__custom__'
              "
              @change="handleHeaderTargetChange($event, index, mapping)"
            >
              <option value="">(Auto / Custom Field)</option>
              <option v-for="cf in canonicalFields" :key="cf" :value="cf">
                {{ cf }}
              </option>
              <option value="__custom__">Custom Field Name...</option>
            </select>
          </label>

          <label
            v-if="customHeaderTargetActive[index]"
            class="form-field"
          >
            <span>Custom Target Name</span>
            <input
              v-model="mapping.target_field"
              type="text"
              placeholder="e.g. po_reference"
            />
          </label>

          <!-- Cell Reference for Invoice Header -->
          <label
            v-if="templateType === 'invoice'"
            class="form-field"
          >
            <span>Cell Reference</span>
            <input
              v-model="mapping.cell_ref"
              type="text"
              placeholder="B2"
            />
          </label>

          <!-- Column Reference for Dataset -->
          <label
            v-if="templateType === 'dataset'"
            class="form-field"
          >
            <span>Column Reference</span>
            <input
              v-model="mapping.column_ref"
              type="text"
              placeholder="A"
            />
          </label>

          <label class="form-field">
            <span>Data Type</span>
            <select v-model="mapping.data_type">
              <option value="text">Text</option>
              <option value="decimal">Decimal / Currency</option>
              <option value="date">Date</option>
              <option value="integer">Integer</option>
            </select>
          </label>

          <label
            v-if="mapping.data_type === 'date'"
            class="form-field"
          >
            <span>Date Format (Optional)</span>
            <input
              v-model="mapping.date_format"
              type="text"
              placeholder="YYYY-MM-DD"
            />
          </label>

          <label class="checkbox-field">
            <input
              v-model="mapping.is_required"
              type="checkbox"
            />
            <span>Required field</span>
          </label>
        </div>
      </div>

      <!-- Section 2: Optional Line Items (Invoice Templates Only) -->
      <div v-if="templateType === 'invoice'" class="line-items-block" style="margin-top: 36px; padding-top: 24px; border-top: 1px solid var(--border-default);">
        <div class="section-heading mapping-heading">
          <div>
            <h3>Line Item Breakdown (Optional)</h3>
            <p>
              Extract repeating product or service rows (e.g. Description, Quantity, Unit Price, Tax Rate, Tax Amount, Amount) mapped by column letters.
            </p>
          </div>

          <button type="button" class="btn btn-secondary" @click="addLineItemMapping">
            <span>+</span>
            Add Line Item Column
          </button>
        </div>

        <div v-if="form.line_item_mappings.length === 0" class="empty-state compact">
          <p>No line item columns configured. (Header-only invoice)</p>
          <button type="button" class="btn btn-secondary" @click="addLineItemMapping">
            + Enable Line Item Extraction
          </button>
        </div>

        <div
          v-for="(mapping, index) in form.line_item_mappings"
          :key="`line-${index}`"
          class="mapping-card"
        >
          <div class="mapping-card-header">
            <div class="mapping-title">
              <span class="mapping-number">{{ String(index + 1).padStart(2, '0') }}</span>
              <strong>Line Item Column {{ index + 1 }}</strong>
            </div>

            <button
              type="button"
              class="btn btn-danger btn-small"
              @click="removeLineItemMapping(index)"
            >
              Remove
            </button>
          </div>

          <div class="mapping-grid">
            <label class="form-field">
              <span>Field Name</span>
              <input
                v-model="mapping.field_name"
                type="text"
                placeholder="description"
              />
            </label>

            <label class="form-field">
              <span>Target Canonical Line Field</span>
              <select
                :value="
                  isCanonicalLineItemOrEmpty(mapping.target_field) &&
                  !customLineItemTargetActive[index]
                    ? mapping.target_field || ''
                    : '__custom__'
                "
                @change="handleLineItemTargetChange($event, index, mapping)"
              >
                <option value="">(Auto / Match Field Name)</option>
                <option v-for="cf in canonicalLineItemFields" :key="cf" :value="cf">
                  {{ cf }}
                </option>
                <option value="__custom__">Custom Field Name...</option>
              </select>
            </label>

            <label
              v-if="customLineItemTargetActive[index]"
              class="form-field"
            >
              <span>Custom Target Name</span>
              <input
                v-model="mapping.target_field"
                type="text"
                placeholder="e.g. sku_code"
              />
            </label>

            <label class="form-field">
              <span>Column Letter</span>
              <input
                v-model="mapping.column_ref"
                type="text"
                placeholder="A"
              />
            </label>

            <label class="form-field">
              <span>Data Type</span>
              <select v-model="mapping.data_type">
                <option value="text">Text</option>
                <option value="decimal">Decimal / Numeric</option>
                <option value="date">Date</option>
                <option value="integer">Integer</option>
              </select>
            </label>

            <label class="checkbox-field">
              <input
                v-model="mapping.is_required"
                type="checkbox"
              />
              <span>Required for each line</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Form Actions -->
      <div class="form-actions" style="margin-top: 32px;">
        <button
          type="button"
          class="btn btn-secondary"
          :disabled="saving"
          @click="closeForm"
        >
          Cancel
        </button>

        <button
          type="button"
          class="btn btn-primary"
          :disabled="saving"
          @click="saveTemplate"
        >
          {{ saving ? 'Saving...' : 'Save Template' }}
        </button>
      </div>
    </div>

    <!-- Template List -->
    <div v-else class="template-list">
      <div v-if="loading" class="glass-card empty-state">
        <div class="loading-spinner"></div>
        <p>Loading templates...</p>
      </div>

      <div v-else-if="templates.length === 0" class="glass-card empty-state">
        <div class="empty-icon">▤</div>
        <h3>No templates found</h3>
        <p>Create your first import template to get started.</p>
        <button class="btn btn-primary" @click="openCreateForm">
          Create Template
        </button>
      </div>

      <div v-else class="glass-card template-table-card">
        <div class="table-header">
          <div>
            <h2>Saved Templates</h2>
            <p>{{ templates.length }} template(s) available</p>
          </div>

          <button
            class="btn btn-secondary btn-small"
            :disabled="loading"
            @click="loadTemplates"
          >
            Refresh
          </button>
        </div>

        <div class="template-table-wrapper">
          <table class="template-table">
            <thead>
              <tr>
                <th>Template Name</th>
                <th>Type</th>
                <th>File Format</th>
                <th>Worksheet</th>
                <th>Mappings</th>
                <th>Updated</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="template in templates"
                :key="template.id"
              >
                <td>
                  <div class="template-name">
                    <strong>{{ template.name }}</strong>
                    <small v-if="template.description">
                      {{ template.description }}
                    </small>
                  </div>
                </td>

                <td>
                  <span
                    class="badge"
                    :class="template.template_type === 'dataset' ? 'badge-dataset' : 'badge-invoice'"
                  >
                    {{ template.template_type === 'dataset' ? 'Dataset Template' : 'Invoice Template' }}
                  </span>
                </td>

                <td>
                  <span class="badge badge-info">
                    {{ template.file_type.toUpperCase() }}
                  </span>
                </td>

                <td class="mono">
                  {{ template.worksheet }}
                </td>

                <td>
                  <span class="mapping-count">
                    {{ template.mapping_count }}
                  </span>
                </td>

                <td class="date-cell">
                  {{ formatDate(template.updated_at) }}
                </td>

                <td>
                  <div class="actions-cell">
                    <button
                      class="btn btn-secondary btn-small"
                      :disabled="loading"
                      @click="editTemplate(template)"
                    >
                      Edit
                    </button>

                    <button
                      class="btn btn-danger btn-small"
                      :disabled="deleting === template.id"
                      @click="deleteTemplate(template)"
                    >
                      {{ deleting === template.id ? 'Deleting...' : 'Delete' }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.template-manager {
  width: 100%;
  padding-top: 32px;
  padding-bottom: 48px;
}

.page-header,
.form-header,
.mapping-heading,
.table-header,
.form-actions,
.mapping-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.page-header {
  margin-bottom: 28px;
}

.eyebrow {
  margin-bottom: 8px;
  color: var(--accent-brand);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.page-header h1,
.form-header h2,
.table-header h2,
.section-heading h3,
.empty-state h3 {
  margin: 0;
  color: var(--text-primary);
}

.page-header h1 {
  font-size: 28px;
  font-weight: 750;
}

.page-description,
.section-heading p,
.table-header p,
.empty-state p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.message {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 14px 16px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: 13px;
}

.message-error {
  border-color: var(--status-error);
  background: rgba(239, 68, 68, 0.08);
  color: var(--status-error);
}

.message-success {
  border-color: var(--status-success);
  background: rgba(34, 197, 94, 0.08);
  color: var(--status-success);
}

.template-form {
  padding: 28px;
}

.form-header {
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border-default);
}

.form-header h2 {
  font-size: 20px;
}

.section-heading {
  margin-top: 28px;
  margin-bottom: 18px;
}

.section-heading h3 {
  font-size: 16px;
}

.mapping-heading {
  align-items: flex-end;
}

.form-grid,
.mapping-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

/* Mode Selection Tabs */
.mode-section {
  margin-top: 28px;
  margin-bottom: 24px;
}

.mode-tabs-header {
  margin-bottom: 14px;
}

.mode-tabs-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
}

.mode-tabs-header p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.mode-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.mode-tab {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  border: 1px solid var(--border-medium, #475569);
  border-radius: var(--radius-md, 8px);
  background: var(--bg-subtle, rgba(30, 41, 59, 0.5));
  color: var(--text-secondary, #94a3b8);
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
}

.mode-tab:hover {
  border-color: var(--accent-brand, #6366f1);
  background: rgba(99, 102, 241, 0.08);
  color: var(--text-primary, #f8fafc);
}

.mode-tab.active {
  border-color: var(--accent-brand, #6366f1);
  background: rgba(99, 102, 241, 0.14);
  color: var(--text-primary, #f8fafc);
  box-shadow: 0 0 0 1px var(--accent-brand, #6366f1);
}

.tab-icon {
  font-size: 24px;
  line-height: 1;
}

.tab-label-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tab-title {
  color: var(--text-primary, #f8fafc);
  font-size: 14px;
  font-weight: 650;
}

.tab-sub {
  color: var(--text-muted, #94a3b8);
  font-size: 12px;
}

.mode-banner {
  padding: 20px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: var(--radius-md, 8px);
  background: rgba(15, 23, 42, 0.5);
}

.mode-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-title-row h4 {
  margin: 0;
  color: var(--text-primary, #f8fafc);
  font-size: 15px;
  font-weight: 700;
}

.mode-description {
  margin: 6px 0 0;
  color: var(--text-secondary, #cbd5e1);
  font-size: 13px;
  line-height: 1.5;
}

.spreadsheet-options {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border-default, rgba(255, 255, 255, 0.08));
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-field-wide {
  grid-column: 1 / -1;
}

.form-field span {
  color: var(--text-secondary, #94a3b8);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.form-field input,
.form-field select,
.form-field textarea {
  width: 100%;
  padding: 11px 14px;
  border: 1px solid var(--border-medium, rgba(255, 255, 255, 0.18));
  border-radius: var(--radius-md, 8px);
  background: linear-gradient(180deg, #0e1726 0%, #0a0f1d 100%);
  color: var(--text-primary, #f8fafc);
  font-size: 13.5px;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.45);
  transition: all 0.2s ease;
}

.form-field input::placeholder,
.form-field textarea::placeholder {
  color: #64748b;
  opacity: 0.8;
}

.form-field select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  padding-right: 38px;
}

.form-field select option {
  background: #0f172a;
  color: #f8fafc;
}

.form-field input:hover,
.form-field select:hover,
.form-field textarea:hover {
  border-color: rgba(99, 102, 241, 0.5);
  background: linear-gradient(180deg, #111c30 0%, #0c1322 100%);
}

.form-field input:focus,
.form-field select:focus,
.form-field textarea:focus {
  outline: none;
  border-color: var(--accent-brand, #6366f1);
  background: linear-gradient(180deg, #111c30 0%, #0c1322 100%);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25), inset 0 1px 2px rgba(0, 0, 0, 0.3);
}

.checkbox-field {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 24px;
  cursor: pointer;
  user-select: none;
}

.checkbox-field input[type='checkbox'] {
  width: 17px;
  height: 17px;
  accent-color: var(--accent-brand, #6366f1);
  border-radius: 4px;
  cursor: pointer;
}

.checkbox-field span {
  color: var(--text-primary, #f8fafc);
  font-size: 13px;
  font-weight: 500;
}

.mapping-card {
  margin-bottom: 16px;
  padding: 20px;
  border: 1px solid var(--border-medium, rgba(255, 255, 255, 0.14));
  border-radius: var(--radius-md, 10px);
  background: linear-gradient(180deg, rgba(19, 29, 49, 0.75) 0%, rgba(15, 23, 42, 0.85) 100%);
  box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.35);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.mapping-card:hover {
  border-color: rgba(99, 102, 241, 0.35);
  box-shadow: 0 6px 20px -2px rgba(0, 0, 0, 0.45);
}

.mapping-card-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
}

.mapping-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mapping-number {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--accent-subtle);
  color: var(--accent-brand);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
}

.mapping-card strong {
  color: var(--text-primary);
  font-size: 14px;
}

.template-table-wrapper {
  overflow-x: auto;
}

.template-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.template-table th,
.template-table td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-default);
  font-size: 13px;
}

.template-table th {
  background: var(--bg-subtle);
  color: var(--text-secondary);
  font-weight: 650;
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.05em;
}

.template-table tr:hover td {
  background: rgba(255, 255, 255, 0.02);
}

.template-name {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.template-name strong {
  color: var(--text-primary);
  font-size: 14px;
}

.template-name small {
  color: var(--text-muted);
  font-size: 12px;
}

.mono {
  font-family: var(--font-mono);
  font-size: 12px;
}

.mapping-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 8px;
  border-radius: var(--radius-full);
  background: var(--bg-subtle);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}

.date-cell {
  color: var(--text-secondary);
  font-size: 12px;
}

.actions-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  text-align: center;
}

.empty-state.compact {
  padding: 28px;
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}

.empty-icon {
  margin-bottom: 12px;
  font-size: 32px;
  opacity: 0.5;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  margin-bottom: 12px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 600;
}

.badge-info {
  background: rgba(56, 189, 248, 0.12);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.25);
}

.badge-invoice {
  background: rgba(99, 102, 241, 0.12);
  color: #818cf8;
  border: 1px solid rgba(99, 102, 241, 0.25);
}

.badge-dataset {
  background: rgba(16, 185, 129, 0.12);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.25);
}
</style>