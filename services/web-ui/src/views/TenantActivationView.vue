<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from '@/composables/useAuth'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/components/ui/toast'

const router = useRouter()
const { t } = useI18n()
const {
  tenantName,
  displayName,
  workspaceEnabled,
  redeemActivationCode,
  canUseAi,
  tenantAccessExpiresAt,
  tenantAccessExpired,
} = useAuth()

const code = ref('')
const isSubmitting = ref(false)
const error = ref('')

const tenantTitle = computed(() => tenantName.value || displayName.value || t('common.unnamed'))
const accessExpiryText = computed(() => {
  if (!tenantAccessExpiresAt.value) {
    return t('activation.noExpiry')
  }
  const parsed = new Date(tenantAccessExpiresAt.value)
  if (Number.isNaN(parsed.getTime())) {
    return tenantAccessExpiresAt.value
  }
  return parsed.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
})

async function handleActivate() {
  if (!code.value.trim()) {
    error.value = t('activation.errors.codeRequired')
    return
  }
  isSubmitting.value = true
  error.value = ''
  try {
    await redeemActivationCode(code.value.trim())
    toast({ title: t('activation.successTitle'), description: t('activation.successDescription') })
    router.push('/tasks')
  } catch (err) {
    error.value = (err as Error).message || t('activation.errors.unexpected')
  } finally {
    isSubmitting.value = false
  }
}

function enterWorkspace() {
  router.push('/tasks')
}
</script>

<template>
  <div class="mx-auto max-w-4xl space-y-5">
    <section class="overflow-hidden rounded-[24px] border border-[#cfddd5] bg-[linear-gradient(135deg,#f6faf6_0%,#edf4ef_46%,#e9f2f4_100%)] p-4.5 shadow-[0_14px_34px_rgba(76,104,84,0.09)] md:p-5">
      <p class="text-[10px] font-bold uppercase tracking-[0.24em] text-[#72907f]">{{ t('activation.eyebrow') }}</p>
      <h1 class="mt-2 text-[1.65rem] font-black tracking-[-0.04em] text-[#203228] md:text-[1.95rem]">
        {{ t('activation.title', { tenant: tenantTitle }) }}
      </h1>
      <p class="mt-1.5 max-w-[34rem] text-[13px] leading-6 text-[#597264]">
        {{ workspaceEnabled ? t('activation.activeDescription') : (tenantAccessExpired ? t('activation.expiredDescription') : t('activation.description')) }}
      </p>

      <div class="mt-3.5 grid gap-2 md:grid-cols-3">
        <article class="rounded-[15px] border border-[#d7e2db] bg-white/92 px-3 py-2.5 shadow-sm">
          <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-[#7b9688]">{{ t('activation.cards.registered') }}</p>
          <p class="mt-1 text-[15px] font-bold text-[#203228]">{{ tenantTitle }}</p>
          <p class="mt-0.5 text-[12px] leading-5 text-[#5f796b]">{{ t('activation.cards.registeredHint') }}</p>
        </article>
        <article class="rounded-[15px] border border-[#d7e2db] bg-white/92 px-3 py-2.5 shadow-sm">
          <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-[#7b9688]">{{ t('activation.cards.workspace') }}</p>
          <p class="mt-1 text-[15px] font-bold text-[#203228]">{{ workspaceEnabled ? t('activation.workspaceReady') : t('activation.workspacePending') }}</p>
          <p class="mt-0.5 text-[12px] leading-5 text-[#5f796b]">
            {{ tenantAccessExpired ? t('activation.cards.workspaceExpiredHint') : t('activation.cards.workspaceHint') }}
          </p>
          <p class="mt-0.5 text-[11px] text-[#7d9789]">
            {{ t('activation.expiryAt', { value: accessExpiryText }) }}
          </p>
        </article>
        <article class="rounded-[15px] border border-[#d7e2db] bg-white/92 px-3 py-2.5 shadow-sm">
          <p class="text-[10px] font-bold uppercase tracking-[0.2em] text-[#7b9688]">{{ t('activation.cards.ai') }}</p>
          <p class="mt-1 text-[15px] font-bold text-[#203228]">{{ canUseAi ? t('activation.aiReady') : t('activation.aiPending') }}</p>
          <p class="mt-0.5 text-[12px] leading-5 text-[#5f796b]">{{ t('activation.cards.aiHint') }}</p>
        </article>
      </div>
    </section>

    <Card class="border-[#d8e6da] bg-white/90 shadow-[0_18px_52px_rgba(76,104,84,0.08)]">
      <CardHeader>
        <CardTitle>{{ t('activation.formTitle') }}</CardTitle>
        <CardDescription>{{ workspaceEnabled ? t('activation.formReadyDescription') : t('activation.formDescription') }}</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <template v-if="!workspaceEnabled">
          <div class="grid gap-2">
            <Label for="activation-code">{{ t('activation.codeLabel') }}</Label>
            <Input
              id="activation-code"
              v-model="code"
              class="h-12 rounded-2xl border-[#d6e6db] bg-[#fbfefb] uppercase tracking-[0.18em]"
              :placeholder="t('activation.codePlaceholder')"
            />
          </div>
          <div v-if="error" class="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ error }}
          </div>
          <div v-if="tenantAccessExpired" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            {{ t('activation.expiredNotice') }}
          </div>
          <Button
            class="h-12 rounded-full bg-[#2b5b47] px-6 text-white hover:bg-[#244d3d]"
            :disabled="isSubmitting"
            @click="handleActivate"
          >
            {{ isSubmitting ? t('activation.submitting') : t('activation.submit') }}
          </Button>
        </template>

        <template v-else>
          <div class="rounded-[20px] border border-[#d8e5d8] bg-[#edf7ef] px-4 py-4 text-sm leading-6 text-[#35523d]">
            {{ t('activation.readyNotice') }}
          </div>
          <Button class="h-12 rounded-full bg-[#2b5b47] px-6 text-white hover:bg-[#244d3d]" @click="enterWorkspace">
            {{ t('activation.enterWorkspace') }}
          </Button>
        </template>
      </CardContent>
    </Card>
  </div>
</template>
