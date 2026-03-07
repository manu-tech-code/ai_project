/**
 * Vue Router configuration.
 *
 * Route structure:
 *   /                          HomeView       — Dashboard, recent jobs
 *   /analyze                   AnalyzeView    — Upload form
 *   /settings                  SettingsView   — VCS providers and integrations
 *   /jobs/:jobId/progress      JobProgressView — Live/completed job logs (guard-free)
 *   /jobs/:jobId/graph         GraphView      — UCG visualization
 *   /jobs/:jobId/smells        SmellsView     — Smell list
 *   /jobs/:jobId/plan          PlanView       — Refactor plan
 *   /jobs/:jobId/patches       PatchesView    — Patch list + diff viewer
 *   /jobs/:jobId/validate      ValidateView   — Validation results
 *   /jobs/:jobId/report        ReportView     — Modernization report
 *   /:pathMatch(.*)*           NotFoundView   — 404
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAnalysisStore } from '@/stores/analysis'

// Eager-loaded layout
import AppLayout from '@/components/layout/AppLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/views/HomeView.vue'),
        meta: { keepAlive: true },
      },
      {
        path: 'analyze',
        name: 'analyze',
        component: () => import('@/views/AnalyzeView.vue'),
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/SettingsView.vue'),
      },
      {
        path: 'jobs/:jobId',
        children: [
          {
            path: '',
            name: 'job-detail',
            redirect: (to) => ({ name: 'graph', params: to.params }),
          },
          {
            path: 'progress',
            name: 'job-progress',
            component: () => import('@/views/JobProgressView.vue'),
          },
          {
            path: 'graph',
            name: 'graph',
            component: () => import('@/views/GraphView.vue'),
            meta: { keepAlive: true },
          },
          {
            path: 'smells',
            name: 'smells',
            component: () => import('@/views/SmellsView.vue'),
            meta: { keepAlive: true },
          },
          {
            path: 'plan',
            name: 'plan',
            component: () => import('@/views/PlanView.vue'),
            meta: { keepAlive: true },
          },
          {
            path: 'patches',
            name: 'patches',
            component: () => import('@/views/PatchesView.vue'),
            meta: { keepAlive: true },
          },
          {
            path: 'validate',
            name: 'validate',
            component: () => import('@/views/ValidateView.vue'),
            meta: { keepAlive: true },
          },
          {
            path: 'report',
            name: 'report',
            component: () => import('@/views/ReportView.vue'),
            meta: { keepAlive: true },
          },
        ],
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

// Redirect to home if navigating to a job route whose ID is not the active job.
// Exception: /jobs/:jobId/progress is always allowed (used for completed job log review).
router.beforeEach((to) => {
  if (to.name === 'job-progress') return
  const jobId = to.params.jobId as string | undefined
  if (jobId) {
    const store = useAnalysisStore()
    if (!store.activeJobId || store.activeJobId !== jobId) {
      return { name: 'home' }
    }
  }
})

// Scroll to top after every navigation (belt-and-suspenders alongside scrollBehavior).
router.afterEach(() => {
  window.scrollTo({ top: 0 })
})

export default router
