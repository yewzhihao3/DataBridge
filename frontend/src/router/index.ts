import { restoreSession, session } from "@/services/session"
import { createRouter, createWebHistory } from 'vue-router'
import IngestionStudioView from '@/views/IngestionStudioView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: () => import("@/views/AuthView.vue"), meta: { public: true } },
    { path: "/register", component: () => import("@/views/AuthView.vue"), meta: { public: true } },
    { path: "/invite", component: () => import("@/views/InviteView.vue"), meta: { public: true } },
    { path: "/settings", component: () => import("@/views/SettingsView.vue") },
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

router.beforeEach(async to => {
  await restoreSession()
  if (!to.meta.public && !session.value) return "/login"
})

export default router
