import { computed, ref } from 'vue'
import { wsService } from '@/services/websocket'

type AppRole = 'admin' | 'tenant'

interface AuthPayload {
  authenticated: boolean
  username: string
  display_name: string | null
  role: AppRole
  tenant_id: number | null
  tenant_name: string | null
  tenant_status: string | null
  workspace_enabled: boolean
  tenant_ai_enabled: boolean
  tenant_activation_required: boolean
  tenant_activated: boolean
  tenant_activated_at: string | null
  tenant_access_expires_at: string | null
  tenant_access_expired: boolean
  can_use_ai: boolean
  allowed_routes: string[]
}

const STORAGE_KEYS = {
  username: 'auth_username',
  displayName: 'auth_display_name',
  role: 'auth_role',
  tenantName: 'auth_tenant_name',
  workspaceEnabled: 'auth_workspace_enabled',
  tenantAiEnabled: 'auth_tenant_ai_enabled',
  tenantActivationRequired: 'auth_tenant_activation_required',
  tenantActivated: 'auth_tenant_activated',
  tenantAccessExpiresAt: 'auth_tenant_access_expires_at',
  tenantAccessExpired: 'auth_tenant_access_expired',
  canUseAi: 'auth_can_use_ai',
  allowedRoutes: 'auth_allowed_routes',
  loggedIn: 'auth_logged_in',
} as const

const username = ref<string | null>(localStorage.getItem(STORAGE_KEYS.username))
const displayName = ref<string | null>(localStorage.getItem(STORAGE_KEYS.displayName))
const role = ref<AppRole | null>((localStorage.getItem(STORAGE_KEYS.role) as AppRole | null) ?? null)
const tenantName = ref<string | null>(localStorage.getItem(STORAGE_KEYS.tenantName))
const workspaceEnabled = ref(localStorage.getItem(STORAGE_KEYS.workspaceEnabled) === 'true')
const tenantAiEnabled = ref(localStorage.getItem(STORAGE_KEYS.tenantAiEnabled) === 'true')
const tenantActivationRequired = ref(localStorage.getItem(STORAGE_KEYS.tenantActivationRequired) === 'true')
const tenantActivated = ref(localStorage.getItem(STORAGE_KEYS.tenantActivated) === 'true')
const tenantAccessExpiresAt = ref<string | null>(localStorage.getItem(STORAGE_KEYS.tenantAccessExpiresAt) || null)
const tenantAccessExpired = ref(localStorage.getItem(STORAGE_KEYS.tenantAccessExpired) === 'true')
const canUseAi = ref(localStorage.getItem(STORAGE_KEYS.canUseAi) === 'true')
const isLoggedIn = ref(localStorage.getItem(STORAGE_KEYS.loggedIn) === 'true')
const allowedRoutes = ref<string[]>(
  JSON.parse(localStorage.getItem(STORAGE_KEYS.allowedRoutes) || '[]'),
)
const hasCheckedSession = ref(false)

function persistAuthState(payload: AuthPayload) {
  username.value = payload.username
  displayName.value = payload.display_name
  role.value = payload.role
  tenantName.value = payload.tenant_name
  workspaceEnabled.value = payload.workspace_enabled
  tenantAiEnabled.value = payload.tenant_ai_enabled
  tenantActivationRequired.value = payload.tenant_activation_required
  tenantActivated.value = payload.tenant_activated
  tenantAccessExpiresAt.value = payload.tenant_access_expires_at
  tenantAccessExpired.value = payload.tenant_access_expired
  canUseAi.value = payload.can_use_ai
  allowedRoutes.value = payload.allowed_routes || []
  isLoggedIn.value = true

  localStorage.setItem(STORAGE_KEYS.username, payload.username)
  localStorage.setItem(STORAGE_KEYS.displayName, payload.display_name || '')
  localStorage.setItem(STORAGE_KEYS.role, payload.role)
  localStorage.setItem(STORAGE_KEYS.tenantName, payload.tenant_name || '')
  localStorage.setItem(STORAGE_KEYS.workspaceEnabled, String(payload.workspace_enabled))
  localStorage.setItem(STORAGE_KEYS.tenantAiEnabled, String(payload.tenant_ai_enabled))
  localStorage.setItem(STORAGE_KEYS.tenantActivationRequired, String(payload.tenant_activation_required))
  localStorage.setItem(STORAGE_KEYS.tenantActivated, String(payload.tenant_activated))
  localStorage.setItem(STORAGE_KEYS.tenantAccessExpiresAt, payload.tenant_access_expires_at || '')
  localStorage.setItem(STORAGE_KEYS.tenantAccessExpired, String(payload.tenant_access_expired))
  localStorage.setItem(STORAGE_KEYS.canUseAi, String(payload.can_use_ai))
  localStorage.setItem(STORAGE_KEYS.allowedRoutes, JSON.stringify(payload.allowed_routes || []))
  localStorage.setItem(STORAGE_KEYS.loggedIn, 'true')
  if (payload.role === 'admin' || payload.workspace_enabled) {
    wsService.start()
  } else {
    wsService.stop()
  }
}

