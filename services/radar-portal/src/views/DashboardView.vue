<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDashboard } from '@/composables/useDashboard'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import Badge from '@/components/ui/badge/Badge.vue'
import { formatNumber, formatRelativeTimeFromNow } from '@/i18n'
import {
  Activity,
  Building2,
  LayoutDashboard,
  Search,
  Settings2,
  Target,
  Users,
} from 'lucide-vue-next'

const router = useRouter()
const { t } = useI18n()
const {
  focusTask,
  stats,
  activities,
  isLoading,
  error,
} = useDashboard()

const statCards = computed(() => [
  {
    label: t('dashboard.stats.activeTasks'),
    value: String(stats.value.enabledTasks),
    detail: t('dashboard.stats.runningCount', { count: stats.value.runningTasks }),
    icon: Activity,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10',
  },
  {
    label: t('dashboard.stats.scannedItems'),
    value: formatNumber(stats.value.scannedItems),
    detail: t('dashboard.stats.resultFiles', { count: stats.value.resultFiles }),
    icon: Search,
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10',
  },
  {
    label: t('dashboard.stats.recommendedItems'),
    value: String(stats.value.recommendedItems),
    detail: t('dashboard.stats.recommendedBreakdown', {
      ai: stats.value.aiRecommendedItems,
      keyword: stats.value.keywordRecommendedItems,
    }),
    icon: Target,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10',
  },
])

const focusTitle = computed(() => focusTask.value?.task_name || t('dashboard.focus.defaultTitle'))
const focusMeta = computed(() => {
  if (!focusTask.value) return t('dashboard.focus.empty')
  const keyword = focusTask.value.keyword || t('dashboard.focus.missingKeyword')
  const count = focusTask.value.total_items
  return t('dashboard.focus.meta', { keyword, count })
})

const quickActions = computed(() => [
  {
    title: t('dashboard.actions.tenantsTitle'),
    description: t('dashboard.actions.tenantsDescription'),
    icon: Building2,
    routeName: 'Tenants',
  },
  {
    title: t('dashboard.actions.accountsTitle'),
    description: t('dashboard.actions.accountsDescription'),
    icon: Users,
    routeName: 'Accounts',
  },
  {
    title: t('dashboard.actions.settingsTitle'),
    description: t('dashboard.actions.settingsDescription'),
    icon: Settings2,
    routeName: 'Settings',
  },
])

function openRoute(routeName: string) {
  router.push({ name: routeName })
}

function openActivity(activity: { filename: string | null; type: string }) {
  if (activity.filename) {
    router.push({ name: 'Results', query: { file: activity.filename } })
    return
  }
  if (activity.type === 'task') {
    router.push({ name: 'Logs' })
    return
  }
  router.push({ name: 'Dashboard' })
}
</script>

