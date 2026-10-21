<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import RankChart from '@/components/charts/RankChart.vue'
import TrendChart from '@/components/charts/TrendChart.vue'
import KpiStrip from '@/components/common/KpiStrip.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import GdInput from '@/components/ui/GdInput.vue'
import { useDataSource } from '@/composables/useDataSource'
import type { CommitActivityPage, RepositoryAnalysis, TimePoint } from '@/services/types'

const props = defineProps<{ analysis: RepositoryAnalysis }>()
const emit = defineEmits<{ 'select-week': [payload: { date: string; count: number }] }>()
const source = useDataSource()
const pageSize = 10
const page = ref(1)
const searchInput = ref('')
const appliedSearch = ref('')
const activity = ref<CommitActivityPage | null>(null)
const loading = ref(false)
const loadError = ref('')
let requestVersion = 0

const weeklyPoints = computed(() => props.analysis.commits.series[0]?.points ?? [])
const pageCount = computed(() => Math.max(1, Math.ceil((activity.value?.total ?? 0) / pageSize)))
const firstRecord = computed(() => activity.value?.total ? (page.value - 1) * pageSize + 1 : 0)
const lastRecord = computed(() => Math.min(page.value * pageSize, activity.value?.total ?? 0))
const dailyPoints = computed<TimePoint[]>(() => (activity.value?.dailyCounts ?? []).map(({ date, count }) => ({ date, value: count })))
const rankedAuthors = computed(() => (activity.value?.authors ?? []).map((author) => ({
  label: `${author.author}${author.anonymous ? ' · 未关联账号' : ''}`,
  value: author.commits,
  muted: author.isBot,
})))
const activeDays = computed(() => activity.value?.dailyCounts.length ?? 0)

