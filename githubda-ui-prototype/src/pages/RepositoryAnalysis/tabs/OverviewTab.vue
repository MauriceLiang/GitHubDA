<script setup lang="ts">
import { ArrowRight } from 'lucide-vue-next'
import { computed } from 'vue'
import GdCard from '@/components/ui/GdCard.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import ObservationList from '@/components/common/ObservationList.vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import GroupedChart from '@/components/charts/GroupedChart.vue'
import TimelineChart from '@/components/charts/TimelineChart.vue'
import type { RepositoryAnalysis } from '@/services/types'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const emit = defineEmits<{ 'select-week': [payload: { date: string; count: number }] }>()
const repoId = computed(() => props.analysis.repository.id)

const commitsPoints = computed(() => props.analysis.commits.series[0]?.points ?? [])
const releasesYear = computed(() => props.analysis.releases)
const latestRelease = computed(() => [...props.analysis.releases].sort((a, b) => +new Date(b.publishedAt) - +new Date(a.publishedAt))[0])
const latestReleaseLabel = computed(() => {
  if (!latestRelease.value) return '—'
  return latestRelease.value.identifierType === 'release_id' ? `Release #${latestRelease.value.tag}` : latestRelease.value.tag
})
const medianInterval = computed(() => {
  const days = props.analysis.releaseIntervals.map((r) => r.days).sort((a, b) => a - b)
  if (!days.length) return null
  return days[Math.floor(days.length / 2)]
})

function selectCommit(dataIndex: number) {
  const point = commitsPoints.value[dataIndex]
  if (point && point.value !== null) emit('select-week', { date: point.date, count: point.value })
}

function repositorySizeLabel(sizeKb: number | null | undefined) {
  if (sizeKb == null) return '—'
  if (sizeKb >= 1024) return `${(sizeKb / 1024).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} MB`
  return `${sizeKb.toLocaleString('zh-CN')} KB`
}
</script>

