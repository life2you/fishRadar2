<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from '@/composables/useAuth'
import { useTasks } from '@/composables/useTasks'
import type { Task, TaskUpdate } from '@/types/task.d.ts'
import { parseTaskFormDefaults } from '@/lib/taskFormQuery'
import TaskCreateDialog from '@/components/tasks/TaskCreateDialog.vue'
import TasksTable from '@/components/tasks/TasksTable.vue'
import TaskForm from '@/components/tasks/TaskForm.vue'
import TenantPortalHero from '@/components/tenant/TenantPortalHero.vue'
import CatchYuTaskCard from '@/components/tenant/CatchYuTaskCard.vue'
import CatchYuTaskStudioDialog from '@/components/tenant/CatchYuTaskStudioDialog.vue'
import { listAccounts, type AccountItem } from '@/api/accounts'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toast'
import { RefreshCw } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
const { t } = useI18n()
const { role, tenantName, username, canUseAi } = useAuth()

const {
  tasks,
  isLoading,
  error,
  fetchTasks,
  removeTask,
  updateTask,
  startTask,
  stopTask,
  stoppingTaskIds,
} = useTasks()
const route = useRoute()

// State for dialogs
const isEditDialogOpen = ref(false)
const isCriteriaDialogOpen = ref(false)
const isEditSubmitting = ref(false)
const selectedTask = ref<Task | null>(null)
const criteriaTask = ref<Task | null>(null)
const criteriaDescription = ref('')
const isCriteriaSubmitting = ref(false)
const isDeleteDialogOpen = ref(false)
const taskToDeleteId = ref<number | null>(null)
const accountOptions = ref<AccountItem[]>([])
const tenantTaskFilter = ref<'all' | 'running' | 'paused' | 'ai' | 'keyword'>('all')
const tenantTaskPage = ref(1)
const TENANT_TASK_PAGE_SIZE = 6
const canManageFixedAccounts = computed(() => role.value === 'admin')
const isTenantPortal = computed(() => role.value === 'tenant')
const tenantWorkspaceName = computed(() => tenantName.value || username.value || t('common.unnamed'))
const adminTenantScopeLabel = computed(() => {
  if (role.value !== 'admin') return null
  const raw = route.query.tenant_id
  return typeof raw === 'string' ? raw : null
})
const tenantTaskStats = computed(() => {
  const enabledCount = tasks.value.filter((task) => task.enabled).length
  const runningCount = tasks.value.filter((task) => task.is_running).length
  const scheduledCount = tasks.value.filter((task) => Boolean(task.cron)).length
  return [
    {
      label: t('tenantPortal.tasks.stats.enabled'),
      value: String(enabledCount),
      detail: undefined,
    },
    {
      label: t('tenantPortal.tasks.stats.running'),
      value: String(runningCount),
      detail: undefined,
    },
    {
      label: t('tenantPortal.tasks.stats.scheduled'),
      value: String(scheduledCount),
      detail: undefined,
    },
  ]
})
const tenantTaskFilterOptions = computed(() => [
  { value: 'all', label: '全部', count: tasks.value.length },
  { value: 'running', label: '运行中', count: tasks.value.filter((task) => task.is_running).length },
  { value: 'paused', label: '已暂停', count: tasks.value.filter((task) => !task.enabled).length },
  { value: 'ai', label: 'AI', count: tasks.value.filter((task) => task.decision_mode === 'ai').length },
  { value: 'keyword', label: '关键词', count: tasks.value.filter((task) => task.decision_mode === 'keyword').length },
])
const filteredTenantTasks = computed(() => {
  switch (tenantTaskFilter.value) {
    case 'running':
      return tasks.value.filter((task) => task.is_running)
    case 'paused':
      return tasks.value.filter((task) => !task.enabled)
    case 'ai':
      return tasks.value.filter((task) => task.decision_mode === 'ai')
    case 'keyword':
      return tasks.value.filter((task) => task.decision_mode === 'keyword')
    default:
      return tasks.value
  }
})
const tenantTaskTotalPages = computed(() => Math.max(1, Math.ceil(filteredTenantTasks.value.length / TENANT_TASK_PAGE_SIZE)))
const pagedTenantTasks = computed(() => {
  const start = (tenantTaskPage.value - 1) * TENANT_TASK_PAGE_SIZE
  return filteredTenantTasks.value.slice(start, start + TENANT_TASK_PAGE_SIZE)
})
const tenantTaskPageSummary = computed(() => {
  if (!filteredTenantTasks.value.length) return '当前筛选下没有任务'
  const start = (tenantTaskPage.value - 1) * TENANT_TASK_PAGE_SIZE + 1
  const end = Math.min(tenantTaskPage.value * TENANT_TASK_PAGE_SIZE, filteredTenantTasks.value.length)
  return `显示 ${start}-${end} / 共 ${filteredTenantTasks.value.length} 个任务`
})

