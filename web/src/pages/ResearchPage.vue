<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Download } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import TrendChart from '@/components/TrendChart.vue'
import { dataMode, services } from '@/services'
import type { DataQuality, Dataset, ResearchResult } from '@/services/domain'
import { download, fullDate, metric, preciseMetric } from '@/lib/format'
import { correlationReading, fieldLabel, pValueLabel } from '@/lib/analysis'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const datasets = ref<Dataset[]>([])
const datasetId = ref('')
const groupBy = ref<'language' | 'star_tier' | 'age_tier'>('language')
const tab = ref('overview')
const tabs = [{ id: 'overview', label: '概览解读' }, { id: 'distribution', label: '分布与分组' }, { id: 'correlation', label: '相关性' }, { id: 'quality', label: '数据质量' }]
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
const result = ref<ResearchResult | null>(null)
const quality = ref<DataQuality | null>(null)
const error = ref('')
const loading = ref(false)
let requestVersion = 0
const researchDatasets = computed(() => datasets.value.filter((dataset) => dataset.type === 'research'))
const currentDataset = computed(() => researchDatasets.value.find((dataset) => dataset.datasetId === datasetId.value) ?? null)
const chartRows = computed(() => result.value?.groups ?? [])
const chartValues = computed(() => chartRows.value.map((row) => row.n))
const groupLabel = computed(() => ({ language: '语言', star_tier: 'Stars 区间', age_tier: '仓库年龄' }[groupBy.value]))

async function loadData() {
  if (!datasetId.value) return
  const version = ++requestVersion
  loading.value = true; error.value = ''
  try {
    const [stats, dataQuality] = await Promise.all([services.researchStatistics(datasetId.value, groupBy.value), services.researchQuality(datasetId.value)])
    if (version !== requestVersion) return
    result.value = stats; quality.value = dataQuality
  } catch (cause) { if (version === requestVersion) { result.value = null; quality.value = null; error.value = cause instanceof Error ? cause.message : '研究数据加载失败' } }
  finally { if (version === requestVersion) loading.value = false }
}
async function exportResearch() {
  if (!datasetId.value || !currentDataset.value?.sampleSize) return
  try { download(await services.exportCsv('research', datasetId.value), `githubda-research-${datasetId.value}.csv`); store.flash('已导出当前研究数据集') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '导出失败' }
}
watch(datasetId, () => { result.value = null; quality.value = null; void loadData() })
watch(groupBy, () => { void loadData() })
onMounted(async () => {
  try {
    datasets.value = await services.listDatasets()
    const preferred = researchDatasets.value.find((dataset) => dataset.sampleSize > 0 && dataset.frozenAt) ?? researchDatasets.value.find((dataset) => dataset.sampleSize > 0) ?? researchDatasets.value[0]
    datasetId.value = preferred?.datasetId ?? ''
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '研究数据集加载失败' }
})
onUnmounted(() => { requestVersion++ })
</script>

