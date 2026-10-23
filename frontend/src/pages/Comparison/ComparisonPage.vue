<script setup lang="ts">
import { Download, Plus, TriangleAlert, X } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import ComparisonChart from '@/components/charts/ComparisonChart.vue'
import RankChart from '@/components/charts/RankChart.vue'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import type { ComparisonMode, TimeWindow } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'
import GdSegmented from '@/components/ui/GdSegmented.vue'

const ui = useUiStore()
const analysis = useAnalysisStore()
const source = useDataSource()
const exporting = ref(false)
const comparisonMode = ref<ComparisonMode>('same_period')
const windowOptions = [30, 90, 180].map((value) => ({ value, label: `${value} 天` }))
const setWindow = (value: string | number) => analysis.setWindow(value as TimeWindow)
const comparisonModeOptions = [
  { value: 'same_period', label: '同期对比', hint: '只比较共同完整周；耗时和发布间隔要求分析窗口一致。' },
  { value: 'individual_periods', label: '各自窗口', hint: '分别使用各仓库自身完整周和可用指标，时间范围可能不同。' },
]
const comparisonModeDescription = computed(() => comparisonMode.value === 'same_period'
  ? '只取所有仓库共同完整的自然周；Issue、PR 和发布间隔还要求观察窗口一致。'
  : '分别展示各仓库自身完整自然周与可用指标；窗口不同时适合比较各自活跃度和处理节奏，不代表同期排名。')
function setComparisonMode(value: string | number) {
  if (value === 'same_period' || value === 'individual_periods') comparisonMode.value = value
}

const { data, loading, error } = useAsyncData(
  () => analysis.compareIds.length >= 2
    ? source.getComparison(analysis.compareIds, analysis.timeWindow, comparisonMode.value)
    : Promise.resolve({ window: { start: '—', end: '—' }, requestedWindowDays: analysis.timeWindow, mode: comparisonMode.value, entries: [], notes: [] }),
  () => [analysis.compareIds.join(','), comparisonMode.value, analysis.timeWindow],
)

const canCompare = computed(() => analysis.compareIds.length >= 2)
const entries = computed(() => data.value?.entries ?? [])
const comparisonNotes = computed(() => (data.value?.notes ?? []).filter((note) => !entries.value.some((entry) => entry.windowReason && note === `${entry.label}：${entry.windowReason}`)))
const short = (label: string) => label.split('/')[1]
const issueItems = computed(() => entries.value.filter((e) => e.issueP50 !== null).map((e) => ({ label: short(e.label), value: e.issueP50 as number, color: e.color })))
const prItems = computed(() => entries.value.filter((e) => e.prP50 !== null).map((e) => ({ label: short(e.label), value: e.prP50 as number, color: e.color })))
const missingReason = (quality: string) => ({
  partial: '覆盖不完整',
  insufficient_samples: '样本不足',
  missing: '未采集',
  failed: '采集失败',
}[quality] ?? (comparisonMode.value === 'same_period' ? '观察窗口不一致' : '当前口径不可比'))
const issueMissing = computed(() => entries.value.filter((e) => e.issueP50 === null).map((e) => `${short(e.label)}：${e.windowAvailable ? missingReason(e.issueQuality) : '范围未覆盖'}`))
const prMissing = computed(() => entries.value.filter((e) => e.prP50 === null).map((e) => `${short(e.label)}：${e.windowAvailable ? missingReason(e.prQuality) : '范围未覆盖'}`))
const totalCommits = (entry: (typeof entries.value)[number]) => entry.points.length && entry.points.every((point) => point.value !== null)
  ? entry.points.reduce((sum, point) => sum + (point.value ?? 0), 0).toLocaleString('en-US')
  : '—'
const entryWindow = (entry: (typeof entries.value)[number]) => entry.windowStart && entry.windowEnd
  ? `${entry.windowStart} 至 ${entry.windowEnd}`
  : '—'

