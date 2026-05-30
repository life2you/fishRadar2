<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Layers3, ListTodo, Radar, RefreshCw } from 'lucide-vue-next'
import { getTenantAccessDetail, type TenantAccessDetail } from '@/api/settings'
import { getAllTasks } from '@/api/tasks'
import { getResultFiles } from '@/api/results'
import type { Task } from '@/types/task.d.ts'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Badge from '@/components/ui/badge/Badge.vue'
import { toast } from '@/components/ui/toast'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const detail = ref<TenantAccessDetail | null>(null)
const tasks = ref<Task[]>([])
const resultFiles = ref<string[]>([])
const isLoading = ref(false)

const tenantId = computed(() => {
  const raw = route.params.tenantId
  const parsed = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(parsed) ? parsed : null
})

const headlineStats = computed(() => {
  const metrics = detail.value?.metrics
  if (!metrics) {
    return []
  }
  return [
    {
      label: t('tenantDetail.stats.tasks'),
      value: String(metrics.task_count),
      hint: t('tenantDetail.stats.tasksHint', { count: metrics.running_task_count }),
    },
    {
      label: t('tenantDetail.stats.results'),
      value: String(metrics.result_file_count),
      hint: t('tenantDetail.stats.resultsHint', { count: metrics.scanned_item_count }),
    },
    {
      label: t('tenantDetail.stats.recommended'),
      value: String(metrics.recommended_item_count),
      hint: t('tenantDetail.stats.recommendedHint', { count: metrics.ai_recommended_item_count }),
    },
    {
      label: t('tenantDetail.stats.members'),
      value: String(detail.value?.tenant.member_count || 0),
      hint: detail.value?.tenant.access_expires_at
        ? t('tenantDetail.stats.expiresAt', { value: formatDateTime(detail.value.tenant.access_expires_at) })
        : t('tenantDetail.stats.noExpiry'),
    },
  ]
})

