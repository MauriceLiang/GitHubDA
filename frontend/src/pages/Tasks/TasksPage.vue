<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { TaskItem, TaskStatus } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const router = useRouter()
const source = useDataSource()
const { data, loading, error, reload } = useAsyncData(() => source.listTasks())
const tasks = ref<TaskItem[]>([])
const retrying = ref<string | null>(null)
let pollTimer: number | undefined

const statusMeta: Record<TaskStatus, { text: string; variant: 'default' | 'warn' | 'plain' }> = {
  queued: { text: '排队中', variant: 'plain' },
  running: { text: '正在采集', variant: 'default' },
  analyzing: { text: '正在分析', variant: 'default' },
  done: { text: '已完成', variant: 'default' },
  partial: { text: '部分完成', variant: 'warn' },
  failed: { text: '失败', variant: 'warn' },
  cancelled: { text: '已取消', variant: 'plain' },
}
const moduleLabel: Record<string, string> = {
  profile: '仓库概况', commits: 'Commit 采集', issues: 'Issue 采集', pulls: 'PR 采集', releases: 'Release 采集', collect_repository: '仓库采集',
}
const counts = ref({ running: 0, queued: 0, partial: 0, failed: 0 })

function sync(value: TaskItem[]) {
  tasks.value = value.map((task) => ({ ...task }))
  counts.value = {
    running: tasks.value.filter((task) => task.status === 'running' || task.status === 'analyzing').length,
    queued: tasks.value.filter((task) => task.status === 'queued').length,
    partial: tasks.value.filter((task) => task.status === 'partial').length,
    failed: tasks.value.filter((task) => task.status === 'failed').length,
  }
}

watch(data, (value) => { if (value) sync(value) }, { immediate: true })
onMounted(() => {
  pollTimer = window.setInterval(() => {
    if (tasks.value.some((task) => task.status === 'queued' || task.status === 'running' || task.status === 'analyzing')) void reload()
  }, 3000)
})
onBeforeUnmount(() => { if (pollTimer !== undefined) window.clearInterval(pollTimer) })

async function refresh() {
  await reload()
}

async function retry(task: TaskItem) {
  retrying.value = task.id
  try {
    await source.retryTask(task.id)
    ui.toast(`已重新排队：${task.repository}`)
    await reload()
  } catch (cause) {
    ui.toast(cause instanceof Error ? cause.message : '重试任务失败')
  } finally {
    retrying.value = null
  }
}

function view(task: TaskItem) {
  if (task.taskType === 'dataset_import') void router.push('/repositories')
  else if (task.repositoryId) void router.push(`/repositories/${task.repositoryId}/overview`)
}

function percent(task: TaskItem): number | null {
  return task.progressKind === 'stages' || task.progressKind === 'records' ? task.progressPercent ?? null : null
}

function taskScopeLabel(task: TaskItem): string {
  if (task.scopeKind === 'window') return `完整窗口${task.windowDays ? ` · ${task.windowDays} 天` : ''}`
  if (task.scopeKind === 'quick') return `快速采集${task.windowDays ? ` · ${task.windowDays} 天` : ''}`
  if (task.scopeKind === 'incremental') return '增量同步'
  if (task.scopeKind === 'backfill') return '历史回填'
  return ''
}

function taskDetail(task: TaskItem): string {
  if (task.taskType === 'dataset_import') {
    if (task.processedRecords !== null && task.processedRecords !== undefined && task.totalRecords !== null && task.totalRecords !== undefined) {
      return `${task.processedRecords.toLocaleString('en-US')} / ${task.totalRecords.toLocaleString('en-US')} 条记录${task.currentFile ? ` · ${task.currentFile}` : ''}`
    }
    if (task.status === 'done' && task.result) {
      const imported = Number(task.result.imported_count ?? 0)
      const events = Number(task.result.event_count ?? 0)
      const skipped = Number(task.result.skipped_count ?? 0)
      return `新增 ${imported.toLocaleString('en-US')} 个仓库 · 活动记录 ${events.toLocaleString('en-US')} 条 · 跳过 ${skipped.toLocaleString('en-US')} 条${task.version ? ` · ${task.version}` : ''}`
    }
    return task.version ? `数据集导入 · ${task.version}` : '数据集导入'
  }
  const scopeLabel = taskScopeLabel(task)
  const windowDates = task.windowStart && task.windowEnd
    ? `${task.windowStart.slice(0, 10)} 至 ${task.windowEnd.slice(0, 10)}`
    : ''
  const active = task.modules?.find((module) => module.status === 'running')
  if (active) return `${scopeLabel ? `${scopeLabel} · ` : ''}${windowDates ? `${windowDates} · ` : ''}${active.pagesFetched} 页 · ${active.observedItems.toLocaleString('en-US')} 条${active.pageCap ? ` / ${active.pageCap} 页预算` : ''}`
  if (task.resumeAfter) return `${scopeLabel ? `${scopeLabel} · ` : ''}${windowDates ? `${windowDates} · ` : ''}限流暂停 · 预计 ${new Date(task.resumeAfter).toLocaleString() } 恢复`
  if ((task.scopeKind === 'quick' || task.scopeKind === 'window') && windowDates) return `${scopeLabel} · ${windowDates}`
  if (task.scopeKind === 'incremental' && task.windowStart && task.windowEnd) return `增量同步 · 重叠区间 ${task.windowStart.slice(0, 10)} 至 ${task.windowEnd.slice(0, 10)}`
  if (task.scopeKind === 'backfill' && task.windowStart && task.windowEnd) return `历史回填 · ${task.windowStart.slice(0, 10)} 至 ${task.windowEnd.slice(0, 10)}`
  if (scopeLabel) return `${scopeLabel}${windowDates ? ` · ${windowDates}` : ''}`
  const latest = task.modules?.filter((module) => module.pagesFetched > 0).at(-1)
  return latest ? `已采集 ${latest.pagesFetched} 页 · ${latest.observedItems.toLocaleString('en-US')} 条` : ''
}
</script>

