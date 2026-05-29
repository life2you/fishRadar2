<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  NotificationSettings,
  NotificationSettingsUpdate,
  NotificationTestResponse,
} from '@/api/settings'
import {
  getTenantNotificationSettings,
  testTenantNotificationSettings,
  updateTenantNotificationSettings,
} from '@/api/settings'
import NotificationSettingsPanel from '@/components/settings/NotificationSettingsPanel.vue'
import { toast } from '@/components/ui/toast'
import { BellRing } from 'lucide-vue-next'
import { useAuth } from '@/composables/useAuth'

const { t } = useI18n()
const { tenantName } = useAuth()
type TenantChannelKey = 'ntfy' | 'bark' | 'gotify' | 'wecom' | 'telegram' | 'webhook'

const settings = ref<NotificationSettings>({})
const isReady = ref(false)
const isSaving = ref(false)
const visibleChannels = ref<TenantChannelKey[]>([])

function notifySuccess(title: string, description?: string) {
  toast({ title, description })
}

function notifyError(title: string, description?: string) {
  toast({ title, description, variant: 'destructive' })
}

async function loadSettings() {
  settings.value = await getTenantNotificationSettings()
  visibleChannels.value = ((settings.value.AVAILABLE_CHANNELS ?? []) as TenantChannelKey[])
  isReady.value = true
}

async function saveSettings(payload: NotificationSettingsUpdate) {
  isSaving.value = true
  try {
    await updateTenantNotificationSettings(payload)
    await loadSettings()
    notifySuccess(t('tenantNotifications.saved'))
  } catch (error) {
    notifyError(t('tenantNotifications.saveFailed'), (error as Error).message)
    throw error
  } finally {
    isSaving.value = false
  }
}

async function testSettings(payload: {
  channel?: string
  settings: NotificationSettingsUpdate
}): Promise<NotificationTestResponse> {
  try {
    return await testTenantNotificationSettings(payload)
  } catch (error) {
    notifyError(t('tenantNotifications.testFailed'), (error as Error).message)
    throw error
  }
}

onMounted(async () => {
  try {
    await loadSettings()
  } catch (error) {
    notifyError(t('tenantNotifications.loadFailed'), (error as Error).message)
  }
})
</script>

<template>
  <div class="space-y-4">
    <section class="rounded-[24px] border border-[#cfddd5] bg-[linear-gradient(135deg,#f6faf6_0%,#edf4ef_46%,#e9f2f4_100%)] px-4 py-4 shadow-[0_14px_34px_rgba(76,104,84,0.08)] md:px-5">
      <div class="max-w-[38rem]">
          <div class="inline-flex items-center gap-2 rounded-full border border-[#d6e2db] bg-white/90 px-3 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-[#72907f]">
            <BellRing class="h-3.5 w-3.5" />
            CatchYu Notify
          </div>
          <h1 class="mt-2 text-[1.6rem] font-black tracking-tight text-[#203228] md:text-[1.9rem]">
            {{ t('tenantNotifications.title', { tenant: tenantName || t('common.unnamed') }) }}
          </h1>
          <p class="mt-1.5 text-[13px] leading-6 text-[#597264] md:text-[14px]">
            {{ t('tenantNotifications.description') }}
          </p>
      </div>
    </section>

    <NotificationSettingsPanel
      :settings="settings"
      :is-ready="isReady"
      :is-saving="isSaving"
      :visible-channels="visibleChannels"
      :save-settings="saveSettings"
      :test-settings="testSettings"
    />
  </div>
</template>
