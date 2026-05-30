<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Task, TaskGenerateRequest } from '@/types/task.d.ts'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import TaskRegionSelector from '@/components/tasks/TaskRegionSelector.vue'

type FormMode = 'create' | 'edit'
type EmittedData = TaskGenerateRequest | Partial<Task>
const AUTO_ACCOUNT_VALUE = '__auto__'
const EMPTY_CRON_VALUE = '__manual__'

const props = defineProps<{
  mode: FormMode
  variant?: 'default' | 'tenant'
  submitLabel?: string
  isSubmitting?: boolean
  allowAiMode?: boolean
  initialData?: Task | null
  accountOptions?: { name: string; path: string }[]
  allowFixedAccount?: boolean
  defaultAccount?: string
  defaultValues?: Partial<TaskGenerateRequest & Partial<Task>>
}>()

const emit = defineEmits<{
  (e: 'submit', data: EmittedData): void
}>()
const { t } = useI18n()

const form = ref<any>({})
const accountStrategy = ref<'auto' | 'fixed' | 'rotate'>('auto')
const selectedAccountStateFile = ref(AUTO_ACCOUNT_VALUE)
const keywordRulesInput = ref('')
const cronMode = ref<'preset' | 'custom'>('preset')
const tenantWizardStep = ref(1)
const tenantStepError = ref('')
const tenantStepErrorField = ref('')

// 常用 cron 预设选项
const cronPresets = computed(() => [
  { value: EMPTY_CRON_VALUE, label: t('tasks.form.cron.manual') },
  { value: '*/5 * * * *', label: t('tasks.form.cron.every5Minutes') },
  { value: '*/15 * * * *', label: t('tasks.form.cron.every15Minutes') },
  { value: '*/30 * * * *', label: t('tasks.form.cron.every30Minutes') },
  { value: '0 * * * *', label: t('tasks.form.cron.hourly') },
  { value: '0 */2 * * *', label: t('tasks.form.cron.every2Hours') },
  { value: '0 */6 * * *', label: t('tasks.form.cron.every6Hours') },
  { value: '0 8 * * *', label: t('tasks.form.cron.daily8') },
  { value: '0 12 * * *', label: t('tasks.form.cron.daily12') },
  { value: '0 18 * * *', label: t('tasks.form.cron.daily18') },
  { value: '0 20 * * *', label: t('tasks.form.cron.daily20') },
  { value: '0 8,12,18 * * *', label: t('tasks.form.cron.daily81218') },
  { value: '0 9 * * 1-5', label: t('tasks.form.cron.weekday9') },
  { value: '0 10 * * 6,0', label: t('tasks.form.cron.weekend10') },
])

// 判断 cron 值是否为预设值
function isPresetCronValue(value: string): boolean {
  if (!value) return true
  return cronPresets.value.some((preset) => preset.value === value)
}

// 判断当前 cron 是否为预设值
const isPresetCron = computed(() => isPresetCronValue(form.value.cron))

// 预设选择的值
const presetCronValue = computed({
  get: () => {
    if (!isPresetCron.value) return EMPTY_CRON_VALUE
    return form.value.cron || EMPTY_CRON_VALUE
  },
  set: (val: string) => { form.value.cron = val === EMPTY_CRON_VALUE ? '' : val },
})
const accountStrategyOptions = computed(() => {
  const options = [
    { value: 'auto', label: t('tasks.form.accountStrategy.auto'), description: t('tasks.form.accountStrategy.autoDescription') },
    { value: 'fixed', label: t('tasks.form.accountStrategy.fixed'), description: t('tasks.form.accountStrategy.fixedDescription') },
    { value: 'rotate', label: t('tasks.form.accountStrategy.rotate'), description: t('tasks.form.accountStrategy.rotateDescription') },
  ]
  if (props.allowFixedAccount === false) {
    return options.filter((option) => option.value !== 'fixed')
  }
  return options
})
const isTenantVariant = computed(() => props.variant === 'tenant')
const canUseAiMode = computed(() => props.allowAiMode !== false)
const keywordRuleCount = computed(() => parseKeywordText(keywordRulesInput.value).length)
const tenantStrategyStepHint = computed(() => (
  canUseAiMode.value ? 'AI 模式或关键词模式。' : '当前仅开放关键词模式。'
))
const tenantStrategyDescription = computed(() => (
  canUseAiMode.value ? '告诉 CatchYu 如何判断线索' : '使用关键词规则筛选目标线索'
))
const tenantChecklistItems = computed(() => (
  canUseAiMode.value
    ? [
        'AI 模式下需要填写详细需求。',
        '关键词模式下至少要有一条关键词规则。',
        '如果你设置了定时规则，保存后就会参与调度。',
      ]
    : [
        '至少填写一条关键词规则。',
        '确认搜索词、价格区间和发布时间范围。',
        '如果你设置了定时规则，保存后就会参与调度。',
      ]
))
const scheduleSummary = computed(() => {
  const cronValue = String(form.value.cron || '')
  if (!cronValue) return '手动触发'
  return cronPresets.value.find((preset) => preset.value === cronValue)?.label || cronValue
})
const publishSummary = computed(() => {
  const mapping: Record<string, string> = {
    最新: t('tasks.form.publishOptions.latest'),
    '1天内': t('tasks.form.publishOptions.oneDay'),
    '3天内': t('tasks.form.publishOptions.threeDays'),
    '7天内': t('tasks.form.publishOptions.sevenDays'),
    '14天内': t('tasks.form.publishOptions.fourteenDays'),
  }
  const value = String(form.value.new_publish_option || '')
  if (!value || value === '__none__') return t('tasks.form.publishOptions.none')
  return mapping[value] || value
})
const summaryTags = computed(() => {
  const tags: string[] = []
  if (form.value.personal_only) tags.push('仅个人卖家')
  if (form.value.free_shipping) tags.push('包邮优先')
  if (form.value.region) tags.push(String(form.value.region))
  if (form.value.min_price || form.value.max_price) {
    const min = form.value.min_price ? `¥${form.value.min_price}` : '不限'
    const max = form.value.max_price ? `¥${form.value.max_price}` : '不限'
    tags.push(`${min} - ${max}`)
  }
  return tags.slice(0, 5)
})
const tenantStepCards = computed(() => [
  {
    step: 1,
    eyebrow: '步骤 1',
    title: '填写关键词',
    description: '先明确任务名和搜索词。',
  },
  {
    step: 2,
    eyebrow: '步骤 2',
    title: '选择策略',
    description: tenantStrategyStepHint.value,
  },
  {
    step: 3,
    eyebrow: '步骤 3',
    title: '设置频率',
    description: '决定手动抓取还是定时抓取。',
  },
  {
    step: 4,
    eyebrow: '步骤 4',
    title: '确认发布',
    description: '检查摘要后即可上线任务。',
  },
])

