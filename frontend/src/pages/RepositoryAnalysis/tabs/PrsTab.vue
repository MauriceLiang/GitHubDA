<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GroupedChart from '@/components/charts/GroupedChart.vue'
import HistogramChart from '@/components/charts/HistogramChart.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import GdInput from '@/components/ui/GdInput.vue'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import type { PullRequestActivityPage, PullRequestActivityRecord, RepositoryAnalysis } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const ui = useUiStore()
const source = useDataSource()
const pageSize = 10
const page = ref(1)
const searchInput = ref('')
const appliedSearch = ref('')
const records = ref<PullRequestActivityPage | null>(null)
const loading = ref(false)
const exporting = ref(false)
const loadError = ref('')
let requestVersion = 0
let detailRequest = 0

const pageCount = computed(() => Math.max(1, Math.ceil((records.value?.total ?? 0) / pageSize)))
const firstRecord = computed(() => records.value?.total ? (page.value - 1) * pageSize + 1 : 0)
const lastRecord = computed(() => Math.min(page.value * pageSize, records.value?.total ?? 0))

async function loadRecords() {
  const version = ++requestVersion
  loading.value = true
  loadError.value = ''
  records.value = null
  try {
    const result = await source.getPullRequestRecords(props.analysis.repository.id, page.value, pageSize, appliedSearch.value)
    if (version === requestVersion) records.value = result
  } catch (cause) {
    if (version === requestVersion) loadError.value = cause instanceof Error ? cause.message : 'Pull Request 记录加载失败'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

watch([() => props.analysis.repository.id, page, appliedSearch], () => { void loadRecords() }, { immediate: true })

function applySearch() {
  const next = searchInput.value.trim()
  if (page.value === 1 && appliedSearch.value === next) {
    void loadRecords()
    return
  }
  page.value = 1
  appliedSearch.value = next
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(0, 10)
}

function formatTime(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : `${date.toISOString().slice(11, 19)} UTC`
}

function formatDuration(value: number | null) {
  return value === null ? '—' : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 天`
}

async function openPullRequest(item: PullRequestActivityRecord) {
  const requestId = ++detailRequest
  const payload = {
    repositoryId: props.analysis.repository.id,
    number: String(item.number),
    title: item.title,
    createdAt: item.createdAt ?? '',
    closedAt: item.closedAt ?? '',
    mergedAt: item.mergedAt ?? '',
    durationDays: formatDuration(item.durationDays),
    commentsCount: String(item.commentsCount),
    state: item.state,
    draft: String(item.draft),
    url: item.url ?? '',
    onlineStatus: 'idle',
    bodyStatus: 'loading',
  }
  ui.openDrawer('pr', payload)
  try {
    const detail = await source.getPullRequestDetail(props.analysis.repository.id, item.number)
    if (requestId !== detailRequest || ui.drawerKind !== 'pr' || ui.drawerPayload?.number !== String(item.number)) return
    if (ui.drawerPayload?.onlineStatus === 'loading' || ui.drawerPayload?.onlineStatus === 'ready') return
    ui.openDrawer('pr', { ...payload, bodyStatus: 'ready', body: detail.body ?? '', commentsCount: String(detail.commentsCount) })
  } catch (cause) {
    if (requestId !== detailRequest || ui.drawerKind !== 'pr' || ui.drawerPayload?.number !== String(item.number)) return
    ui.openDrawer('pr', { ...payload, bodyStatus: 'error', bodyError: cause instanceof Error ? cause.message : '无法读取该 Pull Request 的详细内容' })
  }
}

async function exportCsv() {
  exporting.value = true
  try {
    downloadBlob(await source.exportPullRequestRecords(props.analysis.repository.id, appliedSearch.value), `${props.analysis.repository.id}-pull-requests.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出 Pull Request 记录失败')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <KpiStrip :metrics="analysis.metrics.metrics" />

  <GdCard>
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">PR 合并趋势</h3>
        <p class="mt-0.5 text-[12px] text-muted">按 merged_at 所在自然周统计 · 不代表合并率</p>
      </div>
      <GdCoverageNote :coverage="analysis.pullRequests.coverage" />
    </div>
    <GroupedChart :series="analysis.pullRequests.series" :unit="analysis.pullRequests.unit" :colors="['#2E8FCB']" :height="250" />
    <p class="text-[11px] text-muted">未覆盖或不完整的周保持空值；耗时包含采集到的已合并 PR。</p>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">合并耗时分布</h3>
          <p class="mt-0.5 text-[12px] text-muted">merged_at − created_at</p>
        </div>
        <span class="font-mono text-[11.5px] text-muted">n={{ analysis.prDuration.sampleSize }}</span>
      </div>
      <HistogramChart :buckets="analysis.prDuration.buckets" color="#CE3F7C" unit="个 PR" :height="200" />
      <div class="text-[11px] text-muted">P50 {{ analysis.prDuration.percentiles.p50 ?? '—' }} 天 · P75 {{ analysis.prDuration.percentiles.p75 ?? '—' }} 天 · P90 {{ analysis.prDuration.percentiles.p90 ?? '—' }} 天</div>
      <p v-if="analysis.prDuration.note" class="mt-2 text-[11px] text-warnfg">{{ analysis.prDuration.note }}</p>
    </GdCard>

    <GdCard class="h-[420px] min-h-0 overflow-hidden">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex min-w-0 items-center gap-2">
          <h3 class="m-0 text-[15.5px] font-semibold">PR 逐条记录</h3>
          <GdCoverageNote v-if="records" :coverage="records.coverage" compact />
        </div>
        <GdButton variant="outline" size="sm" :disabled="exporting || loading || !records?.available" @click="exportCsv">{{ exporting ? '导出中…' : '导出 PR CSV' }}</GdButton>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <GdInput v-model="searchInput" size="sm" class="min-w-[190px] flex-1" placeholder="搜索 PR 编号或标题" @enter="applySearch" />
        <GdButton variant="outline" size="sm" :disabled="loading" @click="applySearch">搜索</GdButton>
        <span v-if="records?.available" class="shrink-0 text-[11px] text-muted">{{ records.total.toLocaleString('zh-CN') }} 条 · {{ formatDate(records.windowStart) }} 至 {{ formatDate(records.windowEnd) }}</span>
      </div>

      <p v-if="records?.note" class="m-0 text-[11px] leading-relaxed text-muted">{{ records.note }}</p>

      <div v-if="loading" class="min-h-0 flex-1 overflow-y-auto py-8 text-center text-[12px] text-muted" role="status">正在加载 PR 记录…</div>
      <div v-else-if="loadError" class="min-h-0 flex-1 overflow-y-auto py-6 text-center text-[12px] text-danger">
        <p class="mb-3">{{ loadError }}</p>
        <GdButton variant="outline" size="sm" @click="loadRecords">重新加载</GdButton>
      </div>
      <div v-else-if="records && !records.available" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] leading-relaxed text-muted">{{ records.note }}</div>
      <div v-else-if="records && records.total === 0" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] text-muted">{{ appliedSearch ? '没有找到匹配的 PR。' : '本次采集窗口内没有已关闭的 PR。' }}</div>
      <div v-else class="min-h-0 flex-1 overflow-auto overscroll-contain">
        <table class="w-full min-w-[560px] table-fixed border-collapse text-[12px]">
          <thead class="sticky top-0 z-10 bg-panel">
            <tr class="text-left text-[11px] text-muted">
              <th class="w-[48px] border-b border-line px-1.5 pb-2 font-medium">编号</th>
              <th class="w-[170px] border-b border-line px-1.5 pb-2 font-medium">标题</th>
              <th class="w-[84px] border-b border-line px-1.5 pb-2 font-medium">状态</th>
              <th class="w-[82px] border-b border-line px-1.5 pb-2 font-medium">创建时间</th>
              <th class="w-[82px] border-b border-line px-1.5 pb-2 font-medium">合并/关闭</th>
              <th class="w-[48px] border-b border-line px-1.5 pb-2 text-right font-medium">评论</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in records?.items" :key="item.number" class="border-b border-line/70 last:border-0">
              <td class="whitespace-nowrap px-1.5 py-2.5 font-mono text-ink">
                <button type="button" class="underline decoration-line underline-offset-2 hover:decoration-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" @click="openPullRequest(item)">#{{ item.number }}</button>
              </td>
              <td class="px-1.5 py-2.5 text-ink" :title="item.title"><button type="button" class="line-clamp-2 text-left hover:underline focus-visible:underline" @click="openPullRequest(item)">{{ item.title }}</button><span v-if="item.draft" class="text-[10px] text-muted">草稿</span></td>
              <td class="whitespace-nowrap px-1.5 py-2.5"><GdBadge :variant="item.state === 'merged' ? 'default' : 'warn'">{{ item.state === 'merged' ? '已合并' : '关闭未合并' }}</GdBadge></td>
              <td class="whitespace-nowrap px-1.5 py-2 font-mono text-[10.5px] text-ink"><span>{{ formatDate(item.createdAt) }}</span><span class="block text-[9px] leading-3 text-ink/70">{{ formatTime(item.createdAt) }}</span></td>
              <td class="whitespace-nowrap px-1.5 py-2 font-mono text-[10.5px] text-ink"><span>{{ formatDate(item.mergedAt ?? item.closedAt) }}</span><span class="block text-[9px] leading-3 text-ink/70">{{ formatTime(item.mergedAt ?? item.closedAt) }}</span></td>
              <td class="whitespace-nowrap px-1.5 py-2.5 text-right text-[11px] text-ink">{{ item.commentsCount }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="records?.available && records.total > 0" class="flex shrink-0 items-center justify-between gap-2 border-t border-line pt-2 text-[11px] text-muted">
        <span>显示 {{ firstRecord }}–{{ lastRecord }} / {{ records.total }}</span>
        <div class="flex items-center gap-2">
          <GdButton variant="outline" size="sm" :disabled="loading || page <= 1" @click="page -= 1">上一页</GdButton>
          <span class="font-mono">{{ page }} / {{ pageCount }}</span>
          <GdButton variant="outline" size="sm" :disabled="loading || page >= pageCount" @click="page += 1">下一页</GdButton>
        </div>
      </div>
    </GdCard>
  </div>
</template>