<template>
  <KpiStrip :metrics="analysis.metrics.metrics" />

  <GdCard>
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">开发活动</h3>
        <p class="mt-0.5 text-[12px] text-muted">
          默认分支提交事件，按 UTC 自然周聚合 · {{ analysis.commits.window.start }} 至 {{ analysis.commits.window.end }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="rounded-md bg-track px-2 py-1 text-[11.5px] text-ink/70">{{ analysis.commits.limitation }}</span>
      </div>
    </div>
    <TrendChart :points="commitsPoints" :unit="analysis.commits.unit" :height="260" @select="(p) => selectCommit(p.dataIndex)" />
    <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span>单位：{{ analysis.commits.unit }} · 提交 SHA 去重 · 时区 UTC · 有效样本 {{ analysis.commits.sampleSize?.toLocaleString('en-US') ?? '—' }}</span>
      <span>点击柱查看该周聚合；逐条 Commit 明细暂未提供</span>
    </div>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-3">
    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[14.5px] font-semibold">Issue 处理</h3>
          <p class="mt-0.5 text-[11.5px] text-muted">Issue 关闭数 · 按周</p>
        </div>
        <RouterLink :to="`/repositories/${repoId}/issues`" class="gd-link text-[11.5px]">查看分析 <ArrowRight :size="12" /></RouterLink>
      </div>
      <GroupedChart :series="analysis.issues.series" :unit="analysis.issues.unit" :colors="['#E5A03A', '#CE3F7C']" :height="112" :show-legend="false" />
      <div class="flex items-end gap-3">
        <b class="text-[20px] font-semibold">{{ analysis.issueDuration.percentiles.p50 ?? '—' }} 天</b>
        <span class="text-[11px] leading-tight text-muted">关闭耗时中位数<br />n={{ analysis.issueDuration.sampleSize }} · P90 {{ analysis.issueDuration.percentiles.p90 ?? '—' }} 天</span>
      </div>
    </GdCard>

    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[14.5px] font-semibold">PR 协作</h3>
          <p class="mt-0.5 text-[11.5px] text-muted">PR 合并数 · 按周</p>
        </div>
        <RouterLink :to="`/repositories/${repoId}/prs`" class="gd-link text-[11.5px]">查看分析 <ArrowRight :size="12" /></RouterLink>
      </div>
      <GroupedChart :series="analysis.pullRequests.series" :unit="analysis.pullRequests.unit" :colors="['#CE3F7C', '#2E8FCB']" :height="112" :show-legend="false" />
      <div class="flex items-end gap-3">
        <b class="text-[20px] font-semibold">{{ analysis.prDuration.percentiles.p50 ?? '—' }} 天</b>
        <span class="text-[11px] leading-tight text-muted">合并耗时中位数<br />n={{ analysis.prDuration.sampleSize }} · P90 {{ analysis.prDuration.percentiles.p90 ?? '—' }} 天</span>
      </div>
    </GdCard>

    <GdCard>
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[14.5px] font-semibold">版本发布</h3>
          <p class="mt-0.5 text-[11.5px] text-muted">GitHub Releases · 近 365 天</p>
        </div>
        <RouterLink :to="`/repositories/${repoId}/releases`" class="gd-link text-[11.5px]">查看分析 <ArrowRight :size="12" /></RouterLink>
      </div>
      <TimelineChart :releases="releasesYear" :height="112" compact />
      <div class="flex items-end gap-3">
        <b class="text-[20px] font-semibold">{{ medianInterval?.toLocaleString('en-US', { maximumFractionDigits: 1 }) ?? '—' }} 天</b>
        <span class="text-[11px] leading-tight text-muted">典型发布间隔 · {{ analysis.releases.filter((r) => !r.prerelease).length }} 次正式发布<br />最近 {{ latestReleaseLabel }} · {{ latestRelease?.publishedAt ?? '—' }}</span>
      </div>
    </GdCard>
  </div>

  <div class="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
    <GdCard class="h-[360px] overflow-hidden">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">主要数据观察</h3>
        <p class="mt-0.5 text-[12px] text-muted">完整 8 周提交趋势、Issue/PR 耗时（n≥10）、正式发布节奏（至少 2 次）；部分覆盖只描述已观察样本。</p>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        <ObservationList :observations="analysis.observations" />
      </div>
    </GdCard>

    <GdCard class="h-[360px] overflow-hidden">
      <div>
        <h3 class="m-0 text-[15.5px] font-semibold">基础资料</h3>
        <p class="mt-0.5 text-[12px] text-muted">采集时点快照</p>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        <div class="space-y-2">
          <div class="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3">
            <div><div class="text-[11px] text-muted">Stars</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.stars?.toLocaleString('en-US') ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">Forks</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.forks?.toLocaleString('en-US') ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">主要语言</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.language ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">许可证</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.license ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">开放 Issue / PR</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.openIssuesAndPrCount?.toLocaleString('en-US') ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">仓库大小</div><div class="mt-0.5 text-[13px] font-medium">{{ repositorySizeLabel(analysis.repository.sizeKb) }}</div></div>
            <div><div class="text-[11px] text-muted">创建日期</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.createdAt ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">最近推送</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.pushedAt ?? '—' }}</div></div>
            <div><div class="text-[11px] text-muted">归档状态</div><div class="mt-0.5 text-[13px] font-medium">{{ analysis.repository.archived == null ? '—' : analysis.repository.archived ? '已归档' : '未归档' }}</div></div>
          </div>
          <div class="border-t border-line pt-3">
            <div class="text-[11px] text-muted">Topics</div>
            <div v-if="analysis.repository.topics.length" class="mt-1.5 flex flex-wrap gap-1.5">
              <span v-for="topic in analysis.repository.topics" :key="topic" class="rounded-md bg-track px-2 py-1 text-[11px] text-ink/75">{{ topic }}</span>
            </div>
            <p v-else class="mt-1 text-[12px] text-muted">未设置 Topics</p>
          </div>
          <p class="m-0 text-[11px] leading-relaxed text-muted">Stars / Forks 为背景信息，不参与开发活动分析；开放数量包含 PR。</p>
        </div>
      </div>
    </GdCard>
  </div>
</template>
