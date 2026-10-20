<script setup lang="ts">
import { computed } from 'vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import type { RepositoryAnalysis } from '@/services/types'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const emit = defineEmits<{ 'select-week': [payload: { date: string; count: number }] }>()
const points = computed(() => props.analysis.commits.series[0]?.points ?? [])

function select(dataIndex: number) {
  const point = points.value[dataIndex]
  if (point && point.value !== null) emit('select-week', { date: point.date, count: point.value })
}
</script>

<template>
  <KpiStrip :metrics="analysis.metrics.metrics" />

  <GdCard>
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">Commit 周趋势</h3>
        <p class="mt-0.5 text-[12px] text-muted">默认分支 · SHA 去重 · UTC · {{ analysis.commits.window.start ?? '—' }} 至 {{ analysis.commits.window.end ?? '—' }}</p>
      </div>
      <GdCoverageNote :coverage="analysis.commits.coverage" />
    </div>
    <TrendChart :points="points" :unit="analysis.commits.unit" :height="260" @select="(payload) => select(payload.dataIndex)" />
    <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span>有效样本 {{ analysis.commits.sampleSize?.toLocaleString('en-US') ?? '—' }} · 灰色间断代表该周未达到完整覆盖口径。</span>
      <span>图表为周聚合；逐条 Commit 明细暂未由后端提供。</span>
    </div>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-2">
    <GdCard>
      <h3 class="m-0 text-[15.5px] font-semibold">当前可分析范围</h3>
      <div class="mt-3 grid grid-cols-2 gap-4">
        <div>
          <div class="text-[11px] text-muted">完整周数</div>
          <div class="mt-1 text-[24px] font-semibold">{{ points.filter((point) => point.value !== null).length }}</div>
        </div>
        <div class="border-l border-line pl-4">
          <div class="text-[11px] text-muted">观察 Commit 数</div>
          <div class="mt-1 text-[24px] font-semibold">{{ analysis.metrics.metrics[0]?.value?.toLocaleString('en-US') ?? '—' }}</div>
        </div>
      </div>
      <p class="mt-3 text-[11.5px] leading-relaxed text-muted">{{ analysis.commits.limitation ?? '趋势只统计已采集的自然周；后端未返回的日期保持空缺。' }}</p>
    </GdCard>

    <GdCard>
      <h3 class="m-0 text-[15.5px] font-semibold">尚未提供的活动明细</h3>
      <div class="mt-3 rounded-md bg-warnbg px-3 py-2.5 text-[11.5px] leading-relaxed text-warnfg">
        当前 API 提供自然周 Commit 聚合结果，没有日级序列、作者排行或逐条 Commit 记录，因此这些图表不会用估算值填充。
      </div>
    </GdCard>
  </div>
</template>
