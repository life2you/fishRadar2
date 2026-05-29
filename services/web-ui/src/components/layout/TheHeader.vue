<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import DashboardTaskSearch from '@/components/layout/DashboardTaskSearch.vue'
import LocaleToggle from '@/components/layout/LocaleToggle.vue'
import { useAuth } from '@/composables/useAuth'
import { 
  Shield, 
  Building2,
  Search, 
  UserCircle,
  Settings2,
  Menu,
  Layers3,
  ListTodo,
  LogOut,
  Radar,
  Clock3,
  ScrollText,
  BellRing,
} from 'lucide-vue-next'
import Badge from '@/components/ui/badge/Badge.vue'
import { useMobileNav } from '@/composables/useMobileNav'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const route = useRoute()
const { toggleMobileNav } = useMobileNav()
const { role, homePath, tenantName, username, workspaceEnabled, tenantAccessExpiresAt, logout } = useAuth()
const inactiveSearchValue = ref('')
const { t } = useI18n()

const isDashboard = computed(() => route.name === 'Dashboard' && role.value === 'admin')
const isAdmin = computed(() => role.value === 'admin')
const isTenant = computed(() => role.value === 'tenant')
const tenantTitle = computed(() => tenantName.value || username.value || t('common.unnamed'))
const tenantExpiryLabel = computed(() => {
  if (!tenantAccessExpiresAt.value || !workspaceEnabled.value) {
    return ''
  }
  const parsed = new Date(tenantAccessExpiresAt.value)
  if (Number.isNaN(parsed.getTime())) {
    return tenantAccessExpiresAt.value
  }
  return parsed.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
})
const isTenantExpirySoon = computed(() => {
  if (!tenantAccessExpiresAt.value || !workspaceEnabled.value) {
    return false
  }
  const parsed = new Date(tenantAccessExpiresAt.value)
  if (Number.isNaN(parsed.getTime())) {
    return false
  }
  return parsed.getTime() - Date.now() <= 1000 * 60 * 60 * 24
})
const tenantNavItems = computed(() => {
  if (!workspaceEnabled.value) {
    return [
      {
        to: '/activate',
        name: 'Activate',
        label: t('routes.activate'),
        icon: Radar,
      },
    ]
  }
  return [
    {
      to: '/tasks',
      name: 'Tasks',
      label: t('tenantPortal.nav.tasks'),
      icon: ListTodo,
    },
    {
      to: '/results',
      name: 'Results',
      label: t('tenantPortal.nav.results'),
      icon: Layers3,
    },
    {
      to: '/notifications',
      name: 'Notifications',
      label: t('tenantPortal.nav.notifications'),
      icon: BellRing,
    },
  ]
})
const currentRouteName = computed(() => typeof route.name === 'string' ? route.name : '')

function goAccounts() {
  router.push('/accounts')
}

function goTenants() {
  router.push('/tenants')
}

function goSettings() {
  router.push('/settings')
}

function goLogs() {
  router.push('/logs')
}

function handleLogout() {
  logout()
}
</script>

