import { http } from '@/lib/http'

export interface NotificationSettings {
  NTFY_TOPIC_URL?: string
  GOTIFY_URL?: string
  GOTIFY_TOKEN?: string
  BARK_URL?: string
  WX_BOT_URL?: string
  TELEGRAM_BOT_TOKEN?: string
  TELEGRAM_CHAT_ID?: string
  TELEGRAM_API_BASE_URL?: string
  WEBHOOK_URL?: string
  WEBHOOK_METHOD?: string
  WEBHOOK_HEADERS?: string
  WEBHOOK_CONTENT_TYPE?: string
  WEBHOOK_QUERY_PARAMETERS?: string
  WEBHOOK_BODY?: string
  PCURL_TO_MOBILE?: boolean
  BARK_URL_SET?: boolean
  GOTIFY_TOKEN_SET?: boolean
  WX_BOT_URL_SET?: boolean
  TELEGRAM_BOT_TOKEN_SET?: boolean
  WEBHOOK_URL_SET?: boolean
  WEBHOOK_HEADERS_SET?: boolean
  CONFIGURED_CHANNELS?: string[]
  AVAILABLE_CHANNELS?: string[]
}

export interface NotificationSettingsUpdate {
  NTFY_TOPIC_URL?: string | null
  GOTIFY_URL?: string | null
  GOTIFY_TOKEN?: string | null
  BARK_URL?: string | null
  WX_BOT_URL?: string | null
  TELEGRAM_BOT_TOKEN?: string | null
  TELEGRAM_CHAT_ID?: string | null
  TELEGRAM_API_BASE_URL?: string | null
  WEBHOOK_URL?: string | null
  WEBHOOK_METHOD?: string | null
  WEBHOOK_HEADERS?: string | null
  WEBHOOK_CONTENT_TYPE?: string | null
  WEBHOOK_QUERY_PARAMETERS?: string | null
  WEBHOOK_BODY?: string | null
  PCURL_TO_MOBILE?: boolean
}

export interface NotificationTestResponse {
  message: string
  results: Record<string, {
    label: string
    success: boolean
    message: string
  }>
}

export type TenantNotificationChannel =
  | 'ntfy'
  | 'bark'
  | 'gotify'
  | 'wecom'
  | 'telegram'
  | 'webhook'

export interface AiAccountItem {
  id: number
  name: string
  api_key?: string
  api_key_set: boolean
  base_url: string
  model_name: string
  supports_image: boolean
  supports_text: boolean
  enabled: boolean
  priority: number
  notes?: string | null
  created_at?: string | null
  updated_at?: string | null
  last_test_status?: 'success' | 'failed' | null
  last_test_message?: string | null
  last_tested_at?: string | null
}

export interface AiAccountPayload {
  name: string
  api_key?: string | null
  base_url: string
  model_name: string
  supports_image: boolean
  supports_text: boolean
  enabled: boolean
  priority: number
  notes?: string | null
}

export interface RotationSettings {
  ACCOUNT_ROTATION_ENABLED?: boolean
  ACCOUNT_ROTATION_MODE?: string
  ACCOUNT_ROTATION_RETRY_LIMIT?: number
  ACCOUNT_BLACKLIST_TTL?: number
  PROXY_ROTATION_ENABLED?: boolean
  PROXY_ROTATION_MODE?: string
  PROXY_POOL?: string
  PROXY_ROTATION_RETRY_LIMIT?: number
  PROXY_BLACKLIST_TTL?: number
}

export interface TenantAccessItem {
  id: number
  name: string
  slug: string
  status: string
  ai_enabled: boolean
  activation_required: boolean
  activated_at: string | null
  access_expires_at: string | null
  access_expired: boolean
  workspace_enabled: boolean
  can_use_ai: boolean
  created_at: string
  member_count: number
}

export interface TenantAccessDetail {
  tenant: TenantAccessItem
  metrics: {
    task_count: number
    enabled_task_count: number
    running_task_count: number
    result_file_count: number
    scanned_item_count: number
    ai_recommended_item_count: number
    keyword_recommended_item_count: number
    recommended_item_count: number
    latest_crawl_time: string | null
  }
  latest_activation_code: {
    code: string
    status: string
    duration_minutes: number
    note: string | null
    created_at: string
    redeemed_at: string | null
  } | null
}

export interface ActivationCodeItem {
  id?: number
  code: string
  status: string
  duration_minutes: number
  note: string | null
  created_by_user_id: number | null
  redeemed_by_tenant_id: number | null
  redeemed_by_user_id: number | null
  redeemed_at: string | null
  created_at: string
  redeemed_tenant_name?: string | null
}

export interface SystemStatus {
  scraper_running: boolean
  running_task_ids?: number[]
  ai_configured?: boolean
  notification_configured?: boolean
  headless_mode?: boolean
  running_in_docker?: boolean
  login_state_file: {
    exists: boolean
    path: string
  }
  env_file: {
    exists: boolean
    ntfy_topic_url_set: boolean
    gotify_url_set: boolean
    gotify_token_set: boolean
    bark_url_set: boolean
    wx_bot_url_set: boolean
    telegram_bot_token_set: boolean
    telegram_chat_id_set: boolean
    webhook_url_set: boolean
    webhook_headers_set: boolean
  }
  configured_notification_channels?: string[]
}

export type AnnouncementLevel = 'info' | 'success' | 'warning'
export type AnnouncementStatus = 'draft' | 'active' | 'archived'

