<script setup lang="ts">
import { computed } from 'vue'
import { Download, Eye, EyeOff, Filter, ListFilter, RefreshCw, Trash2 } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface FileOption {
  value: string
  label: string
  taskName?: string
}

const props = defineProps<{
  files: string[]
  fileOptions?: FileOption[]
  selectedFile: string | null
  aiRecommendedOnly: boolean
  keywordRecommendedOnly: boolean
  includeHidden: boolean
  sortBy: 'crawl_time' | 'publish_time' | 'price' | 'keyword_hit_count'
  sortOrder: 'asc' | 'desc'
  isLoading: boolean
  isReady: boolean
}>()

const emit = defineEmits<{
  (e: 'update:selectedFile', value: string): void
  (e: 'update:aiRecommendedOnly', value: boolean): void
  (e: 'update:keywordRecommendedOnly', value: boolean): void
  (e: 'update:includeHidden', value: boolean): void
  (e: 'update:sortBy', value: 'crawl_time' | 'publish_time' | 'price' | 'keyword_hit_count'): void
  (e: 'update:sortOrder', value: 'asc' | 'desc'): void
  (e: 'refresh'): void
  (e: 'export'): void
  (e: 'delete'): void
  (e: 'manage-blacklist'): void
}>()

const options = computed(() => {
  if (!props.isReady) return []
  if (props.fileOptions?.length) return props.fileOptions
  return props.files.map((file) => ({ value: file, label: file }))
})

const isSelectDisabled = computed(() => !props.isReady || options.value.length === 0)
const selectedLabel = computed(() => {
  if (!props.isReady) return '正在同步结果集'
  if (options.value.length === 0) return '暂无结果集'
  if (!props.selectedFile) return '选择一个结果集'
  return options.value.find((item) => item.value === props.selectedFile)?.label || props.selectedFile
})

function toggleExclusive(type: 'ai' | 'keyword') {
  if (type === 'ai') {
    const next = !props.aiRecommendedOnly
    emit('update:aiRecommendedOnly', next)
    if (next) emit('update:keywordRecommendedOnly', false)
    return
  }
  const next = !props.keywordRecommendedOnly
  emit('update:keywordRecommendedOnly', next)
  if (next) emit('update:aiRecommendedOnly', false)
}
</script>

<template>
  <section class="rounded-[30px] border border-[#eadfce] bg-[linear-gradient(180deg,rgba(255,252,246,0.96)_0%,rgba(252,247,239,0.98)_100%)] p-5 shadow-[0_24px_60px_rgba(77,56,35,0.08)]">
    <div class="flex flex-col gap-5">
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_repeat(2,minmax(0,0.75fr))]">
        <div class="space-y-2">
          <p class="text-[11px] font-bold uppercase tracking-[0.24em] text-[#9b8165]">结果集</p>
          <Select
            :model-value="props.selectedFile || undefined"
            @update:model-value="(value) => emit('update:selectedFile', value as string)"
          >
            <SelectTrigger class="h-12 rounded-2xl border-[#e1d4c1] bg-white/90 text-left text-[#2f2218]" :disabled="isSelectDisabled">
              <SelectValue :placeholder="selectedLabel" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="option in options" :key="option.value" :value="option.value">
                {{ option.label }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="space-y-2">
          <p class="text-[11px] font-bold uppercase tracking-[0.24em] text-[#9b8165]">排序字段</p>
          <Select :model-value="props.sortBy" @update:model-value="(value) => emit('update:sortBy', value as any)">
            <SelectTrigger class="h-12 rounded-2xl border-[#e1d4c1] bg-white/90 text-[#2f2218]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="crawl_time">按抓取时间</SelectItem>
              <SelectItem value="publish_time">按发布时间</SelectItem>
              <SelectItem value="price">按价格</SelectItem>
              <SelectItem value="keyword_hit_count">按关键词命中</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="space-y-2">
          <p class="text-[11px] font-bold uppercase tracking-[0.24em] text-[#9b8165]">排序方向</p>
          <Select :model-value="props.sortOrder" @update:model-value="(value) => emit('update:sortOrder', value as any)">
            <SelectTrigger class="h-12 rounded-2xl border-[#e1d4c1] bg-white/90 text-[#2f2218]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="desc">从新到旧</SelectItem>
              <SelectItem value="asc">从旧到新</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition-colors"
            :class="props.aiRecommendedOnly ? 'border-[#d1e2d4] bg-[#edf6ef] text-[#2f5b42]' : 'border-[#e4d8c8] bg-white/75 text-[#6a5744] hover:bg-white'"
            @click="toggleExclusive('ai')"
          >
            <Filter class="h-4 w-4" />
            仅看 AI 推荐
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition-colors"
            :class="props.keywordRecommendedOnly ? 'border-[#ead3c0] bg-[#fbefe1] text-[#9b5524]' : 'border-[#e4d8c8] bg-white/75 text-[#6a5744] hover:bg-white'"
            @click="toggleExclusive('keyword')"
          >
            <ListFilter class="h-4 w-4" />
            仅看关键词推荐
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition-colors"
            :class="props.includeHidden ? 'border-[#dbd5cb] bg-[#f1eeea] text-[#54483c]' : 'border-[#e4d8c8] bg-white/75 text-[#6a5744] hover:bg-white'"
            @click="emit('update:includeHidden', !props.includeHidden)"
          >
            <Eye v-if="props.includeHidden" class="h-4 w-4" />
            <EyeOff v-else class="h-4 w-4" />
            {{ props.includeHidden ? '已显示隐藏项' : '显示隐藏项' }}
          </button>
        </div>

        <div class="flex flex-wrap gap-2">
          <Button
            variant="outline"
            class="rounded-full border-[#e0d3c1] bg-white/82 px-4 text-[#473122] hover:bg-white"
            :disabled="props.isLoading"
            @click="emit('refresh')"
          >
            <RefreshCw class="mr-2 h-4 w-4" />
            刷新
          </Button>
          <Button
            variant="outline"
            class="rounded-full border-[#d6dece] bg-[#edf6ef] px-4 text-[#355943] hover:bg-[#e4f1e7]"
            :disabled="props.isLoading || !props.selectedFile"
            @click="emit('manage-blacklist')"
          >
            管理黑名单
          </Button>
          <Button
            variant="outline"
            class="rounded-full border-[#e7d3c2] bg-[#fff4eb] px-4 text-[#995222] hover:bg-[#ffeedf]"
            :disabled="props.isLoading || !props.selectedFile"
            @click="emit('export')"
          >
            <Download class="mr-2 h-4 w-4" />
            导出 CSV
          </Button>
          <Button
            variant="outline"
            class="rounded-full border-[#f0d7d0] bg-[#fff1ed] px-4 text-[#a24b26] hover:bg-[#ffe8e1]"
            :disabled="props.isLoading || !props.selectedFile"
            @click="emit('delete')"
          >
            <Trash2 class="mr-2 h-4 w-4" />
            删除结果集
          </Button>
        </div>
      </div>
    </div>
  </section>
</template>
