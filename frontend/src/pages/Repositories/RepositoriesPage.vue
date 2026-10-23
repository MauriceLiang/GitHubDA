<script setup lang="ts">
import { ArrowRight, Download, ListChecks, Search, Trash2 } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdInput from '@/components/ui/GdInput.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import type { FeaturedDatasetStatus, RepositoryStatus, RepositorySummary } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const source = useDataSource()
const ui = useUiStore()
const analysis = useAnalysisStore()

const query = ref('')
const tab = ref<'library' | 'search'>('library')
const status = ref<'all' | RepositoryStatus>('all')
const selected = ref<string[]>([])
const searchResults = ref<(RepositorySummary & { alreadyInLibrary: boolean })[]>([])
const searchError = ref<string | null>(null)
const searching = ref(false)
const busyId = ref<string | null>(null)
const clearingSelected = ref(false)
const { data: repositories, loading, error, reload } = useAsyncData(() => source.listRepositories())
const { data: featuredData, error: featuredStatusError, reload: reloadFeaturedStatus } = useAsyncData(() => source.getFeaturedDatasetStatus())
const featuredStatus = ref<FeaturedDatasetStatus | null>(null)
const importingFeatured = ref(false)
const exportingFeatured = ref(false)
let featuredStatusPollTimer: number | undefined

watch(featuredData, (value) => {
  if (!value) return
  const previousActive = featuredStatus.value?.activeTask
  featuredStatus.value = value
  const completed = value.latestTask?.taskId === previousActive?.taskId ? value.latestTask : null
  if (completed?.status === 'succeeded') {
    void reload()
    const imported = Number(completed.result?.imported_count ?? 0)
    const events = Number(completed.result?.event_count ?? 0)
    ui.toast(`精选数据导入完成：新增 ${imported.toLocaleString('zh-CN')} 个仓库，活动记录 ${events.toLocaleString('zh-CN')} 条`)
  } else if (completed?.status === 'failed') {
    ui.toast(completed.errorMessage ?? '精选数据导入失败，可在此重试')
  }
}, { immediate: true })

onMounted(() => {
  featuredStatusPollTimer = window.setInterval(() => {
    if (featuredStatus.value?.activeTask) void reloadFeaturedStatus()
  }, 3000)
})
onBeforeUnmount(() => {
  if (featuredStatusPollTimer !== undefined) window.clearInterval(featuredStatusPollTimer)
})

watch(tab, () => { searchError.value = null })

const filtered = computed(() =>
  (repositories.value ?? []).filter((repo) => {
    const matchesQuery = !query.value || repo.fullName.toLowerCase().includes(query.value.toLowerCase()) || (repo.description ?? '').toLowerCase().includes(query.value.toLowerCase())
    const matchesStatus = status.value === 'all' || repo.status === status.value
    return matchesQuery && matchesStatus
  }),
)
const allFilteredSelected = computed(() => filtered.value.length > 0 && filtered.value.every((repo) => selected.value.includes(repo.id)))

const statusMeta: Record<RepositoryStatus, { text: string; variant: 'default' | 'warn' | 'plain' }> = {
  ready: { text: '已完成', variant: 'default' },
  partial: { text: '部分数据', variant: 'warn' },
  running: { text: '正在更新', variant: 'default' },
  failed: { text: '采集失败', variant: 'warn' },
  idle: { text: '尚未分析', variant: 'plain' },
}

function toggle(repo: RepositorySummary) {
  if (selected.value.includes(repo.id)) selected.value = selected.value.filter((id) => id !== repo.id)
  else if (selected.value.length >= 100) ui.toast('最多一次选择 100 个仓库')
  else selected.value = [...selected.value, repo.id]
}

function toggleAllFiltered() {
  const visibleIds = filtered.value.map((repo) => repo.id)
  if (!visibleIds.length) return

  if (allFilteredSelected.value) {
    const visibleIdSet = new Set(visibleIds)
    selected.value = selected.value.filter((id) => !visibleIdSet.has(id))
    return
  }

  const selectedIds = new Set(selected.value)
  const newIds = visibleIds.filter((id) => !selectedIds.has(id))
  if (selected.value.length + newIds.length > 100) {
    ui.toast('最多一次选择 100 个仓库，请先清除部分已选项')
    return
  }
  selected.value = [...selected.value, ...newIds]
}

function compare() {
  if (selected.value.length < 2 || selected.value.length > 5) return
  analysis.setCompare(selected.value)
  void router.push('/compare')
}

async function searchGithub() {
  if (query.value.trim().length < 2) {
    searchError.value = '请输入至少 2 个字符'
    return
  }
  searching.value = true
  searchError.value = null
  try {
    searchResults.value = await source.searchRepositories(query.value)
  } catch (cause) {
    searchError.value = cause instanceof Error ? cause.message : '搜索 GitHub 仓库失败'
  } finally {
    searching.value = false
  }
}

