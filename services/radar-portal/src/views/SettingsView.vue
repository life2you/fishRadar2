<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BellRing, Bot, ServerCog } from 'lucide-vue-next'
import { useSettings } from '@/composables/useSettings'
import type { AiAccountItem, AiAccountPayload, AnnouncementItem, AnnouncementLevel, AnnouncementStatus, TenantNotificationChannel } from '@/api/settings'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/components/ui/toast'
import { getPromptContent, listPrompts, updatePrompt } from '@/api/prompts'
import RotationSettingsPanel from '@/components/settings/RotationSettingsPanel.vue'
import AdminTenantNotificationChannelsPanel from '@/components/admin/AdminTenantNotificationChannelsPanel.vue'
const { t } = useI18n()

type AiAccountFormState = {
  name: string
  api_key: string
  base_url: string
  model_name: string
  supports_image: boolean
  supports_text: boolean
  enabled: boolean
  priority: number
  notes: string
}

type AnnouncementFormState = {
  title: string
  content: string
  level: AnnouncementLevel
  status: AnnouncementStatus
  dismissible: boolean
  notify_tenants: boolean
  published_at: string
  expires_at: string
}

const {
  tenantNotificationChannels,
  announcements,
  aiAccounts,
  rotationSettings,
  systemStatus,
  isLoading,
  isSaving,
  isReady,
  error,
  fetchAll,
  refreshStatus,
  saveTenantNotificationChannels,
  createAnnouncement,
  createAiAccount,
  updateAnnouncement,
  updateAiAccount,
  deleteAnnouncement,
  deleteAiAccount,
  testAiAccount,
  testExistingAiAccount,
  saveRotationSettings,
} = useSettings()

const activeTab = ref('ai')
const route = useRoute()
const validTabs = new Set(['notifications', 'announcements', 'ai', 'rotation', 'status', 'prompts'])

const promptFiles = ref<string[]>([])
const selectedPrompt = ref<string | null>(null)
const promptContent = ref('')
const isPromptLoading = ref(false)
const isPromptSaving = ref(false)
const promptError = ref<string | null>(null)
const editingAiAccountId = ref<number | null>(null)
const editingAnnouncementId = ref<number | null>(null)
const aiAccountForm = ref<AiAccountFormState>({
  name: '',
  api_key: '',
  base_url: '',
  model_name: '',
  supports_image: true,
  supports_text: true,
  enabled: true,
  priority: 100,
  notes: '',
})
const announcementForm = ref<AnnouncementFormState>({
  title: '',
  content: '',
  level: 'info',
  status: 'draft',
  dismissible: true,
  notify_tenants: false,
  published_at: '',
  expires_at: '',
})
const aiAccountFormTitle = computed(() => editingAiAccountId.value ? '编辑 AI 账号' : '新增 AI 账号')
const announcementFormTitle = computed(() => editingAnnouncementId.value ? '编辑公告' : '发布公告')
const activeAiAccountCount = computed(() => aiAccounts.value.filter((item) => item.enabled).length)
const activeAnnouncementCount = computed(() => announcements.value.filter((item) => item.status === 'active').length)
const settingsHeroCards = computed(() => [
  {
    icon: Bot,
    label: t('settings.hero.cards.ai'),
    value: activeAiAccountCount.value ? t('common.enabled') : t('common.disabled'),
    detail: activeAiAccountCount.value ? `已配置 ${activeAiAccountCount.value} 个 AI 账号` : '尚未配置 AI 账号',
  },
  {
    icon: BellRing,
    label: t('settings.hero.cards.notifications'),
    value: tenantNotificationChannels.value.length ? String(tenantNotificationChannels.value.length) : t('common.empty'),
    detail: tenantNotificationChannels.value.length
      ? t('settings.tenantNotifications.summary', { count: tenantNotificationChannels.value.length })
      : t('settings.tenantNotifications.none'),
  },
  {
    icon: BellRing,
    label: '平台公告',
    value: activeAnnouncementCount.value ? `${activeAnnouncementCount.value}` : t('common.empty'),
    detail: activeAnnouncementCount.value ? `当前有 ${activeAnnouncementCount.value} 条生效公告` : '当前没有生效公告',
  },
  {
    icon: ServerCog,
    label: t('settings.hero.cards.runtime'),
    value: systemStatus.value?.running_in_docker ? 'Docker' : 'Local',
    detail: systemStatus.value?.scraper_running ? t('common.running') : t('common.idle'),
  },
])
const aiAccountList = computed(() => aiAccounts.value)

