<script setup lang="ts">
import { BookOpen, Download, LoaderCircle } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import RankChart from '@/components/charts/RankChart.vue'
import ScatterChart from '@/components/charts/ScatterChart.vue'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdSegmented from '@/components/ui/GdSegmented.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import { useUiStore } from '@/stores/ui'
import type { ResearchAnalysisMode } from '@/services/types'

const ui = useUiStore()
const source = useDataSource()
const exporting = ref(false)
const importing = ref(false)
const requestedMode = ref<ResearchAnalysisMode | 'auto'>('auto')
const { data, loading, error, reload } = useAsyncData(() => source.getResearchDataset(undefined, requestedMode.value), () => requestedMode.value)
const { data: featuredStatus, error: featuredStatusError, reload: reloadFeaturedStatus } = useAsyncData(() => source.getFeaturedDatasetStatus())
const modeOptions = [
  { value: 'exploratory', label: '精选探索', hint: '基于当前本地已采集的精选仓库数据，不代表 GitHub 总体。' },
  { value: 'formal', label: '正式研究', hint: '只读取已确认并导入的研究样本；不会替用户冻结样本清单。' },
]
const selectedMode = computed(() => data.value?.analysisMode ?? (requestedMode.value === 'auto' ? 'exploratory' : requestedMode.value))
const activeFeaturedImport = computed(() => ['queued', 'running'].includes(featuredStatus.value?.activeTask?.status ?? ''))
const featuredImportUnavailable = computed(() => !featuredStatus.value?.available)

const palette = ['#E2683C', '#E5A03A', '#CE3F7C', '#2E8FCB', '#B08310', '#8C6DB0', '#65A765']
const groupItems = computed(() => (data.value?.groups ?? []).map((group, index) => ({ label: group.label, value: group.count, color: palette[index % palette.length] })))
const issueMedianItems = computed(() => (data.value?.groups ?? []).flatMap((group, index) => group.medianCloseDays === null ? [] : [{ label: group.label, value: group.medianCloseDays, color: palette[index % palette.length] }]))
const groupChartHeight = computed(() => Math.max(190, groupItems.value.length * 32))
const issueMedianChartHeight = computed(() => Math.max(190, issueMedianItems.value.length * 32))
const qualityItems = computed(() => (data.value?.quality ?? []).filter((quality) => quality.collected).map((quality) => ({ label: quality.field, value: quality.missingRate })))
const groups = computed(() => (data.value?.groups ?? []).map((group) => group.label))

function setMode(value: string | number) {
  if (value === 'formal' || value === 'exploratory') requestedMode.value = value
}

