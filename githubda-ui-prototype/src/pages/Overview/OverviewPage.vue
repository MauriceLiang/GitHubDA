<script setup lang="ts">
import { ArrowRight, CalendarDays, ChevronRight, Search } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import GdBadge from '@/components/ui/GdBadge.vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import GdInput from '@/components/ui/GdInput.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useDataSource } from '@/composables/useDataSource'
import type { RepositorySummary } from '@/services/types'
import { useAnalysisStore } from '@/stores/analysis'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const ui = useUiStore()
const analysis = useAnalysisStore()
const source = useDataSource()

const input = ref('')
const invalid = ref(false)
const submitting = ref(false)
const submitError = ref<string | null>(null)
const { data: repositories, loading, error } = useAsyncData(() => source.listRepositories())
const { data: tasks } = useAsyncData(() => source.listTasks())

const recent = computed(() => (repositories.value ?? []).slice(0, 5))
const activeTasks = computed(() => (tasks.value ?? []).filter((t) => t.status === 'running' || t.status === 'queued'))
const changes = computed(() =>
  (repositories.value ?? [])
    .filter((repo) => repo.activityDelta !== null)
    .slice(0, 2)
    .map((repo) => ({
      repo,
      text: repo.activityDelta === 0
        ? `${repo.fullName} 近 4 个完整周的活动与前一窗口基本持平（0%）。`
        : `${repo.fullName} 近 4 个完整周提交较前 4 周${repo.activityDelta! < 0 ? '减少' : '增加'} ${Math.abs(repo.activityDelta!)}%，对比窗口完整。`,
    })),
)

const statusLabel: Record<RepositorySummary['status'], { text: string; cls: string }> = {
  ready: { text: '已完成', cls: '' },
  partial: { text: '部分数据', cls: 'warn' },
  running: { text: '正在更新', cls: '' },
  failed: { text: '采集失败', cls: 'warn' },
  idle: { text: '尚未分析', cls: 'plain' },
}

