<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { WandSparkles } from 'lucide-vue-next'
import { createTaskWithAI } from '@/api/tasks'
import { useTaskGenerationJob } from '@/composables/useTaskGenerationJob'
import { useAuth } from '@/composables/useAuth'
import type { TaskGenerateRequest } from '@/types/task.d.ts'
import { parseTaskFormDefaults } from '@/lib/taskFormQuery'
import TaskForm from '@/components/tasks/TaskForm.vue'
import TaskGenerationDialog from '@/components/tasks/TaskGenerationDialog.vue'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

const { t } = useI18n()
const { canUseAi } = useAuth()

const props = defineProps<{
  accountOptions?: { name: string; path: string }[]
  allowFixedAccount?: boolean
}>()

const emit = defineEmits<{
  (event: 'created'): void
}>()

const route = useRoute()
const isFormOpen = ref(false)
const isProgressOpen = ref(false)
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
      isFormOpen.value = false
      isProgressOpen.value = true
      beginPolling(result.job)
      isSubmitting.value = false
      return
    }
    emit('created')
    toast({ title: t('tasks.toasts.created') })
    isFormOpen.value = false
  } catch (error) {
    toast({
      title: t('tasks.toasts.createFailed'),
      description: (error as Error).message,
      variant: 'destructive',
    })
  } finally {
    if (!isProgressOpen.value) {
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
    if (route.query.create === '1') {
      isFormOpen.value = true
    }
  },
  { immediate: true }
)

watch(
  () => activeJob.value?.status,
  (status, previousStatus) => {
    if (!status || status === previousStatus) return
    if (status === 'completed') {
      isSubmitting.value = false
      emit('created')
      toast({ title: t('tasks.toasts.created') })
      isProgressOpen.value = false
      clearJob()
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
  <Dialog v-model:open="isFormOpen">
    <DialogTrigger as-child>
      <Button class="h-12 rounded-full bg-[#21160f] px-6 text-sm font-bold text-white shadow-[0_16px_36px_rgba(33,22,15,0.24)] hover:bg-[#2f2016]">
        <WandSparkles class="mr-2 h-4 w-4" />
        创建监控任务
      </Button>
    </DialogTrigger>
    <DialogContent class="max-h-[90vh] overflow-y-auto border-[#e7daca] bg-[#fffaf1] p-0 shadow-[0_36px_100px_rgba(58,39,20,0.24)] sm:max-w-[960px]">
      <div class="px-5 py-5 sm:px-6 sm:py-6">
        <DialogHeader class="space-y-3 text-left">
          <div class="inline-flex w-fit rounded-full border border-[#ddc9ae] bg-white/80 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.28em] text-[#8a6d4e]">
            CatchYu Task Studio
          </div>
          <DialogTitle class="text-[1.9rem] font-black tracking-[-0.04em] text-[#23170f]">
            创建新的抓鱼任务
          </DialogTitle>
          <p class="max-w-2xl text-sm leading-6 text-[#685542]">
            按你的目标、频率和筛选条件快速创建任务。
          </p>
        </DialogHeader>

        <div class="mt-5">
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
      </div>
    </DialogContent>
  </Dialog>

  <TaskGenerationDialog
    v-model:open="isProgressOpen"
    :job="activeJob"
  />
</template>
