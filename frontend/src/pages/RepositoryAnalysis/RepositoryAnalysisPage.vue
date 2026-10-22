<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ModuleTabs from '@/components/layout/ModuleTabs.vue'
import RepoHeader from '@/components/layout/RepoHeader.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdEmptyState from '@/components/ui/GdEmptyState.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositoryAnalysis } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'
import OverviewTab from './tabs/OverviewTab.vue'
import ActivityTab from './tabs/ActivityTab.vue'
import IssuesTab from './tabs/IssuesTab.vue'
import PrsTab from './tabs/PrsTab.vue'
import ReleasesTab from './tabs/ReleasesTab.vue'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const analysisStore = useAnalysisStore()
const source = useDataSource()
const refreshing = ref(false)
const clearing = ref(false)

const repoId = computed(() => String(route.params.id ?? ''))
const tab = computed(() => String(route.params.tab ?? 'overview'))
const tabComponent = computed(() => ({ overview: OverviewTab, activity: ActivityTab, issues: IssuesTab, prs: PrsTab, releases: ReleasesTab }[tab.value] ?? OverviewTab))

const { data, loading, error, reload } = useAsyncData<RepositoryAnalysis>(
  () => source.getAnalysis(repoId.value, analysisStore.timeWindow, 'week'),
  () => [repoId.value, analysisStore.timeWindow],
)

watch(repoId, (id) => analysisStore.remember(id), { immediate: true })

const notAnalyzed = computed(() => data.value?.repository.status === 'idle')
const failed = computed(() => data.value?.repository.status === 'failed' || Boolean(error.value))

async function refresh(scopeKind: 'quick' | 'window' = 'quick') {
  refreshing.value = true
  try {
    const windowDays = analysisStore.timeWindow
    await source.refreshRepository(repoId.value, { scopeKind, windowDays })
    ui.toast(`已排队：${windowDays} 天 · ${scopeKind === 'window' ? '完整窗口采集' : '快速采集'}，可在任务页查看进度`)
    void router.push('/tasks')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '启动采集失败')
  } finally {
    refreshing.value = false
  }
}

async function clearCurrentRepositoryData() {
  const fullName = data.value?.repository.fullName ?? `仓库 #${repoId.value}`
  if (!window.confirm(`清除 ${fullName} 在本机保存的所有采集与分析数据，包括快照、活动记录、分析结果和原始归档？仓库资料、我的仓库归属与任务历史会保留；若它属于内置精选数据集，会标记为待重新导入。此操作不可撤销。`)) return
  clearing.value = true
  try {
    await source.clearRepositoryData([repoId.value])
    analysisStore.setCompare(analysisStore.compareIds.filter((id) => id !== repoId.value))
    await reload()
    ui.toast('已清除该仓库的本地采集与分析数据')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '清除仓库数据失败')
  } finally {
    clearing.value = false
  }
}

function openWeek(payload: { date: string; count: number }) {
  ui.openDrawer('commits', {
    repoId: repoId.value,
    weekLabel: payload.date,
    count: String(payload.count),
  })
}
</script>

<template>
  <ModuleTabs v-if="data && !notAnalyzed && !failed" :repo-id="repoId" :active="tab" />
  <div class="flex flex-col gap-[18px] px-7 pb-8 pt-[22px]">
    <RepoHeader
      v-if="data"
      :repository="data.repository"
      :coverage="data.coverage"
      :collected-at="data.collectedAt"
      :window-start="data.metrics.window.start"
      :window-end="data.metrics.window.end"
      :refreshing="refreshing"
      @refresh="refresh"
      :clearing="clearing"
      @clear="clearCurrentRepositoryData"
    />

    <div v-if="loading" class="flex flex-col gap-4">
      <div class="h-[92px] animate-pulse rounded-[10px] bg-track/70" />
      <div class="h-[360px] animate-pulse rounded-[10px] bg-track/70" />
      <div class="grid gap-4 lg:grid-cols-3">
        <div v-for="i in 3" :key="i" class="h-[220px] animate-pulse rounded-[10px] bg-track/70" />
      </div>
    </div>

    <GdCard v-else-if="failed">
      <GdEmptyState title="采集失败，暂时没有可展示的分析结果" :description="error ?? data?.coverage.detail ?? '请检查任务状态后重试。'">
        <template #action>
          <GdButton size="sm" class="mt-1" @click="refresh">重试采集</GdButton>
        </template>
      </GdEmptyState>
    </GdCard>

    <GdCard v-else-if="notAnalyzed">
      <GdEmptyState title="尚未分析这个仓库" description="还没有采集任何模块。开始分析后，这里会出现开发活动、Issue / PR 与发布节奏。">
        <template #action>
          <GdButton size="sm" class="mt-1" @click="refresh">开始分析</GdButton>
        </template>
      </GdEmptyState>
    </GdCard>

    <GdCard v-else-if="data && !data.windowAvailability.available" padding="sm" :gap="false">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 class="m-0 text-[15px] font-semibold">尚未采集所选的 {{ data.windowAvailability.requestedDays }} 天范围</h2>
          <p class="mb-0 mt-1 text-[12px] text-muted">{{ data.windowAvailability.reason ?? '当前没有覆盖该范围的分析运行。采集完成后会按所选日期重新计算指标。' }}</p>
        </div>
        <GdButton :disabled="refreshing || clearing" @click="refresh(analysisStore.collectionScope)">按所选范围采集</GdButton>
      </div>
    </GdCard>

    <component :is="tabComponent" v-else-if="data && data.windowAvailability.available" :analysis="data" @select-week="openWeek" />
  </div>
</template>