<template>
  <div class="flex flex-col gap-[18px] px-7 pb-8 pt-[22px]">
    <div>
      <h1 class="m-0 text-[24px] font-semibold">任务</h1>
      <p class="mt-1.5 text-muted">仓库采集与精选数据导入均由后端 Worker 执行；进度只反映实际任务阶段，不代表历史覆盖率。</p>
    </div>

    <section class="grid grid-cols-2 divide-line rounded-[10px] border border-line bg-panel px-5 py-3.5 sm:grid-cols-4 sm:divide-x">
      <div v-for="item in [{ label: '运行中', value: counts.running }, { label: '排队', value: counts.queued }, { label: '部分完成', value: counts.partial }, { label: '失败', value: counts.failed }]" :key="item.label" class="px-0 py-2 sm:px-5 sm:py-0 sm:first:pl-0">
        <div class="text-[12.5px] text-muted">{{ item.label }}</div>
        <div class="mt-1 text-[29px] font-semibold leading-tight">{{ item.value }}</div>
      </div>
    </section>

    <GdCard class="h-[520px] overflow-hidden">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">任务记录</h3>
          <p class="mt-0.5 text-[12px] text-muted">任务进度来自服务端阶段或实际暂存记录数；未知进度不填充百分比。</p>
        </div>
        <GdButton variant="outline" size="sm" :disabled="loading" @click="refresh">刷新</GdButton>
      </div>

      <div v-if="error" class="min-h-0 flex-1 overflow-y-auto overscroll-contain py-3 text-[12px] text-danger">任务加载失败：{{ error }}</div>
      <div v-else-if="loading" class="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div v-for="i in 4" :key="i" class="h-16 animate-pulse rounded bg-track/60" />
      </div>
      <div v-else-if="!tasks.length" class="min-h-0 flex-1 overflow-y-auto overscroll-contain py-10 text-center text-[12px] text-muted">当前没有任务。可以从仓库页添加仓库或导入精选数据。</div>

      <template v-else>
        <div class="hidden grid-cols-[minmax(190px,1.6fr)_96px_92px_minmax(280px,1.8fr)_64px_92px] items-center gap-4 border-b border-line px-1 pb-2 text-[11.5px] text-muted lg:grid">
          <span>任务 / 类型</span><span>状态</span><span>更新时间</span><span>当前阶段</span><span class="text-right">进度</span><span />
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
          <div class="divide-y divide-line">
            <div v-for="task in tasks" :key="task.id" class="grid grid-cols-1 items-center gap-3 py-3 lg:grid-cols-[minmax(190px,1.6fr)_96px_92px_minmax(280px,1.8fr)_64px_92px] lg:gap-4">
              <div class="min-w-0">
                <div class="truncate text-[13px] font-semibold">{{ task.repository }}</div>
                <div class="text-[11.5px] text-muted">
                  {{ task.taskType === 'dataset_import' ? `数据集导入${task.version ? ` · ${task.version}` : ''}` : `${moduleLabel[task.module] ?? task.module}${taskScopeLabel(task) ? ` · ${taskScopeLabel(task)}` : ''}` }}
                  <span v-if="task.isDemo" class="ml-1 text-s1">· 演示任务</span>
                </div>
                <div v-if="taskDetail(task)" class="mt-0.5 truncate text-[10.5px] text-muted" :title="taskDetail(task)">{{ taskDetail(task) }}</div>
              </div>
              <div><GdBadge :variant="statusMeta[task.status].variant">{{ task.taskType === 'dataset_import' && (task.status === 'running' || task.status === 'analyzing') ? '正在导入' : statusMeta[task.status].text }}</GdBadge></div>
              <div class="text-[11.5px] text-muted">{{ task.updatedAt }}</div>
              <div class="min-w-0">
                <div class="truncate text-[11.5px] text-muted" :title="task.stage">{{ task.error ?? task.stage }}</div>
                <div v-if="percent(task) !== null" class="mt-1.5 h-1 overflow-hidden rounded bg-track">
                  <div class="h-full rounded bg-ink transition-[width] duration-500" :style="{ width: `${percent(task)}%` }" />
                </div>
                <div v-else-if="task.progressKind === 'indeterminate' && (task.status === 'running' || task.status === 'analyzing')" class="mt-1.5 h-1 overflow-hidden rounded bg-track">
                  <div class="h-full w-1/3 animate-pulse rounded bg-ink" />
                </div>
              </div>
              <div class="text-right font-mono text-[11.5px] text-muted">{{ percent(task) === null ? '—' : `${Math.round(percent(task)!)}%` }}</div>
              <div class="flex justify-start lg:justify-end">
                <GdButton v-if="task.status === 'failed' || task.status === 'partial'" variant="outline" size="sm" class="min-w-[78px]" :disabled="retrying === task.id" @click="retry(task)">{{ retrying === task.id ? '排队中…' : '重试' }}</GdButton>
                <GdButton v-else variant="ghost" size="sm" class="min-w-[78px]" @click="view(task)">{{ task.taskType === 'dataset_import' ? task.status === 'done' ? '查看结果' : '查看进度' : '查看仓库' }}</GdButton>
              </div>
            </div>
          </div>
        </div>
      </template>
    </GdCard>
  </div>
</template>
