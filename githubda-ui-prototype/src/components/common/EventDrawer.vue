<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdDrawer from '@/components/ui/GdDrawer.vue'
import GdCoverageNote from '@/components/ui/GdCoverageNote.vue'
import ReleaseNotes from '@/components/common/ReleaseNotes.vue'
import { useDataSource } from '@/composables/useDataSource'
import { DEFINITIONS } from '@/services/definitions'
import type { CommitActivityPage, IssueComment } from '@/services/types'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const dataSource = useDataSource()
const payload = computed(() => ui.drawerPayload ?? {})
const issueComments = computed<IssueComment[]>(() => {
  try {
    const value: unknown = JSON.parse(payload.value.commentsJson ?? '[]')
    return Array.isArray(value) ? value as IssueComment[] : []
  } catch {
    return []
  }
})
const pullRequestComments = computed<IssueComment[]>(() => {
  try {
    const value: unknown = JSON.parse(payload.value.commentsJson ?? '[]')
    return Array.isArray(value) ? value as IssueComment[] : []
  } catch {
    return []
  }
})
const definition = computed(() => DEFINITIONS[payload.value.metric ?? 'M01'] ?? DEFINITIONS.M01)
const commitActivity = ref<CommitActivityPage | null>(null)
const commitPage = ref(1)
const commitLoading = ref(false)
const commitError = ref('')
let issueOnlineRequest = 0
let pullRequestOnlineRequest = 0
let commitRequest = 0

async function loadWeekCommits() {
  const repositoryId = payload.value.repositoryId ?? payload.value.repoId
  const weekStart = payload.value.weekLabel
  if (!repositoryId || !weekStart) return
  const requestId = ++commitRequest
  commitLoading.value = true
  commitError.value = ''
  try {
    const result = await dataSource.getCommitActivity(repositoryId, commitPage.value, 20, '', weekStart)
    if (requestId === commitRequest && ui.drawerKind === 'commits') commitActivity.value = result
  } catch (error) {
    if (requestId === commitRequest && ui.drawerKind === 'commits') commitError.value = error instanceof Error ? error.message : 'Commit 明细加载失败'
  } finally {
    if (requestId === commitRequest) commitLoading.value = false
  }
}

watch(
  () => ui.drawerKind === 'commits' ? `${payload.value.repositoryId ?? payload.value.repoId ?? ''}:${payload.value.weekLabel ?? ''}` : '',
  (key) => {
    commitRequest += 1
    commitActivity.value = null
    commitPage.value = 1
    commitError.value = ''
    if (key && key !== ':') void loadWeekCommits()
  },
  { immediate: true },
)

async function fetchIssueOnline() {
  const repositoryId = payload.value.repositoryId
  const issueNumber = Number(payload.value.number)
  if (!repositoryId || !Number.isSafeInteger(issueNumber) || issueNumber <= 0) return

  const requestId = ++issueOnlineRequest
  ui.openDrawer('issue', { ...payload.value, onlineStatus: 'loading', onlineError: '' })
  try {
    const detail = await dataSource.getIssueOnlineDetail(repositoryId, issueNumber)
    const current = ui.drawerPayload
    if (
      requestId !== issueOnlineRequest || ui.drawerKind !== 'issue' ||
      current?.repositoryId !== repositoryId || current.number !== String(issueNumber) || current.onlineStatus !== 'loading'
    ) return
    ui.openDrawer('issue', {
      ...current,
      title: detail.title,
      state: detail.state,
      createdAt: detail.createdAt ?? '',
      closedAt: detail.closedAt ?? '',
      updatedAt: detail.updatedAt ?? '',
      author: detail.author ?? '',
      labels: detail.labels.join(' · '),
      url: detail.url ?? current.url ?? '',
      bodyStatus: 'ready',
      body: detail.body ?? '',
      commentsCount: String(detail.commentsCount),
      commentsJson: JSON.stringify(detail.comments),
      commentsComplete: String(detail.commentsComplete),
      commentsError: detail.commentsError ?? '',
      onlineSource: detail.source,
      onlineStatus: 'ready',
      onlineError: '',
    })
  } catch (error) {
    const current = ui.drawerPayload
    if (
      requestId !== issueOnlineRequest || ui.drawerKind !== 'issue' ||
      current?.repositoryId !== repositoryId || current.number !== String(issueNumber) || current.onlineStatus !== 'loading'
    ) return
    ui.openDrawer('issue', {
      ...current,
      onlineStatus: 'error',
      onlineError: error instanceof Error ? error.message : '在线获取 Issue 详情失败',
    })
  }
}