function formatDateTime(value?: string | null) {
  if (!value) {
    return '未记录'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getAiUsageLabel(item: AiAccountItem) {
  if (item.supports_image && item.supports_text) {
    return '图文通用'
  }
  if (item.supports_image) {
    return '仅图片分析'
  }
  if (item.supports_text) {
    return '仅文本分析'
  }
  return '未配置能力'
}

function getAiUsageTone(item: AiAccountItem) {
  if (item.supports_image && item.supports_text) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  }
  if (item.supports_image) {
    return 'border-violet-200 bg-violet-50 text-violet-700'
  }
  if (item.supports_text) {
    return 'border-sky-200 bg-sky-50 text-sky-700'
  }
  return 'border-slate-200 bg-slate-50 text-slate-500'
}

function getAnnouncementTone(level: AnnouncementLevel) {
  if (level === 'success') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  }
  if (level === 'warning') {
    return 'border-amber-200 bg-amber-50 text-amber-700'
  }
  return 'border-sky-200 bg-sky-50 text-sky-700'
}

function notifySuccess(title: string, description?: string) {
  toast({ title, description })
}

function notifyError(title: string, description?: string) {
  toast({ title, description, variant: 'destructive' })
}

async function handleSaveTenantNotificationChannels(channels: TenantNotificationChannel[]) {
  try {
    await saveTenantNotificationChannels(channels)
    notifySuccess(t('settings.tenantNotifications.saved'))
  } catch (e) {
    notifyError(t('settings.tenantNotifications.saveFailed'), (e as Error).message)
  }
}

function resetAiAccountForm() {
  editingAiAccountId.value = null
  aiAccountForm.value = {
    name: '',
    api_key: '',
    base_url: '',
    model_name: '',
    supports_image: true,
    supports_text: true,
    enabled: true,
    priority: 100,
    notes: '',
  }
}

function resetAnnouncementForm() {
  editingAnnouncementId.value = null
  announcementForm.value = {
    title: '',
    content: '',
      level: 'info',
      status: 'draft',
      dismissible: true,
      notify_tenants: false,
      published_at: '',
      expires_at: '',
  }
}

function handleEditAiAccount(item: AiAccountItem) {
  editingAiAccountId.value = item.id
  aiAccountForm.value = {
    name: item.name,
    api_key: '',
    base_url: item.base_url,
    model_name: item.model_name,
    supports_image: item.supports_image,
    supports_text: item.supports_text,
    enabled: item.enabled,
    priority: item.priority,
    notes: item.notes || '',
  }
}

function toDateTimeLocalValue(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value.slice(0, 16)
  }
  const offsetMs = date.getTimezoneOffset() * 60 * 1000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

function handleEditAnnouncement(item: AnnouncementItem) {
  editingAnnouncementId.value = item.id
  announcementForm.value = {
    title: item.title,
    content: item.content,
    level: item.level,
    status: item.status,
    dismissible: item.dismissible,
    notify_tenants: false,
    published_at: toDateTimeLocalValue(item.published_at),
    expires_at: toDateTimeLocalValue(item.expires_at),
  }
}

async function handleSaveAiAccount() {
  try {
    const payload: AiAccountPayload = {
      ...aiAccountForm.value,
      name: aiAccountForm.value.name.trim(),
      api_key: (aiAccountForm.value.api_key || '').trim() || undefined,
      base_url: aiAccountForm.value.base_url.trim(),
      model_name: aiAccountForm.value.model_name.trim(),
      notes: (aiAccountForm.value.notes || '').trim() || undefined,
      priority: Number(aiAccountForm.value.priority || 100),
    }
    if (!payload.name || !payload.base_url || !payload.model_name) {
      notifyError('AI账号信息不完整', '请填写名称、接口地址和模型名称。')
      return
    }
    if (!payload.supports_image && !payload.supports_text) {
      notifyError('AI账号能力未开启', '至少需要开启图片分析或文本分析中的一种。')
      return
    }
    if (editingAiAccountId.value) {
      await updateAiAccount(editingAiAccountId.value, payload)
      notifySuccess('AI账号已更新')
    } else {
      await createAiAccount(payload)
      notifySuccess('AI账号已创建')
    }
    resetAiAccountForm()
  } catch (e) {
    notifyError('保存AI账号失败', (e as Error).message)
  }
}

