<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { Activity, Clock3, ScrollText, Trash2 } from 'lucide-vue-next'
import { useLogs } from '@/composables/useLogs'
import { useTasks } from '@/composables/useTasks'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toast'

const { t } = useI18n()
const { tasks } = useTasks()
const { logs, isAutoRefresh, clearLogs, toggleAutoRefresh, fetchLogs, setTaskId, loadLatest, loadPrevious, isFetchingHistory, hasMoreHistory } = useLogs()
const logContainer = ref<HTMLElement | null>(null)
const autoScroll = ref(true)
const isClearDialogOpen = ref(false)
const selectedTaskId = ref('')
const isPrepending = ref(false)
const lastScrollTop = ref(0)
const lastScrollHeight = ref(0)

const selectedTask = computed(() => tasks.value.find((task) => String(task.id) === selectedTaskId.value) ?? null)
const heroCards = computed(() => [
  {
    icon: Activity,
    label: t('logs.hero.cards.task'),
    value: selectedTask.value?.task_name || t('logs.selectTask'),
    detail: selectedTask.value?.is_running ? t('common.running') : t('common.idle'),
  },
  {
    icon: Clock3,
    label: t('logs.hero.cards.refresh'),
    value: isAutoRefresh.value ? t('logs.autoRefresh') : t('logs.hero.manualRefresh'),
    detail: autoScroll.value ? t('logs.autoScroll') : t('logs.hero.manualScroll'),
  },
  {
    icon: Trash2,
    label: t('logs.hero.cards.clear'),
    value: selectedTaskId.value ? t('logs.dialogTitle') : t('common.empty'),
    detail: selectedTaskId.value ? t('logs.dialogDescription') : t('logs.hero.clearHint'),
  },
])

// Auto-scroll logic
watch(logs, async () => {
  if (isPrepending.value) {
    await nextTick()
    if (logContainer.value) {
      const delta = logContainer.value.scrollHeight - lastScrollHeight.value
      logContainer.value.scrollTop = lastScrollTop.value + delta
    }
    isPrepending.value = false
    return
  }
  if (autoScroll.value) {
    await nextTick()
    scrollToBottom()
  }
})

watch(tasks, (list) => {
  if (!list.length) {
    selectedTaskId.value = ''
    setTaskId(null)
    return
  }
  if (selectedTaskId.value && list.some((task) => String(task.id) === selectedTaskId.value)) {
    return
  }
  const running = list.find((task) => task.is_running)
  const fallback = list[0]
  if (!fallback) {
    selectedTaskId.value = ''
    setTaskId(null)
    return
  }
  selectedTaskId.value = String(running ? running.id : fallback.id)
}, { immediate: true })

watch(selectedTaskId, (taskId) => {
  const resolvedTaskId = taskId ? Number(taskId) : null
  setTaskId(resolvedTaskId)
  if (resolvedTaskId) {
    loadLatest(50)
  }
})

