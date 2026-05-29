<script setup lang="ts">
import type { ResultItem } from '@/types/result.d.ts'
import CatchYuResultCard from './CatchYuResultCard.vue'

defineProps<{
  results: ResultItem[]
  isLoading: boolean
}>()

const emit = defineEmits<{
  (e: 'toggle-block', item: ResultItem): void
}>()

const skeletonItems = Array.from({ length: 4 }, (_, index) => index)
</script>

<template>
  <section :aria-busy="isLoading" class="space-y-2">
    <div v-if="isLoading" class="grid gap-2">
      <article
        v-for="item in skeletonItems"
        :key="item"
        class="overflow-hidden rounded-[8px] border border-[#e5d8c9] bg-[#fffaf3] shadow-[0_4px_10px_rgba(77,56,35,0.03)]"
      >
        <div class="grid gap-0 lg:grid-cols-[64px_minmax(0,1fr)]">
          <div class="min-h-[64px] animate-pulse bg-[#efe3d1]"></div>
          <div class="space-y-2 p-2.5">
            <div class="h-4 w-2/3 animate-pulse rounded-full bg-[#ecdeca]"></div>
            <div class="h-4 w-1/4 animate-pulse rounded-full bg-[#ecdeca]"></div>
            <div class="h-3.5 w-full animate-pulse rounded-full bg-[#ecdeca]"></div>
            <div class="h-3.5 w-4/5 animate-pulse rounded-full bg-[#ecdeca]"></div>
          </div>
        </div>
      </article>
    </div>

    <div
      v-else-if="results.length === 0"
      class="rounded-[32px] border border-dashed border-[#dccfbf] bg-[#fffaf2] px-6 py-14 text-center"
    >
      <p class="text-sm font-semibold text-[#7b6956]">当前结果集中还没有可展示的条目</p>
      <p class="mt-2 text-sm text-[#8f7c68]">可以切换结果集、放宽筛选条件，或等待下一次扫描完成。</p>
    </div>

    <div v-else class="grid gap-2">
      <CatchYuResultCard
        v-for="item in results"
        :key="item.商品信息.商品ID"
        :item="item"
        @toggle-block="emit('toggle-block', $event)"
      />
    </div>
  </section>
</template>
