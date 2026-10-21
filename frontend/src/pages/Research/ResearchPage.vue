<script setup lang="ts">
import { BookOpen, Download } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import RankChart from '@/components/charts/RankChart.vue'
import ScatterChart from '@/components/charts/ScatterChart.vue'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import { downloadBlob } from '@/lib/download'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const source = useDataSource()
const exporting = ref(false)
const { data, loading, error } = useAsyncData(() => source.getResearchDataset())

const palette = ['#E2683C', '#E5A03A', '#CE3F7C', '#2E8FCB', '#B08310', '#8C6DB0', '#65A765']
const groupItems = computed(() => (data.value?.groups ?? []).map((group, index) => ({ label: group.label, value: group.count, color: palette[index % palette.length] })))
const issueMedianItems = computed(() => (data.value?.groups ?? []).flatMap((group, index) => group.medianCloseDays === null ? [] : [{ label: group.label, value: group.medianCloseDays, color: palette[index % palette.length] }]))
const groupChartHeight = computed(() => Math.max(190, groupItems.value.length * 32))
const issueMedianChartHeight = computed(() => Math.max(190, issueMedianItems.value.length * 32))
const qualityItems = computed(() => (data.value?.quality ?? []).filter((quality) => quality.collected).map((quality) => ({ label: quality.field, value: quality.missingRate })))
const groups = computed(() => (data.value?.groups ?? []).map((group) => group.label))

async function exportResearch() {
  if (!data.value) return
  exporting.value = true
  try {
    downloadBlob(await source.exportRepositories('research', data.value.id), `${data.value.id}-research.csv`)
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '导出研究数据失败')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-[18px] px-7 pb-8 pt-[22px]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="m-0 text-[24px] font-semibold">研究分析</h1>
        <p class="mt-1.5 text-muted">结果来自后端研究数据集；样本量、缺失和覆盖限制随数据展示。</p>
      </div>
      <GdButton v-if="data" variant="outline" :disabled="exporting" @click="exportResearch"><Download :size="14" /> {{ exporting ? '正在导出…' : '导出结果' }}</GdButton>
    </div>

    <p v-if="error" class="rounded-md bg-warnbg px-3 py-2.5 text-[12px] text-warnfg">研究数据集加载失败：{{ error }}</p>
    <div v-else-if="loading" class="flex flex-col gap-4">
      <div class="h-[120px] animate-pulse rounded bg-track/60" />
      <div class="h-[260px] animate-pulse rounded bg-track/60" />
    </div>

    <template v-else-if="data">
      <div v-if="data.repositoryCount === 0" class="rounded-md bg-warnbg px-3 py-2.5 text-[12px] leading-relaxed text-warnfg">
        研究样本清单尚未导入。当前数据集包含 0 个仓库，下面的空图表不是研究结论；请先向后端导入真实采样成员。
      </div>

      <GdCard>
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="font-mono text-[13px] font-semibold">{{ data.name }}</span>
            <GdBadge variant="plain">研究数据集</GdBadge>
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
            <div class="text-[11px] text-muted">冻结日期</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.frozenAt ?? '后端未记录' }}</div>
            <div class="mt-0.5 text-[11px] text-muted">共同观察窗口 {{ data.eventWindow.start ?? '—' }} — {{ data.eventWindow.end ?? '—' }}</div>
          </div>
          <div class="border-line lg:border-l lg:pl-4">
            <div class="text-[11px] text-muted">有效样本与缺失</div>
            <div class="mt-1 text-[12.5px] font-medium">{{ data.repositoryCount }} 个仓库 · {{ data.scatter.sampleSize }} 个有效配对</div>
            <div class="mt-0.5 text-[11px] text-muted">Issue 指标缺失率 {{ data.missingRate === null ? '—' : `${data.missingRate}%` }}</div>
          </div>
        </div>
      </GdCard>

      <section class="grid grid-cols-2 divide-line rounded-[10px] border border-line bg-panel px-5 py-3.5 sm:grid-cols-4 sm:divide-x">
        <div class="px-0 py-2 sm:px-5 sm:py-0 sm:first:pl-0">
          <div class="text-[12.5px] text-muted">研究仓库</div>
          <div class="mt-1 text-[29px] font-semibold leading-tight">{{ data.repositoryCount }}</div>
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
            <p class="mt-0.5 text-[12px] text-muted">后端质量报告中的字段缺失率</p>
          </div>
        </div>
        <RankChart v-if="qualityItems.length" :items="qualityItems" :height="190" value-suffix="%" color="#E2683C" />
        <p v-else class="py-6 text-center text-[12px] text-muted">后端没有返回字段缺失统计。</p>
        <div class="text-[11px] leading-relaxed text-muted">{{ data.limitations.join(' ') }}</div>
      </GdCard>
    </template>
  </div>
</template>