async function submit() {
  const raw = input.value.trim()
  if (!raw) {
    invalid.value = true
    return
  }
  invalid.value = false
  submitError.value = null
  submitting.value = true
  try {
    const result = await source.addRepository(raw)
    analysis.remember(result.repositoryId)
    ui.toast(result.taskId ? '仓库已加入，采集任务已排队' : '仓库已加入分析库')
    void router.push(`/repositories/${result.repositoryId}/overview`)
  } catch (error) {
    submitError.value = error instanceof Error ? error.message : '提交分析失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-[18px] px-7 pb-8 pt-[22px]">
    <header>
      <h1 class="m-0 text-[26px] font-semibold tracking-[-0.3px]">仓库数据分析</h1>
      <p class="mt-1.5 text-muted">输入 GitHub 开源仓库，查看开发活动、Issue / PR 协作与发布节奏。</p>
    </header>

    <GdCard padding="none" class="gap-2.5 p-[22px]">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <GdInput v-model="input" class="flex-1" placeholder="owner/repo 或 GitHub 链接，例如 vuejs/core" :invalid="invalid" @enter="submit">
              <template #icon><Search :size="16" class="text-muted" /></template>
            </GdInput>
            <GdButton class="h-11 px-4" :disabled="submitting" @click="submit">{{ submitting ? '正在提交…' : '开始分析' }}</GdButton>
          </div>
          <p v-if="invalid" class="mt-1.5 text-[12px] text-danger">请输入 owner/repo 或完整的 GitHub 仓库链接</p>
          <p v-else-if="submitError" class="mt-1.5 text-[12px] text-danger">{{ submitError }}</p>
          <p v-else class="mt-2 text-[11.5px] text-muted">支持公开仓库；分析结果包含采集时点与覆盖状态。</p>
        </div>
      </div>
    </GdCard>

    <GdCard>
      <div class="flex items-start justify-between gap-4">
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">最近分析</h3>
          <p class="mt-0.5 text-[12px] text-muted">继续上次的分析，或查看采集状态</p>
        </div>
        <RouterLink to="/repositories" class="gd-link text-[12px]">全部仓库 <ArrowRight :size="12" /></RouterLink>
      </div>
      <div class="divide-y divide-line">
        <p v-if="error" class="py-3 text-[12px] text-danger">加载最近分析失败：{{ error }}</p>
        <div v-else-if="loading" v-for="i in 4" :key="i" class="h-14 animate-pulse bg-track/60" />
        <RouterLink v-for="repo in recent" v-else :key="repo.id" :to="`/repositories/${repo.id}/overview`"
          class="grid cursor-pointer grid-cols-1 items-center gap-3 py-3 transition-colors hover:bg-soft/40 sm:grid-cols-[1.6fr_1.4fr_auto_auto] sm:gap-5">
          <div class="min-w-0">
            <div class="truncate text-[13px] font-semibold">{{ repo.fullName }}</div>
            <div class="truncate text-[11.5px] text-muted">{{ repo.description }}</div>
          </div>
          <div class="text-[11.5px] text-muted">
            <template v-if="repo.status === 'ready' || repo.status === 'partial'">
              {{ repo.activityDelta === null ? '活动样本不足，未生成趋势判断' : `近 4 周较前 4 周 ${repo.activityDelta > 0 ? '+' : ''}${repo.activityDelta}%` }}
            </template>
            <template v-else>{{ repo.status === 'failed' ? '采集失败，可重试' : '尚未产出分析结果' }}</template>
          </div>
          <GdBadge :variant="(statusLabel[repo.status].cls as 'default' | 'warn' | 'plain')">
            {{ statusLabel[repo.status].text }}
          </GdBadge>
          <div class="flex items-center gap-2 text-[11.5px] text-muted">
            <span class="font-mono">{{ repo.lastAnalyzedAt ?? '—' }}</span>
            <ChevronRight :size="14" />
          </div>
        </RouterLink>
      </div>
    </GdCard>

    <div class="grid gap-[18px] lg:grid-cols-[1.4fr_1fr]">
      <GdCard>
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="m-0 text-[15.5px] font-semibold">近期值得关注的变化</h3>
            <p class="mt-0.5 text-[12px] text-muted">仅在前后对比窗口都完整时生成</p>
          </div>
        </div>
        <div class="flex flex-col gap-3">
          <div v-for="item in changes" :key="item.repo.id" class="flex items-start gap-2.5">
            <span class="w-0.5 self-stretch rounded-sm bg-s1" />
            <div>
              <p class="m-0 text-[12.5px] leading-relaxed">{{ item.text }}</p>
              <RouterLink :to="`/repositories/${item.repo.id}/activity`" class="mt-1 inline-block text-[11px] text-muted underline underline-offset-2 hover:text-ink">
                查看周聚合趋势
              </RouterLink>
            </div>
          </div>
          <p v-if="!changes.length" class="text-[12px] text-muted">目前没有满足对比条件的窗口。</p>
        </div>
      </GdCard>

      <GdCard>
        <div>
          <h3 class="m-0 text-[15.5px] font-semibold">正在进行的分析</h3>
          <p class="mt-0.5 text-[12px] text-muted">离开页面不会中断采集</p>
        </div>
        <div v-if="activeTasks.length" class="flex flex-col divide-y divide-line">
          <RouterLink v-for="task in activeTasks" :key="task.id" to="/tasks" class="flex items-center justify-between gap-3 py-2.5 text-[12px] hover:bg-soft/40">
            <span class="min-w-0 truncate">{{ task.repository }}</span>
            <span class="shrink-0 text-muted">{{ task.status === 'running' ? '采集中' : '排队中' }}</span>
          </RouterLink>
        </div>
        <p v-else class="text-[12px] text-muted">当前没有进行中的任务。</p>
        <RouterLink to="/tasks" class="gd-link w-fit text-[12px]"><CalendarDays :size="13" /> 查看任务中心</RouterLink>
      </GdCard>
    </div>
  </div>
</template>