<template>
  <div class="space-y-8 animate-fade-in">
    <section class="overflow-hidden rounded-[24px] border border-[#cfddd5] bg-[linear-gradient(135deg,#f6faf6_0%,#edf4ef_46%,#e9f2f4_100%)] px-4.5 pb-5 pt-4.5 text-[#243329] shadow-[0_14px_34px_rgba(78,99,88,0.08)] md:px-5 md:pb-5.5">
      <div class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div class="max-w-[42rem]">
          <p class="text-[11px] font-black uppercase tracking-[0.28em] text-[#74887c]">CatchYu Console</p>
          <h1 class="mt-2 flex items-center gap-2 text-[1.6rem] font-black tracking-tight md:text-[1.9rem]">
            <LayoutDashboard class="h-5.5 w-5.5 text-[#6ca28a]" />
            {{ t('dashboard.title') }}
          </h1>
          <p class="mt-1.5 max-w-[34rem] text-[13px] leading-6 text-[#627267] md:text-[14px]">
            {{ t('dashboard.description') }}
          </p>
        </div>
        <div class="rounded-[16px] border border-[#d6e2db] bg-white/90 px-3 py-2 shadow-sm backdrop-blur">
          <p class="text-[10px] font-black uppercase tracking-[0.22em] text-[#7f988b]">{{ t('dashboard.hero.label') }}</p>
          <p class="mt-1 max-w-[18rem] text-[13px] leading-5 text-[#65756b]">{{ t('dashboard.hero.description') }}</p>
        </div>
      </div>

      <div class="mt-3.5 grid gap-2.5 lg:grid-cols-3">
        <button
          v-for="item in quickActions"
          :key="item.routeName"
          class="group rounded-[15px] border border-[#d7e2db] bg-white/92 px-3 py-3 text-left shadow-sm backdrop-blur transition-all hover:-translate-y-0.5 hover:bg-white"
          @click="openRoute(item.routeName)"
        >
          <component :is="item.icon" class="h-4.5 w-4.5 text-[#74a08a]" />
          <h2 class="mt-2 text-[14px] font-black text-[#243329]">{{ item.title }}</h2>
          <p class="mt-0.5 text-[12px] leading-5 text-[#66746a]">{{ item.description }}</p>
        </button>
      </div>
    </section>
    <div v-if="error" class="app-alert-error" role="alert">
      {{ error.message }}
    </div>
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <Card
        v-for="stat in statCards"
        :key="stat.label"
        class="app-surface border-none transition-all hover:-translate-y-0.5"
      >
        <CardContent class="p-6">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-bold text-slate-400 uppercase tracking-wider">{{ stat.label }}</p>
              <h3 class="text-2xl font-black text-slate-800 mt-1">{{ stat.value }}</h3>
            </div>
            <div :class="[stat.bg, 'p-3 rounded-2xl']">
              <component :is="stat.icon" :class="['w-6 h-6', stat.color]" />
            </div>
          </div>
          <div class="mt-4 text-xs font-bold text-slate-500">
            {{ stat.detail }}
          </div>
        </CardContent>
      </Card>
    </div>
    <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <Card class="app-surface border-none">
        <CardHeader class="flex flex-col gap-4 border-b border-slate-100/60 pb-5 md:flex-row md:items-start md:justify-between">
          <div class="space-y-2">
            <CardTitle class="text-lg font-bold text-slate-800">
              {{ focusTitle }}
            </CardTitle>
            <p class="text-sm text-slate-500">{{ focusMeta }}</p>
          </div>
          <Badge variant="secondary" class="w-fit bg-blue-100 text-blue-600">
            {{ focusTask?.latest_crawl_time ? t('dashboard.focus.latestUpdate', { time: formatRelativeTimeFromNow(focusTask.latest_crawl_time) }) : t('dashboard.focus.waiting') }}
          </Badge>
        </CardHeader>
        <CardContent class="space-y-6 p-6">
          <div v-if="isLoading" class="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-10 text-center text-sm text-slate-500">
            {{ t('dashboard.focus.loading') }}
          </div>
          <div v-else-if="!focusTask?.filename" class="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-10 text-center text-sm text-slate-500">
            {{ t('dashboard.focus.noResults') }}
          </div>
          <div v-else class="rounded-2xl border border-slate-200/70 bg-slate-50/80 p-5 text-sm leading-7 text-slate-600 shadow-sm">
            {{ t('dashboard.focus.meta', { keyword: focusTask?.keyword || t('dashboard.focus.missingKeyword'), count: focusTask?.total_items || 0 }) }}
          </div>
        </CardContent>
      </Card>
      <div class="space-y-6">
        <Card class="app-surface border-none">
          <CardHeader>
            <CardTitle class="text-lg font-bold text-slate-800 flex items-center gap-2">
              <Activity class="w-5 h-5 text-rose-500" />
              {{ t('dashboard.activity.title') }}
            </CardTitle>
          </CardHeader>
          <CardContent class="p-0">
            <div v-if="activities.length === 0" class="px-4 pb-4 text-sm text-slate-500">
              {{ t('dashboard.activity.empty') }}
            </div>
            <div v-else class="divide-y divide-slate-100/50">
              <button
                v-for="activity in activities"
                :key="activity.id"
                class="w-full p-4 text-left hover:bg-slate-50/50 transition-colors"
                @click="openActivity(activity)"
              >
                <div class="flex items-center justify-between gap-3">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0"></div>
                    <div class="min-w-0">
                      <p class="text-sm font-bold text-slate-700 truncate">{{ activity.title }}</p>
                      <p class="text-[11px] text-slate-400">
                        {{ activity.task_name }} · {{ formatRelativeTimeFromNow(activity.timestamp) }}
                      </p>
                      <p v-if="activity.detail" class="mt-1 text-xs text-slate-500 truncate">{{ activity.detail }}</p>
                    </div>
                  </div>
                  <Badge variant="outline" class="text-[10px] border-slate-200 shrink-0">
                    {{ activity.status }}
                  </Badge>
                </div>
              </button>
            </div>
          </CardContent>
        </Card>
        <Button class="w-full" variant="outline" @click="router.push({ name: 'Logs' })">
          {{ t('dashboard.activity.viewAllLogs') }}
        </Button>
      </div>
    </div>
  </div>
</template>