function parseKeywordText(text: string): string[] {
  const values = String(text || '')
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0)

  const seen = new Set<string>()
  const deduped: string[] = []
  for (const value of values) {
    const key = value.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    deduped.push(value)
  }
  return deduped
}

watch(() => [props.mode, props.initialData, props.defaultValues, props.defaultAccount], () => {
  const defaultValues = props.defaultValues || {}
  if (props.mode === 'edit' && props.initialData) {
    form.value = {
      ...props.initialData,
      ...defaultValues,
      account_strategy:
        defaultValues.account_strategy ||
        props.initialData.account_strategy ||
        (props.initialData.account_state_file ? 'fixed' : 'auto'),
      account_state_file:
        defaultValues.account_state_file ||
        props.initialData.account_state_file ||
        AUTO_ACCOUNT_VALUE,
      analyze_images: defaultValues.analyze_images ?? props.initialData.analyze_images ?? true,
      free_shipping: defaultValues.free_shipping ?? props.initialData.free_shipping ?? true,
      new_publish_option:
        defaultValues.new_publish_option || props.initialData.new_publish_option || '__none__',
      region: defaultValues.region || props.initialData.region || '',
      decision_mode: defaultValues.decision_mode || props.initialData.decision_mode || 'ai',
    }
    keywordRulesInput.value = (defaultValues.keyword_rules || props.initialData.keyword_rules || []).join('\n')
    // 编辑模式下，根据 cron 值判断模式
    const cronVal = defaultValues.cron ?? props.initialData.cron ?? ''
    cronMode.value = isPresetCronValue(cronVal) ? 'preset' : 'custom'
  } else {
    form.value = {
      task_name: '',
      keyword: '',
      description: '',
      analyze_images: true,
      max_pages: 3,
      personal_only: true,
      min_price: undefined,
      max_price: undefined,
      cron: '',
      account_strategy: props.defaultAccount ? 'fixed' : 'auto',
      account_state_file: props.defaultAccount || AUTO_ACCOUNT_VALUE,
      free_shipping: true,
      new_publish_option: '__none__',
      region: '',
      decision_mode: 'ai',
      ...defaultValues,
    }
    if (!form.value.account_strategy) {
      form.value.account_strategy = props.defaultAccount ? 'fixed' : 'auto'
    }
    if (!form.value.account_state_file) {
      form.value.account_state_file = props.defaultAccount || AUTO_ACCOUNT_VALUE
    }
    if (!form.value.new_publish_option) {
      form.value.new_publish_option = '__none__'
    }
    keywordRulesInput.value = ''
    if (defaultValues.keyword_rules && defaultValues.keyword_rules.length > 0) {
      keywordRulesInput.value = defaultValues.keyword_rules.join('\n')
    }
    // 创建模式下，根据默认值判断模式
    const cronVal = defaultValues.cron ?? ''
    cronMode.value = isPresetCronValue(cronVal) ? 'preset' : 'custom'
  }

  accountStrategy.value = form.value.account_strategy || (props.defaultAccount ? 'fixed' : 'auto')
  if (isTenantVariant.value) {
    accountStrategy.value = 'auto'
    form.value.account_strategy = 'auto'
    form.value.account_state_file = null
  }
  if (props.allowFixedAccount === false && accountStrategy.value === 'fixed') {
    accountStrategy.value = 'auto'
    form.value.account_strategy = 'auto'
    form.value.account_state_file = null
  }
  selectedAccountStateFile.value =
    form.value.account_state_file || props.defaultAccount || AUTO_ACCOUNT_VALUE
  if (!canUseAiMode.value && form.value.decision_mode === 'ai') {
    form.value.decision_mode = 'keyword'
  }
  if (isTenantVariant.value) {
    tenantWizardStep.value = 1
  }
}, { immediate: true, deep: true })

watch(canUseAiMode, (enabled) => {
  if (!enabled && form.value.decision_mode === 'ai') {
    form.value.decision_mode = 'keyword'
  }
}, { immediate: true })