export interface AnnouncementItem {
  id: number
  title: string
  content: string
  level: AnnouncementLevel
  status: AnnouncementStatus
  dismissible: boolean
  published_at: string | null
  expires_at: string | null
  created_at: string
  updated_at: string
  created_by_user_id: number | null
}

export interface AnnouncementPayload {
  title: string
  content: string
  level: AnnouncementLevel
  status: AnnouncementStatus
  dismissible: boolean
  notify_tenants?: boolean
  published_at?: string | null
  expires_at?: string | null
}

export async function getNotificationSettings(): Promise<NotificationSettings> {
  return await http('/api/settings/notifications')
}

export async function updateNotificationSettings(settings: NotificationSettingsUpdate): Promise<{ message: string; configured_channels: string[] }> {
  return await http('/api/settings/notifications', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  })
}

export async function testNotificationSettings(
  payload: { channel?: string; settings: NotificationSettingsUpdate }
): Promise<NotificationTestResponse> {
  return await http('/api/settings/notifications/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

export async function getTenantNotificationSettings(): Promise<NotificationSettings> {
  return await http('/api/tenant-settings/notifications')
}

export async function updateTenantNotificationSettings(
  settings: NotificationSettingsUpdate,
): Promise<{ message: string; configured_channels: string[] }> {
  return await http('/api/tenant-settings/notifications', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
}

export async function testTenantNotificationSettings(
  payload: { channel?: string; settings: NotificationSettingsUpdate },
): Promise<NotificationTestResponse> {
  return await http('/api/tenant-settings/notifications/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getTenantNotificationChannels(): Promise<{ channels: TenantNotificationChannel[] }> {
  return await http('/api/settings/tenant-notification-channels')
}

export async function updateTenantNotificationChannels(
  channels: TenantNotificationChannel[],
): Promise<{ message: string; channels: TenantNotificationChannel[] }> {
  return await http('/api/settings/tenant-notification-channels', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channels }),
  })
}

export async function getRotationSettings(): Promise<RotationSettings> {
  return await http('/api/settings/rotation')
}

export async function getAnnouncements(): Promise<{ items: AnnouncementItem[] }> {
  return await http('/api/announcements')
}

export async function getActiveAnnouncements(): Promise<{ items: AnnouncementItem[] }> {
  return await http('/api/announcements/active')
}

export async function createAnnouncement(payload: AnnouncementPayload): Promise<{ message: string; item: AnnouncementItem }> {
  return await http('/api/announcements', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateAnnouncement(
  announcementId: number,
  payload: Partial<AnnouncementPayload>,
): Promise<{ message: string; item: AnnouncementItem }> {
  return await http(`/api/announcements/${announcementId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteAnnouncement(announcementId: number): Promise<{ message: string }> {
  return await http(`/api/announcements/${announcementId}`, {
    method: 'DELETE',
  })
}

export async function updateRotationSettings(settings: RotationSettings): Promise<void> {
  await http('/api/settings/rotation', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  })
}

export async function getAiAccounts(): Promise<{ items: AiAccountItem[] }> {
  return await http('/api/settings/ai-accounts')
}

export async function createAiAccount(payload: AiAccountPayload): Promise<{ message: string; item: AiAccountItem }> {
  return await http('/api/settings/ai-accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateAiAccount(
  accountId: number,
  payload: Partial<AiAccountPayload>,
): Promise<{ message: string; item: AiAccountItem }> {
  return await http(`/api/settings/ai-accounts/${accountId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteAiAccount(accountId: number): Promise<{ message: string }> {
  return await http(`/api/settings/ai-accounts/${accountId}`, {
    method: 'DELETE',
  })
}

export async function testAiAccount(payload: {
  api_key?: string | null
  base_url: string
  model_name: string
}): Promise<{ success: boolean; message: string; response?: string }> {
  return await http('/api/settings/ai-accounts/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function testExistingAiAccount(accountId: number): Promise<{ success: boolean; message: string; response?: string; item?: AiAccountItem | null }> {
  return await http(`/api/settings/ai-accounts/${accountId}/test`, {
    method: 'POST',
  })
}

export async function getSystemStatus(): Promise<SystemStatus> {
  return await http('/api/settings/status')
}

export async function getTenantAccessSettings(): Promise<{ items: TenantAccessItem[] }> {
  return await http('/api/settings/tenants')
}

export async function updateTenantAccessSettings(
  tenantId: number,
  payload: {
    status?: string
    ai_enabled?: boolean
    activation_required?: boolean
    extend_access_minutes?: number
  },
): Promise<{ message: string; item: TenantAccessItem }> {
  return await http(`/api/settings/tenants/${tenantId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getTenantAccessDetail(tenantId: number): Promise<TenantAccessDetail> {
  return await http(`/api/settings/tenants/${tenantId}`)
}

export async function getActivationCodes(): Promise<{ items: ActivationCodeItem[] }> {
  return await http('/api/settings/activation-codes')
}

export async function createActivationCodes(payload: {
  quantity: number
  duration_minutes: number
  note?: string | null
}): Promise<{ message: string; items: ActivationCodeItem[] }> {
  return await http('/api/settings/activation-codes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateLoginState(content: string): Promise<{ message: string }> {
  return await http('/api/login-state', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  })
}

export async function deleteLoginState(): Promise<{ message: string }> {
  return await http('/api/login-state', { method: 'DELETE' })
}