async function fetchPullRequestOnline() {
  const repositoryId = payload.value.repositoryId
  const pullNumber = Number(payload.value.number)
  if (!repositoryId || !Number.isSafeInteger(pullNumber) || pullNumber <= 0) return

  const requestId = ++pullRequestOnlineRequest
  ui.openDrawer('pr', { ...payload.value, onlineStatus: 'loading', onlineError: '' })
  try {
    const detail = await dataSource.getPullRequestOnlineDetail(repositoryId, pullNumber)
    const current = ui.drawerPayload
    if (
      requestId !== pullRequestOnlineRequest || ui.drawerKind !== 'pr' ||
      current?.repositoryId !== repositoryId || current.number !== String(pullNumber) || current.onlineStatus !== 'loading'
    ) return
    ui.openDrawer('pr', {
      ...current,
      title: detail.title,
      state: detail.state,
      createdAt: detail.createdAt ?? '',
      closedAt: detail.closedAt ?? '',
      mergedAt: detail.mergedAt ?? '',
      author: detail.author ?? '',
      labels: detail.labels.join(' · '),
      url: detail.url ?? current.url ?? '',
      bodyStatus: 'ready',
      body: detail.body ?? '',
      commentsCount: String(detail.commentsCount),
      commentsJson: JSON.stringify(detail.comments),
      commentsComplete: String(detail.commentsComplete),
      commentsError: detail.commentsError ?? '',
      onlineSource: 'github',
      onlineStatus: 'ready',
      onlineError: '',
    })
  } catch (error) {
    const current = ui.drawerPayload
    if (
      requestId !== pullRequestOnlineRequest || ui.drawerKind !== 'pr' ||
      current?.repositoryId !== repositoryId || current.number !== String(pullNumber) || current.onlineStatus !== 'loading'
    ) return
    ui.openDrawer('pr', {
      ...current,
      onlineStatus: 'error',
      onlineError: error instanceof Error ? error.message : '在线获取 Pull Request 详情失败',
    })
  }
}

const title = computed(() => {
  switch (ui.drawerKind) {
    case 'commits': return 'Commit 周聚合'
    case 'definitions': return '数据与口径'
    case 'release': return payload.value.identifierType === 'release_id' ? `Release #${payload.value.tag ?? '—'}` : payload.value.tag ?? 'Release'
    case 'issue': return payload.value.title ?? 'Issue'
    case 'pr': return payload.value.title ?? 'Pull Request'
    default: return ''
  }
})
const subtitle = computed(() => ui.drawerKind === 'commits'
  ? `${payload.value.weekLabel ?? ''} · ${payload.value.count ?? '—'} 次提交`
  : ui.drawerKind === 'definitions' ? '指标来源与解释'
    : ui.drawerKind === 'issue' ? `Issue #${payload.value.number ?? '—'} · ${payload.value.state === 'open' ? '进行中' : '已关闭'}`
      : ui.drawerKind === 'pr' ? `Pull Request #${payload.value.number ?? '—'} · ${payload.value.state === 'merged' ? '已合并' : payload.value.state === 'open' ? '进行中' : '关闭未合并'}` : '')
</script>