<template>
  <section class="page-content">
    <PageHeader title="研究" description="先核对样本，再看分组与相关性。这里的结论只适用于当前研究样本。"><button class="button" :disabled="!result?.validSampleSize || loading" @click="exportResearch"><Download :size="15" />导出数据</button></PageHeader>
    <details class="method-note"><summary>第一次看研究分析？先了解这几个概念</summary><div><p><strong>样本与范围：</strong>这里分析的是按规则准备的固定仓库集合。个人库不会自动成为研究样本；冻结成员便于复核，但不能消除抽样偏差。</p><p><strong>中位数与均值：</strong>中位数是排序后的中间位置；均值会受到大数值影响。把两者与有效样本数一起阅读。</p><p><strong>Spearman ρ：</strong>衡量两项指标的排序是否同向或反向，范围 −1 到 1。至少 10 个有效配对且数值不是常量时才计算；相关不代表因果。</p><p><strong>p 值：</strong>描述无关联假设下出现当前或更极端结果的概率，不是“结论正确的概率”，也不表示影响大小。</p></div></details>
    <div class="research-controls"><label><span class="field-label">研究数据集</span><select v-model="datasetId" class="field" aria-label="选择研究数据集"><option v-for="dataset in researchDatasets" :key="dataset.datasetId" :value="dataset.datasetId">{{ dataset.name }} · {{ dataset.frozenAt ? '已冻结' : '未冻结' }}</option></select></label><label><span class="field-label">按什么比较样本</span><select v-model="groupBy" class="field" aria-label="研究分组"><option value="language">按语言</option><option value="star_tier">按 Stars 区间</option><option value="age_tier">按仓库年龄</option></select></label></div>
    <p v-if="error" class="inline-error" role="alert">{{ error }} <button class="text-button" @click="loadData">重新加载</button></p>
    <div v-if="currentDataset" class="dataset-summary"><div><strong>{{ currentDataset.name }}</strong><p>{{ dataMode === 'mock' ? '演示样例' : 'GitHub REST API 样本' }} · 成员 {{ currentDataset.sampleSize }} 个 · 规则 {{ currentDataset.rulesVersion || '未记录' }}<template v-if="currentDataset.frozenAt"> · 冻结于 {{ fullDate(currentDataset.frozenAt) }}</template></p></div><span v-if="!currentDataset.frozenAt" class="warning-text">尚未冻结，请勿作为固定样本结论</span></div>
    <div class="tabs research-tabs" role="tablist" aria-label="研究视图"><button v-for="(item, index) in tabs" :id="`research-tab-${item.id}`" :key="item.id" class="tab" role="tab" :aria-selected="tab === item.id" :tabindex="tab === item.id ? 0 : -1" @keydown="onTabKey($event, index)" aria-controls="research-panel" :class="{ active: tab === item.id }" @click="tab = item.id">{{ item.label }}</button></div>
    <div v-if="loading" class="empty-inline" role="status">正在加载研究结果…</div>
    <div v-else id="research-panel" role="tabpanel" :aria-labelledby="`research-tab-${tab}`">
      <section v-if="tab === 'quality' && quality" class="detail-section"><div class="section-heading"><h2>先核对数据是否足够</h2></div><div class="quality-line"><div><strong>可分析记录</strong><p>具备有效基础快照与关注度字段的样本；不代表所有活动字段完整</p></div><strong>{{ quality.recordsAnalyzable }} / {{ quality.recordsTotal }}</strong></div><div v-for="field in quality.missingFields" :key="field.field" class="quality-line"><div><strong>缺失 {{ fieldLabel(field.field) }}</strong><p>缺失值不作为 0 参与计算</p></div><strong>{{ field.count }}{{ field.rate == null ? '' : ` · ${(field.rate * 100).toFixed(1)}%` }}</strong></div><div class="quality-line"><div><strong>过期样本</strong><p>以数据集的过期规则标记，结果不是实时数据</p></div><strong>{{ quality.staleCount }}</strong></div><p v-for="note in quality.coverageNotes" :key="note" class="quiet-note">{{ note }}</p></section>
      <div v-else-if="result && result.validSampleSize === 0" class="analysis-empty research-empty"><h2>先准备样本，再提出统计结论</h2><p>当前没有可分析记录，因此不会绘制分布或计算相关性。个人库中的仓库不会自动并入研究样本。</p><ol><li>明确问题：比较什么类型、语言和年龄的项目？</li><li>由数据集维护者按抽样规则准备成员，并完成基础采集。</li><li>核对“数据质量”，冻结样本后再阅读统计与导出结果。</li></ol><div class="empty-actions"><button class="button" @click="tab = 'quality'">核对数据质量</button><RouterLink to="/repositories?tab=saved" class="text-link">只想了解一个项目？去我的仓库</RouterLink></div></div>
      <template v-else-if="result">
        <div v-if="tab === 'overview'" class="research-overview">
          <div class="metric-grid research-metrics"><div><span>有效样本</span><strong>{{ result.validSampleSize }}</strong></div><div><span>Stars 中位数</span><strong>{{ metric(result.summary.stars?.median) }}</strong></div><div><span>Forks 中位数</span><strong>{{ metric(result.summary.forks?.median) }}</strong></div></div>
          <div class="readout-grid"><article><h3>典型位置在哪里？</h3><strong>Stars 中位数 {{ metric(result.summary.stars?.median) }}</strong><p>均值为 {{ metric(result.summary.stars?.mean) }}，有效值 {{ result.summary.stars?.count ?? 0 }} 个。结合中位数和分组阅读，避免只看平均水平。</p></article><article><h3>分组能回答什么？</h3><strong>按{{ groupLabel }}观察 {{ chartRows.length }} 个分组</strong><p>检查各组样本数，再比较中位数；组别不同本身不能证明差异的原因。</p><button class="text-button" @click="tab = 'distribution'">查看分组数据</button></article><article><h3>结果可靠吗？</h3><strong>{{ quality?.recordsAnalyzable ?? '—' }} / {{ quality?.recordsTotal ?? '—' }} 条可分析</strong><p>{{ quality?.staleCount ?? '—' }} 条记录已过期。先核对缺失字段、样本规则和冻结状态。</p><button class="text-button" @click="tab = 'quality'">查看数据质量</button></article></div>
          <section class="detail-section"><div class="section-heading"><h2>样本内统计</h2><span class="muted small">n 为各指标有效值数，可能不同</span></div><div class="data-table-scroll"><table class="data-table"><thead><tr><th>指标</th><th>均值</th><th>中位数</th><th>标准差</th><th>有效值 n</th></tr></thead><tbody><tr v-for="[name, value] in Object.entries(result.summary)" :key="name"><th>{{ fieldLabel(name) }}</th><td>{{ preciseMetric(value.mean) }}</td><td>{{ preciseMetric(value.median) }}</td><td>{{ preciseMetric(value.std) }}</td><td>{{ value.count }}</td></tr></tbody></table></div></section>
        </div>
        <section v-else-if="tab === 'distribution'" class="detail-section"><div class="section-heading"><div><h2>样本分组</h2><p class="muted small">有效样本 n = {{ result.validSampleSize }}；分组不代表整个 GitHub 的分布。</p></div></div><TrendChart v-if="result.validSampleSize > 1 && chartRows.length > 1" :labels="chartRows.map((row) => row.group)" :values="chartValues" series-name="样本数" kind="bar" :label="`按${groupLabel}分组的样本数量`" /><p v-else class="quiet-note">当前不足两个有效分组，用表格核对数值，不绘制分布图。</p><div class="data-table-scroll"><table class="data-table group-table"><thead><tr><th>分组</th><th>样本数</th><th>Stars 中位数</th><th>Forks 中位数</th><th>近 90 天有推送</th></tr></thead><tbody><tr v-for="row in chartRows" :key="row.group"><th>{{ row.group }}</th><td>{{ row.n }}</td><td>{{ preciseMetric(row.starsMedian) }}</td><td>{{ preciseMetric(row.forksMedian) }}</td><td>{{ row.recentlyPushed90dPct == null ? '—' : `${row.recentlyPushed90dPct}%` }}</td></tr></tbody></table></div></section>
        <section v-else-if="tab === 'correlation'" class="detail-section"><div class="section-heading"><div><h2>两项指标是否一起变化？</h2><p class="muted small">Spearman 排序相关；只解释样本内关联，不推断因果。</p></div></div><div v-if="!result.correlations.length" class="empty-inline">暂时没有可计算的指标配对。</div><div v-for="item in result.correlations" :key="`${item.x}-${item.y}`" class="correlation-row"><div><strong>{{ fieldLabel(item.x) }} 与 {{ fieldLabel(item.y) }}</strong><span>Spearman ρ · 有效配对 n = {{ item.n }}</span></div><strong>{{ item.coefficient == null ? '—' : item.coefficient.toFixed(2) }}</strong><small>p {{ pValueLabel(item.pValue).startsWith('<') ? '' : '=' }} {{ pValueLabel(item.pValue) }}</small><p class="muted small">{{ correlationReading(item.coefficient, item.n, item.note) }}</p></div></section>
      </template>
      <p v-else-if="!error" class="empty-inline">尚无研究数据集，请由数据集维护者准备研究样本。</p>
    </div>
  </section>
</template>
