<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from '@/composables/useAuth'
import { useResults } from '@/composables/useResults'
import ResultsFilterBar from '@/components/results/ResultsFilterBar.vue'
import ResultsGrid from '@/components/results/ResultsGrid.vue'
import ResultsInsightsPanel from '@/components/results/ResultsInsightsPanel.vue'
import TenantPortalHero from '@/components/tenant/TenantPortalHero.vue'
import CatchYuResultsToolbar from '@/components/tenant/CatchYuResultsToolbar.vue'
import CatchYuResultsInsightsRail from '@/components/tenant/CatchYuResultsInsightsRail.vue'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toast'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const { t } = useI18n()
const { role, tenantName, username } = useAuth()
const route = useRoute()

const {
  files,
  selectedFile,
  results,
  insights,
  filters,
  isLoading,
  error,
  refreshResults,
  reanalyzeSelectedResults,
  exportSelectedResults,
  deleteSelectedFile,
  toggleItemBlock,
  blacklistKeywords,
  isSavingBlacklist,
  saveBlacklistRules,
  fileOptions,
  isFileOptionsReady,
} = useResults()

const isDeleteDialogOpen = ref(false)
const isBlacklistDialogOpen = ref(false)
const blacklistDraft = ref('')
const isTenantPortal = computed(() => role.value === 'tenant')
const tenantWorkspaceName = computed(() => tenantName.value || username.value || t('common.unnamed'))
const adminTenantScopeLabel = computed(() => {
  if (role.value !== 'admin') return null
  const raw = route.query.tenant_id
  return typeof raw === 'string' ? raw : null
})

const selectedTaskLabel = computed(() => {
  if (!selectedFile.value || fileOptions.value.length === 0) return null
  const match = fileOptions.value.find((option) => option.value === selectedFile.value)
  if (!match) return null
  return match.taskName || null
})
const selectedResultHeadline = computed(() => {
  return selectedTaskLabel.value || (selectedFile.value ? selectedFile.value.replace('_full_data.jsonl', '') : '等待选择结果集')
})

const deleteConfirmText = computed(() => {
  return selectedTaskLabel.value
    ? t('results.filters.deleteDialogWithTask', { task: selectedTaskLabel.value })
    : t('results.filters.deleteDialogFallback')
})
const recommendedCount = computed(() => results.value.filter((item) => item.ai_analysis?.is_recommended).length)
const hiddenCount = computed(() => results.value.filter((item) => item._effective_hidden).length)
const tenantResultStats = computed(() => [
  {
    label: t('tenantPortal.results.stats.files'),
    value: String(files.value.length),
    detail: undefined,
  },
  {
    label: t('tenantPortal.results.stats.items'),
    value: String(results.value.length),
    detail: undefined,
  },
  {
    label: t('tenantPortal.results.stats.recommended'),
    value: String(recommendedCount.value),
    detail: undefined,
  },
])

function openDeleteDialog() {
  if (!selectedFile.value) {
    toast({
      title: t('results.filters.noResultToDelete'),
      variant: 'destructive',
    })
    return
  }
  isDeleteDialogOpen.value = true
}

function openBlacklistDialog() {
  if (!selectedFile.value) {
    toast({
      title: t('results.filters.noResultSelected'),
      variant: 'destructive',
    })
    return
  }
  blacklistDraft.value = blacklistKeywords.value.join('\n')
  isBlacklistDialogOpen.value = true
}

function handleExportResults() {
  if (!selectedFile.value) {
    toast({
      title: t('results.filters.noResultToExport'),
      variant: 'destructive',
    })
    return
  }
  exportSelectedResults()
}