<template>
  <GdDrawer :open="ui.drawerKind !== null" :title="title" :subtitle="subtitle" @update:open="(open) => !open && ui.closeDrawer()">
    <template v-if="ui.drawerKind === 'commits'">
      <GdCoverageNote v-if="commitActivity" :coverage="commitActivity.coverage" />
      <p v-if="commitActivity?.note" class="text-[11px] leading-relaxed text-muted">{{ commitActivity.note }}</p>
      <p v-if="commitLoading" class="py-8 text-center text-[12px] text-muted" role="status">正在读取该周的 Commit 归档…</p>
      <div v-else-if="commitError" class="rounded-md bg-warnbg px-3 py-2.5 text-[12px] leading-relaxed text-warnfg" role="alert">
        <p>{{ commitError }}</p>
        <GdButton variant="outline" size="sm" class="mt-2" @click="loadWeekCommits">重新加载</GdButton>
      </div>
      <p v-else-if="commitActivity && !commitActivity.available" class="rounded-md bg-soft px-3 py-5 text-center text-[12px] leading-relaxed text-muted">{{ commitActivity.note }}</p>
      <p v-else-if="commitActivity && !commitActivity.items.length" class="rounded-md bg-soft px-3 py-5 text-center text-[12px] text-muted">该周归档中没有可展示的逐条 Commit。</p>
      <div v-else-if="commitActivity" class="max-h-[65vh] overflow-y-auto overscroll-contain">
        <article v-for="commit in commitActivity.items" :key="commit.sha" class="border-b border-line py-3 last:border-0">
          <a v-if="commit.url" :href="commit.url" target="_blank" rel="noreferrer" class="text-[12.5px] font-medium leading-relaxed text-ink underline decoration-line underline-offset-2 hover:decoration-ink">{{ commit.title }}</a>
          <p v-else class="text-[12.5px] font-medium leading-relaxed text-ink">{{ commit.title }}</p>
          <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-muted">
            <span>{{ commit.author }}<template v-if="commit.isBot"> · Bot</template><template v-else-if="commit.anonymous"> · 未关联账号</template></span>
            <time class="font-mono text-ink">{{ commit.date.slice(0, 10) }} {{ commit.date.slice(11, 19) }} UTC</time>
            <span class="font-mono">{{ commit.sha.slice(0, 8) }}</span>
          </div>
        </article>
        <div v-if="commitActivity.total > 20" class="sticky bottom-0 flex items-center justify-between gap-2 border-t border-line bg-panel py-2 text-[11px] text-muted">
          <span>共 {{ commitActivity.total }} 条</span>
          <div class="flex items-center gap-2">
            <GdButton variant="outline" size="sm" :disabled="commitLoading || commitPage <= 1" @click="commitPage -= 1; loadWeekCommits()">上一页</GdButton>
            <span class="font-mono">{{ commitPage }} / {{ Math.ceil(commitActivity.total / 20) }}</span>
            <GdButton variant="outline" size="sm" :disabled="commitLoading || commitPage >= Math.ceil(commitActivity.total / 20)" @click="commitPage += 1; loadWeekCommits()">下一页</GdButton>
          </div>
        </div>
      </div>
    </template>

    <template v-else-if="ui.drawerKind === 'definitions'">
      <div class="text-[13px] font-semibold">{{ definition.title }}</div>
      <dl class="mt-1 divide-y divide-line text-[12.5px]">
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">计算口径</dt><dd class="m-0">{{ definition.definition }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">数据来源</dt><dd class="m-0">{{ definition.source }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">限制</dt><dd class="m-0">{{ definition.limitation }}</dd></div>
      </dl>
      <p class="mt-2 text-[11px] text-muted">实际时间范围、样本量和覆盖状态显示在当前图表旁。</p>
    </template>

    <template v-else-if="ui.drawerKind === 'release'">
      <dl class="divide-y divide-line text-[12.5px]">
        <div class="grid grid-cols-[110px_1fr] gap-2.5 py-2.5"><dt class="text-muted">发布时间</dt><dd class="m-0 font-mono text-ink">{{ payload.date ?? '—' }}</dd></div>
        <div class="grid grid-cols-[110px_1fr] gap-2.5 py-2.5"><dt class="text-muted">类型</dt><dd class="m-0">{{ payload.type ?? '正式发布' }}</dd></div>
        <div class="grid grid-cols-[110px_1fr] gap-2.5 py-2.5"><dt class="text-muted">相邻间隔</dt><dd class="m-0">{{ payload.interval ?? '—' }}</dd></div>
      </dl>
      <section class="mt-4">
        <h3 class="m-0 text-[13px] font-semibold text-ink">发布说明</h3>
        <p v-if="payload.bodyStatus === 'loading'" class="mt-2 text-[12.5px] text-muted">正在读取版本发布说明…</p>
        <p v-else-if="payload.bodyStatus === 'error'" class="mt-2 text-[12.5px] leading-relaxed text-warnfg">{{ payload.bodyError }}</p>
        <template v-else>
          <div v-if="payload.releaseName" class="mt-2 text-[12.5px] font-medium text-ink">{{ payload.releaseName }}</div>
          <ReleaseNotes v-if="payload.body" :body="payload.body" class="mt-2 max-h-[55vh] overflow-auto rounded-md bg-soft/50 px-3 py-2.5 text-[12.5px] leading-relaxed text-ink" />
          <p v-else class="mt-2 text-[12.5px] text-muted">此版本没有填写发布说明。</p>
        </template>
      </section>
    </template>

    <template v-else-if="ui.drawerKind === 'issue'">
      <dl class="divide-y divide-line text-[12.5px]">
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">Issue 编号</dt><dd class="m-0 font-mono text-ink">#{{ payload.number ?? '—' }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">状态</dt><dd class="m-0">{{ payload.state === 'open' ? '进行中' : '已关闭' }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">创建时间</dt><dd class="m-0 font-mono text-ink">{{ payload.createdAt || '—' }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">关闭时间</dt><dd class="m-0 font-mono text-ink">{{ payload.closedAt || '—' }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">处理耗时</dt><dd class="m-0">{{ payload.durationDays ?? '—' }}</dd></div>
        <div v-if="payload.author" class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">创建者</dt><dd class="m-0">{{ payload.author }}</dd></div>
        <div v-if="payload.labels" class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">标签</dt><dd class="m-0">{{ payload.labels }}</dd></div>
      </dl>
      <section class="mt-4">
        <div class="flex items-center justify-between gap-2">
          <h3 class="m-0 text-[13px] font-semibold text-ink">Issue 描述</h3>
          <GdButton variant="outline" size="sm" :disabled="payload.bodyStatus === 'loading' || payload.onlineStatus === 'loading'" @click="fetchIssueOnline">
            {{ payload.onlineStatus === 'loading' ? '正在获取…' : payload.onlineStatus === 'ready' ? '重新获取' : '在线获取' }}
          </GdButton>
        </div>
        <p class="mt-1.5 text-[11px] leading-relaxed text-muted">点击后才会请求 GitHub 最新内容；评论最多读取 100 条。</p>
        <p v-if="payload.onlineError" class="mt-2 rounded-md bg-warnbg px-3 py-2 text-[11.5px] leading-relaxed text-warnfg" role="alert">{{ payload.onlineError }}；当前仍可查看本地采集内容。</p>
        <p v-if="payload.onlineStatus === 'ready' && payload.onlineSource === 'mock'" class="mt-2 text-[11px] text-muted">演示模式：以下为示例数据，没有连接 GitHub。</p>
        <p v-else-if="payload.onlineStatus === 'ready' && payload.commentsError" class="mt-2 rounded-md bg-warnbg px-3 py-2 text-[11.5px] leading-relaxed text-warnfg" role="status">Issue 正文已获取，但评论读取失败：{{ payload.commentsError }}</p>
        <p v-else-if="payload.onlineStatus === 'ready' && payload.commentsComplete === 'false'" class="mt-2 text-[11px] text-muted">当前显示 {{ issueComments.length }} / {{ payload.commentsCount }} 条评论；评论较多，完整讨论请在 GitHub 查看。</p>
        <p v-else-if="payload.onlineStatus === 'ready' && payload.onlineSource === 'github'" class="mt-2 text-[11px] text-muted">已从 GitHub 获取最新 Issue 内容与评论。</p>
        <p v-if="payload.bodyStatus === 'loading'" class="mt-2 text-[12.5px] text-muted">正在读取 Issue 详情…</p>
        <p v-else-if="payload.bodyStatus === 'error'" class="mt-2 text-[12.5px] leading-relaxed text-warnfg">{{ payload.bodyError }}</p>
        <ReleaseNotes v-else-if="payload.body" :body="payload.body" class="mt-2 max-h-[55vh] overflow-auto rounded-md bg-soft/50 px-3 py-2.5 text-[12.5px] leading-relaxed text-ink" />
        <p v-else-if="payload.bodyStatus === 'ready'" class="mt-2 text-[12.5px] text-muted">此 Issue 没有填写描述。</p>
        <p v-if="payload.onlineStatus !== 'ready' && Number(payload.commentsCount) > 0" class="mt-2 text-[11px] text-muted">本地记录显示有 {{ payload.commentsCount }} 条评论；点击“在线获取”加载讨论内容。</p>
      </section>
      <section v-if="payload.onlineStatus === 'ready'" class="mt-5">
        <div class="flex items-center justify-between gap-2">
          <h3 class="m-0 text-[13px] font-semibold text-ink">讨论记录</h3>
          <span class="text-[11px] text-muted">{{ payload.commentsCount ?? '0' }} 条评论</span>
        </div>
        <p v-if="!issueComments.length && !payload.commentsError" class="mt-2 text-[12px] text-muted">此 Issue 暂无评论。</p>
        <div v-else class="mt-2 space-y-3">
          <article v-for="(comment, index) in issueComments" :key="`${comment.author}-${comment.createdAt}-${index}`" class="rounded-md border border-line bg-soft/40 p-3">
            <div class="flex flex-wrap items-center justify-between gap-1 text-[11px]">
              <span class="font-medium text-ink">{{ comment.author }}</span>
              <time v-if="comment.createdAt" class="font-mono text-muted">{{ comment.createdAt }}</time>
            </div>
            <ReleaseNotes v-if="comment.body" :body="comment.body" class="mt-2 max-h-[40vh] overflow-auto text-[12px] leading-relaxed text-ink" />
            <p v-else class="mt-2 text-[11px] text-muted">此评论没有文字内容。</p>
          </article>
        </div>
      </section>
      <a v-if="payload.url" :href="payload.url" target="_blank" rel="noreferrer" class="mt-4 inline-flex text-[12px] text-ink underline decoration-line underline-offset-2 hover:decoration-ink">在 GitHub 打开</a>
    </template>

    <template v-else-if="ui.drawerKind === 'pr'">
      <dl class="divide-y divide-line text-[12.5px]">
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">PR 编号</dt><dd class="m-0 font-mono text-ink">#{{ payload.number ?? '—' }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">状态</dt><dd class="m-0">{{ payload.state === 'merged' ? '已合并' : payload.state === 'open' ? '进行中' : '关闭未合并' }}<template v-if="payload.draft === 'true'"> · 草稿</template></dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">创建时间</dt><dd class="m-0 font-mono text-ink">{{ payload.createdAt || '—' }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">合并时间</dt><dd class="m-0 font-mono text-ink">{{ payload.mergedAt || '—' }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">关闭时间</dt><dd class="m-0 font-mono text-ink">{{ payload.closedAt || '—' }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">合并耗时</dt><dd class="m-0">{{ payload.durationDays ?? '—' }}</dd></div>
        <div v-if="payload.author" class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">创建者</dt><dd class="m-0">{{ payload.author }}</dd></div>
        <div v-if="payload.labels" class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">标签</dt><dd class="m-0">{{ payload.labels }}</dd></div>
      </dl>
      <section class="mt-4">
        <div class="flex items-center justify-between gap-2">
          <h3 class="m-0 text-[13px] font-semibold text-ink">PR 描述</h3>
          <GdButton variant="outline" size="sm" :disabled="payload.bodyStatus === 'loading' || payload.onlineStatus === 'loading'" @click="fetchPullRequestOnline">
            {{ payload.onlineStatus === 'loading' ? '正在获取…' : payload.onlineStatus === 'ready' ? '重新获取' : '在线获取' }}
          </GdButton>
        </div>
        <p class="mt-1.5 text-[11px] leading-relaxed text-muted">点击后才会请求 GitHub 最新内容；对话评论最多读取 100 条。</p>
        <p v-if="payload.onlineError" class="mt-2 rounded-md bg-warnbg px-3 py-2 text-[11.5px] leading-relaxed text-warnfg" role="alert">{{ payload.onlineError }}；当前仍可查看本地采集内容。</p>
        <p v-if="payload.onlineStatus === 'ready' && payload.commentsError" class="mt-2 rounded-md bg-warnbg px-3 py-2 text-[11.5px] leading-relaxed text-warnfg" role="status">PR 正文已获取，但评论读取失败：{{ payload.commentsError }}</p>
        <p v-else-if="payload.onlineStatus === 'ready' && payload.commentsComplete === 'false'" class="mt-2 text-[11px] text-muted">当前显示 {{ pullRequestComments.length }} / {{ payload.commentsCount }} 条评论；完整讨论请在 GitHub 查看。</p>
        <p v-else-if="payload.onlineStatus === 'ready' && payload.onlineSource === 'github'" class="mt-2 text-[11px] text-muted">已从 GitHub 获取最新 PR 内容与对话评论。</p>
        <p v-if="payload.bodyStatus === 'loading'" class="mt-2 text-[12.5px] text-muted">正在读取 PR 详情…</p>
        <p v-else-if="payload.bodyStatus === 'error'" class="mt-2 text-[12.5px] leading-relaxed text-warnfg">{{ payload.bodyError }}</p>
        <ReleaseNotes v-else-if="payload.body" :body="payload.body" class="mt-2 max-h-[55vh] overflow-auto rounded-md bg-soft/50 px-3 py-2.5 text-[12.5px] leading-relaxed text-ink" />
        <p v-else-if="payload.bodyStatus === 'ready'" class="mt-2 text-[12.5px] text-muted">此 PR 没有填写描述。</p>
        <p v-if="payload.onlineStatus !== 'ready' && Number(payload.commentsCount) > 0" class="mt-2 text-[11px] text-muted">本地记录显示有 {{ payload.commentsCount }} 条评论；点击“在线获取”加载讨论。</p>
      </section>
      <section v-if="payload.onlineStatus === 'ready'" class="mt-5">
        <div class="flex items-center justify-between gap-2">
          <h3 class="m-0 text-[13px] font-semibold text-ink">对话评论</h3>
          <span class="text-[11px] text-muted">{{ pullRequestComments.length }} / {{ payload.commentsCount ?? '0' }} 条</span>
        </div>
        <p v-if="!pullRequestComments.length && !payload.commentsError" class="mt-2 text-[12px] text-muted">此 PR 暂无对话评论。</p>
        <div v-else class="mt-2 space-y-3">
          <article v-for="(comment, index) in pullRequestComments" :key="`${comment.author}-${comment.createdAt}-${index}`" class="rounded-md border border-line bg-soft/40 p-3">
            <div class="flex flex-wrap items-center justify-between gap-1 text-[11px]">
              <span class="font-medium text-ink">{{ comment.author }}</span>
              <time v-if="comment.createdAt" class="font-mono text-muted">{{ comment.createdAt }}</time>
            </div>
            <ReleaseNotes v-if="comment.body" :body="comment.body" class="mt-2 max-h-[40vh] overflow-auto text-[12px] leading-relaxed text-ink" />
            <p v-else class="mt-2 text-[11px] text-muted">此评论没有文字内容。</p>
          </article>
        </div>
      </section>
      <a v-if="payload.url" :href="payload.url" target="_blank" rel="noreferrer" class="mt-4 inline-flex text-[12px] text-ink underline decoration-line underline-offset-2 hover:decoration-ink">在 GitHub 打开</a>
    </template>

    <template #footer>
      <GdButton variant="outline" class="flex-1" @click="ui.closeDrawer()">关闭</GdButton>
    </template>
  </GdDrawer>
</template>
