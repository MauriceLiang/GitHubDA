<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowLeft, ExternalLink, GitCompare, RefreshCw } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import StatusText from '@/components/StatusText.vue'
import TrendChart from '@/components/TrendChart.vue'
import { dataMode, services } from '@/services'
import type { Depth, Repository, RepositoryAnalysis, Task } from '@/services/domain'
import { coverageLabel, dateTime, fullDate, metric } from '@/lib/format'
import { activityKeys, metricDefinitions, observationChange, repositoryReadout } from '@/lib/analysis'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const repo = ref<Repository | null>(null)
const tasks = ref<Task[]>([])
const analyses = ref<Record<Depth, RepositoryAnalysis> | null>(null)
const depth = ref<Depth>('basic')
const series = ref<Array<{ date: string; value: number }>>([])
const tab = ref('overview')
const tabs = [{ id: 'overview', label: '概览解读' }, { id: 'activity', label: '更新与发布' }, { id: 'community', label: '社区协作' }, { id: 'data', label: '数据与口径' }]
function onTabKey(event: KeyboardEvent, index: number) {
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabs.length - 1
  else return
  event.preventDefault()
  tab.value = tabs[next]!.id
  const buttons = (event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
  buttons?.[next]?.focus()
}
const busy = ref(false)
const loading = ref(true)
const error = ref('')
let requestVersion = 0
let selectedInitialDepth = false
let timer = 0
const repositoryId = computed(() => Number(route.params.repositoryId))
const analysis = computed(() => analyses.value?.[depth.value] ?? null)
const metrics = computed(() => analysis.value?.metrics ?? null)
const readout = computed(() => repositoryReadout(metrics.value, analysis.value?.coverage ?? 'not_collected', repo.value?.archived ?? false))
const trend = computed(() => observationChange(series.value))
const activityDefinitions = metricDefinitions.filter((item) => activityKeys.some((key) => key === item.key))
const activeTask = computed(() => tasks.value.some((task) => task.status === 'queued' || task.status === 'running'))

async function load() {
  const id = repositoryId.value
  const version = ++requestVersion
  if (!Number.isInteger(id) || id < 1) { error.value = '仓库编号无效'; loading.value = false; return }
  error.value = ''
  try {
    const [detail, basic, deep, points, taskRows] = await Promise.all([
      services.repositoryDetail(id), services.repositoryAnalysis(id, 'basic'), services.repositoryAnalysis(id, 'deep'), services.repositorySeries(id, 'stars'), services.listTasks(),
    ])
    if (version !== requestVersion) return
    repo.value = detail; analyses.value = { basic, deep }; series.value = points
    tasks.value = taskRows.filter((task) => task.repositoryId === id)
    if (!selectedInitialDepth) { depth.value = deep.metrics ? 'deep' : 'basic'; selectedInitialDepth = true }
  } catch (cause) { if (version === requestVersion) error.value = cause instanceof Error ? cause.message : '仓库详情加载失败' }
  finally { if (version === requestVersion) loading.value = false }
}
async function refresh(requestedDepth: Depth) {
  if (busy.value || !repo.value) return
  busy.value = true; error.value = ''
  try {
    const id = repo.value.repositoryId
    const task = await services.refresh(id, requestedDepth)
    if (id !== repositoryId.value) return
    depth.value = requestedDepth; selectedInitialDepth = true
    store.flash(task.status === 'running' ? '已有任务正在运行' : '采集已排队，结果会在完成后自动更新')
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '无法启动分析任务' }
  finally { busy.value = false }
}
function compare() {
  if (!repo.value) return
  if (!store.selected.includes(repo.value.repositoryId)) store.toggleSelected(repo.value.repositoryId)
  if (store.selected.includes(repo.value.repositoryId)) void router.push('/compare')
}
watch(repositoryId, () => { repo.value = null; analyses.value = null; tasks.value = []; selectedInitialDepth = false; loading.value = true; void load() })
watch(() => route.query.view, (view) => { tab.value = typeof view === 'string' && tabs.some((item) => item.id === view) ? view : 'overview' }, { immediate: true })
onMounted(() => { void load(); timer = window.setInterval(() => { if (activeTask.value && !busy.value) void load() }, 5000) })
onUnmounted(() => { requestVersion++; window.clearInterval(timer) })
</script>

<template>
  <section class="page-content">
    <RouterLink class="back-link" to="/repositories?tab=saved"><ArrowLeft :size="15" />返回仓库</RouterLink>
    <p v-if="error" class="inline-error" role="alert">{{ error }} <button class="text-button" @click="load">重新加载</button></p>
    <p v-if="loading" class="empty-inline" role="status">正在读取已保存的分析结果…</p>
    <template v-if="repo && analyses">
      <PageHeader :title="repo.fullName" :description="repo.description || '暂无仓库简介'">
        <a class="button" :href="repo.htmlUrl" target="_blank" rel="noreferrer"><ExternalLink :size="15" />GitHub</a>
        <button class="button" :disabled="busy || activeTask" @click="refresh('basic')"><RefreshCw :size="15" />刷新基础</button>
        <button class="button primary" :disabled="busy || activeTask" @click="refresh('deep')">{{ activeTask ? '采集中…' : '采集活动数据' }}</button>
      </PageHeader>
      <div class="detail-meta"><span>{{ repo.language || '语言未记录' }}</span><span>{{ repo.archived ? '已归档' : '公开仓库' }}</span><span v-if="repo.license">许可：{{ repo.license }}</span><RouterLink v-if="activeTask" to="/tasks" class="text-link">查看采集进度</RouterLink></div>
      <div class="analysis-scope"><div class="segmented" role="group" aria-label="选择结果范围"><button :class="{ active: depth === 'basic' }" :aria-pressed="depth === 'basic'" @click="depth = 'basic'">基础概况</button><button :class="{ active: depth === 'deep' }" :aria-pressed="depth === 'deep'" @click="depth = 'deep'">活动与协作</button></div><p>{{ depth === 'basic' ? '查看累计关注度、仓库年龄与最近推送。' : '在基础资料之外，查看近 90 天提交与协作、近一年发布。' }}</p></div>
      <div class="result-provenance"><span>{{ dataMode === 'mock' ? '演示样例' : 'GitHub REST API' }} · 采集于 {{ fullDate(analysis?.source?.collectedAt) }}</span><span>当前范围：{{ coverageLabel(analysis?.coverage ?? 'not_collected') }}</span><StatusText :status="analysis?.status ?? 'not_started'" /></div>
      <div v-if="!metrics" class="analysis-empty"><strong>{{ analysis?.status === 'queued' || analysis?.status === 'processing' ? '正在准备这个范围的数据' : '这个范围还没有可用结果' }}</strong><p>基础概况与活动采集分别保存。可以切换查看已有结果，或采集所需范围；完成后页面会自动更新。</p><button class="button small-button" :disabled="busy || activeTask" @click="refresh(depth)">采集{{ depth === 'basic' ? '基础' : '活动' }}数据</button></div>
      <template v-else>
        <div class="metric-grid explained-metrics">
          <div><span>Stars · 星标</span><strong>{{ metric(metrics.stars) }}</strong><small>累计关注量</small></div>
          <div><span>Forks · 派生</span><strong>{{ metric(metrics.forks) }}</strong><small>累计派生次数</small></div>
          <div><span>距最近推送</span><strong>{{ metric(metrics.daysSincePush) }}<small v-if="metrics.daysSincePush != null" class="metric-unit"> 天</small></strong><small>以采集时点计算</small></div>
          <div><span>近 90 天提交</span><strong>{{ metric(metrics.commits90d) }}</strong><small>{{ metrics.commits90d == null ? '尚无完整采集值' : '默认分支提交数' }}</small></div>
        </div>
      </template>
      <div class="tabs detail-tabs" role="tablist" aria-label="仓库详情"><button v-for="(item, index) in tabs" :id="`detail-tab-${item.id}`" :key="item.id" class="tab" role="tab" :aria-selected="tab === item.id" :tabindex="tab === item.id ? 0 : -1" @keydown="onTabKey($event, index)" aria-controls="detail-panel" :class="{ active: tab === item.id }" @click="tab = item.id">{{ item.label }}</button></div>
      <div id="detail-panel" role="tabpanel" :aria-labelledby="`detail-tab-${tab}`">
        <template v-if="tab === 'overview'">
          <section class="detail-section"><div class="section-heading"><h2>当前数据能说明什么</h2><button class="text-button" @click="tab = 'data'">查看指标口径</button></div><div class="readout-grid"><article v-for="item in readout" :key="item.title"><h3>{{ item.title }}</h3><strong>{{ item.fact }}</strong><p>{{ item.explanation }}</p></article></div></section>
          <p v-if="analysis?.coverage === 'partial'" class="quiet-note">部分采集完成：可用值仍可阅读，缺失项不能解释为没有活动。请先核对“数据与口径”，再决定是否重新采集。</p>
          <div class="detail-columns"><section class="detail-section"><div class="section-heading"><h2>项目背景</h2></div><div class="detail-facts"><div><span>仓库年龄</span><strong>{{ metric(metrics?.ageDays) }}{{ metrics?.ageDays == null ? '' : ' 天（截至采集时点）' }}</strong></div><div><span>Topics</span><strong>{{ repo.topics?.join('、') || '未记录' }}</strong></div></div><button class="text-button compare-entry" :disabled="!analyses.basic.metrics" @click="compare"><GitCompare :size="15" />加入比较，查看与同类项目的差异</button></section><section class="detail-section"><div class="section-heading"><h2>最近采集任务</h2><RouterLink to="/tasks" class="text-link">查看任务</RouterLink></div><RouterLink v-for="task in tasks.slice(0, 3)" :key="task.taskId" class="task-plain-row detail-task" to="/tasks"><span class="task-dot" :class="`task-dot-${task.status}`" /><span><strong>{{ task.depth === 'deep' ? '活动采集' : '基础采集' }}</strong><small>{{ dateTime(task.createdAt) }}</small></span><StatusText :status="task.status" /></RouterLink><div v-if="!tasks.length" class="empty-inline">暂无采集任务</div></section></div>
        </template>
        <template v-else-if="tab === 'activity'">
          <section class="detail-section"><div class="section-heading"><h2>更新与发布记录</h2><span class="muted small">{{ depth === 'basic' ? '切换“活动与协作”读取活动指标' : '按各项指标窗口统计' }}</span></div><div class="metric-grid explained-metrics"><div v-for="item in activityDefinitions" :key="item.key"><span>{{ item.label }}</span><strong>{{ metric(metrics?.[item.key]) }}</strong><small>{{ item.window }}</small></div></div></section>
          <section class="detail-section"><div class="section-heading"><h2>Stars 历史观测</h2><span class="muted small">{{ series.length }} 个实际观测日期</span></div><p v-if="trend" class="quiet-note">{{ trend.from }} 至 {{ trend.to }}：变化 {{ trend.change > 0 ? '+' : '' }}{{ metric(trend.change) }}{{ trend.percent == null ? '（起始值为 0，不计算百分比）' : `（${trend.percent > 0 ? '+' : ''}${trend.percent.toFixed(1)}%）` }}。仅比较首末观测值，不推算中间日期。</p><TrendChart v-if="series.length >= 2" :labels="series.map((point) => point.date)" :values="series.map((point) => point.value)" series-name="Stars" label="Stars 历史观测图" /><p v-else class="empty-inline">{{ series.length === 1 ? '只有 1 个观测日期，还不能形成趋势。后续刷新会积累新的观测点。' : '尚无历史观测点。完成基础采集后，才会产生实际记录。' }}</p></section>
        </template>
        <section v-else-if="tab === 'community'" class="detail-section"><div class="section-heading"><h2>社区协作</h2><span class="muted small">采集时点前 90 天</span></div><div class="metric-grid explained-metrics"><div><span>关闭 Issues</span><strong>{{ metric(metrics?.issuesClosed90d) }}</strong><small>不等于问题解决率</small></div><div><span>合并 PR</span><strong>{{ metric(metrics?.prsMerged90d) }}</strong><small>不等于贡献者人数</small></div></div><p class="quiet-note">结合贡献指南、议题内容和维护者回复判断协作体验。仅靠关闭数与合并数，不能判断社区是否健康。</p><p v-if="depth === 'basic'" class="muted small">当前读取基础概况。请切换上方“活动与协作”查看已采集的协作数据。</p></section>
        <section v-else class="detail-section"><div class="section-heading"><h2>数据来源与指标口径</h2><span class="muted small">当前选择：{{ depth === 'basic' ? '基础概况' : '活动与协作' }}</span></div><p class="muted small">采集日期 {{ fullDate(analysis?.source?.collectedAt) }}<template v-if="depth === 'deep' && analysis?.source?.windowStart"> · 活动窗口 {{ fullDate(analysis.source.windowStart) }} 至 {{ fullDate(analysis.source.windowEnd) }}</template>。Release 单独采用采集前 365 天窗口。</p><p class="quiet-note">“完整覆盖”仅描述本次接口与分页的采集范围；不代表覆盖所有分支、私有活动或 GitHub 全部历史。“—”表示没有可用值；0 表示该窗口内采集结果为零。</p><div class="metric-glossary"><div v-for="item in metricDefinitions" :key="item.key"><strong>{{ item.label }}</strong><span>{{ item.window }}</span><p>{{ item.meaning }}</p></div></div><p v-for="note in analysis?.limitations" :key="note" class="quiet-note">{{ note }}</p></section>
      </div>
    </template>
  </section>
</template>
