<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowLeft, Download, X } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import TrendChart from '@/components/TrendChart.vue'
import { services } from '@/services'
import type { Comparison, Depth, Repository } from '@/services/domain'
import { download, fullDate, preciseMetric } from '@/lib/format'
import { comparisonReadout, metricDefinitions } from '@/lib/analysis'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const library = ref<Repository[]>([])
const comparison = ref<Comparison | null>(null)
const depth = ref<Depth>('basic')
const chartMetric = ref<'stars' | 'forks' | 'commits90d'>('stars')
const error = ref('')
const loading = ref(false)
let loadVersion = 0
const selectedRepos = computed(() => store.selected.map((id) => library.value.find((repo) => repo.repositoryId === id)).filter((repo): repo is Repository => Boolean(repo)))
const available = computed(() => library.value.filter((repo) => repo.dataStatus !== 'missing' && !store.selected.includes(repo.repositoryId)))
const eligibleCount = computed(() => library.value.filter((repo) => repo.dataStatus !== 'missing').length)
const metricRows = computed(() => [
  { key: 'stars' as const, label: 'Stars' }, { key: 'forks' as const, label: 'Forks' }, { key: 'ageDays' as const, label: '仓库年龄（天）' }, { key: 'daysSincePush' as const, label: '距最近推送（天）' }, { key: 'commits90d' as const, label: '近 90 天提交' }, { key: 'issuesClosed90d' as const, label: '近 90 天关闭 Issues' }, { key: 'prsMerged90d' as const, label: '近 90 天合并 PR' }, { key: 'releases365d' as const, label: '近一年 Release' },
])
const chartLabel = computed(() => ({ stars: 'Stars', forks: 'Forks', commits90d: '近 90 天提交' }[chartMetric.value]))
const reading = computed(() => comparisonReadout(comparison.value?.repositories ?? [], chartMetric.value))
const selectedDefinition = computed(() => metricDefinitions.find((item) => item.key === chartMetric.value)!)
async function load() {
  const version = ++loadVersion
  loading.value = true; error.value = ''; comparison.value = null
  await loadLibrary()
  if (version !== loadVersion) return
  if (store.selected.length < 2) { comparison.value = null; loading.value = false; return }
  try { const result = await services.compare([...store.selected], depth.value); if (version === loadVersion) comparison.value = result }
  catch (cause) { if (version === loadVersion) { comparison.value = null; error.value = cause instanceof Error ? cause.message : '无法生成比较结果' } }
  finally { if (version === loadVersion) loading.value = false }
}
async function loadLibrary() { try { library.value = await services.listRepositories({ sort: 'name' }) } catch (cause) { error.value = cause instanceof Error ? cause.message : '仓库列表加载失败' } }
async function exportComparison() { try { download(await services.exportComparison(store.selected, depth.value), 'githubda-comparison.csv') } catch (cause) { error.value = cause instanceof Error ? cause.message : '导出失败' } }
function addRepository(value: string) { if (!value) return; store.toggleSelected(Number(value)) }
watch(() => [...store.selected], () => { if (library.value.length) void load() })
watch(depth, () => { void load() })
onMounted(() => { void load() })
onUnmounted(() => { loadVersion++ })
</script>