async function exportComparison() {
  exporting.value = true
  try {
    downloadBlob(await source.exportComparison(analysis.compareIds, analysis.timeWindow, comparisonMode.value), 'repovantage-comparison.csv')
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出比较结果失败')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-[18px] px-7 pb-8 pt-[22px]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="m-0 text-[24px] font-semibold">项目比较</h1>
        <p class="mt-1.5 text-muted">选择时间口径后比较活跃度、处理耗时与发布节奏</p>
      </div>
      <div v-if="canCompare" class="flex flex-wrap items-center gap-2">
        <GdSegmented :model-value="analysis.timeWindow" :options="windowOptions" aria-label="比较时间范围" data-testid="comparison-window" @update:model-value="setWindow" />
        <GdSegmented :model-value="comparisonMode" :options="comparisonModeOptions" size="md" aria-label="选择对比方式" data-testid="comparison-mode" @update:model-value="setComparisonMode" />
        <GdButton variant="outline" :disabled="exporting || loading" data-testid="export-comparison" @click="exportComparison"><Download :size="14" /> {{ exporting ? '正在导出…' : '导出报告数据' }}</GdButton>
      </div>
    </div>

    <GdCard v-if="!canCompare">
      <h3 class="m-0 text-[15.5px] font-semibold">先选择 2–5 个仓库</h3>
      <p class="mt-1 text-[12px] text-muted">去仓库列表勾选至少两个仓库后，可以选择同期或各自窗口进行对比。</p>
      <RouterLink to="/repositories" class="gd-link mt-3 inline-flex text-[12px]"><Plus :size="12" /> 选择仓库</RouterLink>
    </GdCard>

    <template v-else>

    <p class="-mt-2 text-[11.5px] text-muted" data-testid="comparison-description" :data-window-days="data?.requestedWindowDays" :data-mode="data?.mode" :aria-busy="loading">{{ analysis.timeWindow }} 天 · {{ comparisonModeDescription }}</p>

    <div v-for="entry in entries.filter((item) => !item.windowAvailable)" :key="entry.id" class="rounded-md bg-warnbg px-3 py-2 text-[12px] text-warnfg" data-testid="comparison-window-unavailable">
      {{ entry.label }}：{{ entry.windowReason ?? '所选范围未覆盖' }}
      <RouterLink :to="`/repositories/${entry.id}/overview`" class="gd-link ml-2">前往按所选范围采集</RouterLink>
    </div>

    <div class="flex flex-wrap gap-2">
      <span v-for="entry in entries" :key="entry.id" class="inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 py-1.5 text-[12px]">
        <i class="size-2 rounded-sm" :style="{ background: entry.color }" />
        {{ entry.label }}
        <button class="text-muted hover:text-ink" @click="analysis.toggleCompare(entry.id)"><X :size="12" /></button>
      </span>
      <RouterLink to="/repositories" class="inline-flex items-center gap-1 rounded-md border border-line bg-panel px-2.5 py-1.5 text-[12px] text-muted hover:text-ink">
        <Plus :size="12" /> 添加仓库
      </RouterLink>
    </div>

    <div v-if="error || comparisonNotes.length" class="flex items-start gap-2 rounded-md bg-warnbg px-3 py-2.5 text-[11.5px] leading-relaxed text-warnfg">
      <TriangleAlert :size="14" class="mt-0.5 shrink-0" />
      <span>{{ error ?? comparisonNotes.join(' ') }}</span>
    </div>

    <GdCard>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">开发活动对比</h3>
          <p class="mt-0.5 text-[12px] text-muted">每周提交数 · {{ analysis.timeWindow }} 天 · {{ data?.window.start }} 至 {{ data?.window.end }}{{ comparisonMode === 'individual_periods' ? ' · 各仓库独立窗口' : ' · 共同完整周' }}；Release 固定近 365 天</p>
        </div>
        <div class="flex flex-wrap items-center gap-3 text-[11px] text-muted">
          <span v-for="entry in entries" :key="entry.id" class="flex items-center gap-1">
            {{ short(entry.label) }}
            <GdCoverageNote :coverage="entry.coverage" compact />
          </span>
        </div>
      </div>
      <div v-if="loading" class="h-[280px] animate-pulse rounded bg-track/60" />
      <p v-if="error" class="py-8 text-center text-[12px] text-danger">比较数据加载失败：{{ error }}</p>
      <ComparisonChart v-else-if="entries.some((entry) => entry.points.length)" :entries="entries.map((e) => ({ label: e.label.split('/')[1], color: e.color, points: e.points }))" :height="280" />
      <p v-else-if="!loading" class="py-8 text-center text-[12px] text-muted">{{ comparisonMode === 'same_period' ? '所选仓库没有共同的完整 Commit 周，无法绘制同期曲线；可切换到「各自窗口」查看各仓库自身的活动。' : '各仓库自身窗口内都没有可用的完整 Commit 周。' }}</p>
      <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
        <span>单位：次 · SHA 去重 · 各仓库均为默认分支</span>
        <span>曲线在某周中断表示该仓库的采集到此结束，不用 0 补齐</span>
      </div>
    </GdCard>

    <div class="grid gap-4 lg:grid-cols-2">
      <GdCard>
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">Issue 关闭耗时</h3>
            <p class="mt-0.5 text-[12px] text-muted">中位数（天）· 仅统计可比较且覆盖完整的样本</p>
          </div>
        </div>
        <RankChart :items="issueItems" :height="150" value-suffix=" 天" />
        <div class="flex flex-wrap gap-3 text-[11px] text-muted">
          <span v-for="entry in entries.filter((e) => e.issueP50 !== null)" :key="entry.id">{{ short(entry.label) }} · n={{ entry.issueSample }}</span>
          <span v-if="issueMissing.length" class="text-warnfg">{{ issueMissing.join(' / ') }}，显示 —</span>
        </div>
      </GdCard>

      <GdCard>
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">PR 合并耗时</h3>
            <p class="mt-0.5 text-[12px] text-muted">中位数（天）· 数据缺失时不参与对比</p>
          </div>
        </div>
        <RankChart :items="prItems" :height="150" value-suffix=" 天" />
        <div class="flex flex-wrap gap-3 text-[11px] text-muted">
          <span v-for="entry in entries.filter((e) => e.prP50 !== null)" :key="entry.id">{{ short(entry.label) }} · n={{ entry.prSample }}</span>
          <span v-if="prMissing.length" class="text-warnfg">{{ prMissing.join(' / ') }}，显示 —</span>
        </div>
      </GdCard>
    </div>

    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">综合对照表</h3>
          <p class="mt-0.5 text-[12px] text-muted">指标、单位、有效样本与采集时间</p>
        </div>
        <button class="gd-link text-[11.5px]" :disabled="exporting" @click="exportComparison">下载</button>
      </div>
      <table class="w-full border-collapse text-[12.5px]">
        <thead>
          <tr class="text-left text-[11.5px] text-muted">
            <th class="border-b border-line px-2.5 pb-2 font-medium">仓库</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">提交数</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">Issue P50</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">PR P50</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">发布间隔 P50</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">覆盖状态</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">观察窗口</th>
            <th class="border-b border-line px-2.5 pb-2 font-medium">采集时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.id" data-testid="comparison-row" :data-repository-id="entry.id" :data-window-available="entry.windowAvailable">
            <td class="border-b border-line px-2.5 py-2.5">{{ entry.label }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ totalCommits(entry) }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.issueP50 === null ? '—' : `${entry.issueP50} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.prP50 === null ? '—' : `${entry.prP50} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.releaseMedianDays === null ? '—' : `${entry.releaseMedianDays.toLocaleString('en-US', { maximumFractionDigits: 1 })} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5">
              <GdBadge :variant="entry.coverage.state === 'complete' ? 'default' : 'warn'">{{ entry.windowAvailable ? entry.coverage.label : '范围未覆盖' }}</GdBadge>
            </td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono text-muted">{{ entryWindow(entry) }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono text-muted">{{ entry.collectedAt }}</td>
          </tr>
        </tbody>
      </table>
    </GdCard>
    </template>
  </div>
</template>