async function loadActivity() {
  const version = ++requestVersion
  loading.value = true
  loadError.value = ''
  try {
    const result = await source.getCommitActivity(props.analysis.repository.id, page.value, pageSize, appliedSearch.value)
    if (version === requestVersion) activity.value = result
  } catch (cause) {
    if (version === requestVersion) {
      activity.value = null
      loadError.value = cause instanceof Error ? cause.message : 'Commit 活动明细加载失败'
    }
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

watch([() => props.analysis.repository.id, page, appliedSearch], () => { void loadActivity() }, { immediate: true })

function selectWeek(dataIndex: number) {
  const point = weeklyPoints.value[dataIndex]
  if (point && (point.value !== null || point.observedValue !== null && point.observedValue !== undefined)) {
    emit('select-week', { date: point.date, count: point.value ?? point.observedValue ?? 0 })
  }
}

function applySearch() {
  const next = searchInput.value.trim()
  if (page.value === 1 && appliedSearch.value === next) {
    void loadActivity()
    return
  }
  page.value = 1
  appliedSearch.value = next
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(0, 10)
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : `${date.toISOString().slice(11, 19)} UTC`
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
    <TrendChart :points="weeklyPoints" :unit="analysis.commits.unit" :height="260" @select="(payload) => selectWeek(payload.dataIndex)" />
    <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
      <span>有效样本 {{ analysis.commits.sampleSize?.toLocaleString('en-US') ?? '—' }} · 灰色间断代表该周未达到完整覆盖口径。</span>
      <span>点击周趋势点，可查看该周已采集的逐条 Commit。</span>
    </div>
  </GdCard>

  <div class="grid gap-4 lg:grid-cols-2">
    <GdCard class="h-[350px] min-h-0 overflow-hidden">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">每日提交节奏</h3>
          <p class="mt-0.5 text-[12px] text-muted">仅绘制归档中实际出现提交的日期 · UTC</p>
        </div>
        <span class="shrink-0 text-[11px] text-muted">{{ activity?.commitCount.toLocaleString('zh-CN') ?? '—' }} 条 · {{ activeDays }} 个活跃日</span>
      </div>
      <GdCoverageNote v-if="activity" :coverage="activity.coverage" compact />
      <div v-if="loading && !activity" class="flex min-h-0 flex-1 items-center justify-center text-[12px] text-muted" role="status">正在读取本地 Commit 归档…</div>
      <div v-else-if="loadError" class="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 text-center text-[12px] text-danger" role="alert">
        <span>{{ loadError }}</span>
        <GdButton variant="outline" size="sm" @click="loadActivity">重新加载</GdButton>
      </div>
      <div v-else-if="activity && !activity.available" class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] leading-relaxed text-muted">{{ activity.note }}</div>
      <div v-else-if="activity && !activity.dailyCounts.length" class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] text-muted">本次采集范围内没有可展示的逐条 Commit。</div>
      <TrendChart v-else-if="activity" :points="dailyPoints" unit="次" :height="225" />
      <p v-if="activity?.note" class="m-0 text-[10.5px] leading-relaxed text-muted">{{ activity.note }}</p>
    </GdCard>

    <GdCard class="h-[350px] min-h-0 overflow-hidden">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">作者贡献排行</h3>
          <p class="mt-0.5 text-[12px] text-muted">按本次归档中可识别的作者身份聚合</p>
        </div>
        <span class="shrink-0 text-[11px] text-muted">{{ activity?.authorCount.toLocaleString('zh-CN') ?? '—' }} 位作者</span>
      </div>
      <div v-if="activity && activity.authors.length" class="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <RankChart :items="rankedAuthors" color="#CE3F7C" value-suffix=" 次" :height="Math.max(180, activity.authors.length * 30)" />
      </div>
      <div v-else-if="loading" class="flex min-h-0 flex-1 items-center justify-center text-[12px] text-muted" role="status">正在计算作者贡献…</div>
      <div v-else class="flex min-h-0 flex-1 items-center justify-center rounded-md bg-soft px-4 text-center text-[12px] text-muted">当前没有可识别的作者记录。</div>
      <p class="m-0 text-[10.5px] leading-relaxed text-muted">图表展示提交数最多的前 20 位；未关联 GitHub 账号的提交作者按 Git 提交信息中的名称归并，Bot 单独标记。</p>
    </GdCard>
  </div>

  <GdCard class="h-[500px] min-h-0 overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2">
        <h3 class="m-0 text-[15.5px] font-semibold">Commit 逐条记录</h3>
        <GdCoverageNote v-if="activity" :coverage="activity.coverage" compact />
      </div>
      <span v-if="activity?.available" class="shrink-0 text-[11px] text-muted">{{ formatDate(activity.windowStart) }} 至 {{ formatDate(activity.windowEnd) }} · {{ activity.commitCount.toLocaleString('zh-CN') }} 条</span>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <GdInput v-model="searchInput" size="sm" class="min-w-[220px] flex-1" placeholder="搜索提交说明、作者或 SHA" @enter="applySearch" />
      <GdButton variant="outline" size="sm" :disabled="loading" @click="applySearch">搜索</GdButton>
      <span v-if="activity?.available" class="shrink-0 text-[11px] text-muted">匹配 {{ activity.total.toLocaleString('zh-CN') }} 条</span>
    </div>

    <p v-if="activity?.note" class="m-0 text-[11px] leading-relaxed text-muted">{{ activity.note }}</p>

    <div v-if="loading && !activity" class="min-h-0 flex-1 overflow-y-auto py-8 text-center text-[12px] text-muted" role="status">正在加载 Commit 记录…</div>
    <div v-else-if="loadError" class="min-h-0 flex-1 overflow-y-auto py-6 text-center text-[12px] text-danger" role="alert">
      <p class="mb-3">{{ loadError }}</p>
      <GdButton variant="outline" size="sm" @click="loadActivity">重新加载</GdButton>
    </div>
    <div v-else-if="activity && !activity.available" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] leading-relaxed text-muted">{{ activity.note }}</div>
    <div v-else-if="activity && activity.total === 0" class="min-h-0 flex-1 overflow-y-auto rounded-md bg-soft px-3 py-8 text-center text-[12px] text-muted">{{ appliedSearch ? '没有找到匹配的 Commit。' : '本次采集窗口内没有 Commit 记录。' }}</div>
    <div v-else class="min-h-0 flex-1 overflow-auto overscroll-contain">
      <table class="w-full min-w-[640px] table-fixed border-collapse text-[12px]">
        <thead class="sticky top-0 z-10 bg-panel">
          <tr class="text-left text-[11px] text-muted">
            <th class="w-[110px] border-b border-line px-2 pb-2 font-medium">提交</th>
            <th class="border-b border-line px-2 pb-2 font-medium">提交说明</th>
            <th class="w-[150px] border-b border-line px-2 pb-2 font-medium">作者</th>
            <th class="w-[142px] border-b border-line px-2 pb-2 font-medium">提交时间（UTC）</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in activity?.items" :key="item.sha" class="border-b border-line/70 last:border-0">
            <td class="whitespace-nowrap px-2 py-2.5 font-mono text-ink">
              <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer" class="underline decoration-line underline-offset-2 hover:decoration-ink">{{ item.sha.slice(0, 8) }}</a>
              <span v-else>{{ item.sha.slice(0, 8) }}</span>
            </td>
            <td class="px-2 py-2.5 text-ink" :title="item.title"><span class="line-clamp-2">{{ item.title }}</span></td>
            <td class="px-2 py-2.5 text-ink">
              <span class="block truncate" :title="item.author">{{ item.author }}</span>
              <span v-if="item.isBot" class="text-[10px] text-muted">Bot</span>
              <span v-else-if="item.anonymous" class="text-[10px] text-muted">未关联账号</span>
            </td>
            <td class="whitespace-nowrap px-2 py-2.5 font-mono text-[10.5px] text-ink">
              <span class="block">{{ formatDate(item.date) }}</span>
              <span class="block text-[10px] text-ink/70">{{ formatTime(item.date) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="activity?.available && activity.total > 0" class="flex shrink-0 items-center justify-between gap-2 border-t border-line pt-2 text-[11px] text-muted">
      <span>显示 {{ firstRecord }}–{{ lastRecord }} / {{ activity.total }}</span>
      <div class="flex items-center gap-2">
        <GdButton variant="outline" size="sm" :disabled="loading || page <= 1" @click="page -= 1">上一页</GdButton>
        <span class="font-mono">{{ page }} / {{ pageCount }}</span>
        <GdButton variant="outline" size="sm" :disabled="loading || page >= pageCount" @click="page += 1">下一页</GdButton>
      </div>
    </div>
  </GdCard>
</template>
