<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuth } from '@/composables/useAuth'
import LocaleToggle from '@/components/layout/LocaleToggle.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useI18n } from 'vue-i18n'

const loginUsername = ref('')
const loginPassword = ref('')
const registerTenantName = ref('')
const registerDisplayName = ref('')
const registerUsername = ref('')
const registerPassword = ref('')
const registerPasswordConfirm = ref('')
const isLoading = ref(false)
const error = ref('')
const activeTab = ref<'login' | 'register'>('login')

const { login, register } = useAuth()
const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const loginCardTitle = computed(() => (
  activeTab.value === 'login' ? t('login.title') : t('login.registerTitle')
))

watch(activeTab, () => {
  error.value = ''
})

function redirectAfterAuth() {
  const redirectPath = (route.query.redirect as string) || '/'
  router.push(redirectPath)
}

async function handleLogin() {
  if (!loginUsername.value || !loginPassword.value) {
    error.value = t('login.errors.missingCredentials')
    return
  }

  isLoading.value = true
  error.value = ''

  try {
    const success = await login(loginUsername.value, loginPassword.value)
    if (success) {
      redirectAfterAuth()
    } else {
      error.value = t('login.errors.invalidCredentials')
    }
  } catch (_error) {
    error.value = t('login.errors.unexpected')
  } finally {
    isLoading.value = false
  }
}