<template>
  <header
    v-if="isTenant"
    class="sticky top-0 z-[100] border-b border-[#dce9de]/90 bg-[linear-gradient(180deg,rgba(251,249,242,0.96)_0%,rgba(244,248,241,0.95)_52%,rgba(239,245,244,0.94)_100%)] backdrop-blur-xl"
  >
    <div class="mx-auto flex max-w-[1320px] flex-col gap-5 px-4 py-4 md:px-8">
      <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <RouterLink
          :to="homePath"
          class="flex items-center gap-3 rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          :aria-label="t('header.goHome')"
        >
          <div class="flex h-11 w-11 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#2a5d47_0%,#5c9a7b_55%,#8cc9bc_100%)] shadow-[0_18px_42px_rgba(76,120,97,0.24)]">
            <Radar class="h-5 w-5 text-white" />
          </div>
          <div>
            <p class="text-xs font-black uppercase tracking-[0.3em] text-[#739180]">
              CatchYu
            </p>
            <h1 class="text-lg font-black tracking-tight text-[#203228]">
              {{ tenantTitle }}
            </h1>
          </div>
        </RouterLink>

        <div class="flex flex-wrap items-center gap-2 md:justify-end">
          <div
            v-if="tenantExpiryLabel"
            class="rounded-full border px-3 py-1.5 text-xs shadow-sm"
            :class="isTenantExpirySoon
              ? 'border-[#dbe8c9] bg-[#f6fbe9] text-[#5f7a34]'
              : 'border-[#dbe6dd] bg-white/72 text-[#5f7869]'"
          >
            <span class="inline-flex items-center gap-1.5">
              <Clock3 class="h-3.5 w-3.5" />
              <span class="font-medium">{{ t('tenantPortal.expiryLabel') }}</span>
              <span class="font-semibold">{{ tenantExpiryLabel }}</span>
            </span>
          </div>
          <div class="rounded-full border border-[#dce7de] bg-white/80 px-3 py-1.5 text-xs text-[#5f7869] shadow-sm">
            <span class="font-semibold text-[#739180]">{{ t('tenantPortal.signedInAs') }}</span>
            <span class="ml-2 font-black text-[#203228]">{{ username }}</span>
          </div>
          <LocaleToggle />
          <Button
            variant="outline"
            class="rounded-full border-[#dce7de] bg-white/80 text-[#365444] hover:bg-white"
            @click="handleLogout"
          >
            <LogOut class="h-4 w-4" />
            {{ t('tenantPortal.signOut') }}
          </Button>
        </div>
      </div>

      <nav class="flex flex-wrap gap-2">
        <RouterLink
          v-for="item in tenantNavItems"
          :key="item.to"
          :to="item.to"
          class="group inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-bold transition-all"
          :class="currentRouteName === item.name
            ? 'border-[#2b5b47] bg-[#2b5b47] text-white shadow-[0_12px_30px_rgba(43,91,71,0.18)]'
            : 'border-[#dce7de] bg-white/74 text-[#5f7869] hover:border-[#c4d9cb] hover:bg-white hover:text-[#203228]'"
        >
          <component :is="item.icon" class="h-4 w-4" />
          {{ item.label }}
        </RouterLink>
      </nav>
    </div>
  </header>

  <header v-else class="flex items-center justify-between px-6 h-16 bg-white/60 backdrop-blur-md border-b border-slate-200/60 sticky top-0 z-[100]">
    <!-- Brand Logo -->
    <RouterLink
      :to="homePath"
      class="flex items-center gap-2 group rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      :aria-label="t('header.goHome')"
    >
      <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-[linear-gradient(135deg,#08111f_0%,#163256_58%,#4f7fa8_100%)] shadow-[0_14px_34px_rgba(8,17,31,0.24)] transition-transform group-hover:-rotate-6">
        <Shield class="h-5 w-5 text-white" />
      </div>
      <div class="flex flex-col">
        <span class="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">CatchYu</span>
        <h1 class="text-lg font-black tracking-tight text-slate-900">
          Console
        </h1>
      </div>
      <Badge variant="outline" class="ml-2 hidden border-slate-300 bg-slate-100/80 text-[10px] font-bold uppercase tracking-widest text-slate-600 sm:flex">
        Admin
      </Badge>
    </RouterLink>

    <!-- Search & Navigation -->
    <div class="hidden md:flex flex-grow max-w-md mx-8">
      <DashboardTaskSearch v-if="isDashboard" />
      <div v-else class="relative w-full group">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 transition-colors" />
        <input 
          type="text" 
          v-model="inactiveSearchValue"
          readonly
          aria-disabled="true"
          :placeholder="t('header.searchUnavailable')"
          class="w-full h-10 pl-10 pr-4 bg-slate-100/50 border border-slate-200/50 rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 focus:bg-white focus:border-primary/50"
        />
        <kbd class="absolute right-3 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded border border-slate-300 bg-white text-[10px] text-slate-400 font-sans shadow-sm pointer-events-none">
          /
        </kbd>
      </div>
    </div>

    <!-- Actions -->
    <div class="flex items-center gap-3">
      <div class="flex items-center gap-2">
        <LocaleToggle />
      </div>

      <div v-if="isAdmin" class="flex items-center gap-1 sm:gap-2">
         <Button
           variant="ghost"
           size="icon"
           class="rounded-full text-slate-500 hover:bg-slate-900/10 hover:text-slate-900"
           :aria-label="t('header.openTenants')"
           @click="goTenants"
         >
            <Building2 class="w-5 h-5" />
         </Button>
         <Button
           variant="ghost"
           size="icon"
           class="rounded-full text-slate-500 hover:bg-slate-900/10 hover:text-slate-900"
           :aria-label="t('header.openLogs')"
           @click="goLogs"
         >
            <ScrollText class="w-5 h-5" />
         </Button>
         <Button
           variant="ghost"
           size="icon"
           class="rounded-full text-slate-500 hover:bg-slate-900/10 hover:text-slate-900"
           :aria-label="t('header.openSettings')"
           @click="goSettings"
         >
            <Settings2 class="w-5 h-5" />
         </Button>
         <Button
           variant="ghost"
           size="icon"
           class="rounded-full text-slate-500 hover:bg-slate-900/10 hover:text-slate-900"
           :aria-label="t('header.signOut')"
           @click="handleLogout"
         >
            <LogOut class="w-5 h-5" />
         </Button>
      </div>
      
      <div v-if="isAdmin" class="h-6 w-px bg-slate-200 mx-1 hidden sm:block"></div>

      <Button 
        v-if="isAdmin"
        variant="ghost" 
        class="hidden sm:flex items-center gap-2 pl-2 pr-4 rounded-full hover:bg-slate-100 transition-all active:scale-95"
        :aria-label="t('header.openAccounts')"
        @click="goAccounts"
      >
        <div class="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full border border-slate-300 bg-slate-200 shadow-sm">
           <UserCircle class="w-6 h-6 text-slate-500" />
        </div>
        <div class="text-left hidden lg:block">
           <p class="mb-0.5 text-xs font-black leading-none text-slate-700">CatchYu Admin</p>
           <p class="text-[10px] text-slate-400 font-medium">{{ t('header.accountManagement') }}</p>
        </div>
      </Button>

      <Button
        variant="ghost"
        size="icon"
        class="md:hidden"
        :aria-label="t('header.openNavigation')"
        @click="toggleMobileNav"
      >
         <Menu class="w-6 h-6 text-slate-700" />
      </Button>
    </div>
  </header>
</template>