async function exportResearchMembers() {
  if (!data.value) return
  exporting.value = true
  try {
    downloadBlob(await source.exportRepositories('research', data.value.id, data.value.analysisMode), `${data.value.id}-members.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出样本成员失败')
  } finally {
    exporting.value = false
  }
}

async function exportResearchStatistics() {
  if (!data.value) return
  exporting.value = true
  try {
    downloadBlob(await source.exportResearchStatistics(data.value.id, data.value.analysisMode), `${data.value.id}-statistics.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出统计结果失败')
  } finally {
    exporting.value = false
  }
}

async function importFeatured() {
  if (importing.value || !featuredStatus.value?.available || activeFeaturedImport.value) return
  importing.value = true
  try {
    const result = await source.importFeaturedDataset()
    requestedMode.value = 'exploratory'
    await reloadFeaturedStatus()
    if (result.alreadyCurrent) {
      await reload()
      ui.toast('精选数据已是当前版本')
    } else {
      ui.toast('精选数据导入任务已排队，可在任务中心查看进度')
    }
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导入精选数据失败')
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-[18px] px-7 pb-8 pt-[22px]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="m-0 text-[24px] font-semibold">研究分析</h1>
        <p class="mt-1.5 text-muted">选择精选探索或正式研究；样本范围、覆盖质量与分析限制会随结果展示。</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <GdSegmented :model-value="selectedMode" :options="modeOptions" aria-label="研究分析模式" data-testid="research-mode" @update:model-value="setMode" />
        <template v-if="data && data.repositoryCount > 0">
          <GdButton variant="outline" :disabled="exporting" data-testid="export-research-members" @click="exportResearchMembers"><Download :size="14" /> 导出样本成员</GdButton>
          <GdButton variant="outline" :disabled="exporting" data-testid="export-research-statistics" @click="exportResearchStatistics"><Download :size="14" /> 导出统计结果</GdButton>
        </template>
      </div>
    </div>

    <p v-if="error" class="rounded-md bg-warnbg px-3 py-2.5 text-[12px] text-warnfg">研究数据集加载失败：{{ error }}</p>
    <div v-else-if="loading" class="flex flex-col gap-4">
      <div class="h-[120px] animate-pulse rounded bg-track/60" />
      <div class="h-[260px] animate-pulse rounded bg-track/60" />
    </div>

    <template v-else-if="data">
      <GdCard v-if="data.repositoryCount === 0" class="gap-3" data-testid="research-empty-state">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 v-if="data.analysisMode === 'exploratory'" class="m-0 text-[16px] font-semibold">精选数据尚未导入</h2>
            <h2 v-else class="m-0 text-[16px] font-semibold">正式研究样本尚不可分析</h2>
            <p v-if="data.analysisMode === 'exploratory'" class="mt-1 text-[12px] leading-relaxed text-muted">
              {{ featuredStatus?.totalRepositories ? `可导入 ${featuredStatus.totalRepositories} 个精选仓库。` : '当前本机没有可用的精选数据包。' }} 导入只读取随应用提供的数据包，不会请求 GitHub。
            </p>
            <p v-else class="mt-1 text-[12px] leading-relaxed text-muted">
              {{ data.studyStatus === 'pending_confirmation' ? '研究样本清单仍待负责人确认；当前未生成正式结果。' : data.studyStatus === 'approved_not_imported' ? '样本已确认，但成员清单尚未导入。' : '成员清单已导入，尚无可分析的本地采集结果。' }}
            </p>
          </div>
          <GdBadge variant="warn">{{ data.analysisMode === 'exploratory' ? '未导入' : data.studyStatus === 'pending_confirmation' ? '待确认' : data.studyStatus === 'approved_not_imported' ? '待导入' : '等待采集' }}</GdBadge>
        </div>
        <p v-if="featuredStatusError && data.analysisMode === 'exploratory'" class="m-0 text-[11px] text-danger">精选数据包状态读取失败：{{ featuredStatusError }}</p>
        <div v-if="data.analysisMode === 'exploratory'" class="flex flex-wrap items-center gap-2">
          <GdButton :disabled="importing || featuredImportUnavailable || activeFeaturedImport" data-testid="import-featured" @click="importFeatured">
            <LoaderCircle v-if="importing || activeFeaturedImport" :size="14" class="animate-spin" />
            {{ importing ? '正在提交…' : activeFeaturedImport ? '精选数据导入中' : featuredImportUnavailable ? '精选数据包不可用' : '导入精选' }}
          </GdButton>
          <RouterLink to="/tasks" class="gd-link text-[12px]">前往任务中心查看进度</RouterLink>
        </div>
      </GdCard>

      <template v-else>
      <GdCard>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="font-mono text-[13px] font-semibold">{{ data.name }}</span>
            <GdBadge variant="plain">{{ data.analysisMode === 'exploratory' ? '精选探索' : '正式研究' }}</GdBadge>
          </div>
          <button class="gd-link text-[11.5px]" @click="ui.openDrawer('definitions', { metric: 'M14', sample: `${data.repositoryCount} 个仓库 · ${data.scatter.sampleSize} 个有效配对` })">
            <BookOpen :size="13" /> 查看采样说明与局限
          </button>
        </div>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <div class="text-[11px] text-muted">采样来源</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.samplingSource }}</div>
          </div>
          <div class="border-line sm:border-l sm:pl-4">
            <div class="text-[11px] text-muted">采样规则</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.samplingRule }}</div>
          </div>
          <div class="border-line lg:border-l lg:pl-4">
            <div class="text-[11px] text-muted">{{ data.analysisMode === 'exploratory' ? '精选版本 / 快照' : '冻结日期' }}</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.analysisMode === 'exploratory' ? data.datasetVersion ?? '后端未记录' : data.frozenAt ?? '后端未记录' }}</div>
            <div class="mt-0.5 text-[11px] text-muted">观察窗口 {{ data.eventWindow.start ?? '—' }} — {{ data.eventWindow.end ?? '—' }}</div>
          </div>
          <div class="border-line lg:border-l lg:pl-4">
            <div class="text-[11px] text-muted">样本与总体范围</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.repositoryCount }} 个仓库 · {{ data.scatter.sampleSize }} 个有效配对</div>
            <div class="mt-0.5 text-[11px] text-muted">{{ data.isProbabilitySample ? '概率样本' : '非概率样本' }} · {{ data.populationScope }}</div>
            <div class="mt-0.5 text-[11px] text-muted">Issue 指标缺失率 {{ data.missingRate === null ? '—' : `${data.missingRate}%` }}</div>
          </div>
        </div>
      </GdCard>

      <section data-testid="research-kpis" class="grid grid-cols-2 divide-line rounded-[10px] border border-line bg-panel px-5 py-3.5 sm:grid-cols-4 sm:divide-x">
        <div class="px-0 py-2 sm:px-5 sm:py-0 sm:first:pl-0">
          <div class="text-[12.5px] text-muted">样本仓库</div>
          <div data-testid="research-sample-count" class="mt-1 text-[29px] font-semibold leading-tight">{{ data.repositoryCount }}</div>
        </div>
        <div class="px-0 py-2 sm:px-5 sm:py-0">
          <div class="text-[12.5px] text-muted">有效配对样本</div>
          <div class="mt-1 text-[29px] font-semibold leading-tight">{{ data.scatter.sampleSize }}</div>
          <div class="text-[11px] text-muted">同时具备 Issue 与 PR 指标</div>
        </div>
        <div class="px-0 py-2 sm:px-5 sm:py-0">
          <div class="text-[12.5px] text-muted">Issue 关闭耗时 P50</div>
          <div class="mt-1 text-[29px] font-semibold leading-tight">{{ data.issueMedianDays ?? '—' }}<span v-if="data.issueMedianDays !== null" class="ml-1 text-[13px] font-normal text-muted">天</span></div>
          <div class="text-[11px] text-muted">n={{ data.issueSample }}</div>
        </div>
        <div class="px-0 py-2 sm:px-5 sm:py-0">
          <div class="text-[12.5px] text-muted">PR 合并耗时 P50</div>
          <div class="mt-1 text-[29px] font-semibold leading-tight">{{ data.prMedianDays ?? '—' }}<span v-if="data.prMedianDays !== null" class="ml-1 text-[13px] font-normal text-muted">天</span></div>
          <div class="text-[11px] text-muted">n={{ data.prSample }}</div>
        </div>
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
        <GdCard class="h-[360px] overflow-hidden">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="m-0 text-[15.5px] font-semibold">按主要语言分组</h3>
              <p class="mt-0.5 text-[12px] text-muted">研究成员数</p>
            </div>
            <span class="font-mono text-[11.5px] text-muted">n={{ data.repositoryCount }}</span>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
            <RankChart :items="groupItems" :height="groupChartHeight" />
          </div>
          <p v-if="!data.groups.length" class="text-[11px] text-muted">当前数据集没有可展示的分组。</p>
        </GdCard>

        <GdCard class="h-[360px] overflow-hidden">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="m-0 text-[15.5px] font-semibold">各语言 Issue 关闭耗时</h3>
              <p class="mt-0.5 text-[12px] text-muted">组内中位数（天）</p>
            </div>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
            <RankChart :items="issueMedianItems" :height="issueMedianChartHeight" value-suffix=" 天" />
          </div>
          <p v-if="!issueMedianItems.length" class="text-[11px] text-muted">没有具备有效 Issue 耗时样本的语言组。</p>
        </GdCard>
      </div>

      <GdCard>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">Issue 与 PR 协作耗时</h3>
            <p class="mt-0.5 text-[12px] text-muted">每个点是一个仓库：Issue 关闭耗时中位数与 PR 合并耗时中位数（天）</p>
          </div>
          <div class="flex flex-wrap items-center gap-2 text-[11.5px]">
            <span class="font-mono">Spearman ρ = {{ data.scatter.spearman ?? '—' }}</span>
            <span class="text-muted">n={{ data.scatter.sampleSize }} · p={{ data.scatter.pValue ?? '—' }} · {{ data.scatter.note }}</span>
          </div>
        </div>
        <ScatterChart v-if="data.scatter.points.length" :points="data.scatter.points" :groups="groups" :height="280" />
        <p v-else class="py-12 text-center text-[12px] text-muted">没有同时具备 Issue 与 PR 耗时的仓库，暂不绘制散点图。</p>
      </GdCard>

      <GdCard>
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">数据质量</h3>
            <p class="mt-0.5 text-[12px] text-muted">基础资料缺失率与事件指标有效样本；没有满足口径的数据会列出原因</p>
          </div>
        </div>
        <RankChart v-if="qualityItems.length" :items="qualityItems" :height="190" value-suffix="%" color="#E2683C" />
        <p v-else class="py-6 text-center text-[12px] text-muted">后端没有返回字段缺失统计。</p>
        <div v-if="data.metricQuality.length" class="grid gap-2 border-t border-line pt-3 sm:grid-cols-2">
          <div v-for="metric in data.metricQuality" :key="metric.field" class="rounded-md bg-soft/50 px-2.5 py-2 text-[11px]">
            <div class="font-medium">{{ metric.field }} · 有效 {{ metric.validSamples }} / {{ data.repositoryCount }}</div>
            <div class="mt-0.5 text-muted">缺失 {{ metric.missingCount }}{{ metric.missingRate === null ? '' : `（${metric.missingRate}%）` }}<span v-if="metric.reasons.length"> · {{ metric.reasons.join('；') }}</span></div>
          </div>
        </div>
        <div class="text-[11px] leading-relaxed text-muted">{{ data.limitations.join(' ') }}</div>
      </GdCard>
      </template>
    </template>
  </div>
</template>