async function add(repo: RepositorySummary) {
  busyId.value = repo.id
  try {
    const result = await source.addRepository(repo.fullName)
    ui.toast(result.taskId ? '仓库已加入，采集任务已排队' : '仓库已加入分析库')
    await reload()
    void router.push(`/repositories/${result.repositoryId}/overview`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '添加仓库失败')
  } finally {
    busyId.value = null
  }
}

async function remove(repo: RepositorySummary) {
  if (!window.confirm(`从分析库移除 ${repo.fullName}？历史任务与数据不会删除。`)) return
  busyId.value = repo.id
  try {
    await source.removeRepository(repo.id)
    selected.value = selected.value.filter((id) => id !== repo.id)
    await reload()
    ui.toast('已从分析库移除')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '移除仓库失败')
  } finally {
    busyId.value = null
  }
}

async function deleteSelectedRepositories() {
  const repositoryIds = [...selected.value]
  if (!repositoryIds.length) return
  const names = new Map((repositories.value ?? []).map((repo) => [repo.id, repo.fullName]))
  const shownNames = repositoryIds.slice(0, 5).map((id) => names.get(id) ?? `仓库 #${id}`)
  const remaining = repositoryIds.length - shownNames.length
  const list = `${shownNames.join('、')}${remaining > 0 ? ` 等 ${repositoryIds.length} 个仓库` : ''}`
  if (!window.confirm(`确定删除所选仓库的本地采集与分析数据，并从“我的仓库”移除吗？\n\n${list}\n\n仓库资料、其他数据集归属与任务历史会保留；内置精选数据集中的对应条目会标记为待重新导入。此操作不可撤销。`)) return

  clearingSelected.value = true
  try {
    await source.clearRepositoryData(repositoryIds, { removeFromLibrary: true })
    selected.value = selected.value.filter((id) => !repositoryIds.includes(id))
    analysis.setCompare(analysis.compareIds.filter((id) => !repositoryIds.includes(id)))
    await Promise.all([reload(), reloadFeaturedStatus()])
    ui.toast(`已删除 ${repositoryIds.length} 个仓库的本地数据并从“我的仓库”移除`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '删除所选仓库失败')
  } finally {
    clearingSelected.value = false
  }
}

async function importFeatured() {
  if (!featuredStatus.value?.available || importingFeatured.value) return
  importingFeatured.value = true
  try {
    const result = await source.importFeaturedDataset()
    await reloadFeaturedStatus()
    if (result.alreadyCurrent) ui.toast('精选数据包当前版本已导入')
    else ui.toast('精选数据导入任务已排队，可在任务中心查看进度')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导入精选仓库失败')
  } finally {
    importingFeatured.value = false
  }
}

async function handleFeaturedImport() {
  const latest = featuredStatus.value?.latestTask
  if (latest?.status === 'failed' && latest.bundleHash === featuredStatus.value?.bundleHash && !featuredStatus.value?.alreadyCurrent) {
    importingFeatured.value = true
    try {
      await source.retryTask(latest.taskId)
      await reloadFeaturedStatus()
      ui.toast('精选数据导入已重新排队')
    } catch (cause) {
      ui.toast(cause instanceof Error ? cause.message : '重试精选数据导入失败')
    } finally {
      importingFeatured.value = false
    }
    return
  }
  await importFeatured()
}

function featuredImportLabel(): string {
  if (importingFeatured.value) return '正在排队…'
  const active = featuredStatus.value?.activeTask
  if (active?.status === 'queued') return '等待导入 Worker'
  if (active?.phase === 'validating') return '正在校验数据包'
  if (active?.phase === 'staging') return `准备导入数据${active.progressPercent === null ? '' : ` · ${Math.round(active.progressPercent)}%`}`
  if (active?.phase === 'importing' || active?.phase === 'finalizing') return '正在写入本地分析库'
  if (featuredStatus.value?.alreadyCurrent) return '已导入当前版本'
  if (featuredStatus.value?.latestTask?.status === 'failed' && featuredStatus.value.latestTask.bundleHash === featuredStatus.value.bundleHash) return '重试导入'
  return '导入精选仓库'
}