watch(() => form.value.task_name, () => {
  if (tenantStepErrorField.value === 'task_name') {
    tenantStepError.value = ''
    tenantStepErrorField.value = ''
  }
})

watch(() => form.value.keyword, () => {
  if (tenantStepErrorField.value === 'keyword') {
    tenantStepError.value = ''
    tenantStepErrorField.value = ''
  }
})

watch(() => form.value.description, () => {
  if (tenantStepErrorField.value === 'description') {
    tenantStepError.value = ''
    tenantStepErrorField.value = ''
  }
})

watch(keywordRulesInput, () => {
  if (tenantStepErrorField.value === 'keyword_rules') {
    tenantStepError.value = ''
    tenantStepErrorField.value = ''
  }
})

watch(accountStrategy, (value) => {
  if (isTenantVariant.value) {
    accountStrategy.value = 'auto'
    form.value.account_strategy = 'auto'
    form.value.account_state_file = null
    return
  }
  form.value.account_strategy = value
  if (value === 'fixed') {
    form.value.account_state_file = selectedAccountStateFile.value || props.defaultAccount || AUTO_ACCOUNT_VALUE
    return
  }
  form.value.account_state_file = null
})

watch(() => props.allowFixedAccount, (allowFixedAccount) => {
  if (allowFixedAccount === false && accountStrategy.value === 'fixed') {
    accountStrategy.value = 'auto'
  }
}, { immediate: true })

watch(selectedAccountStateFile, (value) => {
  if (accountStrategy.value !== 'fixed') return
  form.value.account_state_file = value || props.defaultAccount || AUTO_ACCOUNT_VALUE
})

function handleAccountStrategyChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value as 'auto' | 'fixed' | 'rotate'
  accountStrategy.value = value
}

function handleAccountStateFileChange(event: Event) {
  selectedAccountStateFile.value = (event.target as HTMLSelectElement).value || AUTO_ACCOUNT_VALUE
}

function handleSubmit() {
  if (!form.value.task_name || !form.value.keyword) {
    toast({
      title: t('tasks.form.validation.incomplete'),
      description: t('tasks.form.validation.nameAndKeywordRequired'),
      variant: 'destructive',
    })
    return
  }

  const decisionMode = form.value.decision_mode || 'ai'
  if (decisionMode === 'ai' && !canUseAiMode.value) {
    toast({
      title: 'AI 分析暂未开通',
      description: '当前租户暂未开通 AI 分析能力，可先切换到关键词模式。',
      variant: 'destructive',
    })
    return
  }
  if (decisionMode === 'ai' && !String(form.value.description || '').trim()) {
    toast({
      title: t('tasks.form.validation.incomplete'),
      description: t('tasks.form.validation.aiDescriptionRequired'),
      variant: 'destructive',
    })
    return
  }

  const keywordRules = parseKeywordText(keywordRulesInput.value)
  if (decisionMode === 'keyword' && keywordRules.length === 0) {
    toast({
      title: t('tasks.form.validation.keywordRuleIncomplete'),
      description: t('tasks.form.validation.keywordRuleRequired'),
      variant: 'destructive',
    })
    return
  }

  // Filter out fields that shouldn't be sent in update requests
  const { id, is_running, next_run_at, ...submitData } = form.value as any
  const currentAccountStrategy = isTenantVariant.value ? 'auto' : (accountStrategy.value || 'auto')
  if (currentAccountStrategy === 'fixed') {
    const currentAccountStateFile = selectedAccountStateFile.value || AUTO_ACCOUNT_VALUE
    if (currentAccountStateFile === AUTO_ACCOUNT_VALUE) {
      toast({
        title: t('tasks.form.validation.accountStrategyIncomplete'),
        description: t('tasks.form.validation.fixedAccountRequired'),
        variant: 'destructive',
      })
      return
    }
    submitData.account_state_file = currentAccountStateFile
  } else {
    submitData.account_state_file = null
  }

  if (typeof submitData.region === 'string') {
    const normalized = submitData.region
      .trim()
      .split('/')
      .map((part: string) => part.trim().replace(/(省|市)$/u, ''))
      .filter((part: string) => part.length > 0)
      .join('/')
    submitData.region = normalized
  }

  if (submitData.new_publish_option === '__none__') {
    submitData.new_publish_option = ''
  }

  submitData.decision_mode = decisionMode
  submitData.account_strategy = currentAccountStrategy
  submitData.analyze_images = submitData.analyze_images !== false
  submitData.keyword_rules = decisionMode === 'keyword' ? keywordRules : []
  if (isTenantVariant.value) {
    submitData.account_state_file = null
  }
  if (decisionMode === 'keyword') {
    submitData.description = ''
  }

  emit('submit', submitData)
}

