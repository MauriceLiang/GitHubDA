<script setup lang="ts">
import { computed } from 'vue'
import RankChart from '@/components/charts/RankChart.vue'
import TimelineChart from '@/components/charts/TimelineChart.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdCard from '@/components/ui/GdCard.vue'
import type { ReleaseRecord, RepositoryAnalysis } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import { useDataSource } from '@/composables/useDataSource'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const ui = useUiStore()
const dataSource = useDataSource()
let releaseDetailRequest = 0

const yearReleases = computed(() => props.analysis.releases)
const intervalItems = computed(() => props.analysis.releaseIntervals.map((r, i) => ({ label: `间隔 ${i + 1}`, value: Number(r.days.toFixed(1)) })))
const intervalChartHeight = computed(() => Math.max(190, intervalItems.value.length * 24))
const identifierLabel = computed(() => yearReleases.value[0]?.identifierType === 'release_id' ? 'Release ID' : '版本')
const sorted = computed(() => [...yearReleases.value].sort((a, b) => +new Date(b.publishedAt) - +new Date(a.publishedAt)))
const median = computed(() => {
  const days = props.analysis.releaseIntervals.map((r) => r.days).sort((a, b) => a - b)
  return days.length ? days[Math.floor(days.length / 2)] : null
})

async function openRelease(release: ReleaseRecord) {
  const requestId = ++releaseDetailRequest
  const payload: Record<string, string> = {
    tag: release.tag,
    identifierType: release.identifierType ?? 'tag',
    date: release.publishedAt,
    type: release.prerelease ? '预发布（prerelease）' : '正式发布',
    interval: release.intervalDays === null ? '—' : `${release.intervalDays.toLocaleString('en-US', { maximumFractionDigits: 1 })} 天`,
    bodyStatus: 'loading',
  }
  ui.openDrawer('release', payload)
  try {
    const detail = await dataSource.getReleaseDetails(props.analysis.repository.id, release.tag)
    if (requestId !== releaseDetailRequest || ui.drawerKind !== 'release' || ui.drawerPayload?.tag !== release.tag) return
    ui.openDrawer('release', { ...payload, bodyStatus: 'ready', body: detail.body ?? '', releaseName: detail.name ?? '' })
  } catch (error) {
    if (requestId !== releaseDetailRequest || ui.drawerKind !== 'release' || ui.drawerPayload?.tag !== release.tag) return
    ui.openDrawer('release', { ...payload, bodyStatus: 'error', bodyError: error instanceof Error ? error.message : '无法读取该版本的发布说明' })
  }
}
</script>

<template>
  <KpiStrip :metrics="analysis.metrics.metrics" />

  <GdCard class="h-[360px] overflow-hidden">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">发布时间线</h3>
        <p class="mt-0.5 text-[12px] text-muted">横轴按真实日期 · 默认放大最近 90 天 · 滑块浏览近 365 天 · 同日版本错开显示</p>
      </div>
    <span class="text-[11.5px] text-muted">正式发布 {{ yearReleases.length }} 次</span>
    </div>
    <TimelineChart :releases="yearReleases" :height="220" @select="openRelease" />
    <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span>后端当前只提供正式 Release 的日期聚合；没有 Release 不代表没有代码更新</span>
      <span>点击圆点或下方记录查看 Release 详情</span>
    </div>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
    <GdCard class="h-[420px] overflow-hidden">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">相邻发布间隔</h3>
          <p class="mt-0.5 text-[12px] text-muted">近 365 天正式 Release · 按发布时间排序后的相邻天数</p>
        </div>
        <span class="font-mono text-[11.5px] text-muted">n={{ analysis.releaseIntervals.length }} · P50 {{ median?.toLocaleString('en-US', { maximumFractionDigits: 1 }) ?? '—' }} 天</span>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        <RankChart :items="intervalItems" color="#E2683C" value-suffix=" 天" :height="intervalChartHeight" />
      </div>
      <p class="text-[11px] text-muted">相邻间隔至少需要 2 次正式发布；样本不足时只列出记录。</p>
    </GdCard>

    <GdCard class="h-[420px] overflow-hidden">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">发布记录</h3>
          <p class="mt-0.5 text-[12px] text-muted">点击行查看 Release 详情</p>
        </div>
      </div>
      <div class="min-h-0 flex-1 overflow-auto overscroll-contain">
        <table class="w-full min-w-[560px] border-collapse text-[12.5px]">
          <thead class="sticky top-0 z-10 bg-panel">
            <tr class="text-left text-[11.5px] text-muted">
              <th class="border-b border-line px-2.5 pb-2 font-medium">{{ identifierLabel }}</th>
              <th class="border-b border-line px-2.5 pb-2 font-medium">发布时间</th>
              <th class="border-b border-line px-2.5 pb-2 font-medium">类型</th>
              <th class="border-b border-line px-2.5 pb-2 font-medium">间隔</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="release in sorted" :key="release.tag" class="cursor-pointer hover:bg-soft/40" @click="openRelease(release)">
              <td class="border-b border-line px-2.5 py-2.5 font-mono">
                <button type="button" class="text-left hover:underline focus-visible:underline" @click.stop="openRelease(release)">{{ release.identifierType === 'release_id' ? `#${release.tag}` : release.tag }}</button>
              </td>
              <td class="border-b border-line px-2.5 py-2.5 font-mono text-muted">{{ release.publishedAt }}</td>
              <td class="border-b border-line px-2.5 py-2.5">{{ release.prerelease ? '预发布' : '正式' }}</td>
              <td class="border-b border-line px-2.5 py-2.5 font-mono">{{ release.intervalDays === null ? '—' : `${release.intervalDays.toLocaleString('en-US', { maximumFractionDigits: 1 })} 天` }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </GdCard>
  </div>
</template>
