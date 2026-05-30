<script setup lang="ts">
import { computed, toRefs } from 'vue'
import {
  Bot,
  CirclePlay,
  Clock3,
  Eye,
  MapPin,
  PauseCircle,
  Pencil,
  ScanSearch,
  ShieldCheck,
  Trash2,
} from 'lucide-vue-next'
import type { Task } from '@/types/task.d.ts'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'

const props = defineProps<{
  task: Task
  isStopping?: boolean
}>()
const { task, isStopping } = toRefs(props)

const emit = defineEmits<{
  (e: 'run', taskId: number): void
  (e: 'stop', taskId: number): void
  (e: 'edit', task: Task): void
  (e: 'delete', taskId: number): void
  (e: 'toggle-enabled', payload: { task: Task; enabled: boolean }): void
}>()

const decisionModeLabel = computed(() => props.task.decision_mode === 'keyword' ? '关键词模式' : 'AI 模式')
const decisionModeTone = computed(() =>
  props.task.decision_mode === 'keyword'
    ? 'border-[#d7e4d8] bg-[#eef6ef] text-[#355943]'
    : 'border-[#edd9c7] bg-[#fbefe1] text-[#8f4e1f]'
)
const scheduleLabel = computed(() => props.task.cron || '手动触发')
const statusTone = computed(() => {
  if (props.task.is_running) {
    return {
      dot: 'bg-[#3d7d58]',
      label: '扫描进行中',
      shell: 'border-[#dce9df] bg-[#edf6ef] text-[#325341]',
    }
  }
  if (props.task.enabled) {
    return {
      dot: 'bg-[#c27f2b]',
      label: '待命中',
      shell: 'border-[#eadcc7] bg-[#fbf4e8] text-[#7e5d37]',
    }
  }
  return {
    dot: 'bg-[#8a8177]',
    label: '已暂停',
    shell: 'border-[#e6dfd7] bg-[#f7f2ec] text-[#71675d]',
  }
})
const tags = computed(() => {
  const values: string[] = []
  if (props.task.personal_only) values.push('仅个人卖家')
  if (props.task.free_shipping) values.push('包邮优先')
  if (props.task.region) values.push(props.task.region)
  if (props.task.keyword_rules?.length) values.push(`${props.task.keyword_rules.length} 条关键词规则`)
  return values.slice(0, 4)
})
const priceRange = computed(() => {
  const min = props.task.min_price
  const max = props.task.max_price
  if (!min && !max) return '不限价格'
  if (min && max) return `¥${min} - ¥${max}`
  if (min) return `¥${min} 起`
  return `最高 ¥${max}`
})
</script>

<template>
  <article class="group rounded-[20px] border border-[#eadfce] bg-[linear-gradient(180deg,rgba(255,251,244,0.96)_0%,rgba(252,248,241,0.98)_100%)] p-3.5 shadow-[0_14px_30px_rgba(77,56,35,0.06)] transition-transform duration-300 hover:-translate-y-0.5">
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div class="min-w-0 space-y-2">
          <div class="flex flex-wrap items-center gap-2">
            <span class="inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-bold" :class="statusTone.shell">
              <span class="h-2 w-2 rounded-full" :class="statusTone.dot"></span>
              {{ statusTone.label }}
            </span>
            <span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold" :class="decisionModeTone">
              <Bot v-if="task.decision_mode === 'ai'" class="h-3 w-3" />
              <ScanSearch v-else class="h-3 w-3" />
              {{ decisionModeLabel }}
            </span>
          </div>

          <div>
            <h3 class="line-clamp-1 text-[1.08rem] font-black tracking-[-0.03em] text-[#241a12]">
              {{ task.task_name }}
            </h3>
            <p class="mt-1 text-[13px] font-semibold text-[#7a6046]">
              关键词：{{ task.keyword }}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-3 self-start rounded-full border border-[#e4d8c7] bg-white/80 px-3 py-1.5 shadow-sm">
          <div class="text-right">
            <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-[#a0886f]">启用状态</p>
            <p class="mt-0.5 text-sm font-semibold text-[#332419]">{{ task.enabled ? '参与调度' : '暂停调度' }}</p>
          </div>
          <Switch :model-value="task.enabled" @update:model-value="(value) => emit('toggle-enabled', { task, enabled: value === true })" />
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <span class="inline-flex items-center gap-1.5 rounded-full border border-[#e7ddce] bg-white/86 px-2.5 py-1 text-[11px] font-semibold text-[#694f39]">
          <Clock3 class="h-3 w-3 text-[#c6582e]" />
          {{ scheduleLabel }}
        </span>
        <span class="inline-flex rounded-full border border-[#e7ddce] bg-white/86 px-2.5 py-1 text-[11px] font-semibold text-[#694f39]">
          {{ priceRange }}
        </span>
        <span class="inline-flex rounded-full border border-[#e7ddce] bg-white/86 px-2.5 py-1 text-[11px] font-semibold text-[#694f39]">
          搜索 {{ task.max_pages || 0 }} 页
        </span>
        <span
          v-for="tag in tags"
          :key="tag"
          class="inline-flex items-center gap-1 rounded-full border border-[#e7ddce] bg-[#faf4eb] px-2.5 py-1 text-[11px] font-semibold text-[#694f39]"
        >
          <MapPin v-if="tag === task.region" class="h-3 w-3" />
          <ShieldCheck v-else-if="tag === '仅个人卖家'" class="h-3 w-3" />
          <Eye v-else class="h-3 w-3" />
          {{ tag }}
        </span>
      </div>

      <div class="flex flex-wrap gap-2 border-t border-[#eee5d8] pt-3">
        <Button
          v-if="!task.is_running"
          class="h-9 rounded-full bg-[#21160f] px-3.5 text-sm text-white hover:bg-[#332117]"
          @click="emit('run', task.id)"
        >
          <CirclePlay class="mr-1.5 h-4 w-4" />
          立即启动
        </Button>
        <Button
          v-else
          variant="outline"
          class="h-9 rounded-full border-[#c6582e]/30 bg-[#fff5ef] px-3.5 text-sm text-[#a24b26] hover:bg-[#fff1e6]"
          :disabled="isStopping"
          @click="emit('stop', task.id)"
        >
          <PauseCircle class="mr-1.5 h-4 w-4" />
          {{ isStopping ? '停止中...' : '停止任务' }}
        </Button>
        <Button variant="outline" class="h-9 rounded-full border-[#ddcfbc] bg-white/80 px-3.5 text-sm text-[#473122] hover:bg-white" @click="emit('edit', task)">
          <Pencil class="mr-1.5 h-4 w-4" />
          编辑
        </Button>
        <Button
          variant="outline"
          class="h-9 rounded-full border-[#f1d7d0] bg-[#fff2ef] px-3.5 text-sm text-[#a24b26] hover:bg-[#ffeae5]"
          @click="emit('delete', task.id)"
        >
          <Trash2 class="mr-1.5 h-4 w-4" />
          删除
        </Button>
      </div>
    </div>
  </article>
</template>
