<script setup lang="ts">
import { ArrowRight, Download, Search } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
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
const { data: repositories, loading, error, reload } = useAsyncData(() => source.listRepositories())
const { data: featuredData, error: featuredStatusError, reload: reloadFeaturedStatus } = useAsyncData(() => source.getFeaturedDatasetStatus())
const featuredStatus = ref<FeaturedDatasetStatus | null>(null)
const importingFeatured = ref(false)
const exportingFeatured = ref(false)

watch(featuredData, (value) => { if (value) featuredStatus.value = value }, { immediate: true })

watch(tab, () => { searchError.value = null })

const filtered = computed(() =>
  (repositories.value ?? []).filter((repo) => {
    const matchesQuery = !query.value || repo.fullName.toLowerCase().includes(query.value.toLowerCase()) || (repo.description ?? '').toLowerCase().includes(query.value.toLowerCase())
    const matchesStatus = status.value === 'all' || repo.status === status.value
    return matchesQuery && matchesStatus
  }),
)

const statusMeta: Record<RepositoryStatus, { text: string; variant: 'default' | 'warn' | 'plain' }> = {
  ready: { text: '已完成', variant: 'default' },
  partial: { text: '部分数据', variant: 'warn' },
  running: { text: '正在更新', variant: 'default' },
  failed: { text: '采集失败', variant: 'warn' },
  idle: { text: '尚未分析', variant: 'plain' },
}

function toggle(repo: RepositorySummary) {
  if (selected.value.includes(repo.id)) selected.value = selected.value.filter((id) => id !== repo.id)
  else if (selected.value.length >= 5) ui.toast('最多同时比较 5 个仓库')
  else selected.value = [...selected.value, repo.id]
}

function compare() {
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

async function importFeatured() {
  if (!featuredStatus.value?.available || importingFeatured.value) return
  importingFeatured.value = true
  try {
    const result = await source.importFeaturedDataset()
    await Promise.all([reload(), reloadFeaturedStatus()])
    ui.toast(`精选仓库导入完成：新增 ${result.importedCount} 个，已存在 ${result.alreadyPresentCount} 个；快照 ${result.snapshotCount} 份、活动记录 ${result.eventCount} 条${result.warningCount ? `，${result.warningCount} 项数据提示` : ''}`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导入精选仓库失败')
  } finally {
    importingFeatured.value = false
  }
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
          <GdButton variant="outline" size="sm" :disabled="!featuredStatus?.available || importingFeatured" :title="featuredStatus?.reason ?? undefined" @click="importFeatured">
            {{ importingFeatured ? '正在导入…' : '导入精选仓库' }}
          </GdButton>
          <GdButton variant="ghost" size="sm" :disabled="!featuredStatus?.available || exportingFeatured" @click="exportFeatured">
            <Download :size="13" />{{ exportingFeatured ? '准备下载…' : '下载数据包' }}
          </GdButton>
        </div>
        <span v-if="featuredStatus?.available" class="text-[10.5px] text-muted">{{ featuredStatus.importedRepositories }}/{{ featuredStatus.totalRepositories }} 已导入 · {{ featuredStatus.version }}</span>
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
            <input v-if="tab === 'library'" type="checkbox" class="size-3.5 accent-ink" :checked="selected.includes(repo.id)" @change="toggle(repo)" />
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
              <GdButton v-if="tab === 'library'" variant="ghost" size="sm" :disabled="busyId === repo.id" @click="remove(repo)">移除</GdButton>
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
      <span>已选择 {{ selected.length }} 个仓库{{ selected.length === 1 ? '，再选 1 个可比较' : '' }}</span>
      <div class="flex gap-2">
        <GdButton variant="ghost" size="sm" @click="selected = []">清除</GdButton>
        <GdButton size="sm" :disabled="selected.length < 2" @click="compare">进入比较 <ArrowRight :size="12" /></GdButton>
      </div>
    </div>
  </div>
</template>