async function handleDeleteAiAccount(item: AiAccountItem) {
  try {
    await deleteAiAccount(item.id)
    notifySuccess('AI账号已删除')
    if (editingAiAccountId.value === item.id) {
      resetAiAccountForm()
    }
  } catch (e) {
    notifyError('删除AI账号失败', (e as Error).message)
  }
}

async function handleSaveAnnouncement() {
  try {
    const payload = {
      title: announcementForm.value.title.trim(),
      content: announcementForm.value.content.trim(),
      level: announcementForm.value.level,
      status: announcementForm.value.status,
      dismissible: announcementForm.value.dismissible,
      notify_tenants: announcementForm.value.notify_tenants,
      published_at: announcementForm.value.published_at || null,
      expires_at: announcementForm.value.expires_at || null,
    }
    if (!payload.title || !payload.content) {
      notifyError('公告内容不完整', '请填写标题和公告内容。')
      return
    }
    if (editingAnnouncementId.value) {
      await updateAnnouncement(editingAnnouncementId.value, payload)
      notifySuccess('公告已更新')
    } else {
      await createAnnouncement(payload)
      notifySuccess('公告已发布')
    }
    resetAnnouncementForm()
  } catch (e) {
    notifyError('保存公告失败', (e as Error).message)
  }
}

async function handleDeleteAnnouncement(item: AnnouncementItem) {
  try {
    await deleteAnnouncement(item.id)
    notifySuccess('公告已删除')
    if (editingAnnouncementId.value === item.id) {
      resetAnnouncementForm()
    }
  } catch (e) {
    notifyError('删除公告失败', (e as Error).message)
  }
}

async function handleTestAiAccount() {
  try {
    const payload = {
      api_key: (aiAccountForm.value.api_key || '').trim() || undefined,
      base_url: aiAccountForm.value.base_url.trim(),
      model_name: aiAccountForm.value.model_name.trim(),
    }
    if (!payload.base_url || !payload.model_name) {
      notifyError('AI账号信息不完整', '测试前请先填写接口地址和模型名称。')
      return
    }
    const res = await testAiAccount(payload)
    if (res.success) {
      notifySuccess('AI账号测试成功', res.message)
    } else {
      notifyError('AI账号测试失败', res.message)
    }
  } catch (e) {
    notifyError('AI账号测试失败', (e as Error).message)
  }
}

async function handleTestExistingAiAccount(item: AiAccountItem) {
  try {
    const res = await testExistingAiAccount(item.id)
    if (res.success) {
      notifySuccess('AI账号测试成功', res.message)
    } else {
      notifyError('AI账号测试失败', res.message)
    }
  } catch (e) {
    notifyError('AI账号测试失败', (e as Error).message)
  }
}

async function handleSaveRotation() {
  try {
    await saveRotationSettings()
    notifySuccess(t('settings.rotation.saved'))
  } catch (e) {
    notifyError(t('settings.rotation.saveFailed'), (e as Error).message)
  }
}

async function fetchPrompts() {
  isPromptLoading.value = true
  promptError.value = null
  try {
    const files = await listPrompts()
    promptFiles.value = files

    if (selectedPrompt.value && files.includes(selectedPrompt.value)) {
      return
    }

    const lastSelected = localStorage.getItem('lastSelectedPrompt')
    if (lastSelected && files.includes(lastSelected)) {
      selectedPrompt.value = lastSelected
      return
    }

    selectedPrompt.value = files[0] || null
  } catch (e) {
    promptError.value = (e as Error).message || t('settings.prompts.promptListFailed')
  } finally {
    isPromptLoading.value = false
  }
}

async function handleSavePrompt() {
  if (!selectedPrompt.value) {
    notifyError(t('settings.prompts.selectPromptFile'))
    return
  }
  isPromptSaving.value = true
  try {
    const res = await updatePrompt(selectedPrompt.value, promptContent.value)
    notifySuccess(t('settings.prompts.saveSuccess'), res.message)
  } catch (e) {
    notifyError(t('settings.prompts.saveFailed'), (e as Error).message)
  } finally {
    isPromptSaving.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'prompts') {
    fetchPrompts()
  }
})

