import { createRouter, createWebHistory } from 'vue-router'
import IngestionStudioView from '@/views/IngestionStudioView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'ingestion-studio',
      component: IngestionStudioView,
    },
    {
      path: '/history',
      name: 'import-history',
      component: () => import('@/views/ImportHistoryView.vue'),
    },
    {
      path: '/templates',
      name: 'template-manager',
      component: () => import('@/views/TemplateManagerView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

export default router
