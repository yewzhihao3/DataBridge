<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/api'
import { suggestionDraft } from '@/composables/useSuggestionDraft'
import type { WorkbookAnalysis } from '@/types/api'

const props = defineProps<{ fileId: number; disabled: boolean }>()
const emit = defineEmits<{ (e: 'select', id: number): void; (e: 'manual'): void }>()
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
const bestMatch = computed(() => result.value?.template_matches[0] ?? null)
const selectedMatch = ref<{ template_id: number; name: string; confidence: string } | null>(null)

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
function useMatch() { if (!bestMatch.value) return; selectedMatch.value = bestMatch.value; emit('select', bestMatch.value.template_id) }

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
    <h2 id="suggestions-title">DataBridge recommends</h2>
    <p v-if="loading" role="status">Analyzing workbook structure…</p>
    <p v-if="error" role="status">{{ error }}</p>
    <template v-if="result">
      <div class="sheet-choice">
        <label for="analysis-sheet">Worksheet</label>
        <span v-if="result.profiles.length === 1" class="worksheet-value">{{ result.selected_worksheet }}</span>
        <select v-else id="analysis-sheet" class="custom-select" :value="result.selected_worksheet" :disabled="disabled || loading"
          @change="analyze(($event.target as HTMLSelectElement).value)">
          <option v-for="sheet in result.profiles" :key="sheet.name" :value="sheet.name">{{ sheet.name }}{{ sheet.is_hidden ? ' (hidden)' : '' }}</option>
        </select>
        <span v-if="result.profiles.length > 1">DataBridge recommends this worksheet.</span>
      </div>
      <div v-if="selectedMatch" class="selected-state"><p>✓ Template selected</p><strong>{{ selectedMatch.name }}</strong><span>{{ result.analysis.suggested_template_type === 'invoice' ? 'Invoice' : 'Dataset' }} · {{ mappings.length }} mapped fields</span><button type="button" class="btn btn-secondary" @click="selectedMatch = null; emit('manual')">Change</button></div>
      <div v-else-if="bestMatch" class="recommendation">
        <p class="recommendation-kicker">✓ Use saved template</p>
        <h3>{{ bestMatch.name }}</h3>
        <p>{{ result.analysis.suggested_template_type === 'invoice' ? 'Invoice' : 'Dataset' }} · {{ mappings.length }} mapped fields</p>
        <p class="confidence">{{ bestMatch.confidence }} confidence match</p>
        <button type="button" class="btn btn-primary" :disabled="disabled" @click="useMatch">Use {{ bestMatch.name }}</button>
      </div>
      <p v-else class="muted">No saved template is a strong enough match. You can review the detected mapping or map it manually.</p>
      <div v-if="!selectedMatch" class="other-options"><h3>Other options</h3><button v-if="result.analysis.suggested_template_type" type="button" class="btn btn-secondary" :disabled="disabled || loading" @click="review">Review detected mapping</button><button type="button" class="btn btn-secondary" :disabled="disabled" @click="ignored = true; emit('manual')">Map manually</button></div>
      <details class="analysis-details"><summary>View analysis details</summary><p><strong>{{ result.analysis.suggested_template_type ?? 'Uncertain structure' }}</strong> · {{ result.analysis.confidence }} confidence</p><p v-for="reason in result.analysis.reasons" :key="reason">{{ reason }}</p><div v-if="mappings.length" class="mapping-scroll"><table><thead><tr><th>Field</th><th>Group</th><th>Location</th><th>Confidence / reason</th></tr></thead><tbody><tr v-for="m in mappings" :key="`${m.mapping_group}-${m.field_name}`"><td>{{ m.target_field }}</td><td>{{ m.mapping_group }}</td><td>{{ m.cell_ref || m.column_ref }}</td><td>{{ m.confidence }} — {{ m.reason }}</td></tr></tbody></table></div><p v-if="result.analysis.table">Table header: {{ result.analysis.table.header_row }} · Data rows: {{ result.analysis.table.data_start_row }}–{{ result.analysis.table.data_end_row }}.</p><p v-for="warning in result.warnings" :key="warning">{{ warning }}</p></details>
    </template>
  </section>
</template>

<style scoped>
.suggestions { padding: 1.75rem; display: grid; gap: 1.2rem; width: 100%; }
h2 { font-size: 1.1rem; } h3 { font-size: 1rem; } p, summary { color: var(--text-secondary); font-size: .85rem; }
.sheet-choice { display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; }.worksheet-value { color: var(--text-primary); font-weight: 600; }
.sheet-choice select { width: auto; max-width: 100%; }
.recommendation { display: grid; gap: .45rem; padding: 1.25rem; border: 1px solid var(--accent-border); border-radius: var(--radius-md); background: var(--accent-soft); }.recommendation-kicker { color: var(--success); font-weight: 700; }.recommendation h3 { color: var(--text-primary); font-size: 1.15rem; }.confidence { color: var(--text-primary); font-weight: 600; }.recommendation .btn { justify-self: center; margin-top: .5rem; }.other-options { display: grid; justify-items: start; gap: .65rem; }.analysis-details { display: grid; gap: .75rem; }.analysis-details summary { color: var(--text-primary); }
.selected-state { display: grid; gap: .35rem; padding: 1.1rem 1.25rem; border: 1px solid var(--status-success-border); border-radius: var(--radius-md); background: var(--bg-surface); }.selected-state p { color: var(--status-success); font-weight: 700; }.selected-state strong { color: var(--text-primary); }.selected-state .btn { justify-self: start; margin-top: .35rem; }
.mapping-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .8rem; }
th, td { text-align: left; padding: .65rem; border-bottom: 1px solid var(--border-default); }
th { color: var(--text-secondary); } summary { cursor: pointer; }
</style>
