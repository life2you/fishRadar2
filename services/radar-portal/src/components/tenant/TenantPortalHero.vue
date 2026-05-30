<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'

interface HeroStat {
  label: string
  value: string
  detail?: string
}

defineProps<{
  eyebrow: string
  title: string
  description: string
  note?: string
  stats: HeroStat[]
}>()
</script>

<template>
  <section class="relative overflow-hidden rounded-[24px] border border-[#cfddd1] bg-[radial-gradient(circle_at_top_left,rgba(174,210,190,0.24),transparent_30%),radial-gradient(circle_at_top_right,rgba(188,214,228,0.18),transparent_26%),linear-gradient(145deg,#f7fbf6_0%,#edf5ef_48%,#eaf4f2_100%)] px-4.5 py-4 shadow-[0_14px_34px_rgba(77,100,84,0.09)] md:px-5 md:py-4.5">
    <div aria-hidden="true" class="pointer-events-none absolute inset-0">
      <div class="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#8bb09a]/45 to-transparent"></div>
      <div class="absolute bottom-0 left-[10%] h-28 w-28 rounded-full bg-[#d6c98e]/10 blur-3xl"></div>
      <div class="absolute right-[8%] top-[18%] h-32 w-32 rounded-full bg-[#94baa5]/16 blur-3xl"></div>
    </div>

    <div class="relative z-10 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
      <div class="max-w-[46rem] space-y-2">
        <div class="flex flex-wrap items-center gap-2.5">
          <span class="inline-flex items-center gap-2 rounded-full border border-[#cfdccf] bg-white/86 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.24em] text-[#56705f] shadow-sm backdrop-blur">
            <Sparkles class="h-3.5 w-3.5 text-[#5d9b79]" />
            CatchYu
          </span>
          <span class="inline-flex rounded-full border border-[#d6e1d3] bg-[#f8fbf7] px-3 py-1 text-[10px] font-semibold tracking-[0.14em] text-[#718478]">
            {{ eyebrow }}
          </span>
        </div>

        <div class="space-y-1.5">
          <h1 class="max-w-2xl text-[1.68rem] font-black tracking-[-0.05em] text-[#213126] md:text-[1.95rem] md:leading-[1.08]">
            {{ title }}
          </h1>
          <p class="max-w-[38rem] text-[13px] leading-6 text-[#617165] md:text-[14px]">
            {{ description }}
          </p>
        </div>

        <div v-if="note" class="flex flex-wrap gap-2.5">
          <p class="inline-flex rounded-full border border-[#cfddd1] bg-white/90 px-3 py-1 text-[11px] font-medium text-[#5d6f63] shadow-sm">
            {{ note }}
          </p>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2 xl:max-w-[20rem] xl:justify-end">
        <slot name="actions" />
      </div>
    </div>

    <div v-if="stats.length" class="relative z-10 mt-3.5 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
      <article
        v-for="stat in stats"
        :key="stat.label"
        class="rounded-[15px] border border-[#d4e0d5] bg-[linear-gradient(180deg,rgba(255,255,255,0.94)_0%,rgba(244,248,243,0.99)_100%)] px-3 py-2.5 shadow-[0_8px_18px_rgba(95,115,101,0.07)]"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-[#7b8e7d]">
              {{ stat.label }}
            </p>
            <p v-if="stat.detail" class="mt-1 text-[11px] leading-4 text-[#687870]">
              {{ stat.detail }}
            </p>
          </div>
          <p class="shrink-0 text-[1.22rem] font-black tracking-[-0.05em] text-[#213126]">
            {{ stat.value }}
          </p>
        </div>
      </article>
    </div>
  </section>
</template>
