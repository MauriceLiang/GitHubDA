<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ArrowRight, ArrowUpRight, Search } from '@lucide/vue'
import { RouterLink, useRouter } from 'vue-router'
import StatusText from '@/components/StatusText.vue'
import { dataMode, services } from '@/services'
import type { Overview, Repository, Task } from '@/services/domain'
import { dateTime, metric } from '@/lib/format'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const store = useAppStore()
const overview = ref<Overview | null>(null)
const repositories = ref<Repository[]>([])
const tasks = ref<Task[]>([])
const input = ref('')
const inputElement = ref<HTMLInputElement | null>(null)
const error = ref('')
const busy = ref(false)
const loading = ref(true)
let timer = 0
const taskRepo = computed(() => new Map(repositories.value.map((repo) => [repo.repositoryId, repo.fullName])))
const firstRepository = computed(() => overview.value?.recentRepositories[0])
function useExample(value: string) { input.value = value; error.value = ''; inputElement.value?.focus() }

async function load() {
  try {
    const [summary, library, list] = await Promise.all([services.overview(), services.listRepositories({ sort: 'last_collected', order: 'desc' }), services.listTasks()])
    overview.value = summary; repositories.value = library; tasks.value = list
  } catch (cause) { if (!overview.value) error.value = cause instanceof Error ? cause.message : '数据暂时不可用' }
  finally { loading.value = false }
}
async function analyze() {
  if (busy.value || !input.value.trim()) return
  busy.value = true; error.value = ''
  try {
    const result = await services.addAndAnalyze(input.value)
    input.value = ''
    store.flash(result.existing ? '仓库已在个人库中，已打开原有详情' : '已加入分析队列')
    await router.push(`/repositories/${result.repositoryId}`)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '仓库地址无效' }
  finally { busy.value = false }
}
onMounted(() => { void load(); timer = window.setInterval(() => { void load() }, dataMode === 'mock' ? 1500 : 5000) })
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <section class="page-content overview-page">
    <h1 class="overview-title">分析 GitHub 仓库</h1>
    <p class="overview-intro">先了解关注度与最近更新，再按需要查看维护活动、比较候选项目。</p>
    <form class="hero-form" @submit.prevent="analyze">
      <Search :size="17" />
      <input ref="inputElement" v-model="input" type="text" aria-label="仓库地址" autocomplete="url" placeholder="粘贴 GitHub 链接，或输入 vuejs/core" :disabled="busy" />
      <button class="button primary" :disabled="busy || !input.trim()" type="submit">{{ busy ? '正在解析…' : '开始分析' }}<ArrowRight :size="16" /></button>
    </form>
    <p class="inline-help" :class="{ error: error }" role="status">{{ error || `首次添加会采集基础资料；提交、议题与发布等活动数据，可在详情页继续采集。${dataMode === 'mock' ? '当前为演示样例。' : ''}` }}</p>
    <div class="example-inputs"><span>试填一个仓库</span><button type="button" :disabled="busy" @click="useExample('vuejs/core')">vuejs/core</button><button type="button" :disabled="busy" @click="useExample('psf/requests')">psf/requests</button><RouterLink v-if="firstRepository" :to="`/repositories/${firstRepository.repositoryId}`" class="text-link">先看已有分析 <ArrowRight :size="13" /></RouterLink></div>
    <ol v-if="!overview || overview.total < 2" class="getting-started" aria-label="开始使用的三个步骤"><li><span>1</span><div><strong>输入仓库</strong><p>支持公开仓库链接或 owner/repo。</p></div></li><li><span>2</span><div><strong>阅读基础概况</strong><p>先看数据时间、关注度与最近推送。</p></div></li><li><span>3</span><div><strong>按问题深入</strong><p>采集活动，或选 2–5 个同类项目比较。</p></div></li></ol>

    <div v-if="overview" class="overview-stats" aria-label="仓库统计">
      <div><span>已添加仓库</span><strong>{{ overview.total }}</strong></div>
      <div><span>已有基础数据</span><strong>{{ overview.analyzed }}</strong></div>
      <div><span>进行中任务</span><strong>{{ overview.active }}</strong></div>
      <div><span>最近采集</span><strong class="stat-date">{{ dateTime(overview.latestCollection) }}</strong></div>
    </div>
    <div v-else-if="loading" class="overview-stats skeleton-line" aria-label="正在加载统计" />

    <section class="question-paths" aria-label="按问题选择分析路径">
      <RouterLink :to="firstRepository ? `/repositories/${firstRepository.repositoryId}?view=activity` : '/repositories?tab=discover'"><strong>这个项目最近有更新吗？ <ArrowUpRight :size="15" /></strong><span>看推送时间、提交与发布记录。</span></RouterLink>
      <RouterLink to="/compare"><strong>几个候选项目差别在哪？ <ArrowUpRight :size="15" /></strong><span>在同一指标定义下比较，核对数据范围。</span></RouterLink>
      <RouterLink to="/research"><strong>一组开源项目有什么规律？ <ArrowUpRight :size="15" /></strong><span>核对研究样本，再看分组与相关性。</span></RouterLink>
    </section>

    <div class="overview-columns">
      <section>
        <div class="section-heading"><h2>最近仓库</h2><RouterLink to="/repositories?tab=saved">查看全部 <ArrowRight :size="14" /></RouterLink></div>
        <div v-if="overview?.recentRepositories.length" class="compact-list">
          <RouterLink v-for="repo in overview.recentRepositories" :key="repo.repositoryId" class="overview-repo" :to="`/repositories/${repo.repositoryId}`">
            <span class="repo-mark">{{ repo.fullName.split('/').at(-1)?.slice(0, 1).toLocaleUpperCase() }}</span>
            <span class="overview-repo-main"><strong>{{ repo.fullName }}</strong><small>{{ repo.description || '暂无仓库简介' }}</small></span>
            <span class="overview-repo-stars">{{ metric(repo.stars) }} <span>★</span></span>
            <ArrowUpRight class="row-arrow" :size="16" />
          </RouterLink>
        </div>
        <div v-else class="empty-inline"><strong>还没有仓库</strong><span>输入仓库地址开始分析。</span></div>
      </section>
      <section>
        <div class="section-heading"><h2>最近任务</h2><RouterLink to="/tasks">查看全部 <ArrowRight :size="14" /></RouterLink></div>
        <div v-if="overview?.recentTasks.length" class="task-list-plain">
          <RouterLink v-for="task in overview.recentTasks.slice(0, 4)" :key="task.taskId" class="task-plain-row" to="/tasks">
            <span class="task-dot" :class="`task-dot-${task.status}`" />
            <span><strong>{{ taskRepo.get(task.repositoryId) || `仓库 ${task.repositoryId}` }}</strong><small>{{ task.depth === 'deep' ? '深度' : '基础' }}分析 · {{ dateTime(task.createdAt) }}</small></span>
            <StatusText :status="task.status" />
          </RouterLink>
        </div>
        <div v-else class="empty-inline"><strong>暂无分析任务</strong><span>新建分析后会显示在这里。</span></div>
      </section>
    </div>
  </section>
</template>
