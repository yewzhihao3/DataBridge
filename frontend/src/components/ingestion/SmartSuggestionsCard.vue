<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/api'
import { suggestionDraft } from '@/composables/useSuggestionDraft'
import type { WorkbookAnalysis } from '@/types/api'

const props = defineProps<{ fileId: number; disabled: boolean }>()
const emit = defineEmits<{ (e: 'select', id: number): void }>()
const router = useRouter()
const result = ref<WorkbookAnalysis | null>(null)
const loading = ref(false)
const error = ref('')
const ignored = ref(false)
let generation = 0
const mappings = computed(() => result.value ? [
  ...result.value.analysis.mappings,
  ...(result.value.analysis.suggested_template_type === 'invoice' ? result.value.analysis.table?.columns ?? [] : []),
] : [])

async function analyze(sheet?: string) {
  const current = ++generation
  loading.value = true
  result.value = null
  error.value = ''
  try {
    const data = await api.analyzeWorkbook(props.fileId, sheet)
    if (current === generation) result.value = data
  } catch (e: any) {
    if (current === generation) error.value = e.message || 'Analysis unavailable. Continue with manual mapping.'
  } finally {
    if (current === generation) loading.value = false
  }
}
watch(() => props.fileId, () => { ignored.value = false; analyze() }, { immediate: true })

function review() {
  const analysis = result.value?.analysis
  if (!analysis?.suggested_template_type) return
  suggestionDraft.value = {
    name: '', file_type: 'xlsx', worksheet: analysis.worksheet,
    template_type: analysis.suggested_template_type,
    header_row: analysis.table?.header_row, data_start_row: analysis.table?.data_start_row,
    field_mappings: mappings.value.map(({ confidence, reason, ...mapping }) => ({ ...mapping })),
  }
  router.push('/templates?review=suggestions')
}
</script>

<template>
  <section class="glass-card suggestions" aria-labelledby="suggestions-title" v-if="!ignored">
    <h2 id="suggestions-title">Workbook suggestions</h2>
    <p>Review suggestions before creating a template. Preview and import remain separate steps.</p>
    <p v-if="loading" role="status">Analyzing workbook structure…</p>
    <p v-if="error" role="status">{{ error }}</p>
    <template v-if="result">
      <div class="sheet-choice">
        <label for="analysis-sheet">Analyze worksheet</label>
        <select id="analysis-sheet" class="custom-select" :value="result.selected_worksheet" :disabled="disabled || loading"
          @change="analyze(($event.target as HTMLSelectElement).value)">
          <option v-for="sheet in result.profiles" :key="sheet.name" :value="sheet.name">{{ sheet.name }}{{ sheet.is_hidden ? ' (hidden)' : '' }}</option>
        </select>
        <span>Suggested worksheet: {{ result.suggested_worksheet }}</span>
      </div>
      <p><strong>{{ result.analysis.suggested_template_type ?? 'Uncertain structure' }}</strong> · {{ result.analysis.confidence }} confidence</p>
      <p v-for="reason in result.analysis.reasons" :key="reason">{{ reason }}</p>
      <div v-if="mappings.length" class="mapping-scroll">
        <table><thead><tr><th>Field</th><th>Group</th><th>Location</th><th>Confidence / reason</th></tr></thead>
          <tbody><tr v-for="m in mappings" :key="`${m.mapping_group}-${m.field_name}`">
            <td>{{ m.target_field }}</td><td>{{ m.mapping_group }}</td><td>{{ m.cell_ref || m.column_ref }}</td><td>{{ m.confidence }} — {{ m.reason }}</td>
          </tr></tbody></table>
      </div>
      <p v-if="result.analysis.table">Table header: {{ result.analysis.table.header_row }} · Data rows: {{ result.analysis.table.data_start_row }}–{{ result.analysis.table.data_end_row }}. The existing extractor checks row boundaries during preview.</p>
      <p v-if="!result.template_matches.length">No strong template match.</p>
      <div v-for="match in result.template_matches" :key="match.template_id" class="template-match">
        <span>This looks like your saved <strong>{{ match.name }}</strong> template · {{ match.confidence }} confidence.</span>
        <button type="button" class="btn btn-secondary" :disabled="disabled" @click="emit('select', match.template_id)">Select {{ match.name }} for preview</button>
      </div>
      <details><summary>Analysis notes</summary><p v-for="warning in result.warnings" :key="warning">{{ warning }}</p></details>
    </template>
    <div class="actions">
      <button v-if="result?.analysis.suggested_template_type" type="button" class="btn btn-primary" :disabled="disabled || loading" @click="review">Use Suggestions &amp; Review Mapping</button>
      <button type="button" class="btn btn-secondary" :disabled="disabled" @click="ignored = true">Ignore and Map Manually</button>
      <router-link to="/templates" class="btn btn-secondary">Create a manual template</router-link>
    </div>
  </section>
</template>

<style scoped>
.suggestions { padding: 1.5rem; display: grid; gap: 1rem; }
h2 { font-size: 1.1rem; } p, summary { color: var(--text-secondary); font-size: .85rem; }
.sheet-choice, .actions, .template-match { display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; }
.sheet-choice select { width: auto; max-width: 100%; }
.mapping-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .8rem; }
th, td { text-align: left; padding: .65rem; border-bottom: 1px solid var(--border-default); }
th { color: var(--text-secondary); } summary { cursor: pointer; }
</style>