watch(
  () => route.query.tab,
  (tab) => {
    if (typeof tab === 'string' && validTabs.has(tab)) {
      activeTab.value = tab
    }
  },
  { immediate: true }
)

watch(selectedPrompt, async (value) => {
  if (!value) {
    promptContent.value = ''
    return
  }
  localStorage.setItem('lastSelectedPrompt', value)
  isPromptLoading.value = true
  promptError.value = null
  try {
    const data = await getPromptContent(value)
    promptContent.value = data.content
  } catch (e) {
    promptError.value = (e as Error).message || t('settings.prompts.promptContentFailed')
  } finally {
    isPromptLoading.value = false
  }
})

onMounted(() => {
  if (!isLoading.value) {
    fetchAll()
  }
})
</script>

<template>
  <div class="space-y-6">
    <section class="rounded-[20px] border border-[#d7e2db] bg-[linear-gradient(135deg,#f7fbf7_0%,#eef5f0_100%)] px-4 py-4 text-[#243329] shadow-[0_10px_24px_rgba(78,99,88,0.06)]">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div class="max-w-[42rem]">
          <p class="text-[10px] font-black uppercase tracking-[0.24em] text-[#74887c]">CatchYu Console</p>
          <div class="mt-1.5 flex flex-wrap items-center gap-3">
            <h1 class="text-[1.45rem] font-black tracking-tight text-[#243329]">{{ t('settings.title') }}</h1>
            <span class="rounded-full border border-[#d7e2db] bg-white/90 px-2.5 py-1 text-[11px] font-medium text-[#5d7064]">
              {{ t('settings.hero.panelLabel') }}
            </span>
          </div>
          <p class="mt-1 text-[13px] leading-5 text-[#627267]">{{ t('settings.description') }}</p>
        </div>
        <div class="text-[12px] leading-5 text-[#66766b] lg:max-w-[18rem]">{{ t('settings.hero.panelDescription') }}</div>
      </div>

      <div class="mt-3 flex flex-wrap gap-2">
        <article
          v-for="card in settingsHeroCards"
          :key="card.label"
          class="flex min-w-[190px] flex-1 items-start gap-3 rounded-[14px] border border-[#d7e2db] bg-white/94 px-3 py-2.5 shadow-sm"
        >
          <component :is="card.icon" class="mt-0.5 h-4.5 w-4.5 shrink-0 text-[#74a08a]" />
          <div class="min-w-0">
            <p class="text-[10px] font-black uppercase tracking-[0.18em] text-[#88a094]">{{ card.label }}</p>
            <p class="mt-0.5 text-[14px] font-black text-[#243329]">{{ card.value }}</p>
            <p class="mt-0.5 text-[12px] leading-5 text-[#66766b]">{{ card.detail }}</p>
          </div>
        </article>
      </div>
    </section>
    
    <div v-if="error" class="app-alert-error mb-4" role="alert">
      {{ error.message }}
    </div>

    <Tabs v-model="activeTab" class="w-full">
      <TabsList class="mb-4 flex w-full flex-nowrap justify-start gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1">
        <TabsTrigger class="shrink-0" value="ai">{{ t('settings.tabs.ai') }}</TabsTrigger>
        <TabsTrigger class="shrink-0" value="rotation">{{ t('settings.tabs.rotation') }}</TabsTrigger>
        <TabsTrigger class="shrink-0" value="notifications">{{ t('settings.tabs.notifications') }}</TabsTrigger>
        <TabsTrigger class="shrink-0" value="announcements">平台公告</TabsTrigger>
        <TabsTrigger class="shrink-0" value="status">{{ t('settings.tabs.status') }}</TabsTrigger>
        <TabsTrigger class="shrink-0" value="prompts">{{ t('settings.tabs.prompts') }}</TabsTrigger>
      </TabsList>

      <!-- AI Tab -->
      <TabsContent value="ai">
        <div class="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>AI账号池</CardTitle>
              <CardDescription>为文本分析和图片分析维护多个 AI 账号，系统会按任务能力自动选择可用账号。</CardDescription>
            </CardHeader>
            <CardContent class="space-y-5">
              <p v-if="!isReady || isLoading" class="text-sm text-slate-500">正在加载 AI 配置...</p>
              <div class="grid gap-3 md:grid-cols-3">
                <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p class="text-xs font-semibold text-slate-500">已启用账号</p>
                  <p class="mt-1 text-2xl font-black text-slate-900">{{ activeAiAccountCount }}</p>
                </div>
                <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p class="text-xs font-semibold text-slate-500">图片分析账号</p>
                  <p class="mt-1 text-2xl font-black text-slate-900">{{ aiAccounts.filter((item) => item.enabled && item.supports_image).length }}</p>
                </div>
                <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p class="text-xs font-semibold text-slate-500">文本分析账号</p>
                  <p class="mt-1 text-2xl font-black text-slate-900">{{ aiAccounts.filter((item) => item.enabled && item.supports_text).length }}</p>
                </div>
              </div>

              <div class="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
                <div class="space-y-3">
                  <div
                    v-if="!aiAccountList.length"
                    class="rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 px-4 py-6 text-sm text-slate-500"
                  >
                    还没有自定义 AI 账号，建议先创建一个可用账号。
                  </div>
                  <article
                    v-for="item in aiAccountList"
                    :key="`${item.id}-${item.name}`"
                    class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm"
                  >
                    <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                          <h3 class="text-base font-black text-slate-900">{{ item.name }}</h3>
                          <span class="rounded-full border px-2 py-0.5 text-[11px] font-semibold" :class="item.enabled ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-slate-200 bg-slate-100 text-slate-500'">
                            {{ item.enabled ? '启用中' : '已停用' }}
                          </span>
                        </div>
                        <p class="mt-1 break-all text-sm text-slate-600">{{ item.base_url }}</p>
                        <p class="mt-1 text-sm text-slate-500">{{ item.model_name }}</p>
                        <div class="mt-3 flex flex-wrap gap-2">
                          <span class="rounded-full border px-2.5 py-1 text-xs font-semibold" :class="getAiUsageTone(item)">{{ getAiUsageLabel(item) }}</span>
                          <span class="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-600">优先级 {{ item.priority }}</span>
                          <span class="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-600">{{ item.api_key_set ? '已配置密钥' : '无密钥' }}</span>
                        </div>
                        <div class="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                          <div class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                            <p class="font-semibold text-slate-600">最近更新</p>
                            <p class="mt-1 text-sm text-slate-800">{{ formatDateTime(item.updated_at || item.created_at) }}</p>
                          </div>
                          <div class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                            <p class="font-semibold text-slate-600">最近测试</p>
                            <p
                              class="mt-1 text-sm font-semibold"
                              :class="item.last_test_status === 'success' ? 'text-emerald-700' : item.last_test_status === 'failed' ? 'text-rose-700' : 'text-slate-700'"
                            >
                              {{
                                item.last_test_status === 'success'
                                  ? '已通过'
                                  : item.last_test_status === 'failed'
                                    ? '失败'
                                    : '未测试'
                              }}
                            </p>
                            <p class="mt-1 line-clamp-2 text-xs text-slate-500">
                              {{
                                item.last_tested_at
                                  ? `${formatDateTime(item.last_tested_at)} · ${item.last_test_message || '最近一次测试已完成'}`
                                  : '建议创建后先测试一次连接。'
                              }}
                            </p>
                          </div>
                        </div>
                        <p v-if="item.notes" class="mt-3 text-sm text-slate-500">{{ item.notes }}</p>
                      </div>
                      <div class="flex shrink-0 flex-wrap gap-2">
                        <Button variant="outline" size="sm" @click="handleTestExistingAiAccount(item)">测试</Button>
                        <Button variant="outline" size="sm" @click="handleEditAiAccount(item)">编辑</Button>
                        <Button variant="outline" size="sm" class="text-rose-600 hover:text-rose-700" @click="handleDeleteAiAccount(item)">删除</Button>
                      </div>
                    </div>
                  </article>
                </div>

                <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h3 class="text-lg font-black text-slate-900">{{ aiAccountFormTitle }}</h3>
                      <p class="mt-1 text-sm text-slate-500">为不同任务能力准备专用 AI 账号。</p>
                    </div>
                    <Button variant="outline" size="sm" @click="resetAiAccountForm">重置</Button>
                  </div>

                  <div class="mt-5 space-y-4">
                    <div class="grid gap-2">
                      <Label>账号名称</Label>
                      <Input v-model="aiAccountForm.name" placeholder="例如：图片分析主账号" />
                    </div>
                    <div class="grid gap-2">
                      <Label>API Base URL</Label>
                      <Input v-model="aiAccountForm.base_url" placeholder="https://api.openai.com/v1" />
                    </div>
                    <div class="grid gap-2">
                      <Label>API Key</Label>
                      <Input v-model="aiAccountForm.api_key" type="password" :placeholder="editingAiAccountId ? '留空则保持原密钥不变' : '输入新的 API Key'" />
                    </div>
                    <div class="grid gap-2">
                      <Label>模型名称</Label>
                      <Input v-model="aiAccountForm.model_name" placeholder="gpt-4o-mini / Qwen2.5-VL-72B-Instruct" />
                    </div>
                    <div class="grid gap-4 sm:grid-cols-2">
                      <label class="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-3 text-sm text-slate-700">
                        <input v-model="aiAccountForm.supports_text" type="checkbox" class="h-4 w-4" />
                        支持文本分析
                      </label>
                      <label class="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-3 text-sm text-slate-700">
                        <input v-model="aiAccountForm.supports_image" type="checkbox" class="h-4 w-4" />
                        支持图片分析
                      </label>
                    </div>
                    <div class="grid gap-4 sm:grid-cols-2">
                      <label class="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-3 text-sm text-slate-700">
                        <input v-model="aiAccountForm.enabled" type="checkbox" class="h-4 w-4" />
                        启用该账号
                      </label>
                      <div class="grid gap-2">
                        <Label>优先级</Label>
                        <Input v-model.number="aiAccountForm.priority" type="number" min="1" />
                      </div>
                    </div>
                    <div class="grid gap-2">
                      <Label>备注</Label>
                      <Textarea v-model="aiAccountForm.notes" placeholder="例如：只给图片任务使用，额度较高。" />
                    </div>
                  </div>

                  <div class="mt-5 flex flex-wrap gap-2">
                    <Button variant="outline" @click="handleTestAiAccount" :disabled="isSaving">测试连接</Button>
                    <Button @click="handleSaveAiAccount" :disabled="isSaving">{{ editingAiAccountId ? '保存修改' : '创建账号' }}</Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

        </div>
      </TabsContent>

      <!-- Rotation Tab -->
      <TabsContent value="rotation">
        <RotationSettingsPanel
          :settings="rotationSettings"
          :is-ready="isReady"
          :is-saving="isSaving"
          @save="handleSaveRotation"
        />
      </TabsContent>

      <!-- Notifications Tab -->
      <TabsContent value="notifications">
        <AdminTenantNotificationChannelsPanel
          :channels="tenantNotificationChannels"
          :is-ready="isReady"
          :is-saving="isSaving"
          @save="handleSaveTenantNotificationChannels"
        />
      </TabsContent>

      <TabsContent value="announcements">
        <Card>
          <CardHeader>
            <CardTitle>平台公告</CardTitle>
            <CardDescription>向所有租户统一发布升级通知、维护提醒和临时说明。</CardDescription>
          </CardHeader>
          <CardContent class="space-y-5">
            <div class="grid gap-3 md:grid-cols-3">
              <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p class="text-xs font-semibold text-slate-500">生效中公告</p>
                <p class="mt-1 text-2xl font-black text-slate-900">{{ activeAnnouncementCount }}</p>
              </div>
              <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p class="text-xs font-semibold text-slate-500">草稿</p>
                <p class="mt-1 text-2xl font-black text-slate-900">{{ announcements.filter((item) => item.status === 'draft').length }}</p>
              </div>
              <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                <p class="text-xs font-semibold text-slate-500">可关闭公告</p>
                <p class="mt-1 text-2xl font-black text-slate-900">{{ announcements.filter((item) => item.dismissible).length }}</p>
              </div>
            </div>

            <div class="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
              <div class="space-y-3">
                <div
                  v-if="!announcements.length"
                  class="rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 px-4 py-6 text-sm text-slate-500"
                >
                  当前还没有平台公告，可以先发布一条升级说明。
                </div>
                <article
                  v-for="item in announcements"
                  :key="item.id"
                  class="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm"
                >
                  <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-2">
                        <h3 class="text-base font-black text-slate-900">{{ item.title }}</h3>
                        <span class="rounded-full border px-2 py-0.5 text-[11px] font-semibold" :class="getAnnouncementTone(item.level)">
                          {{ item.level === 'warning' ? '提醒' : item.level === 'success' ? '完成' : '通知' }}
                        </span>
                        <span class="rounded-full border px-2 py-0.5 text-[11px] font-semibold" :class="item.status === 'active' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : item.status === 'draft' ? 'border-slate-200 bg-slate-100 text-slate-600' : 'border-amber-200 bg-amber-50 text-amber-700'">
                          {{ item.status === 'active' ? '生效中' : item.status === 'draft' ? '草稿' : '已归档' }}
                        </span>
                      </div>
                      <p class="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">{{ item.content }}</p>
                      <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                        <span class="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1">发布时间 {{ formatDateTime(item.published_at || item.updated_at) }}</span>
                        <span class="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1">{{ item.expires_at ? `到期 ${formatDateTime(item.expires_at)}` : '长期有效' }}</span>
                        <span class="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1">{{ item.dismissible ? '租户可关闭' : '租户不可关闭' }}</span>
                      </div>
                    </div>
                    <div class="flex shrink-0 flex-wrap gap-2">
                      <Button variant="outline" size="sm" @click="handleEditAnnouncement(item)">编辑</Button>
                      <Button variant="outline" size="sm" class="text-rose-600 hover:text-rose-700" @click="handleDeleteAnnouncement(item)">删除</Button>
                    </div>
                  </div>
                </article>
              </div>

              <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <h3 class="text-lg font-black text-slate-900">{{ announcementFormTitle }}</h3>
                    <p class="mt-1 text-sm text-slate-500">租户登录后会在工作台顶部看到这里发布的公告。</p>
                  </div>
                  <Button variant="outline" size="sm" @click="resetAnnouncementForm">重置</Button>
                </div>

                <div class="mt-5 space-y-4">
                  <div class="grid gap-2">
                    <Label>公告标题</Label>
                    <Input v-model="announcementForm.title" placeholder="例如：系统将于今晚 23:00 升级" />
                  </div>
                  <div class="grid gap-2">
                    <Label>公告内容</Label>
                    <Textarea v-model="announcementForm.content" rows="6" placeholder="填写面向租户的升级说明、影响范围和预计恢复时间。" />
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <div class="grid gap-2">
                      <Label>公告级别</Label>
                      <Select :model-value="announcementForm.level" @update:model-value="(value) => announcementForm.level = value as AnnouncementLevel">
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="info">普通通知</SelectItem>
                          <SelectItem value="success">完成提醒</SelectItem>
                          <SelectItem value="warning">维护提醒</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div class="grid gap-2">
                      <Label>公告状态</Label>
                      <Select :model-value="announcementForm.status" @update:model-value="(value) => announcementForm.status = value as AnnouncementStatus">
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="draft">草稿</SelectItem>
                          <SelectItem value="active">立即生效</SelectItem>
                          <SelectItem value="archived">归档</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <div class="grid gap-2">
                      <Label>发布时间</Label>
                      <Input v-model="announcementForm.published_at" type="datetime-local" />
                    </div>
                    <div class="grid gap-2">
                      <Label>到期时间</Label>
                      <Input v-model="announcementForm.expires_at" type="datetime-local" />
                    </div>
                  </div>
                  <label class="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-3 text-sm text-slate-700">
                    <input v-model="announcementForm.dismissible" type="checkbox" class="h-4 w-4" />
                    允许租户在当前浏览器关闭这条公告
                  </label>
                  <label class="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-3 text-sm text-slate-700">
                    <input v-model="announcementForm.notify_tenants" type="checkbox" class="h-4 w-4" />
                    发布时同步推送到租户已配置的通知渠道
                  </label>
                </div>

                <div class="mt-5 flex flex-wrap gap-2">
                  <Button @click="handleSaveAnnouncement" :disabled="isSaving">{{ editingAnnouncementId ? '保存公告' : '发布公告' }}</Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </TabsContent>

      <!-- Status Tab -->
      <TabsContent value="status">
        <Card>
          <CardHeader>
            <CardTitle>{{ t('settings.status.title') }}</CardTitle>
            <div class="flex justify-end">
                <Button variant="outline" size="sm" @click="refreshStatus" :disabled="isLoading">{{ t('settings.status.refresh') }}</Button>
            </div>
          </CardHeader>
          <CardContent>
            <div v-if="systemStatus" class="space-y-6">
              <!-- Scraper Process Status -->
              <div class="flex items-center justify-between border-b pb-4">
                <div>
                  <h3 class="font-medium">{{ t('settings.status.scraper') }}</h3>
                  <p class="text-sm text-gray-500">{{ t('settings.status.scraperDescription') }}</p>
                </div>
                <span :class="systemStatus.scraper_running ? 'text-green-600 font-bold bg-green-50 px-3 py-1 rounded-full' : 'text-gray-500 bg-gray-100 px-3 py-1 rounded-full'">
                  {{ systemStatus.scraper_running ? t('common.running') : t('common.idle') }}
                </span>
              </div>

              <!-- Env Config Status -->
              <div>
                <div class="flex items-center justify-between mb-4">
                    <div>
                        <h3 class="font-medium">{{ t('settings.status.env') }}</h3>
                        <p class="text-sm text-gray-500">{{ t('settings.status.envDescription') }}</p>
                    </div>
                    <span :class="systemStatus.env_file.exists ? 'text-green-600 font-bold bg-green-50 px-3 py-1 rounded-full' : 'text-red-600 font-bold bg-red-50 px-3 py-1 rounded-full'">
                        {{ systemStatus.env_file.exists ? t('settings.status.loaded') : t('settings.status.missing') }}
                    </span>
                </div>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="p-3 border rounded-lg" :class="tenantNotificationChannels.length ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'">
                         <div class="flex justify-between items-center">
                            <span class="font-medium text-sm">{{ t('settings.status.channels') }}</span>
                             <span class="text-xs font-bold" :class="tenantNotificationChannels.length ? 'text-green-700' : 'text-gray-500'">
                                {{ tenantNotificationChannels.length ? t('common.active') : t('common.inactive') }}
                            </span>
                        </div>
                         <div class="text-xs text-gray-500 mt-1">
                            {{ tenantNotificationChannels.join(', ') || t('settings.status.none') }}
                        </div>
                    </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-8 text-gray-500">
                {{ t('settings.status.fetching') }}
            </div>
          </CardContent>
        </Card>
      </TabsContent>

      <!-- Prompt Tab -->
      <TabsContent value="prompts">
        <Card>
          <CardHeader>
            <CardTitle>{{ t('settings.prompts.title') }}</CardTitle>
            <CardDescription>{{ t('settings.prompts.description') }}</CardDescription>
          </CardHeader>
          <CardContent class="space-y-4">
            <div v-if="promptError" class="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded">
              {{ promptError }}
            </div>

            <div class="grid gap-2">
              <Label>{{ t('settings.prompts.selectFile') }}</Label>
              <Select
                :model-value="selectedPrompt || undefined"
                @update:model-value="(value) => selectedPrompt = value as string"
              >
                <SelectTrigger>
                  <SelectValue :placeholder="t('settings.prompts.placeholder')" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="file in promptFiles" :key="file" :value="file">
                    {{ file }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <p v-if="!promptFiles.length && !isPromptLoading" class="text-sm text-gray-500">
                {{ t('settings.prompts.none') }}
              </p>
            </div>

            <div class="grid gap-2">
              <Label>{{ t('settings.prompts.content') }}</Label>
              <Textarea
                v-model="promptContent"
                class="min-h-[240px]"
                :disabled="!selectedPrompt || isPromptLoading"
                :placeholder="t('settings.prompts.contentPlaceholder')"
              />
            </div>
          </CardContent>
          <CardFooter>
            <Button :disabled="isPromptSaving || !selectedPrompt" @click="handleSavePrompt">
              {{ isPromptSaving ? t('common.saving') : t('settings.prompts.save') }}
            </Button>
          </CardFooter>
        </Card>
      </TabsContent>
    </Tabs>
  </div>
</template>
