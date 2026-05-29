<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BellRing } from 'lucide-vue-next'
import type { TenantNotificationChannel } from '@/api/settings'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'

const props = defineProps<{
  channels: TenantNotificationChannel[]
  isReady: boolean
  isSaving: boolean
}>()

const emit = defineEmits<{
  save: [channels: TenantNotificationChannel[]]
}>()

const { t } = useI18n()

const channelItems = computed(() => [
  { key: 'ntfy', title: 'Ntfy', description: t('settings.tenantNotifications.channels.ntfy') },
  { key: 'wecom', title: t('notifyPanel.wecom.title'), description: t('settings.tenantNotifications.channels.wecom') },
  { key: 'telegram', title: 'Telegram', description: t('settings.tenantNotifications.channels.telegram') },
  { key: 'gotify', title: 'Gotify', description: t('settings.tenantNotifications.channels.gotify') },
  { key: 'bark', title: 'Bark', description: t('settings.tenantNotifications.channels.bark') },
  { key: 'webhook', title: t('notifyPanel.webhook.title'), description: t('settings.tenantNotifications.channels.webhook') },
] satisfies Array<{ key: TenantNotificationChannel; title: string; description: string }>)

const selected = computed(() => new Set(props.channels))
const enabledCount = computed(() => props.channels.length)

function toggleChannel(channel: TenantNotificationChannel, enabled: boolean) {
  const next = new Set(props.channels)
  if (enabled) {
    next.add(channel)
  } else {
    next.delete(channel)
  }
  emit('save', Array.from(next))
}
</script>

<template>
  <Card class="app-surface overflow-hidden border-none">
    <CardHeader class="pb-4">
      <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <div class="flex items-center gap-2 text-slate-800">
            <BellRing class="h-5 w-5 text-sky-600" />
            <CardTitle>{{ t('settings.tenantNotifications.title') }}</CardTitle>
          </div>
          <CardDescription class="mt-2 max-w-2xl">{{ t('settings.tenantNotifications.description') }}</CardDescription>
        </div>
        <div class="flex items-center gap-2">
          <Badge variant="outline" class="border-slate-200 bg-slate-50 px-3 py-1.5 text-slate-700">
            {{ t('settings.tenantNotifications.summary', { count: enabledCount }) }}
          </Badge>
        </div>
      </div>
    </CardHeader>

    <CardContent v-if="isReady" class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <article
        v-for="item in channelItems"
        :key="item.key"
        class="rounded-[22px] border p-4 shadow-sm transition-colors"
        :class="selected.has(item.key)
          ? 'border-sky-200 bg-sky-50/60'
          : 'border-slate-200 bg-white'"
      >
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <p class="text-base font-black text-slate-900">{{ item.title }}</p>
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-bold"
                :class="selected.has(item.key)
                  ? 'bg-sky-100 text-sky-700'
                  : 'bg-slate-100 text-slate-500'"
              >
                {{ selected.has(item.key) ? t('common.enabled') : t('common.disabled') }}
              </span>
            </div>
            <p class="mt-2 text-sm leading-6 text-slate-500">{{ item.description }}</p>
          </div>
          <Switch
            :model-value="selected.has(item.key)"
            :disabled="isSaving"
            @update:model-value="(value) => toggleChannel(item.key, !!value)"
          />
        </div>
      </article>
    </CardContent>

    <CardContent v-else class="py-8 text-sm text-slate-500">
      {{ t('notifyPanel.loading') }}
    </CardContent>
  </Card>
</template>