async function exportFeatured() {
  if (!featuredStatus.value?.available || exportingFeatured.value) return
  exportingFeatured.value = true
  try {
    const blob = await source.exportFeaturedDataset()
    downloadBlob(blob, `repovantage-dataset-${featuredStatus.value.version ?? 'featured-v1'}.zip`)
    ui.toast('精选数据包已开始下载')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '下载精选数据包失败')
  } finally {
    exportingFeatured.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-[18px] px-7 pb-8 pt-[22px]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="m-0 text-[24px] font-semibold">仓库</h1>
        <p class="mt-1.5 text-muted">我的分析库与公开仓库发现</p>
      </div>
      <div class="flex flex-col items-end gap-1">
        <div class="flex items-center gap-1.5">
          <GdButton
            variant="outline"
            size="sm"
            :loading="importingFeatured || Boolean(featuredStatus?.activeTask)"
            :disabled="!featuredStatus?.available || Boolean(featuredStatus?.activeTask) || Boolean(featuredStatus?.alreadyCurrent)"
            :title="featuredStatus?.reason ?? undefined"
            @click="handleFeaturedImport"
          >
            {{ featuredImportLabel() }}
          </GdButton>
          <GdButton variant="ghost" size="sm" :disabled="!featuredStatus?.available || exportingFeatured" @click="exportFeatured">
            <Download :size="13" />{{ exportingFeatured ? '准备下载…' : '下载数据包' }}
          </GdButton>
        </div>
        <span v-if="featuredStatus?.activeTask" class="text-right text-[10.5px] text-muted">
          {{ featuredStatus.activeTask.message ?? '正在导入精选数据' }}
          <template v-if="featuredStatus.activeTask.progressKind === 'records' && featuredStatus.activeTask.totalRecords">
            · {{ featuredStatus.activeTask.processedRecords.toLocaleString('zh-CN') }}/{{ featuredStatus.activeTask.totalRecords.toLocaleString('zh-CN') }} 条
          </template>
        </span>
        <span v-else-if="featuredStatus?.latestTask?.status === 'failed' && featuredStatus.latestTask.bundleHash === featuredStatus.bundleHash && !featuredStatus.alreadyCurrent" class="max-w-[420px] text-right text-[10.5px] text-danger">
          {{ featuredStatus.latestTask.errorMessage ?? '上次导入失败，可重试' }}
        </span>
        <span v-else-if="featuredStatus?.available" class="text-[10.5px] text-muted">
          {{ featuredStatus.importedRepositories }}/{{ featuredStatus.totalRepositories }} 已导入 · {{ featuredStatus.version }}
          <span v-if="featuredStatus.isDemo"> · 演示状态</span>
        </span>
        <span v-else class="max-w-[360px] text-right text-[10.5px] text-muted">{{ featuredStatusError ?? featuredStatus?.reason ?? '正在读取内置数据包状态…' }}</span>
      </div>
    </div>

    <div class="flex gap-[22px] border-b border-line text-[13px]">
      <button class="flex h-[38px] items-center" :class="tab === 'library' ? 'border-b-2 border-ink font-semibold' : 'text-muted hover:text-ink'" @click="tab = 'library'">我的仓库</button>
      <button class="flex h-[38px] items-center" :class="tab === 'search' ? 'border-b-2 border-ink font-semibold' : 'text-muted hover:text-ink'" @click="tab = 'search'">发现仓库</button>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <GdInput v-model="query" size="sm" :placeholder="tab === 'library' ? '搜索已加入的仓库' : '搜索 GitHub 仓库或关键词'" class="max-w-[320px] flex-1" @enter="tab === 'search' && searchGithub()">
        <template #icon><Search :size="15" class="text-muted" /></template>
      </GdInput>
      <select v-if="tab === 'library'" v-model="status" class="h-[38px] rounded-lg border border-line bg-panel px-2.5 text-[12.5px] text-muted outline-none">
        <option value="all">数据状态：全部</option>
        <option value="ready">已完成</option>
        <option value="partial">部分数据</option>
        <option value="running">正在更新</option>
        <option value="failed">采集失败</option>
        <option value="idle">尚未分析</option>
      </select>
      <GdButton v-if="tab === 'library'" variant="outline" size="sm" :disabled="!filtered.length || clearingSelected" title="全选当前搜索和状态筛选结果" @click="toggleAllFiltered">
        <ListChecks :size="13" />{{ allFilteredSelected ? '取消当前全选' : '全选当前列表' }}
      </GdButton>
      <GdButton v-else size="sm" :disabled="searching" @click="searchGithub">{{ searching ? '搜索中…' : '搜索 GitHub' }}</GdButton>
    </div>

    <GdCard padding="sm" class="h-[520px] overflow-hidden">
      <div class="hidden grid-cols-[24px_1.7fr_1fr_104px_96px_76px_132px] gap-3 border-b border-line px-1 pb-2 text-[11.5px] text-muted lg:grid">
        <span />
        <span>仓库</span><span>语言 / Stars</span><span>数据状态</span><span>上次分析</span><span>活动变化</span><span />
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        <p v-if="tab === 'library' && error" class="py-4 text-[12px] text-danger">加载仓库列表失败：{{ error }}</p>
        <p v-else-if="tab === 'search' && searchError" class="py-4 text-[12px] text-danger">{{ searchError }}</p>
        <div v-else-if="tab === 'library' && loading || tab === 'search' && searching" class="flex flex-col gap-2 py-2">
          <div v-for="i in 5" :key="i" class="h-14 animate-pulse rounded bg-track/60" />
        </div>
        <div v-else class="divide-y divide-line">
          <div v-for="repo in (tab === 'library' ? filtered : searchResults)" :key="repo.id" class="grid grid-cols-[24px_1fr] items-center gap-3 py-3 lg:grid-cols-[24px_1.7fr_1fr_104px_96px_76px_132px]">
            <input v-if="tab === 'library'" type="checkbox" :aria-label="`选择仓库 ${repo.fullName}`" data-testid="repository-select" :data-repository-id="repo.id" class="size-3.5 accent-ink" :disabled="clearingSelected || busyId === repo.id" :checked="selected.includes(repo.id)" @change="toggle(repo)" />
            <span v-else />
            <div class="min-w-0">
              <div class="truncate text-[13px] font-semibold">{{ repo.fullName }}</div>
              <div class="truncate text-[11.5px] text-muted">{{ repo.description ?? '无公开简介' }}</div>
            </div>
            <div class="hidden text-[11.5px] text-muted lg:block">{{ repo.language ?? '语言未知' }} · ★ {{ repo.stars?.toLocaleString('en-US') ?? '—' }}</div>
            <div class="hidden lg:block"><GdBadge :variant="statusMeta[repo.status].variant">{{ statusMeta[repo.status].text }}</GdBadge></div>
            <div class="hidden font-mono text-[11.5px] text-muted lg:block">{{ repo.lastAnalyzedAt ?? '—' }}</div>
            <div class="hidden font-mono text-[11.5px] lg:block" :class="repo.activityDelta === null || repo.activityDelta === 0 ? 'text-muted' : repo.activityDelta < 0 ? 'text-s1' : 'text-s3'">
              {{ repo.activityDelta === null ? '—' : `${repo.activityDelta > 0 ? '+' : ''}${repo.activityDelta}%` }}
            </div>
            <div class="col-span-2 flex items-center justify-end gap-2 lg:col-span-1">
              <RouterLink v-if="tab === 'library'"
                :to="`/repositories/${repo.id}/overview`"
                class="inline-flex h-7 items-center rounded-md border border-line bg-panel px-2.5 text-[12px] font-medium hover:bg-soft"
              >
                {{ repo.status === 'idle' ? '开始分析' : '查看分析' }}
              </RouterLink>
              <GdButton v-if="tab === 'library'" variant="ghost" size="sm" :disabled="clearingSelected || busyId === repo.id" @click="remove(repo)">移除</GdButton>
              <GdButton v-else size="sm" :disabled="repo.alreadyInLibrary || busyId === repo.id" @click="add(repo)">{{ repo.alreadyInLibrary ? '已在分析库' : busyId === repo.id ? '正在添加…' : '添加并分析' }}</GdButton>
            </div>
          </div>
          <p v-if="tab === 'library' && !filtered.length" class="py-6 text-center text-[12px] text-muted">没有匹配的仓库。</p>
          <p v-else-if="tab === 'search' && !searchResults.length && !searching" class="py-6 text-center text-[12px] text-muted">输入关键词并搜索 GitHub。</p>
        </div>
      </div>
      <div class="flex items-center justify-between pt-2 text-[11.5px] text-muted">
        <span>{{ tab === 'library' ? `分析库 ${filtered.length} 个仓库（最多加载 100 个）` : `搜索结果 ${searchResults.length} 个（最多显示 20 个）` }}</span>
      </div>
    </GdCard>

    <div v-if="selected.length" class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-soft px-3.5 py-2.5 text-[12.5px]">
      <span>已选择 {{ selected.length }} 个仓库<span class="text-muted"> · 删除最多支持 100 个，比较需选择 2–5 个</span></span>
      <div class="flex gap-2">
        <GdButton variant="ghost" size="sm" :disabled="clearingSelected" @click="selected = []">清除选择</GdButton>
        <GdButton variant="danger" size="sm" :loading="clearingSelected" :disabled="busyId !== null" @click="deleteSelectedRepositories"><Trash2 :size="12" />删除所选仓库及数据</GdButton>
        <GdButton data-testid="compare-selected" size="sm" :disabled="selected.length < 2 || selected.length > 5 || clearingSelected" @click="compare">进入比较 <ArrowRight :size="12" /></GdButton>
      </div>
    </div>
  </div>
</template>
