import { ref } from 'vue'
import type { TemplateCreate } from '@/types/api'

// In-memory only: keep the upload available while reviewing a template.
export const suggestionDraft = ref<TemplateCreate | null>(null)
export const reviewedTemplateId = ref<number | null>(null)
