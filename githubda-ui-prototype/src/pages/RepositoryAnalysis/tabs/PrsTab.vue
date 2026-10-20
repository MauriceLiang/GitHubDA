<script setup lang="ts">
import { ref } from 'vue'
import GroupedChart from '@/components/charts/GroupedChart.vue'
import HistogramChart from '@/components/charts/HistogramChart.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import type { RepositoryAnalysis } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const ui = useUiStore()
const source = useDataSource()
const exporting = ref(false)

async function exportCsv() {
  exporting.value = true
  try {
    downloadBlob(await source.exportInsights(props.analysis.repository.id), `${props.analysis.repository.id}-insights.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出分析结果失败')
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

    <GdCard>
      <div class="flex items-center justify-between gap-3">
        <h3 class="m-0 text-[15.5px] font-semibold">PR 逐条记录</h3>
        <GdButton variant="outline" size="sm" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '导出聚合 CSV' }}</GdButton>
      </div>
      <div class="mt-3 rounded-md bg-warnbg px-3 py-2.5 text-[11.5px] leading-relaxed text-warnfg">
        当前后端没有提供 PR 标题、编号、未合并列表或评论明细。CSV 导出的是已采集的周聚合和耗时指标。
      </div>
    </GdCard>
  </div>
</template>
