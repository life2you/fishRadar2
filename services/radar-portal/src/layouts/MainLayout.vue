<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import TheHeader from '@/components/layout/TheHeader.vue'
import TheSidebar from '@/components/layout/TheSidebar.vue'
import { useAuth } from '@/composables/useAuth'
import { useMobileNav } from '@/composables/useMobileNav'
import { getActiveAnnouncements } from '@/api/settings'
import type { AnnouncementItem } from '@/api/settings'
import { Button } from '@/components/ui/button'
import { X } from 'lucide-vue-next'

const { isMobileNavOpen, closeMobileNav } = useMobileNav()
const { role, workspaceEnabled } = useAuth()
const { t } = useI18n()
const isTenant = computed(() => role.value === 'tenant')
const tenantAnnouncements = ref<AnnouncementItem[]>([])
const dismissedAnnouncementKeys = ref<string[]>([])

function announcementStorageKey(item: AnnouncementItem) {
  return `tenant_announcement_dismissed:${item.id}:${item.updated_at}`
}

function loadDismissedAnnouncements() {
  if (typeof window === 'undefined') return
  const raw = localStorage.getItem('tenantDismissedAnnouncements')
  dismissedAnnouncementKeys.value = raw ? JSON.parse(raw) : []
}

function persistDismissedAnnouncements() {
  if (typeof window === 'undefined') return
  localStorage.setItem('tenantDismissedAnnouncements', JSON.stringify(dismissedAnnouncementKeys.value))
}

function dismissAnnouncement(item: AnnouncementItem) {
  const key = announcementStorageKey(item)
  if (!dismissedAnnouncementKeys.value.includes(key)) {
    dismissedAnnouncementKeys.value = [...dismissedAnnouncementKeys.value, key]
    persistDismissedAnnouncements()
  }
}

const visibleTenantAnnouncements = computed(() =>
  tenantAnnouncements.value.filter((item) => !dismissedAnnouncementKeys.value.includes(announcementStorageKey(item))),
)

function getAnnouncementTone(level: string) {
  if (level === 'success') {
    return 'border-emerald-200 bg-emerald-50/90 text-emerald-800'
  }
  if (level === 'warning') {
    return 'border-amber-200 bg-amber-50/92 text-amber-900'
  }
  return 'border-sky-200 bg-sky-50/92 text-sky-900'
}

async function loadTenantAnnouncements() {
  if (!isTenant.value || !workspaceEnabled.value) {
    tenantAnnouncements.value = []
    return
  }
  try {
    const response = await getActiveAnnouncements()
    tenantAnnouncements.value = response.items
  } catch {
    tenantAnnouncements.value = []
  }
}

watch([isTenant, workspaceEnabled], () => {
  loadTenantAnnouncements()
}, { immediate: true })

onMounted(() => {
  loadDismissedAnnouncements()
})
</script>