async function handleRegister() {
  if (!registerTenantName.value || !registerUsername.value || !registerPassword.value) {
    error.value = t('login.errors.registerRequired')
    return
  }
  if (registerPassword.value.length < 6) {
    error.value = t('login.errors.passwordTooShort')
    return
  }
  if (registerPassword.value !== registerPasswordConfirm.value) {
    error.value = t('login.errors.passwordMismatch')
    return
  }

  isLoading.value = true
  error.value = ''

  try {
    await register({
      tenant_name: registerTenantName.value.trim(),
      display_name: registerDisplayName.value.trim(),
      username: registerUsername.value.trim(),
      password: registerPassword.value,
    })
    router.push('/activate')
  } catch (err) {
    error.value = (err as Error).message || t('login.errors.registerFailed')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 px-4 py-8 selection:bg-emerald-500/20">
    <div aria-hidden="true" class="absolute inset-0 pointer-events-none">
      <div class="absolute left-[-5%] top-[-10%] h-96 w-96 rounded-full bg-emerald-500/5 blur-3xl"></div>
      <div class="absolute bottom-[-15%] right-[-5%] h-[30rem] w-[30rem] rounded-full bg-cyan-500/5 blur-3xl"></div>
      <div class="absolute bottom-[5%] left-[20%] h-80 w-80 rounded-full bg-indigo-500/5 blur-3xl"></div>
      <div class="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(16,185,129,0.06),transparent_60%)]"></div>
    </div>

    <div class="absolute right-6 top-6">
      <LocaleToggle />
    </div>

    <div class="relative z-10 grid w-full max-w-6xl gap-5 lg:grid-cols-[1.02fr_0.98fr]">
      <section class="rounded-[30px] border border-emerald-500/10 bg-slate-900/40 backdrop-blur-md p-6 shadow-glass lg:p-8 hover:border-emerald-500/20 transition-all duration-300">
        <p class="text-[11px] font-bold uppercase tracking-[0.3em] text-emerald-400">{{ t('login.brandEyebrow') }}</p>
        <h1 class="mt-4 text-3xl font-black tracking-[-0.05em] text-slate-100 lg:text-[2.9rem] leading-[1.1]">{{ t('login.heroTitle') }}</h1>
        <p class="mt-4 max-w-2xl text-sm leading-6 text-slate-300/80">
          {{ t('login.heroDescription') }}
        </p>

        <div class="mt-6 grid gap-3 md:grid-cols-3">
          <article class="rounded-[20px] border border-slate-900/60 bg-slate-950/60 p-3.5 shadow-sm hover:border-emerald-500/15 transition-all duration-200">
            <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-emerald-400/80">{{ t('login.cards.register') }}</p>
            <p class="mt-2.5 text-base font-bold text-slate-100">{{ t('login.cards.registerTitle') }}</p>
            <p class="mt-1.5 text-sm leading-5 text-slate-400">{{ t('login.cards.registerDescription') }}</p>
          </article>
          <article class="rounded-[20px] border border-slate-900/60 bg-slate-950/60 p-3.5 shadow-sm hover:border-emerald-500/15 transition-all duration-200">
            <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-emerald-400/80">{{ t('login.cards.activate') }}</p>
            <p class="mt-2.5 text-base font-bold text-slate-100">{{ t('login.cards.activateTitle') }}</p>
            <p class="mt-1.5 text-sm leading-5 text-slate-400">{{ t('login.cards.activateDescription') }}</p>
          </article>
          <article class="rounded-[20px] border border-slate-900/60 bg-slate-950/60 p-3.5 shadow-sm hover:border-emerald-500/15 transition-all duration-200">
            <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-emerald-400/80">{{ t('login.cards.workspace') }}</p>
            <p class="mt-2.5 text-base font-bold text-slate-100">{{ t('login.cards.workspaceTitle') }}</p>
            <p class="mt-1.5 text-sm leading-5 text-slate-400">{{ t('login.cards.workspaceDescription') }}</p>
          </article>
        </div>
      </section>

      <Card class="border border-emerald-500/10 bg-slate-900/30 backdrop-blur-md shadow-glass">
        <CardHeader>
          <CardTitle class="text-2xl text-center text-slate-100 font-bold tracking-tight">{{ loginCardTitle }}</CardTitle>
          <CardDescription class="text-center text-slate-400">
            {{ activeTab === 'login' ? t('login.description') : t('login.registerDescription') }}
          </CardDescription>
        </CardHeader>

        <CardContent class="space-y-4">
          <Tabs v-model="activeTab" class="w-full">
            <TabsList class="grid h-11 w-full grid-cols-2 rounded-full bg-slate-950/60 border border-slate-900 p-1">
              <TabsTrigger value="login" class="rounded-full data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">{{ t('login.tabs.login') }}</TabsTrigger>
              <TabsTrigger value="register" class="rounded-full data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">{{ t('login.tabs.register') }}</TabsTrigger>
            </TabsList>

            <TabsContent value="login" class="mt-5">
              <form class="space-y-4" @submit.prevent="handleLogin">
                <div class="grid gap-2">
                  <Label for="username" class="text-slate-300">{{ t('login.username') }}</Label>
                  <Input id="username" v-model="loginUsername" type="text" placeholder="admin" required class="bg-slate-950/60 border-slate-900 text-slate-100 focus-visible:ring-emerald-500" />
                </div>
                <div class="grid gap-2">
                  <Label for="password" class="text-slate-300">{{ t('login.password') }}</Label>
                  <Input id="password" v-model="loginPassword" type="password" required class="bg-slate-950/60 border-slate-900 text-slate-100 focus-visible:ring-emerald-500" />
                </div>
                <Button class="h-11 w-full rounded-full bg-emerald-500 text-slate-950 font-bold hover:bg-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)] hover:shadow-[0_0_25px_rgba(16,185,129,0.4)] transition-all duration-300" type="submit" :disabled="isLoading">
                  {{ isLoading ? t('login.submitting') : t('login.submit') }}
                </Button>
              </form>
            </TabsContent>

            <TabsContent value="register" class="mt-5">
              <form class="space-y-4" @submit.prevent="handleRegister">
                <div class="grid gap-2">
                  <Label for="tenant-name" class="text-slate-300">{{ t('login.tenantName') }}</Label>
                  <Input id="tenant-name" v-model="registerTenantName" type="text" :placeholder="t('login.tenantNamePlaceholder')" required class="bg-slate-950/60 border-slate-900 text-slate-100 focus-visible:ring-emerald-500" />
                </div>
                <div class="grid gap-2">
                  <Label for="display-name" class="text-slate-300">{{ t('login.displayName') }}</Label>
                  <Input id="display-name" v-model="registerDisplayName" type="text" :placeholder="t('login.displayNamePlaceholder')" class="bg-slate-950/60 border-slate-900 text-slate-100 focus-visible:ring-emerald-500" />
                </div>
                <div class="grid gap-2">
                  <Label for="register-username" class="text-slate-300">{{ t('login.username') }}</Label>
                  <Input id="register-username" v-model="registerUsername" type="text" :placeholder="t('login.usernamePlaceholder')" required class="bg-slate-950/60 border-slate-900 text-slate-100 focus-visible:ring-emerald-500" />
                </div>
                <div class="grid gap-2">
                  <Label for="register-password" class="text-slate-300">{{ t('login.password') }}</Label>
                  <Input id="register-password" v-model="registerPassword" type="password" required class="bg-slate-950/60 border-slate-900 text-slate-100 focus-visible:ring-emerald-500" />
                </div>
                <div class="grid gap-2">
                  <Label for="register-password-confirm" class="text-slate-300">{{ t('login.passwordConfirm') }}</Label>
                  <Input id="register-password-confirm" v-model="registerPasswordConfirm" type="password" required class="bg-slate-950/60 border-slate-900 text-slate-100 focus-visible:ring-emerald-500" />
                </div>
                <Button class="h-11 w-full rounded-full bg-emerald-500 text-slate-950 font-bold hover:bg-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)] hover:shadow-[0_0_25px_rgba(16,185,129,0.4)] transition-all duration-300" type="submit" :disabled="isLoading">
                  {{ isLoading ? t('login.registerSubmitting') : t('login.registerSubmit') }}
                </Button>
              </form>
            </TabsContent>
          </Tabs>

          <div v-if="error" class="rounded-2xl border border-red-950 bg-red-950/30 px-4 py-3 text-sm font-medium text-red-300 backdrop-blur-sm" role="alert">
            {{ error }}
          </div>
        </CardContent>

        <CardFooter class="justify-center text-center text-xs leading-6 text-slate-500">
          {{ activeTab === 'login' ? t('login.footer') : t('login.registerFooter') }}
        </CardFooter>
      </Card>
    </div>
  </div>
</template>