async function handleDeleteResults() {
  if (!selectedFile.value) return
  try {
    await deleteSelectedFile(selectedFile.value)
    toast({ title: t('results.filters.resultDeleted') })
  } catch (e) {
    toast({
      title: t('results.filters.deleteFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    isDeleteDialogOpen.value = false
  }
}

async function handleReanalyzeResults() {
  if (!selectedFile.value) {
    toast({
      title: t('results.filters.noResultSelected'),
      variant: 'destructive',
    })
    return
  }
  try {
    const payload = await reanalyzeSelectedResults()
    if (!payload) return
    toast({
      title: t('results.filters.reanalyzeDone'),
      description: t('results.filters.reanalyzeDoneDescription', {
        updated: payload.updated_count,
        failed: payload.failed_count,
      }),
    })
  } catch (e) {
    toast({
      title: t('results.filters.reanalyzeFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  }
}

function parseBlacklistKeywords(input: string) {
  return input
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

async function handleSaveBlacklistRules() {
  try {
    await saveBlacklistRules(parseBlacklistKeywords(blacklistDraft.value))
    toast({ title: t('results.filters.blacklistSaved') })
    isBlacklistDialogOpen.value = false
  } catch (e) {
    toast({
      title: t('results.filters.blacklistSaveFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  }
}
</script>

<template>
  <div>
    <div v-if="isTenantPortal" class="space-y-6">
      <TenantPortalHero
        :eyebrow="t('tenantPortal.eyebrow')"
        :title="t('tenantPortal.results.title', { tenant: tenantWorkspaceName })"
        :description="t('tenantPortal.results.description')"
        :stats="tenantResultStats"
      />

      <section class="space-y-4">
        <div v-if="error" class="app-alert-error mb-4" role="alert">
          <strong class="font-bold">{{ t('common.error') }}</strong>
          <span class="block sm:inline">{{ error.message }}</span>
        </div>

        <CatchYuResultsToolbar
          :files="files"
          :file-options="fileOptions"
          :is-ready="isFileOptionsReady"
          v-model:selectedFile="selectedFile"
          v-model:aiRecommendedOnly="filters.ai_recommended_only"
          v-model:keywordRecommendedOnly="filters.keyword_recommended_only"
          v-model:includeHidden="filters.include_hidden"
          v-model:sortBy="filters.sort_by"
          v-model:sortOrder="filters.sort_order"
          :is-loading="isLoading"
          @refresh="refreshResults"
          @manage-blacklist="openBlacklistDialog"
          @export="handleExportResults"
          @delete="openDeleteDialog"
        />

        <section
          v-if="selectedFile"
          class="rounded-[16px] border border-[#d7e2db] bg-white/92 px-4 py-3 text-[13px] text-[#5f7869] shadow-sm"
        >
          <p class="text-[10px] font-bold uppercase tracking-[0.18em] text-[#7f988b]">当前结果集</p>
          <h3 class="mt-1 text-[1rem] font-black tracking-[-0.02em] text-[#203228]">{{ selectedResultHeadline }}</h3>
          <p class="mt-0.5 leading-5">共 {{ results.length }} 条记录，其中 {{ recommendedCount }} 条推荐，{{ hiddenCount }} 条已隐藏。</p>
        </section>

        <div class="space-y-4">
          <ResultsGrid :results="results" :is-loading="isLoading" @toggle-block="toggleItemBlock" />
          <CatchYuResultsInsightsRail
            :insights="insights"
            :selected-task-label="selectedTaskLabel"
            :blacklist-keywords="blacklistKeywords"
            :can-export="Boolean(selectedFile)"
            :can-manage-blacklist="Boolean(selectedFile)"
            @export="handleExportResults"
            @manage-blacklist="openBlacklistDialog"
          />
        </div>
      </section>
    </div>

    <template v-else>
      <h1 class="text-2xl font-bold text-gray-800 mb-6">
        {{ t('results.title') }}
      </h1>
      <div v-if="adminTenantScopeLabel" class="mb-4 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
        {{ t('tenantDetail.scopeHint', { id: adminTenantScopeLabel }) }}
      </div>

      <div v-if="error" class="app-alert-error mb-4" role="alert">
        <strong class="font-bold">{{ t('common.error') }}</strong>
        <span class="block sm:inline">{{ error.message }}</span>
      </div>

      <ResultsFilterBar
        :files="files"
        :file-options="fileOptions"
        :is-ready="isFileOptionsReady"
        v-model:selectedFile="selectedFile"
        v-model:aiRecommendedOnly="filters.ai_recommended_only"
        v-model:keywordRecommendedOnly="filters.keyword_recommended_only"
        v-model:includeHidden="filters.include_hidden"
        v-model:sortBy="filters.sort_by"
        v-model:sortOrder="filters.sort_order"
        :is-loading="isLoading"
        @refresh="refreshResults"
        @reanalyze="handleReanalyzeResults"
        @manage-blacklist="openBlacklistDialog"
        @export="handleExportResults"
        @delete="openDeleteDialog"
      />

      <ResultsInsightsPanel :insights="insights" :selected-task-label="selectedTaskLabel" />

      <ResultsGrid :results="results" :is-loading="isLoading" @toggle-block="toggleItemBlock" />
    </template>

    <Dialog v-model:open="isDeleteDialogOpen">
      <DialogContent class="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{{ t('results.filters.deleteDialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{ deleteConfirmText }}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button variant="destructive" :disabled="isLoading" @click="handleDeleteResults">
            {{ t('results.filters.confirmDelete') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isBlacklistDialogOpen">
      <DialogContent class="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{{ t('results.filters.blacklistDialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{ t('results.filters.blacklistDialogDescription') }}
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-2">
          <label class="text-sm font-medium text-slate-700">
            {{ t('results.filters.blacklistRulesLabel') }}
          </label>
          <Textarea
            v-model="blacklistDraft"
            class="min-h-[180px]"
            :placeholder="t('results.filters.blacklistRulesPlaceholder')"
          />
          <p class="text-xs leading-5 text-slate-500">
            {{ t('results.filters.blacklistRulesHint') }}
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isBlacklistDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button :disabled="isSavingBlacklist" @click="handleSaveBlacklistRules">
            {{ t('results.filters.confirmBlacklistSave') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