<template>
  <div
    v-if="isTenant"
    class="relative min-h-screen w-full overflow-hidden bg-[linear-gradient(180deg,#fbf8f1_0%,#f2f6ef_44%,#eef5f3_100%)] selection:bg-primary/15"
  >
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[120] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
    >
      {{ t('common.skipToContent') }}
    </a>

    <div aria-hidden="true" class="pointer-events-none fixed inset-0 overflow-hidden">
      <div class="absolute left-[-8%] top-[-3%] h-[34rem] w-[34rem] rounded-full bg-[#cfe0bf]/28 blur-[140px]"></div>
      <div class="absolute right-[-10%] top-[8%] h-[28rem] w-[28rem] rounded-full bg-[#b8d7ce]/24 blur-[130px]"></div>
      <div class="absolute bottom-[-14%] left-[24%] h-[28rem] w-[28rem] rounded-full bg-[#f0d9b6]/22 blur-[135px]"></div>
      <div class="absolute inset-x-[10%] top-[8.5rem] h-px bg-gradient-to-r from-transparent via-[#a8beaa]/45 to-transparent"></div>
      <div class="absolute inset-x-[6%] bottom-0 h-[38%] bg-[radial-gradient(circle_at_bottom,rgba(255,255,255,0.22),transparent_68%)]"></div>
    </div>

    <TheHeader class="relative z-20" />

    <main id="main-content" tabindex="-1" class="relative z-10 px-4 py-6 focus:outline-none md:px-8 md:py-10">
      <div class="mx-auto max-w-[1320px] animate-fade-in">
        <div v-if="visibleTenantAnnouncements.length" class="mb-4 space-y-3">
          <section
            v-for="item in visibleTenantAnnouncements"
            :key="item.id"
            class="rounded-2xl border px-4 py-3 shadow-sm"
            :class="getAnnouncementTone(item.level)"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="text-[11px] font-black uppercase tracking-[0.18em] opacity-75">平台公告</p>
                  <span class="rounded-full border border-current/15 bg-white/55 px-2 py-0.5 text-[11px] font-semibold">
                    {{ item.level === 'warning' ? '维护提醒' : item.level === 'success' ? '完成通知' : '升级通知' }}
                  </span>
                </div>
                <h2 class="mt-1 text-base font-black">{{ item.title }}</h2>
                <p class="mt-1 whitespace-pre-wrap text-sm leading-6 opacity-90">{{ item.content }}</p>
              </div>
              <Button
                v-if="item.dismissible"
                variant="ghost"
                size="icon"
                class="h-8 w-8 shrink-0 rounded-full text-current hover:bg-white/55"
                @click="dismissAnnouncement(item)"
              >
                <X class="h-4 w-4" />
              </Button>
            </div>
          </section>
        </div>
        <RouterView v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </div>
    </main>
  </div>

  <div v-else class="relative min-h-screen w-full flex flex-col bg-[linear-gradient(180deg,#f7f8f2_0%,#f1f6f2_46%,#eef4f6_100%)] selection:bg-primary/15">
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[120] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
    >
      {{ t('common.skipToContent') }}
    </a>

    <!-- 背景装饰渐变 -->
    <div aria-hidden="true" class="fixed inset-0 pointer-events-none overflow-hidden">
      <div class="absolute -top-[12%] -left-[8%] h-[42%] w-[38%] rounded-full bg-[#c8dacb]/24 blur-[130px]"></div>
      <div class="absolute top-[16%] -right-[8%] h-[38%] w-[34%] rounded-full bg-[#c7dbe8]/28 blur-[120px]"></div>
      <div class="absolute -bottom-[12%] left-[16%] h-[34%] w-[30%] rounded-full bg-[#ead5b8]/20 blur-[110px]"></div>
    </div>

    <!-- Header -->
    <TheHeader class="sticky top-0 z-50 glass" />

    <transition name="mobile-nav">
      <div v-if="isMobileNavOpen" class="fixed inset-0 z-[90] md:hidden">
        <button
          type="button"
          class="absolute inset-0 bg-slate-950/25 backdrop-blur-[2px]"
          :aria-label="t('common.close')"
          @click="closeMobileNav"
        />
        <aside class="relative h-full w-72 border-r border-slate-200/60 bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(244,247,250,0.94)_100%)] p-4 shadow-2xl backdrop-blur-xl">
          <TheSidebar class="pt-16" @navigate="closeMobileNav" />
        </aside>
      </div>
    </transition>

    <div class="flex flex-grow relative z-10">
      <!-- Sidebar -->
      <aside class="hidden md:block w-64 flex-shrink-0 border-r border-slate-200/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.9)_0%,rgba(243,246,249,0.92)_100%)] backdrop-blur-sm">
        <TheSidebar class="sticky top-16 h-[calc(100vh-4rem)] p-4" />
      </aside>

      <!-- Main Content Area -->
      <main id="main-content" tabindex="-1" class="flex-grow overflow-x-hidden p-4 focus:outline-none md:p-8">
        <div class="max-w-7xl mx-auto animate-fade-in">
          <RouterView v-slot="{ Component }">
            <transition name="page" mode="out-in">
              <component :is="Component" />
            </transition>
          </RouterView>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.page-enter-active,
.page-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.mobile-nav-enter-active,
.mobile-nav-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.mobile-nav-enter-from,
.mobile-nav-leave-to {
  opacity: 0;
  transform: translateX(-12px);
}

@media (prefers-reduced-motion: reduce) {
  .page-enter-active,
  .page-leave-active,
  .mobile-nav-enter-active,
  .mobile-nav-leave-active {
    transition: none;
  }

  .page-enter-from,
  .page-leave-to,
  .mobile-nav-enter-from,
  .mobile-nav-leave-to {
    opacity: 1;
    transform: none;
  }
}
</style>