function clearAuthState() {
  username.value = null
  displayName.value = null
  role.value = null
  tenantName.value = null
  workspaceEnabled.value = false
  tenantAiEnabled.value = false
  tenantActivationRequired.value = false
  tenantActivated.value = false
  tenantAccessExpiresAt.value = null
  tenantAccessExpired.value = false
  canUseAi.value = false
  allowedRoutes.value = []
  isLoggedIn.value = false

  localStorage.removeItem(STORAGE_KEYS.username)
  localStorage.removeItem(STORAGE_KEYS.displayName)
  localStorage.removeItem(STORAGE_KEYS.role)
  localStorage.removeItem(STORAGE_KEYS.tenantName)
  localStorage.removeItem(STORAGE_KEYS.workspaceEnabled)
  localStorage.removeItem(STORAGE_KEYS.tenantAiEnabled)
  localStorage.removeItem(STORAGE_KEYS.tenantActivationRequired)
  localStorage.removeItem(STORAGE_KEYS.tenantActivated)
  localStorage.removeItem(STORAGE_KEYS.tenantAccessExpiresAt)
  localStorage.removeItem(STORAGE_KEYS.tenantAccessExpired)
  localStorage.removeItem(STORAGE_KEYS.canUseAi)
  localStorage.removeItem(STORAGE_KEYS.allowedRoutes)
  localStorage.removeItem(STORAGE_KEYS.loggedIn)
  wsService.stop()
}

export function useAuth() {
  const isAuthenticated = computed(() => isLoggedIn.value)
  const homePath = computed(() => {
    if (role.value === 'tenant') {
      return workspaceEnabled.value ? '/tasks' : '/activate'
    }
    return '/dashboard'
  })

  function canAccessRoute(routeName: string | null | undefined) {
    if (!routeName) {
      return false
    }
    if (role.value === 'admin') {
      return true
    }
    return allowedRoutes.value.includes(routeName.toLowerCase())
  }

  async function ensureSession(force = false): Promise<boolean> {
    if (hasCheckedSession.value && !force) {
      return isLoggedIn.value
    }
    hasCheckedSession.value = true

    try {
      const response = await fetch('/auth/me', {
        method: 'GET',
        credentials: 'same-origin',
      })
      if (!response.ok) {
        clearAuthState()
        return false
      }
      const payload = await response.json() as AuthPayload
      persistAuthState(payload)
      return true
    } catch (error) {
      console.error('Auth session check failed', error)
      clearAuthState()
      return false
    }
  }

  async function login(user: string, pass: string): Promise<boolean> {
    try {
      const response = await fetch('/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ username: user, password: pass }),
      })

      if (!response.ok) {
        return false
      }

      const payload = await response.json() as AuthPayload
      persistAuthState(payload)
      hasCheckedSession.value = true
      return true
    } catch (error) {
      console.error('Login error', error)
      return false
    }
  }

  async function register(payload: {
    username: string
    password: string
    tenant_name: string
    display_name?: string
  }): Promise<void> {
    const response = await fetch('/auth/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Registration failed')
    }
    const authPayload = await response.json() as AuthPayload
    persistAuthState(authPayload)
    hasCheckedSession.value = true
  }

  async function redeemActivationCode(code: string): Promise<void> {
    const response = await fetch('/auth/activate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ code }),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Activation failed')
    }
    const authPayload = await response.json() as AuthPayload
    persistAuthState(authPayload)
  }

  async function logout() {
    try {
      await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
      })
    } catch (error) {
      console.error('Logout error', error)
    } finally {
      clearAuthState()
      window.location.href = '/login'
    }
  }

  return {
    username,
    displayName,
    role,
    tenantName,
    workspaceEnabled,
    tenantAiEnabled,
    tenantActivationRequired,
    tenantActivated,
    tenantAccessExpiresAt,
    tenantAccessExpired,
    canUseAi,
    allowedRoutes,
    isAuthenticated,
    homePath,
    canAccessRoute,
    ensureSession,
    login,
    register,
    redeemActivationCode,
    logout,
  }
}
