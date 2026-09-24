
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
const loading = ref(false)
const saving = ref(false)
const deleting = ref<number | null>(null)

const errorMessage = ref('')
const successMessage = ref('')

const isFormOpen = ref(false)
const editingTemplateId = ref<number | null>(null)

// Mode tab: 'cell' (Invoice Mapping) or 'column' (Multi-Record Import)
const activeTab = ref<'cell' | 'column'>('cell')

const form = reactive<TemplateCreate>({
  name: '',
  description: '',
  file_type: 'xlsx',
  worksheet: '',
  header_row: 1,
  data_start_row: 2,
  field_mappings: [],
})

const resetForm = () => {
  form.name = ''
  form.description = ''
  form.file_type = 'xlsx'
  form.worksheet = ''
  form.header_row = 1
  form.data_start_row = 2
  form.field_mappings = []
  editingTemplateId.value = null
  activeTab.value = 'cell'
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

const customTargetActive = reactive<Record<number, boolean>>({})

const isCanonicalOrEmpty = (field: string | null | undefined): boolean => {
  if (!field) return true
  return canonicalFields.value.includes(field)
}

const handleTargetFieldChange = (
  event: Event,
  index: number,
  mapping: TemplateFieldMapping,
) => {
  const value = (event.target as HTMLSelectElement).value
  if (value === '__custom__') {
    customTargetActive[index] = true
    if (isCanonicalOrEmpty(mapping.target_field)) {
      mapping.target_field = ''
    }
  } else {
    customTargetActive[index] = false
    mapping.target_field = value
  }
}

const switchTab = (targetTab: 'cell' | 'column') => {
  if (activeTab.value === targetTab) return

  // Check if switching might alter populated references
  const hasIncompatibleData = form.field_mappings.some((m) => {
    if (targetTab === 'column') {
      return !!m.cell_ref?.trim()
    } else {
      return !!m.column_ref?.trim()
    }
  })

  if (hasIncompatibleData) {
    const fromName =
      activeTab.value === 'cell' ? 'Invoice Mapping' : 'Multi-Record Import'
    const toName =
      targetTab === 'cell' ? 'Invoice Mapping' : 'Multi-Record Import'
    const confirmMessage = `Switching from ${fromName} to ${toName} will convert your field mapping configuration. Are you sure you want to switch?`
    if (!window.confirm(confirmMessage)) {
      return
    }
  }

  activeTab.value = targetTab

  // Update mapping_type for all mappings and attempt smart reference preservation
  form.field_mappings.forEach((mapping) => {
    mapping.mapping_type = targetTab
    if (targetTab === 'column') {
      // If cell_ref is e.g. "B4", extract column "B"
      if (mapping.cell_ref && !mapping.column_ref) {
        const match = mapping.cell_ref.trim().match(/^([A-Za-z]+)/)
        if (match) {
          mapping.column_ref = match[1].toUpperCase()
        }
      }
    } else if (targetTab === 'cell') {
      // If column_ref is e.g. "B", set cell_ref to "B1" if empty
      if (mapping.column_ref && !mapping.cell_ref) {
        mapping.cell_ref = `${mapping.column_ref.trim().toUpperCase()}1`
      }
    }
  })
}

const addMapping = () => {
  form.field_mappings.push({
    field_name: '',
    target_field: '',
    mapping_type: activeTab.value,
    cell_ref: '',
    column_ref: '',
    is_required: false,
    data_type: 'text',
    date_format: '',
  })
}

const removeMapping = (index: number) => {
  delete customTargetActive[index]
  form.field_mappings.splice(index, 1)
}

const loadCanonicalFields = async () => {
  try {
    canonicalFields.value = await api.listCanonicalFields()
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

    // Automatically detect mode based on existing field mappings
    const hasColumnMapping = detail.field_mappings.some(
      (m) => m.mapping_type === 'column',
    )
    activeTab.value = hasColumnMapping ? 'column' : 'cell'

    form.field_mappings = detail.field_mappings.map((mapping) => ({
      id: mapping.id,
      field_name: mapping.field_name,
      target_field: mapping.target_field || '',
      mapping_type: mapping.mapping_type || activeTab.value,
      cell_ref: mapping.cell_ref || '',
      column_ref: mapping.column_ref || '',
      is_required: mapping.is_required,
      data_type: mapping.data_type,
      date_format: mapping.date_format || '',
    }))

    editingTemplateId.value = detail.id
    isFormOpen.value = true
  } catch (error: any) {
    errorMessage.value =
      error.message || 'Failed to load template details.'
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

  if (activeTab.value === 'column') {
    if (!form.header_row || form.header_row < 1) {
      errorMessage.value = 'Header row must be at least 1.'
      return false
    }
    if (!form.data_start_row || form.data_start_row < 1) {
      errorMessage.value = 'Data start row must be at least 1.'
      return false
    }
  }

  if (form.field_mappings.length === 0) {
    errorMessage.value = 'Add at least one field mapping.'
    return false
  }

  for (const mapping of form.field_mappings) {
    if (!mapping.field_name.trim()) {
      errorMessage.value = 'Every mapping must have a field name.'
      return false
    }

    if (activeTab.value === 'cell' && !mapping.cell_ref?.trim()) {
      errorMessage.value = `Cell reference is required for "${mapping.field_name}".`
      return false
    }

    if (activeTab.value === 'column' && !mapping.column_ref?.trim()) {
      errorMessage.value = `Column reference is required for "${mapping.field_name}".`
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
    const payload: TemplateCreate = {
      name: form.name.trim(),
      description: form.description?.trim() || '',
      file_type: form.file_type,
      worksheet: form.worksheet.trim(),
      header_row:
        activeTab.value === 'column'
          ? form.header_row
            ? Number(form.header_row)
            : 1
          : undefined,
      data_start_row:
        activeTab.value === 'column'
          ? form.data_start_row
            ? Number(form.data_start_row)
            : 2
          : undefined,
      field_mappings: form.field_mappings.map((mapping) => ({
        field_name: mapping.field_name.trim(),
        target_field: mapping.target_field?.trim() || undefined,
        mapping_type: activeTab.value,
        cell_ref:
          activeTab.value === 'cell'
            ? mapping.cell_ref?.trim() || undefined
            : undefined,
        column_ref:
          activeTab.value === 'column'
            ? mapping.column_ref?.trim() || undefined
            : undefined,
        is_required: mapping.is_required,
        data_type: mapping.data_type,
        date_format: mapping.date_format?.trim() || undefined,
      })),
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
          Create and manage templates for importing business data.
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
            {{
              editingTemplateId !== null
                ? 'Edit Template'
                : 'Create Template'
            }}
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
        <p>Configure the basic details of this import template.</p>
      </div>

      <div class="form-grid">
        <label class="form-field">
          <span>Template Name</span>

          <input
            v-model="form.name"
            type="text"
            placeholder="Supplier A Invoice"
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

      <!-- Import Mode Selection Tabs -->
      <div class="mode-section">
        <div class="mode-tabs-header">
          <h3>Import Mode</h3>
          <p>Select how data is structured in your source files.</p>
        </div>

        <div class="mode-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            :aria-selected="activeTab === 'cell'"
            class="mode-tab"
            :class="{ active: activeTab === 'cell' }"
            @click="switchTab('cell')"
          >
            <div class="tab-icon">📄</div>
            <div class="tab-label-group">
              <span class="tab-title">Invoice Mapping</span>
              <span class="tab-sub">Single Invoice Cell Extraction</span>
            </div>
          </button>

          <button
            type="button"
            role="tab"
            :aria-selected="activeTab === 'column'"
            class="mode-tab"
            :class="{ active: activeTab === 'column' }"
            @click="switchTab('column')"
          >
            <div class="tab-icon">📊</div>
            <div class="tab-label-group">
              <span class="tab-title">Multi-Record Import</span>
              <span class="tab-sub">Spreadsheet Row Dataset</span>
            </div>
          </button>
        </div>

        <!-- Mode Banner / Header Details -->
        <div class="mode-banner glass-card">
          <div v-if="activeTab === 'cell'" class="mode-info">
            <div class="mode-title-row">
              <h4>Invoice Mapping</h4>

              <span class="info-tooltip-wrapper">
                <button
                  type="button"
                  class="info-icon-btn"
                  aria-label="Invoice Mapping Info"
                  tabindex="-1"
                >
                  ⓘ
                </button>
                <span class="tooltip-content">
                  Use Invoice Mapping when one uploaded file represents one
                  invoice. Each field is extracted from a specific Excel cell,
                  such as Invoice Number → F4 or Total Amount → F20.
                </span>
              </span>
            </div>

            <p class="mode-description">
              Extract fields from specific cells in a single invoice.
            </p>
          </div>

          <div v-else class="mode-info">
            <div class="mode-title-row">
              <h4>Multi-Record Import</h4>

              <span class="info-tooltip-wrapper">
                <button
                  type="button"
                  class="info-icon-btn"
                  aria-label="Multi-Record Import Info"
                  tabindex="-1"
                >
                  ⓘ
                </button>
                <span class="tooltip-content">
                  Use Multi-Record Import for spreadsheet-style datasets
                  where each row represents a separate record. For example, Row
                  2 may contain Invoice 001 and Row 3 may contain Invoice 002.
                </span>
              </span>
            </div>

            <p class="mode-description">
              Import multiple records from a structured spreadsheet where each
              row represents one record.
            </p>

            <!-- Spreadsheet row parameters for Multi-Record Import mode -->
            <div class="form-grid spreadsheet-options">
              <label class="form-field">
                <div class="field-label-row">
                  <span>Header Row</span>

                  <span class="info-tooltip-wrapper">
                    <button
                      type="button"
                      class="info-icon-btn"
                      aria-label="Header Row Info"
                      tabindex="-1"
                    >
                      ⓘ
                    </button>
                    <span class="tooltip-content">
                      The spreadsheet row containing the column headings.
                    </span>
                  </span>
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

                  <span class="info-tooltip-wrapper">
                    <button
                      type="button"
                      class="info-icon-btn"
                      aria-label="Data Start Row Info"
                      tabindex="-1"
                    >
                      ⓘ
                    </button>
                    <span class="tooltip-content">
                      The first spreadsheet row containing an actual record.
                      Rows before this are ignored.
                    </span>
                  </span>
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

      <!-- Field Mappings -->
      <div class="section-heading mapping-heading">
        <div>
          <h3>Field Mappings</h3>

          <p v-if="activeTab === 'cell'">
            Map fields to specific cell coordinates (e.g. B3, F4).
          </p>
          <p v-else>
            Map fields to spreadsheet column letters (e.g. A, B, C).
          </p>
        </div>

        <button type="button" class="btn btn-secondary" @click="addMapping">
          <span>+</span>
          Add Mapping
        </button>
      </div>

      <div
        v-if="form.field_mappings.length === 0"
        class="empty-state compact"
      >
        <p>No field mappings added yet.</p>

        <button type="button" class="btn btn-secondary" @click="addMapping">
          Add Your First Mapping
        </button>
      </div>

      <div
        v-for="(mapping, index) in form.field_mappings"
        :key="index"
        class="mapping-card"
      >
        <div class="mapping-card-header">
          <div class="mapping-title">
            <span class="mapping-number">
              {{ String(index + 1).padStart(2, '0') }}
            </span>

            <strong>Field Mapping {{ index + 1 }}</strong>
          </div>

          <button
            type="button"
            class="btn btn-danger btn-small"
            @click="removeMapping(index)"
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
              placeholder="company_name"
            />
          </label>

          <label class="form-field">
            <span>Target Field</span>

            <select
              :value="
                isCanonicalOrEmpty(mapping.target_field) &&
                !customTargetActive[index]
                  ? mapping.target_field || ''
                  : '__custom__'
              "
              @change="handleTargetFieldChange($event, index, mapping)"
            >
              <option value="">(Auto / Match Field Name)</option>
              <option
                v-for="cf in canonicalFields"
                :key="cf"
                :value="cf"
              >
                {{ cf }}
              </option>
              <option value="__custom__">Custom target field...</option>
            </select>

            <input
              v-if="
                (!isCanonicalOrEmpty(mapping.target_field) &&
                  mapping.target_field !== '') ||
                customTargetActive[index]
              "
              v-model="mapping.target_field"
              type="text"
              placeholder="Enter custom target field name..."
              style="margin-top: 0.5rem;"
            />
          </label>

          <!-- Show Cell Reference ONLY in Invoice Mapping ('cell') mode -->
          <label
            v-if="activeTab === 'cell'"
            class="form-field"
          >
            <div class="field-label-row">
              <span>Cell Reference</span>

              <span class="info-tooltip-wrapper">
                <button
                  type="button"
                  class="info-icon-btn"
                  aria-label="Cell Reference Info"
                  tabindex="-1"
                >
                  ⓘ
                </button>
                <span class="tooltip-content">
                  The exact Excel cell containing this value, such as B3, F4,
                  or F20.
                </span>
              </span>
            </div>

            <input
              v-model="mapping.cell_ref"
              type="text"
              placeholder="B3"
            />
          </label>

          <!-- Show Column Reference ONLY in Multi-Record Import ('column') mode -->
          <label
            v-if="activeTab === 'column'"
            class="form-field"
          >
            <div class="field-label-row">
              <span>Column Reference</span>

              <span class="info-tooltip-wrapper">
                <button
                  type="button"
                  class="info-icon-btn"
                  aria-label="Column Reference Info"
                  tabindex="-1"
                >
                  ⓘ
                </button>
                <span class="tooltip-content">
                  The Excel column containing this field, such as A, B, C, or
                  AA.
                </span>
              </span>
            </div>

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
              <option value="decimal">Decimal</option>
              <option value="date">Date</option>
              <option value="integer">Integer</option>
            </select>
          </label>

          <label
            v-if="mapping.data_type === 'date'"
            class="form-field"
          >
            <span>Date Format</span>

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

      <!-- Form Actions -->
      <div class="form-actions">
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

        <p>
          Create your first import template to get started.
        </p>

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
                <th>Name</th>
                <th>File Type</th>
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
                      {{
                        deleting === template.id
                          ? 'Deleting...'
                          : 'Delete'
                      }}
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

/* Tooltips */
.field-label-row {
  display: flex;
  align-items: center;
}

.info-tooltip-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
}

.info-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 17px;
  height: 17px;
  padding: 0;
  border: 1px solid var(--border-medium, #475569);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-muted, #94a3b8);
  font-size: 11px;
  font-weight: 600;
  cursor: help;
  transition: all 0.2s ease;
}

.info-icon-btn:hover {
  border-color: var(--accent-brand, #6366f1);
  background: var(--accent-brand, #6366f1);
  color: #ffffff;
}

.tooltip-content {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%) translateY(4px);
  width: max-content;
  max-width: 280px;
  padding: 8px 12px;
  border: 1px solid var(--border-medium, #475569);
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-card, #0f172a);
  color: var(--text-primary, #f8fafc);
  font-size: 11px;
  font-weight: 400;
  line-height: 1.45;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
  z-index: 100;
  white-space: normal;
  text-transform: none;
  letter-spacing: normal;
}

.info-tooltip-wrapper:hover .tooltip-content,
.info-tooltip-wrapper:focus-within .tooltip-content {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.tooltip-content::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border-width: 5px;
  border-style: solid;
  border-color: var(--border-medium, #475569) transparent transparent
    transparent;
}

/* Form Controls */
.form-field input:not([type='checkbox']),
.form-field select,
.form-field textarea {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 0.7rem 0.85rem;
  border: 1px solid var(--border-medium, #475569);
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-input, #1e293b) !important;
  color: var(--text-primary, #f8fafc) !important;
  font-family: inherit;
  font-size: 0.875rem;
  line-height: 1.4;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    background 0.2s ease;
}

.form-field input:not([type='checkbox'])::placeholder,
.form-field textarea::placeholder {
  color: var(--text-muted, #94a3b8);
  opacity: 1;
}

.form-field input:not([type='checkbox']):focus,
.form-field select:focus,
.form-field textarea:focus {
  outline: none;
  border-color: var(--accent-brand, #6366f1);
  box-shadow: 0 0 0 3px var(--accent-brand-subtle, rgba(99, 102, 241, 0.2));
}

.form-field select {
  cursor: pointer;
  color-scheme: dark;
}

.form-field select option {
  background: var(--bg-card, #111827);
  color: var(--text-primary, #f8fafc);
}

.form-field textarea {
  min-height: 80px;
  resize: vertical;
}

.checkbox-field input[type='checkbox'] {
  width: 16px;
  height: 16px;
  padding: 0;
  margin: 0;
  cursor: pointer;
  accent-color: var(--accent-brand, #6366f1);
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.form-field span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.form-field-wide {
  grid-column: 1 / -1;
}

.mapping-card {
  margin-bottom: 16px;
  padding: 20px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
}

.mapping-card-header {
  margin-bottom: 20px;
}

.mapping-title {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-primary);
}

.mapping-number {
  color: var(--accent-brand);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
}

.mapping-grid {
  gap: 16px;
}

.checkbox-field {
  display: flex;
  align-items: center;
  align-self: end;
  gap: 8px;
  min-height: 40px;
  color: var(--text-secondary);
  font-size: 12px;
}

.checkbox-field input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-brand);
}

.btn-small {
  padding: 7px 11px;
  font-size: 11px;
}

.form-actions {
  justify-content: flex-end;
  margin-top: 28px;
  padding-top: 24px;
  border-top: 1px solid var(--border-default);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  padding: 32px;
  text-align: center;
}

.empty-state.compact {
  min-height: 140px;
  margin-bottom: 20px;
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
}

.empty-icon {
  margin-bottom: 14px;
  color: var(--accent-brand);
  font-size: 36px;
}

.empty-state h3 {
  font-size: 18px;
}

.empty-state .btn {
  margin-top: 20px;
}

.table-header {
  padding: 24px 24px 20px;
}

.table-header h2 {
  font-size: 17px;
}

.template-table-wrapper {
  overflow-x: auto;
  border-top: 1px solid var(--border-default);
}

.template-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.template-table th,
.template-table td {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  white-space: nowrap;
}

.template-table th {
  background: var(--bg-subtle);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.template-table td {
  color: var(--text-secondary);
  font-size: 12px;
}

.template-table tbody tr {
  transition: background var(--transition-fast);
}

.template-table tbody tr:hover {
  background: var(--bg-card-hover);
}

.template-table tbody tr:last-child td {
  border-bottom: none;
}

.template-name {
  display: flex;
  flex-direction: column;
  gap: 5px;
  max-width: 260px;
}

.template-name strong {
  color: var(--text-primary);
  font-size: 13px;
}

.template-name small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: normal;
}

.mapping-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  border-radius: 6px;
  background: var(--bg-subtle);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
}

.date-cell {
  color: var(--text-muted) !important;
  font-size: 11px !important;
}

.actions-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  margin-bottom: 14px;
  border: 3px solid var(--border-default);
  border-top-color: var(--accent-brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .template-manager {
    padding-top: 20px;
  }

  .page-header,
  .form-header,
  .mapping-heading,
  .table-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .form-grid,
  .mapping-grid,
  .mode-tabs {
    grid-template-columns: 1fr;
  }

  .form-field-wide {
    grid-column: auto;
  }

  .template-form {
    padding: 20px;
  }

  .form-actions {
    align-items: stretch;
    flex-direction: column-reverse;
  }

  .form-actions .btn {
    width: 100%;
  }

  .mapping-heading .btn {
    width: 100%;
  }

  .tooltip-content {
    left: 0;
    transform: translateY(4px);
    max-width: 240px;
  }

  .info-tooltip-wrapper:hover .tooltip-content,
  .info-tooltip-wrapper:focus-within .tooltip-content {
    transform: translateY(0);
  }

  .tooltip-content::after {
    left: 12px;
    transform: none;
  }
}
</style>
e>