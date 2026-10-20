<script setup lang="ts">
import { CalendarDays, Database, Download, ExternalLink, GitCompare, Info, RefreshCw, Scale, Code2 } from 'lucide-vue-next'
import { ref } from 'vue'
import type { Coverage, RepositorySummary, TimeWindow } from '@/services/types'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdIconButton from '@/components/ui/GdIconButton.vue'
import GdSegmented from '@/components/ui/GdSegmented.vue'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ repository: RepositorySummary; coverage: Coverage; collectedAt: string | null; windowStart: string | null; windowEnd: string | null; refreshing?: boolean }>()
const analysis = useAnalysisStore()
const ui = useUiStore()
const source = useDataSource()
const exporting = ref(false)
const statusMeta = {
  ready: { text: '已完成', variant: 'default' as const },
  partial: { text: '部分数据', variant: 'warn' as const },
  running: { text: '采集中', variant: 'plain' as const },
  idle: { text: '尚未分析', variant: 'plain' as const },
  failed: { text: '采集失败', variant: 'warn' as const },
}
const windowOptions = [
  { value: 30, label: '30 天', disabled: true, hint: '当前后端指标按固定 90 天观察窗口计算' },
  { value: 90, label: '90 天' },
  { value: 180, label: '180 天', disabled: true, hint: '当前后端最多提供 90 天活动分析' },
]
const emit = defineEmits<{ refresh: [] }>()
const setWindow = (value: string | number) => analysis.setWindow(value as TimeWindow)

function toggleCompare() {
  const selected = analysis.compareIds.includes(props.repository.id)
  if (!selected && analysis.compareIds.length >= 5) {
    ui.toast('最多同时比较 5 个仓库')
    return
  }
  analysis.toggleCompare(props.repository.id)
  ui.toast(selected ? `已从比较中移除：${props.repository.fullName}` : `已加入比较：${props.repository.fullName}`)
}

async function exportCsv() {
  exporting.value = true
  try {
    downloadBlob(await source.exportInsights(props.repository.id), `${props.repository.id}-insights.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出分析结果失败')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="flex flex-wrap items-start justify-between gap-6">
    <div class="min-w-0">
      <h1 class="flex flex-wrap items-center gap-2.5 text-[25px] font-semibold leading-tight tracking-[-0.2px]">
        {{ repository.fullName }}
        <a :href="repository.htmlUrl" target="_blank" rel="noreferrer" :aria-label="`在 GitHub 打开 ${repository.fullName}`"><ExternalLink :size="15" class="text-muted" /></a>
        <GdBadge :variant="statusMeta[repository.status].variant">{{ statusMeta[repository.status].text }}</GdBadge>
      </h1>
      <p class="mt-2 max-w-[720px] leading-relaxed text-muted">{{ repository.description ?? '暂无公开简介' }}</p>
      <div class="mt-3 flex flex-wrap items-center gap-3 text-[12.5px] text-muted">
        <span v-if="repository.language" class="flex items-center gap-1.5"><Code2 :size="13" /> {{ repository.language }}</span>
        <span v-if="repository.license" class="flex items-center gap-1.5"><Scale :size="13" /> {{ repository.license }} 许可</span>
        <span class="flex items-center gap-1.5"><CalendarDays :size="13" /> {{ windowStart ?? '—' }} — {{ windowEnd ?? '—' }}</span>
        <span class="flex items-center gap-1.5"><Database :size="13" /> 分析于 {{ collectedAt ?? '—' }}</span>
        <span class="flex items-center gap-1.5" :class="coverage.state !== 'complete' ? 'font-medium text-warnfg' : ''">
          <span class="size-1.5 rounded-full" :class="coverage.state === 'complete' ? 'bg-ink/60' : 'bg-warnfg'" />
          {{ coverage.label }}{{ coverage.detail ? ` · ${coverage.detail}` : '' }}
        </span>
        <button class="gd-link text-[12.5px]" @click="ui.openDrawer('definitions', { metric: 'M01' })"><Info :size="13" /> 数据与口径</button>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <GdSegmented :model-value="analysis.timeWindow" :options="windowOptions" @update:model-value="setWindow" />
      <GdButton variant="outline" @click="toggleCompare"><GitCompare :size="14" /> {{ analysis.compareIds.includes(repository.id) ? '移出比较' : '加入比较' }}</GdButton>
      <GdButton :disabled="refreshing" @click="emit('refresh')"><RefreshCw :size="14" /> {{ refreshing ? '排队中…' : '更新分析' }}</GdButton>
      <GdIconButton label="导出聚合 CSV" :disabled="exporting" @click="exportCsv"><Download :size="16" /></GdIconButton>
    </div>
  </div>
</template>