const tenantStatusLabel = computed(() => {
  if (!detail.value) return ''
  if (detail.value.tenant.workspace_enabled) {
    return t('tenantDetail.workspaceReady')
  }
  return t('tenantDetail.workspacePending')
})

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return t('common.empty')
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function fetchTenantDetail() {
  if (!tenantId.value) {
    return
  }
  isLoading.value = true
  try {
    const [detailResponse, taskResponse, resultResponse] = await Promise.all([
      getTenantAccessDetail(tenantId.value),
      getAllTasks(tenantId.value),
      getResultFiles(tenantId.value),
    ])
    detail.value = detailResponse
    tasks.value = taskResponse
    resultFiles.value = resultResponse
  } catch (e) {
    toast({
      title: t('tenantDetail.loadFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    isLoading.value = false
  }
}

function openTenantTasks() {
  if (!tenantId.value) return
  router.push({ name: 'Tasks', query: { tenant_id: String(tenantId.value) } })
}

function openTenantResults() {
  if (!tenantId.value) return
  router.push({ name: 'Results', query: { tenant_id: String(tenantId.value) } })
}

onMounted(fetchTenantDetail)
watch(() => route.params.tenantId, fetchTenantDetail)
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <Button variant="outline" class="rounded-full" @click="router.push({ name: 'Tenants' })">
        <ArrowLeft class="mr-2 h-4 w-4" />
        {{ t('tenantDetail.back') }}
      </Button>
      <Button variant="outline" class="rounded-full" :disabled="isLoading" @click="fetchTenantDetail">
        <RefreshCw class="mr-2 h-4 w-4" />
        {{ t('common.refresh') }}
      </Button>
    </div>

    <section class="overflow-hidden rounded-[24px] border border-[#cfddd5] bg-[linear-gradient(135deg,#f6faf6_0%,#edf4ef_46%,#e9f2f4_100%)] px-4.5 py-4.5 text-[#203228] shadow-[0_14px_34px_rgba(76,104,84,0.09)] md:px-5">
      <div class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div class="max-w-[42rem]">
          <p class="text-[11px] font-black uppercase tracking-[0.3em] text-[#72907f]">CatchYu Console</p>
          <h1 class="mt-2 text-[1.65rem] font-black tracking-tight text-[#203228] md:text-[1.95rem]">
            {{ detail?.tenant.name || t('tenantDetail.loadingTitle') }}
          </h1>
          <p class="mt-1.5 text-[13px] leading-6 text-[#597264] md:text-[14px]">
            {{ detail?.tenant.slug || '' }} · {{ t('tenantDetail.description') }}
          </p>
          <div class="mt-2.5 flex flex-wrap items-center gap-1.5">
            <Badge variant="outline" class="border-[#c9ddd0] bg-white/76 text-[#355344]">{{ detail?.tenant.status || 'active' }}</Badge>
            <Badge variant="outline" class="border-[#c9ddd0] bg-white/76 text-[#355344]">{{ tenantStatusLabel }}</Badge>
            <Badge variant="outline" class="border-[#c9ddd0] bg-white/76 text-[#355344]">
              {{ detail?.tenant.can_use_ai ? t('tenantDetail.aiReady') : t('tenantDetail.aiPending') }}
            </Badge>
          </div>
        </div>

        <div class="rounded-[16px] border border-[#d6e2db] bg-white/90 px-3 py-2 shadow-sm backdrop-blur xl:max-w-[17rem]">
          <p class="text-[10px] font-black uppercase tracking-[0.22em] text-[#7b9688]">{{ t('tenantDetail.panelLabel') }}</p>
          <p class="mt-1 text-[13px] leading-5 text-[#557061]">
            {{ detail?.latest_activation_code
              ? t('tenantDetail.latestCode', { code: detail.latest_activation_code.code })
              : t('tenantDetail.noCode') }}
          </p>
        </div>
      </div>

      <div class="mt-3.5 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="item in headlineStats"
          :key="item.label"
          class="rounded-[15px] border border-[#d7e2db] bg-white/92 px-3 py-2.5 shadow-sm backdrop-blur"
        >
          <p class="text-[10px] font-black uppercase tracking-[0.18em] text-[#7d9789]">{{ item.label }}</p>
          <p class="mt-1 text-[15px] font-black tracking-tight text-[#203228]">{{ item.value }}</p>
          <p class="mt-0.5 text-[12px] leading-5 text-[#5f796b]">{{ item.hint }}</p>
        </article>
      </div>
    </section>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
      <Card class="border border-slate-200/80 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
        <CardHeader class="flex flex-row items-center justify-between gap-3">
          <div>
            <CardTitle class="text-lg font-black text-slate-900">{{ t('tenantDetail.tasksTitle') }}</CardTitle>
            <CardDescription>{{ t('tenantDetail.tasksDescription') }}</CardDescription>
          </div>
          <Button variant="outline" class="rounded-full" @click="openTenantTasks">
            <ListTodo class="mr-2 h-4 w-4" />
            {{ t('tenantDetail.openTasks') }}
          </Button>
        </CardHeader>
        <CardContent class="space-y-3">
          <div
            v-for="task in tasks.slice(0, 8)"
            :key="task.id"
            class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4"
          >
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p class="text-base font-black text-slate-900">{{ task.task_name }}</p>
                <p class="mt-1 text-sm text-slate-500">{{ task.keyword }}</p>
              </div>
              <div class="flex flex-wrap gap-2">
                <Badge variant="outline">{{ task.enabled ? t('common.enabled') : t('common.disabled') }}</Badge>
                <Badge variant="outline">{{ task.is_running ? t('common.running') : t('common.idle') }}</Badge>
                <Badge variant="outline">{{ task.decision_mode === 'ai' ? 'AI' : t('common.keyword') }}</Badge>
              </div>
            </div>
          </div>
          <div v-if="!tasks.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 px-4 py-8 text-center text-sm text-slate-500">
            {{ t('tenantDetail.noTasks') }}
          </div>
        </CardContent>
      </Card>

      <div class="space-y-6">
        <Card class="border border-slate-200/80 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
          <CardHeader class="flex flex-row items-center justify-between gap-3">
            <div>
              <CardTitle class="text-lg font-black text-slate-900">{{ t('tenantDetail.resultsTitle') }}</CardTitle>
              <CardDescription>{{ t('tenantDetail.resultsDescription') }}</CardDescription>
            </div>
            <Button variant="outline" class="rounded-full" @click="openTenantResults">
              <Layers3 class="mr-2 h-4 w-4" />
              {{ t('tenantDetail.openResults') }}
            </Button>
          </CardHeader>
          <CardContent class="space-y-3">
            <div
              v-for="file in resultFiles.slice(0, 8)"
              :key="file"
              class="rounded-2xl border border-slate-200 bg-slate-50/80 p-4"
            >
              <p class="text-sm font-black text-slate-900">{{ file.replace('_full_data.jsonl', '') }}</p>
              <p class="mt-1 text-xs text-slate-500">{{ file }}</p>
            </div>
            <div v-if="!resultFiles.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 px-4 py-8 text-center text-sm text-slate-500">
              {{ t('tenantDetail.noResults') }}
            </div>
          </CardContent>
        </Card>

        <Card class="border border-slate-200/80 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
          <CardHeader>
            <CardTitle class="text-lg font-black text-slate-900">{{ t('tenantDetail.accessTitle') }}</CardTitle>
            <CardDescription>{{ t('tenantDetail.accessDescription') }}</CardDescription>
          </CardHeader>
          <CardContent class="space-y-3 text-sm text-slate-600">
            <div class="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <Radar class="mt-0.5 h-4 w-4 text-slate-500" />
              <div>
                <p class="font-semibold text-slate-900">{{ t('tenantDetail.activatedAt') }}</p>
                <p>{{ formatDateTime(detail?.tenant.activated_at) }}</p>
              </div>
            </div>
            <div class="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <Radar class="mt-0.5 h-4 w-4 text-slate-500" />
              <div>
                <p class="font-semibold text-slate-900">{{ t('tenantDetail.expiresAt') }}</p>
                <p>{{ detail?.tenant.access_expires_at ? formatDateTime(detail.tenant.access_expires_at) : t('tenantDetail.noExpiry') }}</p>
              </div>
            </div>
            <div class="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <Radar class="mt-0.5 h-4 w-4 text-slate-500" />
              <div>
                <p class="font-semibold text-slate-900">{{ t('tenantDetail.activationMode') }}</p>
                <p>{{ detail?.tenant.activation_required ? t('tenantDetail.activationRequired') : t('tenantDetail.activationNotRequired') }}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
</template>
