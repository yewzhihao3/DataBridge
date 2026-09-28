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
      path: '/explorer',
      name: 'data-explorer',
      component: () => import('@/views/DataExplorerView.vue'),
    },
    {
      path: '/exports',
      name: 'export-center',
      component: () => import('@/views/ExportCenterView.vue'),
    },
    {
      path: '/templates',
      name: 'template-manager',
      component: () => import('@/views/TemplateManagerView.vue'),
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

export default router
