<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminTenantAccessPanel from '@/components/admin/AdminTenantAccessPanel.vue'

const { t } = useI18n()
const tenantSummaryItems = ref<Array<{ label: string; value: string; detail: string }>>([])
</script>

<template>
  <div class="space-y-6">
    <section class="overflow-hidden rounded-[24px] border border-[#cfddd5] bg-[linear-gradient(135deg,#f6faf6_0%,#edf4ef_46%,#e9f2f4_100%)] px-4.5 pb-5.5 pt-4.5 text-[#243329] shadow-[0_14px_34px_rgba(78,99,88,0.08)] md:px-5 md:pb-6">
      <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p class="text-[11px] font-black uppercase tracking-[0.28em] text-[#74887c]">CatchYu Console</p>
          <h1 class="mt-2 text-[1.6rem] font-black tracking-tight text-[#243329] md:text-[1.9rem]">
            {{ t('tenants.hero.title') }}
          </h1>
          <p class="mt-1.5 max-w-[34rem] text-[13px] leading-6 text-[#627267] md:text-[14px]">
            {{ t('tenants.hero.description') }}
          </p>
        </div>
        <div v-if="tenantSummaryItems.length" class="mt-1 grid gap-2 sm:grid-cols-3 xl:mt-0 xl:min-w-[420px] xl:max-w-[460px] xl:self-end">
          <article
            v-for="summary in tenantSummaryItems"
            :key="summary.label"
            class="rounded-2xl border border-white/70 bg-white/78 px-3.5 py-2.5 shadow-[0_10px_24px_rgba(126,145,133,0.08)] backdrop-blur-sm"
          >
            <p class="text-[11px] font-black uppercase tracking-[0.18em] text-[#74887c]">{{ summary.label }}</p>
            <div class="mt-2 flex items-end justify-between gap-3">
              <p class="text-xl font-black text-[#243329]">{{ summary.value }}</p>
              <p class="text-right text-[11px] text-[#6e7f74]">{{ summary.detail }}</p>
            </div>
          </article>
        </div>
      </div>
    </section>

    <AdminTenantAccessPanel hide-inline-summary @summary-loaded="tenantSummaryItems = $event" />
  </div>
</template>