<template>
  <section class="page-content">
    <RouterLink class="back-link" to="/repositories?tab=saved"><ArrowLeft :size="15" />返回仓库</RouterLink>
    <PageHeader title="仓库比较" description="先选用途相近的项目，再看关注度、更新与协作有哪些差异。"><button class="button" :disabled="selectedRepos.length < 2 || loading || !comparison" @click="exportComparison"><Download :size="15" />导出比较</button></PageHeader>
    <div class="compare-toolbar"><strong>已选择 {{ store.selected.length }} / 5</strong><select class="field compact-field" aria-label="添加仓库进行比较" @change="addRepository(($event.target as HTMLSelectElement).value)"><option value="">＋ 添加仓库</option><option v-for="repo in available" :key="repo.repositoryId" :value="repo.repositoryId">{{ repo.fullName }}</option></select><select v-model="depth" class="field compact-field" aria-label="比较分析深度"><option value="basic">基础分析</option><option value="deep">深度分析</option></select><button v-if="store.selected.length" class="text-button" @click="store.clearSelected()"><X :size="14" />清除选择</button></div>
    <div class="compare-chips"><span v-for="repo in selectedRepos" :key="repo.repositoryId" class="compare-chip">{{ repo.fullName }}<button :aria-label="`移除 ${repo.fullName}`" @click="store.toggleSelected(repo.repositoryId)"><X :size="13" /></button></span></div>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <div v-if="store.selected.length < 2" class="empty-inline compare-empty"><strong>从两个用途相近的项目开始</strong><span>例如比较两个 HTTP 客户端；尽量核对语言、仓库年龄与采集时间。</span><span>{{ eligibleCount < 2 ? '当前可比较仓库不足两个。先添加并完成基础采集，再回来选择。' : '从上方添加仓库，或回到“我的仓库”勾选 2–5 个项目。' }}</span><RouterLink :to="eligibleCount < 2 ? '/repositories?tab=discover' : '/repositories?tab=saved'" class="text-link">{{ eligibleCount < 2 ? '查找另一个仓库' : '选择仓库' }}</RouterLink></div>
    <template v-else-if="comparison">
      <div class="comparison-reading"><div><span class="field-label">当前观察指标 · {{ chartLabel }}</span><h2>{{ reading.headline }}</h2><p>{{ reading.detail }}</p><small>{{ reading.count }} / {{ comparison.repositories.length }} 个有效值 · {{ selectedDefinition.window }}。{{ selectedDefinition.meaning }}</small></div><select v-model="chartMetric" class="field compact-field" aria-label="选择比较图表指标"><option value="stars">Stars · 关注度</option><option value="forks">Forks · 派生</option><option value="commits90d">近 90 天提交</option></select></div>
      <p v-if="chartMetric === 'commits90d' && depth === 'basic'" class="quiet-note">提交数属于活动结果，基础概况不会包含这项数据。<button class="text-button" @click="depth = 'deep'">读取活动结果</button></p>
      <div class="compare-table-scroll"><table class="compare-table"><thead><tr><th>比较指标</th><th v-for="repo in comparison.repositories" :key="repo.repositoryId"><RouterLink :to="`/repositories/${repo.repositoryId}`" class="text-link">{{ repo.fullName }}</RouterLink></th></tr></thead><tbody><tr v-for="row in metricRows" :key="row.key"><th>{{ row.label }}</th><td v-for="repo in comparison.repositories" :key="repo.repositoryId">{{ preciseMetric(repo.metrics[row.key]) }}</td></tr><tr><th>基础快照日期</th><td v-for="repo in comparison.repositories" :key="repo.repositoryId">{{ fullDate(repo.source?.profileCollectedAt) }}</td></tr><tr v-if="depth === 'deep'"><th>活动采集窗口</th><td v-for="repo in comparison.repositories" :key="repo.repositoryId">{{ repo.source?.analysisDepth === 'deep' ? `${fullDate(repo.source.windowStart)} 至 ${fullDate(repo.source.windowEnd)}` : '尚无活动结果' }}<small v-if="repo.source?.analysisDepth === 'deep'" class="source-caption">Release 采用采集前 365 天</small></td></tr><tr><th>数据覆盖</th><td v-for="repo in comparison.repositories" :key="repo.repositoryId">{{ repo.coverage === 'complete' ? '完整' : repo.coverage === 'partial' ? '部分' : repo.coverage === 'not_collected' ? '未采集' : '未知' }}</td></tr></tbody></table></div>
      <div class="chart-toolbar"><div><h2>{{ chartLabel }} 对比</h2><p class="muted small">指标定义相同，各仓库以各自的采集时点为准；缺失值不绘制为零。</p></div></div>
      <TrendChart v-if="comparison.repositories.some((repo) => repo.metrics[chartMetric] !== null)" :labels="comparison.repositories.map((repo) => repo.fullName)" :values="comparison.repositories.map((repo) => repo.metrics[chartMetric])" :series-name="chartLabel" kind="bar" label="仓库指标对比图" />
      <p v-else class="empty-inline">所选指标尚无有效数据，不绘制图表。</p>
      <p v-for="warning in comparison.basis.warnings" :key="warning" class="quiet-note">{{ warning }}</p>
    </template>
    <div v-else-if="loading" class="empty-inline">正在生成比较结果…</div>
  </section>
</template>
