<script setup lang="ts">
import { computed, toRefs } from 'vue'
import { Download, ShieldBan, Sparkles, TrendingUp } from 'lucide-vue-next'
import { formatDateTime } from '@/i18n'
import type { ResultInsights } from '@/types/result.d.ts'
import { Button } from '@/components/ui/button'
import PriceTrendChart from '@/components/results/PriceTrendChart.vue'

const props = defineProps<{
  insights: ResultInsights | null
  selectedTaskLabel?: string | null
  blacklistKeywords: string[]
  canExport?: boolean
  canManageBlacklist?: boolean
}>()
const { insights, selectedTaskLabel, blacklistKeywords, canExport, canManageBlacklist } = toRefs(props)

const emit = defineEmits<{
  (e: 'export'): void
  (e: 'manage-blacklist'): void
}>()

const summaryCards = computed(() => {
  if (!props.insights) {
    return [
      { label: '当前均价', value: '—', detail: '等待结果集数据' },
      { label: '历史均价', value: '—', detail: '等待价格快照' },
      { label: '最低价格', value: '—', detail: '等待价格快照' },
    ]
  }
  return [
    {
      label: '当前均价',
      value: props.insights.market_summary.avg_price ? `¥${props.insights.market_summary.avg_price}` : '—',
      detail: `样本 ${props.insights.market_summary.sample_count || 0} 条`,
    },
    {
      label: '历史均价',
      value: props.insights.history_summary.avg_price ? `¥${props.insights.history_summary.avg_price}` : '—',
      detail: `独立商品 ${props.insights.history_summary.unique_items || 0} 个`,
    },
    {
      label: '最低价格',
      value: props.insights.market_summary.min_price ? `¥${props.insights.market_summary.min_price}` : '—',
      detail: props.insights.market_summary.max_price ? `最高 ¥${props.insights.market_summary.max_price}` : '暂无价格区间',
    },
  ]
})

const latestSnapshotText = computed(() => {
  if (!props.insights?.latest_snapshot_at) return '还没有形成趋势快照'
  return formatDateTime(props.insights.latest_snapshot_at, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
})
</script>

<template>
  <aside class="space-y-4">
    <section class="rounded-[30px] border border-[#eadfce] bg-[linear-gradient(180deg,rgba(255,251,244,0.98)_0%,rgba(250,244,235,0.98)_100%)] p-5 shadow-[0_24px_60px_rgba(77,56,35,0.08)]">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-[11px] font-bold uppercase tracking-[0.24em] text-[#9b8165]">情报侧栏</p>
          <h3 class="mt-3 text-2xl font-black tracking-[-0.04em] text-[#241a12]">
            {{ selectedTaskLabel || '选择结果集后查看洞察' }}
          </h3>
          <p class="mt-3 text-sm leading-6 text-[#6a5744]">
            围绕价格趋势、黑名单规则和导出动作，帮助你把结果页快速收束成可判断的情报面板。
          </p>
        </div>
        <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#f3e2ca] text-[#a25c23]">
          <Sparkles class="h-5 w-5" />
        </div>
      </div>

      <div class="mt-5 grid gap-3">
        <article
          v-for="card in summaryCards"
          :key="card.label"
          class="rounded-[22px] border border-white/85 bg-white/85 p-4 shadow-sm"
        >
          <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-[#9b8165]">{{ card.label }}</p>
          <p class="mt-2 text-2xl font-black tracking-[-0.04em] text-[#23170f]">{{ card.value }}</p>
          <p class="mt-2 text-xs leading-5 text-[#6a5744]">{{ card.detail }}</p>
        </article>
      </div>
    </section>

    <section class="rounded-[30px] border border-[#eadfce] bg-white/88 p-5 shadow-[0_24px_60px_rgba(77,56,35,0.08)]">
      <div class="flex items-center gap-2 text-[#9b8165]">
        <TrendingUp class="h-4 w-4" />
        <p class="text-[11px] font-bold uppercase tracking-[0.24em]">价格走势</p>
      </div>
      <div class="mt-4">
        <PriceTrendChart :points="insights?.daily_trend || []" />
      </div>
      <p class="mt-3 text-xs leading-5 text-[#6a5744]">
        最新快照：{{ latestSnapshotText }}
      </p>
    </section>

    <section class="rounded-[30px] border border-[#eadfce] bg-[linear-gradient(180deg,#fffef9_0%,#f7f1e8_100%)] p-5 shadow-[0_24px_60px_rgba(77,56,35,0.08)]">
      <div class="flex items-center gap-2 text-[#9b8165]">
        <ShieldBan class="h-4 w-4" />
        <p class="text-[11px] font-bold uppercase tracking-[0.24em]">黑名单规则</p>
      </div>
      <div class="mt-4 flex flex-wrap gap-2">
        <span
          v-for="keyword in blacklistKeywords.slice(0, 8)"
          :key="keyword"
          class="rounded-full border border-[#e5d8c6] bg-white/90 px-3 py-1 text-xs font-semibold text-[#684e38]"
        >
          {{ keyword }}
        </span>
        <span v-if="blacklistKeywords.length === 0" class="text-sm text-[#7d6b57]">
          当前没有黑名单关键词
        </span>
      </div>

      <div class="mt-5 grid gap-2">
        <Button
          class="h-11 rounded-full bg-[#21160f] text-white hover:bg-[#2f2016]"
          :disabled="!canManageBlacklist"
          @click="emit('manage-blacklist')"
        >
          管理黑名单
        </Button>
        <Button
          variant="outline"
          class="h-11 rounded-full border-[#e6d4c1] bg-[#fff5ea] text-[#9b5524] hover:bg-[#ffecdc]"
          :disabled="!canExport"
          @click="emit('export')"
        >
          <Download class="mr-2 h-4 w-4" />
          导出当前结果
        </Button>
      </div>
    </section>
  </aside>
</template>
