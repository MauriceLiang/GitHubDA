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
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const analysis = useAnalysisStore()
const source = useDataSource()
const exporting = ref(false)

const { data, loading, error } = useAsyncData(
  () => analysis.compareIds.length >= 2
    ? source.getComparison(analysis.compareIds, analysis.timeWindow)
    : Promise.resolve({ window: { start: '—', end: '—' }, entries: [], notes: [] }),
  () => [analysis.compareIds.join(',')],
)

const canCompare = computed(() => analysis.compareIds.length >= 2)
const entries = computed(() => data.value?.entries ?? [])
const short = (label: string) => label.split('/')[1]
const issueItems = computed(() => entries.value.filter((e) => e.issueP50 !== null).map((e) => ({ label: short(e.label), value: e.issueP50 as number, color: e.color })))
const prItems = computed(() => entries.value.filter((e) => e.prP50 !== null).map((e) => ({ label: short(e.label), value: e.prP50 as number, color: e.color })))
const issueMissing = computed(() => entries.value.filter((e) => e.issueP50 === null).map((e) => short(e.label)))
const prMissing = computed(() => entries.value.filter((e) => e.prP50 === null).map((e) => short(e.label)))
const totalCommits = (entry: (typeof entries.value)[number]) => entry.points.length && entry.points.every((point) => point.value !== null)
  ? entry.points.reduce((sum, point) => sum + (point.value ?? 0), 0).toLocaleString('en-US')
  : '—'

async function exportComparison() {
  exporting.value = true
  try {
    downloadBlob(await source.exportComparison(analysis.compareIds), 'githubda-comparison.csv')
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
        <p class="mt-1.5 text-muted">同一时间窗口、同一统计口径 · 只陈列差异，不生成排名</p>
      </div>
      <GdButton v-if="canCompare" variant="outline" :disabled="exporting" @click="exportComparison"><Download :size="14" /> {{ exporting ? '正在导出…' : '导出报告数据' }}</GdButton>
    </div>

    <GdCard v-if="!canCompare">
      <h3 class="m-0 text-[15.5px] font-semibold">先选择 2–5 个仓库</h3>
      <p class="mt-1 text-[12px] text-muted">比较只使用共同完整自然周；去仓库列表勾选至少两个仓库后再查看结果。</p>
      <RouterLink to="/repositories" class="gd-link mt-3 inline-flex text-[12px]"><Plus :size="12" /> 选择仓库</RouterLink>
    </GdCard>

    <template v-else>

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

    <div v-if="error || data?.notes.length" class="flex items-start gap-2 rounded-md bg-warnbg px-3 py-2.5 text-[11.5px] leading-relaxed text-warnfg">
      <TriangleAlert :size="14" class="mt-0.5 shrink-0" />
      <span>{{ error ?? data?.notes.join(' ') }}</span>
    </div>

    <GdCard>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">开发活动对比</h3>
          <p class="mt-0.5 text-[12px] text-muted">每周提交数 · {{ data?.window.start }} 至 {{ data?.window.end }}</p>
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
      <p v-else-if="!loading" class="py-8 text-center text-[12px] text-muted">所选仓库没有共同的完整 Commit 周，无法绘制对比曲线。</p>
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
            <p class="mt-0.5 text-[12px] text-muted">中位数（天）· 灰色表示样本缺失</p>
          </div>
        </div>
        <RankChart :items="issueItems" :height="150" value-suffix=" 天" />
        <div class="flex flex-wrap gap-3 text-[11px] text-muted">
          <span v-for="entry in entries.filter((e) => e.issueP50 !== null)" :key="entry.id">{{ short(entry.label) }} · n={{ entry.issueSample }}</span>
          <span v-if="issueMissing.length" class="text-warnfg">{{ issueMissing.join(' / ') }}：样本不足，显示 —</span>
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
          <span v-if="prMissing.length" class="text-warnfg">{{ prMissing.join(' / ') }}：样本不足，显示 —</span>
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
            <th class="border-b border-line px-2.5 pb-2 font-medium">采集时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.id">
            <td class="border-b border-line px-2.5 py-2.5">{{ entry.label }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ totalCommits(entry) }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.issueP50 === null ? '—' : `${entry.issueP50} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.prP50 === null ? '—' : `${entry.prP50} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ entry.releaseMedianDays === null ? '—' : `${entry.releaseMedianDays.toLocaleString('en-US', { maximumFractionDigits: 1 })} 天` }}</td>
            <td class="border-b border-line px-2.5 py-2.5">
              <GdBadge :variant="entry.coverage.state === 'complete' ? 'default' : 'warn'">{{ entry.coverage.label }}</GdBadge>
            </td>
            <td class="border-b border-line px-2.5 py-2.5 font-mono text-muted">{{ entry.collectedAt }}</td>
          </tr>
        </tbody>
      </table>
    </GdCard>
    </template>
  </div>
</template>
