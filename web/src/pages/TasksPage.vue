<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ExternalLink, RotateCcw } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import StatusText from '@/components/StatusText.vue'
import { dataMode, services } from '@/services'
import type { Repository, Task } from '@/services/domain'
import { dateTime, taskLabel } from '@/lib/format'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const filter = ref('all')
const tasks = ref<Task[]>([])
const repositories = ref<Repository[]>([])
const selectedId = ref('')
const loading = ref(false)
const error = ref('')
const busyId = ref('')
const selected = computed(() => tasks.value.find((task) => task.taskId === selectedId.value) ?? null)
const repoNames = computed(() => new Map(repositories.value.map((repo) => [repo.repositoryId, repo.fullName])))
const filters = [{ id: 'all', label: '全部' }, { id: 'active', label: '进行中' }, { id: 'done', label: '已完成' }, { id: 'problem', label: '需关注' }]
let timer = 0

async function load() {
  loading.value = tasks.value.length === 0; error.value = ''
  try { const [taskRows, repos] = await Promise.all([services.listTasks(filter.value), services.listRepositories()]); tasks.value = taskRows; repositories.value = repos; if (selectedId.value && !taskRows.some((task) => task.taskId === selectedId.value)) selectedId.value = '' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '任务列表加载失败' }
  finally { loading.value = false }
}
async function retry(task: Task) {
  if (busyId.value) return
  busyId.value = task.taskId; error.value = ''
  try { const next = await services.retryTask(task.taskId); store.flash('已创建新的重试任务，原任务记录仍保留'); filter.value = 'all'; await load(); selectedId.value = next.taskId }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '重试失败' }
  finally { busyId.value = '' }
}
function progress(task: Task) { return task.progressKind === 'stages' && task.progressPercent != null ? task.progressPercent : null }
onMounted(() => { void load(); timer = window.setInterval(() => { void load() }, dataMode === 'mock' ? 1300 : 3500) })
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <section class="page-content">
    <PageHeader title="任务" description="查看采集状态、任务阶段与历史记录。" />
    <div class="segmented task-filters" role="tablist" aria-label="任务筛选"><button v-for="item in filters" :key="item.id" :class="{ active: filter === item.id }" @click="filter = item.id; selectedId = ''; void load()">{{ item.label }}</button></div>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <div class="task-layout">
      <div class="task-list">
        <button v-for="task in tasks" :key="task.taskId" class="task-row" :class="{ selected: selectedId === task.taskId }" @click="selectedId = task.taskId">
          <span class="task-dot" :class="`task-dot-${task.status}`" />
          <span class="task-row-main"><strong>{{ repoNames.get(task.repositoryId) || `仓库 ${task.repositoryId}` }}</strong><small>{{ task.depth === 'deep' ? '深度分析' : '基础分析' }} · {{ dateTime(task.createdAt) }}</small></span>
          <span class="task-row-status"><StatusText :status="task.status" /><span v-if="progress(task) != null">阶段进度 {{ progress(task) }}%</span><span v-else-if="task.status === 'queued'">等待 Worker</span></span>
        </button>
        <div v-if="loading" class="empty-inline">正在加载任务…</div>
        <div v-else-if="!tasks.length" class="empty-inline"><strong>这里还没有任务</strong><span>新建仓库分析后，任务会显示在这里。</span><RouterLink to="/" class="text-link">开始分析</RouterLink></div>
      </div>
      <aside v-if="selected" class="task-detail">
        <div class="section-heading"><h2>任务详情</h2><button class="text-button" @click="selectedId = ''">关闭</button></div>
        <div class="task-detail-title"><div><strong>{{ repoNames.get(selected.repositoryId) || `仓库 ${selected.repositoryId}` }}</strong><small>{{ selected.depth === 'deep' ? '深度分析' : '基础分析' }} · {{ dateTime(selected.createdAt) }}</small></div><StatusText :status="selected.status" /></div>
        <div v-if="progress(selected) != null" class="progress-wrap"><div class="progress-track"><span :style="{ width: `${progress(selected)}%` }" /></div><small>阶段进度 {{ progress(selected) }}% · 不代表数据覆盖率</small></div>
        <p v-else-if="selected.status === 'queued'" class="quiet-note">任务已排队，尚无阶段进度。</p>
        <p v-else-if="selected.message" class="quiet-note">{{ selected.message }}</p>
        <dl class="task-facts"><div><dt>任务编号</dt><dd class="mono">{{ selected.taskId }}</dd></div><div><dt>当前阶段</dt><dd>{{ selected.phase || taskLabel(selected.status) }}</dd></div><div><dt>预计时间</dt><dd>{{ selected.etaSeconds == null ? '暂不可估计' : `${selected.etaSeconds} 秒` }}</dd></div></dl>
        <div v-if="selected.modules.length" class="module-list"><strong>采集模块</strong><div v-for="module in selected.modules" :key="module.name"><span>{{ module.name }}</span><span>{{ module.status }} · {{ module.coverage }}</span></div></div>
        <div class="dialog-actions"><RouterLink v-if="selected.repositoryId" class="button" :to="`/repositories/${selected.repositoryId}`"><ExternalLink :size="14" />打开仓库</RouterLink><button v-if="selected.status === 'failed' || selected.status === 'partial'" class="button primary" :disabled="busyId === selected.taskId" @click="retry(selected)"><RotateCcw :size="14" />{{ busyId === selected.taskId ? '正在重试…' : '重新执行' }}</button></div>
      </aside>
    </div>
  </section>
</template>
