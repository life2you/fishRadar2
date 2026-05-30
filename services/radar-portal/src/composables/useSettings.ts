import { ref, onMounted } from 'vue'
import * as settingsApi from '@/api/settings'
import type {
  AnnouncementItem,
  AnnouncementPayload,
  AiAccountItem,
  AiAccountPayload,
  RotationSettings,
  SystemStatus,
  TenantNotificationChannel,
} from '@/api/settings'

export function useSettings() {
  const tenantNotificationChannels = ref<TenantNotificationChannel[]>([])
  const announcements = ref<AnnouncementItem[]>([])
  const aiAccounts = ref<AiAccountItem[]>([])
  const rotationSettings = ref<RotationSettings>({})
  const systemStatus = ref<SystemStatus | null>(null)
  const isReady = ref(false)
  
  const isLoading = ref(false)
  const isSaving = ref(false)
  const error = ref<Error | null>(null)

  async function fetchAll() {
    isLoading.value = true
    error.value = null
    try {
      const [tenantChannels, aiAccountResponse, rotation, status, announcementResponse] = await Promise.all([
        settingsApi.getTenantNotificationChannels(),
        settingsApi.getAiAccounts(),
        settingsApi.getRotationSettings(),
        settingsApi.getSystemStatus(),
        settingsApi.getAnnouncements(),
      ])
      tenantNotificationChannels.value = tenantChannels.channels
      aiAccounts.value = aiAccountResponse.items
      rotationSettings.value = rotation
      systemStatus.value = status
      announcements.value = announcementResponse.items
    } catch (e) {
      if (e instanceof Error) error.value = e
    } finally {
      isLoading.value = false
      isReady.value = true
    }
  }

  async function refreshStatus() {
    isLoading.value = true
    error.value = null
    try {
      systemStatus.value = await settingsApi.getSystemStatus()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function saveTenantNotificationChannels(channels: TenantNotificationChannel[]) {
    isSaving.value = true
    try {
      const [channelSettings, status] = await Promise.all([
        settingsApi.updateTenantNotificationChannels(channels),
        settingsApi.getSystemStatus()
      ])
      tenantNotificationChannels.value = channelSettings.channels
      systemStatus.value = status
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function refreshAiAccounts() {
    aiAccounts.value = (await settingsApi.getAiAccounts()).items
  }

  async function refreshAnnouncements() {
    announcements.value = (await settingsApi.getAnnouncements()).items
  }

  async function createAiAccount(payload: AiAccountPayload) {
    isSaving.value = true
    try {
      await settingsApi.createAiAccount(payload)
      await refreshAiAccounts()
      systemStatus.value = await settingsApi.getSystemStatus()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function updateAiAccount(accountId: number, payload: Partial<AiAccountPayload>) {
    isSaving.value = true
    try {
      await settingsApi.updateAiAccount(accountId, payload)
      await refreshAiAccounts()
      systemStatus.value = await settingsApi.getSystemStatus()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function deleteAiAccount(accountId: number) {
    isSaving.value = true
    try {
      await settingsApi.deleteAiAccount(accountId)
      await refreshAiAccounts()
      systemStatus.value = await settingsApi.getSystemStatus()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function testAiAccount(payload: {
    api_key?: string | null
    base_url: string
    model_name: string
  }) {
    isSaving.value = true
    try {
      return await settingsApi.testAiAccount(payload)
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function testExistingAiAccount(accountId: number) {
    isSaving.value = true
    try {
      const result = await settingsApi.testExistingAiAccount(accountId)
      await refreshAiAccounts()
      systemStatus.value = await settingsApi.getSystemStatus()
      return result
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function saveRotationSettings() {
    isSaving.value = true
    try {
      await settingsApi.updateRotationSettings(rotationSettings.value)
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function createAnnouncement(payload: AnnouncementPayload) {
    isSaving.value = true
    try {
      await settingsApi.createAnnouncement(payload)
      await refreshAnnouncements()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function updateAnnouncement(id: number, payload: Partial<AnnouncementPayload>) {
    isSaving.value = true
    try {
      await settingsApi.updateAnnouncement(id, payload)
      await refreshAnnouncements()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function deleteAnnouncement(id: number) {
    isSaving.value = true
    try {
      await settingsApi.deleteAnnouncement(id)
      await refreshAnnouncements()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  onMounted(fetchAll)

  return {
    tenantNotificationChannels,
    announcements,
    aiAccounts,
    rotationSettings,
    systemStatus,
    isLoading,
    isSaving,
    isReady,
    error,
    fetchAll,
    saveTenantNotificationChannels,
    createAiAccount,
    createAnnouncement,
    updateAiAccount,
    updateAnnouncement,
    deleteAiAccount,
    deleteAnnouncement,
    testAiAccount,
    testExistingAiAccount,
    saveRotationSettings,
    refreshStatus,
  }
}