function validateTenantStep(step: number): boolean {
  tenantStepError.value = ''
  tenantStepErrorField.value = ''

  if (step === 1) {
    if (!String(form.value.task_name || '').trim()) {
      tenantStepError.value = '请先填写任务名称。'
      tenantStepErrorField.value = 'task_name'
      toast({
        title: t('tasks.form.validation.incomplete'),
        description: '请先填写任务名称。',
        variant: 'destructive',
      })
      return false
    }
    if (!String(form.value.keyword || '').trim()) {
      tenantStepError.value = '请先填写搜索关键词。'
      tenantStepErrorField.value = 'keyword'
      toast({
        title: t('tasks.form.validation.incomplete'),
        description: '请先填写搜索关键词。',
        variant: 'destructive',
      })
      return false
    }
  }

  if (step === 2) {
    const decisionMode = form.value.decision_mode || 'ai'
    if (decisionMode === 'ai') {
      if (!canUseAiMode.value) {
        tenantStepError.value = '当前租户暂未开通 AI 分析能力，可先切换到关键词模式。'
        tenantStepErrorField.value = 'decision_mode'
        toast({
          title: 'AI 分析暂未开通',
          description: '当前租户暂未开通 AI 分析能力，可先切换到关键词模式。',
          variant: 'destructive',
        })
        return false
      }
      if (!String(form.value.description || '').trim()) {
        tenantStepError.value = t('tasks.form.validation.aiDescriptionRequired')
        tenantStepErrorField.value = 'description'
        toast({
          title: t('tasks.form.validation.incomplete'),
          description: t('tasks.form.validation.aiDescriptionRequired'),
          variant: 'destructive',
        })
        return false
      }
    }

    if (decisionMode === 'keyword' && parseKeywordText(keywordRulesInput.value).length === 0) {
      tenantStepError.value = t('tasks.form.validation.keywordRuleRequired')
      tenantStepErrorField.value = 'keyword_rules'
      toast({
        title: t('tasks.form.validation.keywordRuleIncomplete'),
        description: t('tasks.form.validation.keywordRuleRequired'),
        variant: 'destructive',
      })
      return false
    }
  }

  return true
}

function goToNextTenantStep() {
  if (!validateTenantStep(tenantWizardStep.value)) return
  tenantWizardStep.value = Math.min(4, tenantWizardStep.value + 1)
}

function goToPreviousTenantStep() {
  tenantStepError.value = ''
  tenantStepErrorField.value = ''
  tenantWizardStep.value = Math.max(1, tenantWizardStep.value - 1)
}
</script>

