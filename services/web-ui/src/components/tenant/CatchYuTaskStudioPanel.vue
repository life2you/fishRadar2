<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Sparkles } from 'lucide-vue-next'
import { createTaskWithAI } from '@/api/tasks'
import { useTaskGenerationJob } from '@/composables/useTaskGenerationJob'
import { useAuth } from '@/composables/useAuth'
import type { TaskGenerateRequest } from '@/types/task.d.ts'
import { parseTaskFormDefaults } from '@/lib/taskFormQuery'
import TaskForm from '@/components/tasks/TaskForm.vue'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'

const props = defineProps<{
  accountOptions?: { name: string; path: string }[]
  allowFixedAccount?: boolean
}>()

const emit = defineEmits<{
  (event: 'created'): void
  (event: 'cancel'): void
}>()

const { t } = useI18n()
const route = useRoute()
const { canUseAi } = useAuth()
const isSubmitting = ref(false)
const defaultAccountPath = ref('')
const defaultValues = ref({})

const {
  activeJob,
  pollingError,
  beginPolling,
  clearJob,
} = useTaskGenerationJob()

function resolveAccountPath(accountName: string) {
  const match = (props.accountOptions || []).find((account) => account.name === accountName)
  return match ? match.path : ''
}

async function handleCreateTask(data: TaskGenerateRequest) {
  isSubmitting.value = true
  clearJob()
  try {
    const result = await createTaskWithAI(data)
    if (result.job) {
      beginPolling(result.job)
      return
    }
    toast({ title: t('tasks.toasts.created') })
    emit('created')
  } catch (error) {
    toast({
      title: t('tasks.toasts.createFailed'),
      description: (error as Error).message,
      variant: 'destructive',
    })
  } finally {
    if (!activeJob.value || activeJob.value.status === 'completed' || activeJob.value.status === 'failed') {
      isSubmitting.value = false
    }
  }
}

watch(
  () => [route.query, props.accountOptions],
  () => {
    const accountName = typeof route.query.account === 'string' ? route.query.account : ''
    defaultAccountPath.value = accountName ? resolveAccountPath(accountName) : ''
    defaultValues.value = parseTaskFormDefaults(route.query)
  },
  { immediate: true }
)

watch(
  () => activeJob.value?.status,
  (status, previousStatus) => {
    if (!status || status === previousStatus) return
    if (status === 'completed') {
      isSubmitting.value = false
      toast({ title: t('tasks.toasts.created') })
      clearJob()
      emit('created')
      return
    }
    if (status === 'failed') {
      isSubmitting.value = false
      toast({
        title: t('tasks.toasts.createFailed'),
        description: activeJob.value?.error || activeJob.value?.message,
        variant: 'destructive',
      })
    }
  }
)

watch(pollingError, (value) => {
  if (!value) return
  isSubmitting.value = false
  toast({
    title: t('tasks.toasts.progressFailed'),
    description: value.message,
    variant: 'destructive',
  })
})
</script>

<template>
  <section class="rounded-[34px] border border-[#eadfce] bg-[linear-gradient(180deg,rgba(255,250,242,0.98)_0%,rgba(249,242,232,0.98)_100%)] p-5 shadow-[0_28px_70px_rgba(77,56,35,0.10)] md:p-6">
    <div class="flex flex-col gap-4 border-b border-[#eadbc8] pb-5 md:flex-row md:items-start md:justify-between">
      <div>
        <div class="inline-flex items-center gap-2 rounded-full border border-[#ddc9ae] bg-white/80 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.26em] text-[#8a6d4e]">
          <Sparkles class="h-3.5 w-3.5 text-[#c6582e]" />
          CatchYu Task Studio
        </div>
        <h2 class="mt-4 text-3xl font-black tracking-[-0.04em] text-[#241a12]">创建新的抓鱼任务</h2>
        <p class="mt-3 max-w-3xl text-sm leading-7 text-[#685542]">
          在 CatchYu 里先定目标，再选模式、频率和筛选策略，最后直接发布任务。
        </p>
      </div>
      <Button
        variant="outline"
        class="rounded-full border-[#dfd2c1] bg-white/82 px-5 text-[#473122] hover:bg-white"
        @click="emit('cancel')"
      >
        收起创建器
      </Button>
    </div>

    <div class="mt-6 space-y-5">
      <div v-if="activeJob" class="rounded-[28px] border border-[#d6e1d8] bg-[#edf6ef] p-5">
        <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p class="text-[11px] font-bold uppercase tracking-[0.24em] text-[#5f806b]">AI 生成进度</p>
            <h3 class="mt-3 text-xl font-black tracking-[-0.03em] text-[#21402f]">{{ activeJob.task_name }}</h3>
            <p class="mt-2 text-sm leading-6 text-[#3e5d4c]">{{ activeJob.message }}</p>
          </div>
          <div class="rounded-full border border-[#c5d6c9] bg-white/75 px-4 py-2 text-sm font-bold text-[#2f5b42]">
            {{ activeJob.status }}
          </div>
        </div>
        <div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <article
            v-for="step in activeJob.steps"
            :key="step.key"
            class="rounded-[22px] border border-white/90 bg-white/78 p-4 shadow-sm"
          >
            <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-[#75927f]">{{ step.status }}</p>
            <p class="mt-2 text-sm font-bold text-[#21402f]">{{ step.label }}</p>
            <p class="mt-2 text-xs leading-5 text-[#476755]">{{ step.message }}</p>
          </article>
        </div>
      </div>

      <TaskForm
        mode="create"
        variant="tenant"
        submit-label="发布 CatchYu 任务"
        :is-submitting="isSubmitting"
        :allow-ai-mode="canUseAi"
        :account-options="accountOptions"
        :allow-fixed-account="allowFixedAccount"
        :default-account="defaultAccountPath"
        :default-values="defaultValues"
        @submit="(data) => handleCreateTask(data as TaskGenerateRequest)"
      />
    </div>
  </section>
</template>
