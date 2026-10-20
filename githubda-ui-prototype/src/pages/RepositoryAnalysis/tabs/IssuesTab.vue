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
        <h3 class="m-0 text-[15.5px] font-semibold">Issue 关闭趋势</h3>
        <p class="mt-0.5 text-[12px] text-muted">按 closed_at 所在自然周统计 · 已排除 Pull Request</p>
      </div>
      <GdCoverageNote :coverage="analysis.issues.coverage" />
    </div>
    <GroupedChart :series="analysis.issues.series" :unit="analysis.issues.unit" :colors="['#CE3F7C']" :height="250" />
    <p class="text-[11px] text-muted">未覆盖或不完整的周保持空值；关闭耗时只纳入有效 created_at 与 closed_at 样本。</p>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">关闭耗时分布</h3>
          <p class="mt-0.5 text-[12px] text-muted">closed_at − created_at · 仅统计窗口内关闭事件</p>
        </div>
        <span class="font-mono text-[11.5px] text-muted">n={{ analysis.issueDuration.sampleSize }}</span>
      </div>
      <HistogramChart :buckets="analysis.issueDuration.buckets" color="#E5A03A" unit="个 Issue" :height="200" />
      <div class="text-[11px] text-muted">P50 {{ analysis.issueDuration.percentiles.p50 ?? '—' }} 天 · P75 {{ analysis.issueDuration.percentiles.p75 ?? '—' }} 天 · P90 {{ analysis.issueDuration.percentiles.p90 ?? '—' }} 天</div>
      <p v-if="analysis.issueDuration.note" class="mt-2 text-[11px] text-warnfg">{{ analysis.issueDuration.note }}</p>
    </GdCard>

    <GdCard>
      <div class="flex items-center justify-between gap-3">
        <h3 class="m-0 text-[15.5px] font-semibold">Issue 逐条记录</h3>
        <GdButton variant="outline" size="sm" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '导出聚合 CSV' }}</GdButton>
      </div>
      <div class="mt-3 rounded-md bg-warnbg px-3 py-2.5 text-[11.5px] leading-relaxed text-warnfg">
        当前后端仅提供按周计数和耗时分布，没有返回 Issue 标题、编号或逐条时间戳。CSV 导出的是当前聚合指标。
      </div>
    </GdCard>
  </div>
</template>