function scrollToBottom() {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

async function handleScroll() {
  if (!logContainer.value) return
  if (!hasMoreHistory.value || isFetchingHistory.value) return
  if (logContainer.value.scrollTop > 120) return
  lastScrollTop.value = logContainer.value.scrollTop
  lastScrollHeight.value = logContainer.value.scrollHeight
  isPrepending.value = true
  await loadPrevious(50)
}

function openClearDialog() {
  isClearDialogOpen.value = true
}

async function handleClearLogs() {
  try {
    await clearLogs()
    toast({ title: t('logs.logsCleared') })
  } catch (e) {
    toast({
      title: t('logs.clearFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    isClearDialogOpen.value = false
  }
}
</script>

<template>
  <div class="flex h-[calc(100vh-100px)] flex-col gap-4">
    <section class="rounded-[20px] border border-[#d7e2db] bg-[linear-gradient(135deg,#f7fbf7_0%,#eef5f0_100%)] px-4 py-4 text-[#243329] shadow-[0_10px_24px_rgba(78,99,88,0.06)]">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div class="max-w-[42rem]">
          <p class="text-[10px] font-black uppercase tracking-[0.24em] text-[#74887c]">CatchYu Console</p>
          <div class="mt-1.5 flex flex-wrap items-center gap-3">
            <h1 class="flex items-center gap-2 text-[1.45rem] font-black tracking-tight text-[#243329]">
              <ScrollText class="h-5 w-5 text-[#6ca28a]" />
              {{ t('logs.title') }}
            </h1>
            <span class="rounded-full border border-[#d7e2db] bg-white/90 px-2.5 py-1 text-[11px] font-medium text-[#5d7064]">
              {{ t('logs.hero.panelLabel') }}
            </span>
          </div>
          <p class="mt-1 text-[13px] leading-5 text-[#627267]">{{ t('logs.description') }}</p>
        </div>
        <div class="text-[12px] leading-5 text-[#66766b] lg:max-w-[18rem]">{{ t('logs.hero.panelDescription') }}</div>
      </div>

      <div class="mt-3 grid gap-2 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div class="flex flex-wrap gap-2">
          <article
            v-for="card in heroCards"
            :key="card.label"
            class="flex min-w-[190px] flex-1 items-start gap-3 rounded-[14px] border border-[#d7e2db] bg-white/94 px-3 py-2.5 shadow-sm"
          >
            <component :is="card.icon" class="mt-0.5 h-4.5 w-4.5 shrink-0 text-[#74a08a]" />
            <div class="min-w-0">
              <p class="text-[10px] font-black uppercase tracking-[0.18em] text-[#88a094]">{{ card.label }}</p>
              <p class="mt-0.5 text-[14px] font-black text-[#243329]">{{ card.value }}</p>
              <p class="mt-0.5 text-[12px] leading-5 text-[#66766b]">{{ card.detail }}</p>
            </div>
          </article>
        </div>
        <div class="rounded-[14px] border border-[#d7e2db] bg-white/94 p-3 shadow-sm">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Label class="text-sm text-[#65756a]">{{ t('logs.task') }}</Label>
              <Select v-model="selectedTaskId">
                <SelectTrigger class="w-full border-white/80 bg-white text-[#243329] sm:w-[260px]">
                  <SelectValue :placeholder="t('logs.selectTask')" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="task in tasks" :key="task.id" :value="String(task.id)">
                    {{ task.task_name }}{{ task.is_running ? t('logs.taskRunningSuffix') : '' }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button variant="outline" size="sm" class="border-white/80 bg-white text-[#243329] hover:bg-white/90" :disabled="!selectedTaskId" @click="fetchLogs">
              {{ t('common.refresh') }}
            </Button>
            <Button variant="destructive" size="sm" :disabled="!selectedTaskId" @click="openClearDialog">
              {{ t('logs.clearLogs') }}
            </Button>
          </div>

          <div class="mt-3 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <div class="flex items-center space-x-2">
              <Switch id="auto-refresh" :model-value="isAutoRefresh" @update:model-value="toggleAutoRefresh" />
              <Label for="auto-refresh" class="text-[#65756a]">{{ t('logs.autoRefresh') }}</Label>
            </div>

            <div class="flex items-center space-x-2">
              <Switch id="auto-scroll" v-model="autoScroll" />
              <Label for="auto-scroll" class="text-[#65756a]">{{ t('logs.autoScroll') }}</Label>
            </div>
          </div>
        </div>
      </div>
    </section>

    <Card class="app-surface flex flex-1 flex-col overflow-hidden border-none">
      <CardContent class="flex-1 p-0 relative">
        <pre
          ref="logContainer"
          @scroll="handleScroll"
          class="absolute inset-0 p-4 bg-gray-950 text-gray-100 font-mono text-sm overflow-auto whitespace-pre-wrap break-all"
        >{{ logs }}</pre>
      </CardContent>
    </Card>

    <Dialog v-model:open="isClearDialogOpen">
      <DialogContent class="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{{ t('logs.dialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{ t('logs.dialogDescription') }}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isClearDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button variant="destructive" @click="handleClearLogs">{{ t('logs.confirmClear') }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