<template>
  <form v-if="isTenantVariant" id="task-form" @submit.prevent="handleSubmit">
    <div class="space-y-6">
      <div class="grid gap-3 md:grid-cols-4">
        <article
          v-for="card in tenantStepCards"
          :key="card.step"
          class="rounded-[22px] border px-4 py-3 shadow-sm transition-colors"
          :class="tenantWizardStep === card.step
            ? 'border-[#d7c19f] bg-[#fff5e6]'
            : tenantWizardStep > card.step
              ? 'border-[#d7e4d9] bg-[#f3faf4]'
              : 'border-[#eadbc8] bg-white/80'"
        >
          <p class="text-[11px] font-bold uppercase tracking-[0.22em]" :class="tenantWizardStep === card.step ? 'text-[#9b6b35]' : 'text-[#9b8165]'">
            {{ card.eyebrow }}
          </p>
          <p class="mt-2 text-sm font-bold text-[#2b1d13]">{{ card.title }}</p>
          <p class="mt-1 text-xs leading-5 text-[#6f5b47]">{{ card.description }}</p>
        </article>
      </div>

      <div class="space-y-5">
        <section v-if="tenantWizardStep === 1" class="rounded-[28px] border border-[#eadbc8] bg-white/82 p-5 shadow-sm">
          <div class="mb-4">
            <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-[#9b8165]">基础设定</p>
            <h3 class="mt-2 text-xl font-black tracking-[-0.03em] text-[#241a12]">定义你要抓的目标商品</h3>
          </div>
          <div class="grid gap-4 lg:grid-cols-2">
            <div class="space-y-2">
              <Label for="task-name" class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.taskName') }}</Label>
              <Input id="task-name" v-model="form.task_name" class="h-12 rounded-2xl bg-[#fffdf8]" :class="tenantStepErrorField === 'task_name' ? 'border-rose-300 focus-visible:ring-rose-200' : 'border-[#e1d4c1]'" :placeholder="t('tasks.form.taskNamePlaceholder')" required />
            </div>
            <div class="space-y-2">
              <Label for="keyword" class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.keyword') }}</Label>
              <Input id="keyword" v-model="form.keyword" class="h-12 rounded-2xl bg-[#fffdf8]" :class="tenantStepErrorField === 'keyword' ? 'border-rose-300 focus-visible:ring-rose-200' : 'border-[#e1d4c1]'" :placeholder="t('tasks.form.keywordPlaceholder')" required />
            </div>
          </div>
          <p v-if="tenantWizardStep === 1 && tenantStepError" class="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {{ tenantStepError }}
          </p>
        </section>

        <section v-if="tenantWizardStep === 2" class="rounded-[28px] border border-[#eadbc8] bg-white/82 p-5 shadow-sm">
          <div class="space-y-4">
            <div class="mb-4">
              <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-[#9b8165]">分析策略</p>
              <h3 class="mt-2 text-xl font-black tracking-[-0.03em] text-[#241a12]">{{ tenantStrategyDescription }}</h3>
            </div>
            <div class="space-y-2">
              <Label class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.decisionMode') }}</Label>
              <div class="grid gap-3" :class="canUseAiMode ? 'md:grid-cols-2' : 'md:grid-cols-1'">
                <button
                  v-if="canUseAiMode"
                  type="button"
                  class="rounded-[20px] border p-3.5 text-left transition-colors"
                  :class="form.decision_mode === 'ai' ? 'border-[#d6e1d8] bg-[#edf6ef]' : 'border-[#eadbc8] bg-[#fffaf2]'"
                  @click="form.decision_mode = 'ai'"
                >
                  <p class="text-sm font-bold text-[#2b1d13]">{{ t('tasks.form.aiMode') }}</p>
                  <p class="mt-1.5 text-xs leading-5 text-[#6f5b47]">
                    适合复杂判断，系统会异步生成分析标准。
                  </p>
                </button>
                <button
                  type="button"
                  class="rounded-[20px] border p-3.5 text-left transition-colors"
                  :class="form.decision_mode === 'keyword' ? 'border-[#ead3c0] bg-[#fbefe1]' : 'border-[#eadbc8] bg-[#fffaf2]'"
                  @click="form.decision_mode = 'keyword'"
                >
                  <p class="text-sm font-bold text-[#2b1d13]">{{ t('tasks.form.keywordMode') }}</p>
                  <p class="mt-1.5 text-xs leading-5 text-[#6f5b47]">适合规则明确的场景，命中关键词即可推荐。</p>
                </button>
              </div>
              <p v-if="!canUseAiMode" class="mt-3 rounded-2xl border border-[#eadbc8] bg-[#fff7ed] px-4 py-3 text-xs leading-6 text-[#8b5a2b]">
                当前租户未开通 AI 模式。AI 模式可按你的详细需求自动判断商品，更适合复杂筛选场景；当前可先使用关键词模式创建任务。
              </p>
            </div>

            <div class="space-y-4">
              <div v-if="form.decision_mode === 'ai'" class="space-y-2">
                <Label for="description" class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.description') }}</Label>
                <Textarea id="description" v-model="form.description" class="min-h-[120px] rounded-[20px] bg-[#fffdf8]" :class="tenantStepErrorField === 'description' ? 'border-rose-300 focus-visible:ring-rose-200' : 'border-[#e1d4c1]'" :placeholder="t('tasks.form.descriptionPlaceholder')" />
              </div>

              <div v-if="form.decision_mode === 'ai'" class="rounded-[20px] border border-[#d6e1d8] bg-[#f5faf6] p-3.5">
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <p class="text-sm font-bold text-[#2b1d13]">{{ t('tasks.form.analyzeImages') }}</p>
                    <p class="mt-1 text-xs leading-5 text-[#6f5b47]">{{ t('tasks.form.analyzeImagesHint') }}</p>
                  </div>
                  <Switch id="analyze-images" v-model="form.analyze_images" />
                </div>
              </div>

              <div v-if="form.decision_mode === 'keyword'" class="space-y-2">
                <Label class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.keywordRules') }}</Label>
                <p class="text-xs text-[#7d6b57]">{{ t('tasks.form.keywordRulesHint') }}</p>
                <Textarea v-model="keywordRulesInput" class="min-h-[120px] rounded-[20px] bg-[#fffdf8]" :class="tenantStepErrorField === 'keyword_rules' ? 'border-rose-300 focus-visible:ring-rose-200' : 'border-[#e1d4c1]'" :placeholder="t('tasks.form.keywordRulesPlaceholder')" />
              </div>
              <details class="rounded-[20px] border border-[#e7dbc9] bg-[#fffaf4] px-4 py-3">
                <summary class="cursor-pointer list-none text-sm font-bold text-[#4b3727]">
                  更多筛选条件
                </summary>
                <p class="mt-1 text-xs text-[#7d6b57]">价格、发布时间、区域和卖家偏好都可以放在这里补充。</p>
                <div class="mt-4 grid gap-4 lg:grid-cols-2">
                  <div class="space-y-2">
                    <Label class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.priceRange') }}</Label>
                    <div class="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
                      <Input type="number" v-model="form.min_price as any" class="h-11 rounded-2xl border-[#e1d4c1] bg-[#fffdf8]" :aria-label="t('tasks.form.minPrice')" :placeholder="t('tasks.form.minPrice')" />
                      <span class="text-[#8f7b68]">-</span>
                      <Input type="number" v-model="form.max_price as any" class="h-11 rounded-2xl border-[#e1d4c1] bg-[#fffdf8]" :aria-label="t('tasks.form.maxPrice')" :placeholder="t('tasks.form.maxPrice')" />
                    </div>
                  </div>
                  <div class="space-y-2">
                    <Label for="max-pages" class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.maxPages') }}</Label>
                    <Input id="max-pages" v-model.number="form.max_pages" type="number" class="h-11 rounded-2xl border-[#e1d4c1] bg-[#fffdf8]" />
                  </div>
                  <div class="space-y-2 lg:col-span-2">
                    <Label class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.newPublish') }}</Label>
                    <Select v-model="form.new_publish_option as any">
                      <SelectTrigger class="h-11 rounded-2xl border-[#e1d4c1] bg-[#fffdf8]">
                        <SelectValue :placeholder="t('tasks.form.publishOptions.none')" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">{{ t('tasks.form.publishOptions.none') }}</SelectItem>
                        <SelectItem value="最新">{{ t('tasks.form.publishOptions.latest') }}</SelectItem>
                        <SelectItem value="1天内">{{ t('tasks.form.publishOptions.oneDay') }}</SelectItem>
                        <SelectItem value="3天内">{{ t('tasks.form.publishOptions.threeDays') }}</SelectItem>
                        <SelectItem value="7天内">{{ t('tasks.form.publishOptions.sevenDays') }}</SelectItem>
                        <SelectItem value="14天内">{{ t('tasks.form.publishOptions.fourteenDays') }}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div class="space-y-2 lg:col-span-2">
                    <Label class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.region') }}</Label>
                    <TaskRegionSelector v-model="form.region as any" />
                    <p class="text-xs text-[#7d6b57]">{{ t('tasks.form.regionHint') }}</p>
                  </div>
                  <div class="rounded-[20px] border border-[#e8ddcf] bg-white/80 p-3.5">
                    <div class="flex items-center justify-between gap-3">
                      <div>
                        <p class="text-sm font-bold text-[#2b1d13]">{{ t('tasks.form.personalOnly') }}</p>
                        <p class="mt-1 text-xs text-[#6f5b47]">优先只抓个人卖家发布的商品。</p>
                      </div>
                      <Switch id="personal-only" v-model="form.personal_only" />
                    </div>
                  </div>
                  <div class="rounded-[20px] border border-[#e8ddcf] bg-white/80 p-3.5">
                    <div class="flex items-center justify-between gap-3">
                      <div>
                        <p class="text-sm font-bold text-[#2b1d13]">{{ t('tasks.form.freeShipping') }}</p>
                        <p class="mt-1 text-xs text-[#6f5b47]">筛掉不包邮的商品，适合直接比较到手价。</p>
                      </div>
                      <Switch id="free-shipping" v-model="form.free_shipping" />
                    </div>
                  </div>
                </div>
              </details>
            </div>
            <p v-if="tenantWizardStep === 2 && tenantStepError" class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {{ tenantStepError }}
            </p>
          </div>
        </section>

        <section v-if="tenantWizardStep === 3" class="rounded-[28px] border border-[#eadbc8] bg-white/82 p-5 shadow-sm">
          <div class="mb-4">
            <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-[#9b8165]">执行方式</p>
            <h3 class="mt-2 text-xl font-black tracking-[-0.03em] text-[#241a12]">决定任务如何启动和运行</h3>
          </div>
          <div class="space-y-4">
            <div class="space-y-2">
              <Label for="cron" class="text-sm font-semibold text-[#4b3727]">{{ t('tasks.form.schedule') }}</Label>
              <Tabs v-model="cronMode" class="w-full">
                <TabsList class="grid h-12 w-full grid-cols-2 rounded-2xl bg-[#f7efe3]">
                  <TabsTrigger value="preset">{{ t('tasks.form.cronPresetTab') }}</TabsTrigger>
                  <TabsTrigger value="custom">{{ t('tasks.form.cronCustomTab') }}</TabsTrigger>
                </TabsList>
                <TabsContent value="preset" class="mt-3">
                  <Select v-model="presetCronValue">
                    <SelectTrigger class="h-12 rounded-2xl border-[#e1d4c1] bg-[#fffdf8]">
                      <SelectValue :placeholder="t('tasks.form.cronPlaceholder')" />
                    </SelectTrigger>
                    <SelectContent class="border-[#e7daca] bg-[#fffaf1] text-[#2b1d13] shadow-[0_24px_60px_rgba(58,39,20,0.18)]">
                      <SelectItem v-for="preset in cronPresets" :key="preset.value" :value="preset.value">
                        {{ preset.label }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </TabsContent>
                <TabsContent value="custom" class="mt-3">
                  <Input id="cron" v-model="form.cron" class="h-12 rounded-2xl border-[#e1d4c1] bg-[#fffdf8]" :placeholder="t('tasks.form.cronCustomPlaceholder')" />
                  <p class="mt-2 text-xs text-[#7d6b57]">{{ t('tasks.form.cronCustomHintLine1') }}</p>
                  <p class="text-xs text-[#7d6b57]">{{ t('tasks.form.cronCustomHintLine2') }}</p>
                </TabsContent>
              </Tabs>
            </div>

            <div v-if="mode === 'edit'" class="rounded-[24px] border border-[#e8ddcf] bg-[#fcf7ef] p-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-bold text-[#2b1d13]">启用状态</p>
                  <p class="mt-1 text-xs text-[#6f5b47]">关闭后任务不会参与调度，也不会自动运行。</p>
                </div>
                <Switch v-model="form.enabled" />
              </div>
            </div>
          </div>
        </section>

        <section v-if="tenantWizardStep === 4" class="rounded-[28px] border border-[#eadbc8] bg-white/82 p-5 shadow-sm">
          <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-[#9b8165]">确认发布</p>
          <h3 class="mt-2 text-xl font-black tracking-[-0.03em] text-[#241a12]">检查这条 CatchYu 任务</h3>

          <div class="mt-4 grid gap-3 md:grid-cols-2">
            <div class="rounded-[20px] border border-[#e8ddcf] bg-[#fcf7ef] px-4 py-3">
              <p class="text-[11px] font-bold uppercase tracking-[0.18em] text-[#9b8165]">任务名</p>
              <p class="mt-1 text-sm font-bold text-[#2b1d13]">{{ form.task_name || '未命名任务' }}</p>
            </div>
            <div class="rounded-[20px] border border-[#e8ddcf] bg-[#fcf7ef] px-4 py-3">
              <p class="text-[11px] font-bold uppercase tracking-[0.18em] text-[#9b8165]">关键词</p>
              <p class="mt-1 text-sm font-bold text-[#2b1d13]">{{ form.keyword || '待填写' }}</p>
            </div>
            <div class="rounded-[20px] border border-[#e8ddcf] bg-[#fcf7ef] px-4 py-3">
              <p class="text-[11px] font-bold uppercase tracking-[0.18em] text-[#9b8165]">模式</p>
              <p class="mt-1 text-sm font-bold text-[#2b1d13]">{{ form.decision_mode === 'keyword' ? t('tasks.form.keywordMode') : t('tasks.form.aiMode') }}</p>
            </div>
            <div class="rounded-[20px] border border-[#e8ddcf] bg-[#fcf7ef] px-4 py-3">
              <p class="text-[11px] font-bold uppercase tracking-[0.18em] text-[#9b8165]">频率</p>
              <p class="mt-1 text-sm font-bold text-[#2b1d13]">{{ scheduleSummary }}</p>
            </div>
          </div>

          <div class="mt-4 rounded-[20px] border border-[#eadbc8] bg-white/88 p-4">
            <div class="grid gap-2 text-sm leading-6 text-[#5f4d3d] md:grid-cols-2">
              <p><span class="font-semibold text-[#2b1d13]">关键词规则：</span>{{ keywordRuleCount }} 条</p>
              <p><span class="font-semibold text-[#2b1d13]">发布时间：</span>{{ publishSummary }}</p>
            </div>
            <div v-if="summaryTags.length > 0" class="mt-3 flex flex-wrap gap-2">
              <span
                v-for="tag in summaryTags"
                :key="tag"
                class="rounded-full border border-[#e5d8c6] bg-white/90 px-3 py-1 text-xs font-semibold text-[#684e38]"
              >
                {{ tag }}
              </span>
            </div>
          </div>

          <div class="mt-4 rounded-[20px] border border-[#eadbc8] bg-white/88 p-4">
            <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-[#9b8165]">发布前检查</p>
            <ul class="mt-3 space-y-2 text-sm leading-6 text-[#5f4d3d]">
              <li v-for="item in tenantChecklistItems" :key="item">{{ item }}</li>
            </ul>
          </div>
        </section>

        <div class="flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            class="rounded-full border-[#decdb8] bg-white/85 px-5"
            :disabled="tenantWizardStep === 1 || isSubmitting"
            @click="goToPreviousTenantStep"
          >
            上一步
          </Button>
          <div class="flex items-center gap-3">
            <p class="text-xs font-medium text-[#816c58]">第 {{ tenantWizardStep }} / 4 步</p>
            <Button
              v-if="tenantWizardStep < 4"
              type="button"
              class="rounded-full bg-[#21160f] px-5 text-white hover:bg-[#2f2016]"
              @click="goToNextTenantStep"
            >
              下一步
            </Button>
            <Button
              v-else-if="submitLabel"
              type="submit"
              class="rounded-full bg-[#21160f] px-5 text-white hover:bg-[#2f2016]"
              :disabled="isSubmitting"
            >
              {{ isSubmitting ? t('tasks.createDialog.submitting') : submitLabel }}
            </Button>
          </div>
        </div>
      </div>
    </div>
  </form>

  <form v-else id="task-form" @submit.prevent="handleSubmit">
    <div class="grid gap-6 py-4">
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label for="task-name" class="sm:text-right">{{ t('tasks.form.taskName') }}</Label>
        <Input id="task-name" v-model="form.task_name" class="sm:col-span-3" :placeholder="t('tasks.form.taskNamePlaceholder')" required />
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label for="keyword" class="sm:text-right">{{ t('tasks.form.keyword') }}</Label>
        <Input id="keyword" v-model="form.keyword" class="sm:col-span-3" :placeholder="t('tasks.form.keywordPlaceholder')" required />
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label class="sm:text-right">{{ t('tasks.form.decisionMode') }}</Label>
        <div class="sm:col-span-3">
          <Select v-model="form.decision_mode">
            <SelectTrigger>
              <SelectValue :placeholder="t('tasks.form.decisionModePlaceholder')" />
            </SelectTrigger>
                    <SelectContent class="border-[#e7daca] bg-[#fffaf1] text-[#2b1d13] shadow-[0_24px_60px_rgba(58,39,20,0.18)]">
              <SelectItem v-if="canUseAiMode" value="ai">{{ t('tasks.form.aiMode') }}</SelectItem>
              <SelectItem value="keyword">{{ t('tasks.form.keywordMode') }}</SelectItem>
            </SelectContent>
          </Select>
          <p v-if="!canUseAiMode" class="mt-2 text-xs text-amber-700">
            当前租户尚未开通 AI 分析能力，暂时只能使用关键词模式。
          </p>
        </div>
      </div>
      <div v-if="form.decision_mode === 'ai'" class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label for="description" class="sm:text-right">{{ t('tasks.form.description') }}</Label>
        <div class="sm:col-span-3">
          <Textarea
            id="description"
            v-model="form.description"
            :placeholder="t('tasks.form.descriptionPlaceholder')"
          />
        </div>
      </div>
      <div v-if="form.decision_mode === 'ai'" class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label for="analyze-images" class="sm:text-right">{{ t('tasks.form.analyzeImages') }}</Label>
        <div class="space-y-1 sm:col-span-3">
          <Switch id="analyze-images" v-model="form.analyze_images" />
          <p class="text-xs text-gray-500">
            {{ t('tasks.form.analyzeImagesHint') }}
          </p>
        </div>
      </div>
      <div v-if="form.decision_mode === 'keyword'" class="grid gap-2 sm:grid-cols-4 sm:gap-4">
        <Label class="pt-1 sm:pt-2 sm:text-right">{{ t('tasks.form.keywordRules') }}</Label>
        <div class="space-y-2 sm:col-span-3">
          <p class="text-xs text-gray-500">
            {{ t('tasks.form.keywordRulesHint') }}
          </p>
          <Textarea
            v-model="keywordRulesInput"
            class="min-h-[120px]"
            :placeholder="t('tasks.form.keywordRulesPlaceholder')"
          />
        </div>
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label class="sm:text-right">{{ t('tasks.form.priceRange') }}</Label>
        <div class="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:col-span-3">
          <Input type="number" v-model="form.min_price as any" :aria-label="t('tasks.form.minPrice')" :placeholder="t('tasks.form.minPrice')" />
          <span>-</span>
          <Input type="number" v-model="form.max_price as any" :aria-label="t('tasks.form.maxPrice')" :placeholder="t('tasks.form.maxPrice')" />
        </div>
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label for="max-pages" class="sm:text-right">{{ t('tasks.form.maxPages') }}</Label>
        <Input id="max-pages" v-model.number="form.max_pages" type="number" class="sm:col-span-3" />
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label for="cron" class="sm:text-right">{{ t('tasks.form.schedule') }}</Label>
        <div class="space-y-2 sm:col-span-3">
          <Tabs v-model="cronMode" class="w-full">
            <TabsList class="grid w-full grid-cols-2">
              <TabsTrigger value="preset">{{ t('tasks.form.cronPresetTab') }}</TabsTrigger>
              <TabsTrigger value="custom">{{ t('tasks.form.cronCustomTab') }}</TabsTrigger>
            </TabsList>
            <TabsContent value="preset">
              <Select v-model="presetCronValue">
                <SelectTrigger>
                  <SelectValue :placeholder="t('tasks.form.cronPlaceholder')" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="preset in cronPresets" :key="preset.value" :value="preset.value">
                    {{ preset.label }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </TabsContent>
            <TabsContent value="custom">
              <Input
                id="cron"
                v-model="form.cron"
                :placeholder="t('tasks.form.cronCustomPlaceholder')"
              />
              <p class="text-xs text-gray-500 mt-1">
                {{ t('tasks.form.cronCustomHintLine1') }}
              </p>
              <p class="text-xs text-gray-500">
                {{ t('tasks.form.cronCustomHintLine2') }}
              </p>
            </TabsContent>
          </Tabs>
        </div>
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label class="sm:text-right">{{ t('tasks.form.accountStrategyLabel') }}</Label>
        <div class="space-y-2 sm:col-span-3">
          <select
            :value="accountStrategy"
            class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            @change="handleAccountStrategyChange"
          >
            <option v-for="option in accountStrategyOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
          <p class="text-xs text-gray-500">
            {{ accountStrategyOptions.find((option) => option.value === accountStrategy)?.description }}
          </p>
        </div>
      </div>
      <div v-if="accountStrategy === 'fixed'" class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label class="sm:text-right">{{ t('tasks.form.fixedAccount') }}</Label>
        <div class="sm:col-span-3">
          <select
            :value="selectedAccountStateFile"
            class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            @change="handleAccountStateFileChange"
          >
            <option :value="AUTO_ACCOUNT_VALUE">{{ t('tasks.form.selectAccount') }}</option>
            <option v-for="account in accountOptions || []" :key="account.path" :value="account.path">
              {{ account.name }}
            </option>
          </select>
        </div>
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label for="personal-only" class="sm:text-right">{{ t('tasks.form.personalOnly') }}</Label>
        <div class="sm:col-span-3">
          <Switch id="personal-only" v-model="form.personal_only" />
        </div>
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label for="free-shipping" class="sm:text-right">{{ t('tasks.form.freeShipping') }}</Label>
        <div class="sm:col-span-3">
          <Switch id="free-shipping" v-model="form.free_shipping" />
        </div>
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label class="sm:text-right">{{ t('tasks.form.newPublish') }}</Label>
        <div class="sm:col-span-3">
          <Select v-model="form.new_publish_option as any">
            <SelectTrigger>
              <SelectValue :placeholder="t('tasks.form.publishOptions.none')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">{{ t('tasks.form.publishOptions.none') }}</SelectItem>
              <SelectItem value="最新">{{ t('tasks.form.publishOptions.latest') }}</SelectItem>
              <SelectItem value="1天内">{{ t('tasks.form.publishOptions.oneDay') }}</SelectItem>
              <SelectItem value="3天内">{{ t('tasks.form.publishOptions.threeDays') }}</SelectItem>
              <SelectItem value="7天内">{{ t('tasks.form.publishOptions.sevenDays') }}</SelectItem>
              <SelectItem value="14天内">{{ t('tasks.form.publishOptions.fourteenDays') }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div class="grid gap-2 sm:grid-cols-4 sm:items-center sm:gap-4">
        <Label class="sm:text-right">{{ t('tasks.form.region') }}</Label>
        <div class="space-y-1 sm:col-span-3">
          <TaskRegionSelector v-model="form.region as any" />
          <p class="text-xs text-gray-500">{{ t('tasks.form.regionHint') }}</p>
        </div>
      </div>
    </div>
  </form>
</template>
