import { watch } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { useAuth } from '@/composables/useAuth'
import { i18n, t } from '@/i18n'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { titleKey: 'routes.login' },
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { titleKey: 'routes.dashboard', requiresAuth: true, allowedRoles: ['admin'] },
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('@/views/TasksView.vue'),
        meta: { titleKey: 'routes.tasks', requiresAuth: true },
      },
      {
        path: 'activate',
        name: 'Activate',
        component: () => import('@/views/TenantActivationView.vue'),
        meta: { titleKey: 'routes.activate', requiresAuth: true, allowedRoles: ['tenant'] },
      },
      {
        path: 'accounts',
        name: 'Accounts',
        component: () => import('@/views/AccountsView.vue'),
        meta: { titleKey: 'routes.accounts', requiresAuth: true, allowedRoles: ['admin'] },
      },
      {
        path: 'tenants',
        name: 'Tenants',
        component: () => import('@/views/TenantsView.vue'),
        meta: { titleKey: 'routes.tenants', requiresAuth: true, allowedRoles: ['admin'] },
      },
      {
        path: 'tenants/:tenantId',
        name: 'TenantDetail',
        component: () => import('@/views/TenantDetailView.vue'),
        meta: { titleKey: 'routes.tenantDetail', requiresAuth: true, allowedRoles: ['admin'] },
      },
      {
        path: 'results',
        name: 'Results',
        component: () => import('@/views/ResultsView.vue'),
        meta: { titleKey: 'routes.results', requiresAuth: true },
      },
      {
        path: 'notifications',
        name: 'Notifications',
        component: () => import('@/views/TenantNotificationsView.vue'),
        meta: { titleKey: 'routes.notifications', requiresAuth: true, allowedRoles: ['tenant'] },
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/LogsView.vue'),
        meta: { titleKey: 'routes.logs', requiresAuth: true, allowedRoles: ['admin'] },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/SettingsView.vue'),
        meta: { titleKey: 'routes.settings', requiresAuth: true, allowedRoles: ['admin'] },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

function updateDocumentTitle() {
  const currentRoute = router.currentRoute.value
  const titleKey = typeof currentRoute.meta.titleKey === 'string'
    ? currentRoute.meta.titleKey
    : null
  const appName = t('app.name')
  document.title = titleKey ? `${t(titleKey)} - ${appName}` : appName
}

router.beforeEach(async (to, _from, next) => {
  const { isAuthenticated, ensureSession, canAccessRoute, homePath } = useAuth()

  if (to.meta.requiresAuth || to.name === 'Login') {
    await ensureSession()
  }

  if (to.meta.requiresAuth && !isAuthenticated.value) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }

  if (to.name === 'Login' && isAuthenticated.value) {
    next(homePath.value)
    return
  }

  if (to.meta.requiresAuth && !canAccessRoute(typeof to.name === 'string' ? to.name : null)) {
    next(homePath.value)
    return
  }

  next()
})

router.afterEach(() => {
  updateDocumentTitle()
})

watch(
  () => i18n.global.locale.value,
  () => {
    updateDocumentTitle()
  },
)

export default router