const taskToDelete = computed(() => {
  if (taskToDeleteId.value === null) return null
  return tasks.value.find((task) => task.id === taskToDeleteId.value) || null
})
const editDefaults = computed(() => parseTaskFormDefaults(route.query))

function handleDeleteTask(taskId: number) {
  taskToDeleteId.value = taskId
  isDeleteDialogOpen.value = true
}

async function handleConfirmDeleteTask() {
  if (!taskToDelete.value) {
    toast({ title: t('tasks.toasts.notFound'), variant: 'destructive' })
    isDeleteDialogOpen.value = false
    return
  }
  try {
    await removeTask(taskToDelete.value.id)
    toast({ title: t('tasks.toasts.deleted') })
  } catch (e) {
    toast({
      title: t('tasks.toasts.deleteFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    isDeleteDialogOpen.value = false
    taskToDeleteId.value = null
  }
}

function handleEditTask(task: Task) {
  selectedTask.value = task
  isEditDialogOpen.value = true
}

watch(
  () => [route.query.edit, tasks.value],
  () => {
    const editTaskId = typeof route.query.edit === 'string' ? Number(route.query.edit) : NaN
    if (!Number.isFinite(editTaskId)) return
    const match = tasks.value.find((task) => task.id === editTaskId)
    if (!match) return
    selectedTask.value = match
    isEditDialogOpen.value = true
  },
  { immediate: true }
)

watch(tenantTaskFilter, () => {
  tenantTaskPage.value = 1
})

watch(tenantTaskTotalPages, (totalPages) => {
  if (tenantTaskPage.value > totalPages) {
    tenantTaskPage.value = totalPages
  }
})

async function handleUpdateTask(data: TaskUpdate) {
  if (!selectedTask.value) return
  isEditSubmitting.value = true
  try {
    await updateTask(selectedTask.value.id, data)
    isEditDialogOpen.value = false
  }
  catch (e) {
    toast({
      title: t('tasks.toasts.updateFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  }
  finally {
    isEditSubmitting.value = false
  }
}

function handleOpenCriteriaDialog(task: Task) {
  criteriaTask.value = task
  criteriaDescription.value = task.description || ''
  isCriteriaDialogOpen.value = true
}

async function handleRefreshCriteria() {
  if (!criteriaTask.value) return
  if (!criteriaDescription.value.trim()) {
    toast({
      title: t('tasks.toasts.descriptionRequired'),
      description: t('tasks.criteria.descriptionRequired'),
      variant: 'destructive',
    })
    return
  }

  isCriteriaSubmitting.value = true
  try {
    await updateTask(criteriaTask.value.id, { description: criteriaDescription.value })
    isCriteriaDialogOpen.value = false
  } catch (e) {
    toast({
      title: t('tasks.toasts.regenerateFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    isCriteriaSubmitting.value = false
  }
}

async function handleStartTask(taskId: number) {
  try {
    await startTask(taskId)
  } catch (e) {
    toast({
      title: t('tasks.toasts.startFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  }
}

async function handleStopTask(taskId: number) {
  try {
    await stopTask(taskId)
  } catch (e) {
    toast({
      title: t('tasks.toasts.stopFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  }
}

async function handleToggleEnabled(task: Task, enabled: boolean) {
  const previous = task.enabled
  task.enabled = enabled
  try {
    await updateTask(task.id, { enabled })
  } catch (e) {
    task.enabled = previous
    toast({
      title: t('tasks.toasts.toggleFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  }
}

async function fetchAccountOptions() {
  if (!canManageFixedAccounts.value) {
    accountOptions.value = []
    return
  }
  try {
    accountOptions.value = await listAccounts()
  } catch (e) {
    toast({
      title: t('tasks.toasts.loadAccountsFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  }
}

onMounted(fetchAccountOptions)
</script>

<template>
  <div>
    <div v-if="isTenantPortal" class="space-y-6">
      <TenantPortalHero
        :eyebrow="t('tenantPortal.eyebrow')"
        :title="t('tenantPortal.tasks.title', { tenant: tenantWorkspaceName })"
        :description="t('tenantPortal.tasks.description')"
        :stats="tenantTaskStats"
      >
        <template #actions>
          <CatchYuTaskStudioDialog
            :account-options="accountOptions"
            :allow-fixed-account="canManageFixedAccounts"
            @created="fetchTasks"
          />
          <Button
            variant="outline"
            class="h-10 rounded-full border-[#d4dfd5] bg-white/88 px-4 text-[13px] text-[#446050] hover:bg-white"
            :disabled="isLoading"
            @click="fetchTasks"
          >
            <RefreshCw class="mr-1.5 h-3.5 w-3.5" />
            刷新任务
          </Button>
        </template>
      </TenantPortalHero>

      <section class="space-y-4">
        <div v-if="error" class="app-alert-error" role="alert">
          <strong class="font-bold">{{ t('common.error') }}</strong>
          <span class="block sm:inline">{{ error.message }}</span>
        </div>

        <div v-if="isLoading" class="rounded-[28px] border border-dashed border-[#dccfbf] bg-[#fffaf2] px-6 py-12 text-center text-sm text-[#7b6956]">
          {{ t('common.loading') }}
        </div>

        <div v-else-if="tasks.length === 0" class="rounded-[28px] border border-dashed border-[#dccfbf] bg-[#fffaf2] px-6 py-14 text-center">
          <p class="text-lg font-bold text-[#4a3627]">还没有 CatchYu 任务</p>
          <p class="mt-2 text-sm text-[#7b6956]">先创建一个监控任务，再回来统一管理启动、编辑和结果追踪。</p>
        </div>

        <div v-else class="space-y-4">
          <section class="rounded-[24px] border border-[#eadfce] bg-white/88 p-4 shadow-sm">
            <div class="flex flex-wrap gap-2">
              <button
                v-for="option in tenantTaskFilterOptions"
                :key="option.value"
                type="button"
                class="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition-colors"
                :class="tenantTaskFilter === option.value
                  ? 'border-[#244735] bg-[#244735] text-white'
                  : 'border-[#e1d4c1] bg-[#fffaf2] text-[#6a5744] hover:bg-white'"
                @click="tenantTaskFilter = option.value as typeof tenantTaskFilter"
              >
                <span>{{ option.label }}</span>
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-bold"
                  :class="tenantTaskFilter === option.value ? 'bg-white/18 text-white' : 'bg-white text-[#8a6a4f]'"
                >
                  {{ option.count }}
                </span>
              </button>
            </div>
          </section>

          <div
            v-if="filteredTenantTasks.length === 0"
            class="rounded-[28px] border border-dashed border-[#dccfbf] bg-[#fffaf2] px-6 py-12 text-center"
          >
            <p class="text-base font-bold text-[#4a3627]">当前筛选下没有任务</p>
            <p class="mt-2 text-sm text-[#7b6956]">可以切换筛选条件，或者新建一个任务。</p>
          </div>

          <CatchYuTaskCard
            v-for="task in pagedTenantTasks"
            :key="task.id"
            :task="task"
            :is-stopping="stoppingTaskIds.has(task.id)"
            @delete="handleDeleteTask"
            @edit="handleEditTask"
            @run="handleStartTask"
            @stop="handleStopTask"
            @toggle-enabled="({ task, enabled }) => handleToggleEnabled(task, enabled)"
          />

          <div
            v-if="filteredTenantTasks.length > TENANT_TASK_PAGE_SIZE"
            class="flex flex-col gap-3 rounded-[24px] border border-[#eadfce] bg-[#fffaf2] px-4 py-3 text-sm text-[#6a5744] md:flex-row md:items-center md:justify-between"
          >
            <span>{{ tenantTaskPageSummary }}</span>
            <div class="flex items-center gap-2">
              <Button
                variant="outline"
                class="rounded-full border-[#ddcfbc] bg-white/80 px-4 text-[#473122] hover:bg-white"
                :disabled="tenantTaskPage <= 1"
                @click="tenantTaskPage -= 1"
              >
                上一页
              </Button>
              <span class="text-xs font-semibold text-[#8a6a4f]">第 {{ tenantTaskPage }} / {{ tenantTaskTotalPages }} 页</span>
              <Button
                variant="outline"
                class="rounded-full border-[#ddcfbc] bg-white/80 px-4 text-[#473122] hover:bg-white"
                :disabled="tenantTaskPage >= tenantTaskTotalPages"
                @click="tenantTaskPage += 1"
              >
                下一页
              </Button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <template v-else>
      <div class="mb-6 flex justify-between items-center">
        <div>
          <h1 class="text-2xl font-bold text-gray-800">
            {{ t('tasks.title') }}
          </h1>
          <p v-if="adminTenantScopeLabel" class="mt-1 text-sm text-sky-700">
            {{ t('tenantDetail.scopeHint', { id: adminTenantScopeLabel }) }}
          </p>
        </div>
        <TaskCreateDialog
          :account-options="accountOptions"
          :allow-fixed-account="canManageFixedAccounts"
          @created="fetchTasks"
        />
      </div>

      <div v-if="error" class="app-alert-error mb-4" role="alert">
        <strong class="font-bold">{{ t('common.error') }}</strong>
        <span class="block sm:inline">{{ error.message }}</span>
      </div>

      <TasksTable
        :tasks="tasks"
        :is-loading="isLoading"
        :stopping-ids="stoppingTaskIds"
        @delete-task="handleDeleteTask"
        @edit-task="handleEditTask"
        @run-task="handleStartTask"
        @stop-task="handleStopTask"
        @refresh-criteria="handleOpenCriteriaDialog"
        @toggle-enabled="handleToggleEnabled"
      />
    </template>

    <!-- Edit Task Dialog -->
    <Dialog v-model:open="isEditDialogOpen">
      <DialogContent :class="isTenantPortal ? 'border-[#e7daca] bg-[#fffaf1] shadow-[0_36px_100px_rgba(58,39,20,0.24)] sm:max-w-[820px]' : 'sm:max-w-[640px]'" class="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{{ t('tasks.editDialog.title', { task: selectedTask?.task_name || "" }) }}</DialogTitle>
        </DialogHeader>
        <TaskForm
          v-if="selectedTask"
          mode="edit"
          :variant="isTenantPortal ? 'tenant' : 'default'"
          :allow-ai-mode="!isTenantPortal || canUseAi"
          :initial-data="selectedTask"
          :account-options="accountOptions"
          :allow-fixed-account="canManageFixedAccounts"
          :default-values="editDefaults"
          @submit="(data) => handleUpdateTask(data as TaskUpdate)"
        />
        <DialogFooter>
          <Button type="submit" form="task-form" :disabled="isEditSubmitting">
            {{ isEditSubmitting ? t('common.saving') : t('tasks.editDialog.save') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Refresh Criteria Dialog -->
    <Dialog v-model:open="isCriteriaDialogOpen">
      <DialogContent class="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>{{ t('tasks.criteria.title') }}</DialogTitle>
          <DialogDescription>
            {{ t('tasks.criteria.description') }}
          </DialogDescription>
        </DialogHeader>
        <div class="grid gap-3">
          <label class="text-sm font-medium text-gray-700">{{ t('tasks.form.description') }}</label>
          <Textarea
            v-model="criteriaDescription"
            class="min-h-[140px]"
            :placeholder="t('tasks.form.descriptionPlaceholder')"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isCriteriaDialogOpen = false">
            {{ t('common.cancel') }}
          </Button>
          <Button :disabled="isCriteriaSubmitting" @click="handleRefreshCriteria">
            {{ isCriteriaSubmitting ? t('tasks.criteria.generating') : t('tasks.criteria.action') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isDeleteDialogOpen">
      <DialogContent class="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{{ t('tasks.deleteDialog.title') }}</DialogTitle>
          <DialogDescription>
            {{ taskToDelete ? t('tasks.deleteDialog.descriptionWithTask', { task: taskToDelete.task_name }) : t('tasks.deleteDialog.descriptionFallback') }}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button variant="destructive" @click="handleConfirmDeleteTask">{{ t('tasks.deleteDialog.confirm') }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
