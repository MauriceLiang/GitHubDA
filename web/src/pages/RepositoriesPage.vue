<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowDownUp, Download, GitCompare, Plus, Search, X } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import RepositoryLine from '@/components/RepositoryLine.vue'
import ModalShell from '@/components/ModalShell.vue'
import { services } from '@/services'
import type { Depth, Repository } from '@/services/domain'
import { download } from '@/lib/format'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const isDiscover = computed(() => route.query.tab === 'discover')
const rows = ref<Repository[]>([])
const discoverRows = ref<Repository[]>([])
const query = ref('')
const language = ref('')
const status = ref('')
const sort = ref<'name' | 'stars' | 'last_collected'>('name')
const order = ref<'asc' | 'desc'>('asc')
const loading = ref(false)
const error = ref('')
const discoverQuery = ref('')
const discoverLanguage = ref('')
const removeTarget = ref<Repository | null>(null)
const languages = computed(() => [...new Set(rows.value.map((repo) => repo.language).filter((value): value is string => Boolean(value)))].sort())
const selectedCount = computed(() => store.selected.length)
const canCompare = computed(() => selectedCount.value >= 2 && selectedCount.value <= 5)

async function loadLibrary() {
  loading.value = true; error.value = ''
  try { rows.value = await services.listRepositories({ query: query.value, language: language.value || undefined, status: status.value || undefined, sort: sort.value, order: order.value }) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '仓库列表加载失败' }
  finally { loading.value = false }
}
async function searchDiscover() {
  if (!discoverQuery.value.trim()) { discoverRows.value = []; return }
  loading.value = true; error.value = ''
  try { discoverRows.value = await services.searchRepositories(discoverQuery.value, discoverLanguage.value || undefined) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '搜索失败' }
  finally { loading.value = false }
}
async function analyze(repo: Repository) {
  try { const result = await services.addAndAnalyze(repo.fullName); store.flash(result.existing ? '仓库已在个人库中' : '已加入分析队列'); await router.push(`/repositories/${result.repositoryId}`) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '无法开始分析' }
}
async function remove() {
  if (!removeTarget.value) return
  try { await services.remove(removeTarget.value.repositoryId); store.selected = store.selected.filter((id) => id !== removeTarget.value?.repositoryId); store.persist(); store.flash('已从个人库移除，历史分析数据仍保留'); removeTarget.value = null; await loadLibrary() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '移除失败' }
}
async function refresh(id: number, depth: Depth) {
  try { const task = await services.refresh(id, depth); store.flash(task.status === 'running' ? '已有任务正在运行' : '分析任务已排队'); await loadLibrary() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '无法启动分析任务' }
}
function compare() { void router.push('/compare') }
async function exportLibrary() { try { download(await services.exportCsv('library'), 'githubda-repositories.csv'); store.flash('已导出个人库 CSV') } catch (cause) { error.value = cause instanceof Error ? cause.message : '导出失败' } }
watch(() => route.query.tab, () => { error.value = ''; if (isDiscover.value) discoverRows.value = []; else void loadLibrary() })
onMounted(() => { if (!isDiscover.value) void loadLibrary() })
</script>

<template>
  <section class="page-content">
    <PageHeader title="仓库" description="管理个人分析库，或查找新的公开仓库。">
      <button v-if="!isDiscover" class="button" @click="exportLibrary"><Download :size="15" />导出</button>
    </PageHeader>
    <div class="tabs" role="tablist" aria-label="仓库类型">
      <RouterLink class="tab" :class="{ active: !isDiscover }" to="/repositories?tab=saved" role="tab" :aria-selected="!isDiscover">我的仓库</RouterLink>
      <RouterLink class="tab" :class="{ active: isDiscover }" to="/repositories?tab=discover" role="tab" :aria-selected="isDiscover">发现仓库</RouterLink>
    </div>

    <template v-if="!isDiscover">
      <form class="filter-row" @submit.prevent="loadLibrary">
        <label class="search-field"><Search :size="15" /><input v-model="query" aria-label="筛选仓库" placeholder="搜索仓库名称" /></label>
        <select v-model="language" class="field compact-field" aria-label="按语言筛选"><option value="">所有语言</option><option v-for="item in languages" :key="item">{{ item }}</option></select>
        <select v-model="status" class="field compact-field" aria-label="按状态筛选"><option value="">所有状态</option><option value="completed">已完成</option><option value="partial">部分完成</option><option value="processing">分析中</option><option value="failed">失败</option><option value="not_started">尚未分析</option></select>
        <select v-model="sort" class="field compact-field" aria-label="排序字段"><option value="name">按名称</option><option value="stars">按 Stars</option><option value="last_collected">按采集时间</option></select>
        <button class="icon-button sort-order" type="button" :aria-label="order === 'asc' ? '升序' : '降序'" @click="order = order === 'asc' ? 'desc' : 'asc'; loadLibrary()"><ArrowDownUp :size="16" /></button>
        <button class="button" type="submit">筛选</button>
      </form>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <div class="list-toolbar"><span>{{ rows.length }} 个仓库</span><div v-if="selectedCount" class="selection-tools"><span>已选 {{ selectedCount }} / 5</span><button class="text-button" @click="store.clearSelected()"><X :size="14" />清除</button><button class="button primary small-button" :disabled="!canCompare" @click="compare"><GitCompare :size="15" />比较所选</button></div></div>
      <div class="repository-list">
        <RepositoryLine v-for="repo in rows" :key="repo.repositoryId" :repo="repo" selectable show-menu :selected="store.selected.includes(repo.repositoryId)" :disabled="repo.dataStatus === 'missing'" @select="store.toggleSelected" @refresh="refresh" @remove="removeTarget = $event" />
        <div v-if="loading" class="empty-inline">正在加载仓库…</div>
        <div v-else-if="!rows.length" class="empty-inline"><strong>{{ query || language || status ? '没有符合条件的仓库' : '个人库为空' }}</strong><span>{{ query || language || status ? '调整筛选条件后重试。' : '从“发现仓库”开始查找。' }}</span><RouterLink v-if="!query && !language && !status" to="/repositories?tab=discover" class="text-link">查找仓库</RouterLink></div>
      </div>
    </template>

    <template v-else>
      <form class="filter-row discover-form" @submit.prevent="searchDiscover">
        <label class="search-field"><Search :size="15" /><input v-model="discoverQuery" aria-label="搜索公开仓库" placeholder="仓库名称或关键词" /></label>
        <select v-model="discoverLanguage" class="field compact-field" aria-label="搜索语言"><option value="">所有语言</option><option>TypeScript</option><option>JavaScript</option><option>Python</option><option>Rust</option><option>Go</option></select>
        <button class="button primary" type="submit"><Search :size="15" />搜索</button>
      </form>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <div class="repository-list discover-list">
        <div v-for="repo in discoverRows" :key="repo.repositoryId" class="repository-line discover-line">
          <div class="repo-mark">{{ repo.fullName.split('/').at(-1)?.slice(0, 1).toLocaleUpperCase() }}</div>
          <RouterLink v-if="repo.alreadyInLibrary" class="repository-main" :to="`/repositories/${repo.repositoryId}`"><strong>{{ repo.fullName }}</strong><span>{{ repo.description || '暂无仓库简介' }}</span></RouterLink>
          <a v-else class="repository-main" :href="repo.htmlUrl" target="_blank" rel="noreferrer"><strong>{{ repo.fullName }}</strong><span>{{ repo.description || '暂无仓库简介' }}</span></a>
          <span class="repo-language">{{ repo.language || '—' }}</span><span class="repo-stars">{{ repo.stars?.toLocaleString('zh-CN') ?? '—' }} <span>★</span></span>
          <button v-if="repo.alreadyInLibrary" class="button small-button" @click="router.push(`/repositories/${repo.repositoryId}`)">查看分析</button><button v-else class="button primary small-button" @click="analyze(repo)"><Plus :size="14" />开始分析</button>
        </div>
        <div v-if="loading" class="empty-inline">正在搜索…</div>
        <div v-else-if="discoverQuery && !discoverRows.length" class="empty-inline"><strong>没有找到仓库</strong><span>检查关键词，或尝试 owner/repo 地址。</span></div>
        <div v-else-if="!discoverQuery" class="empty-inline"><strong>搜索公开仓库</strong><span>输入关键词后查看搜索结果。</span></div>
      </div>
    </template>
  </section>

  <ModalShell :open="Boolean(removeTarget)" title="从个人库移除" :description="removeTarget ? `将 ${removeTarget.fullName} 从个人库移除。已保存的历史分析和任务记录会保留。` : ''" @update:open="(open) => { if (!open) removeTarget = null }">
    <div class="dialog-actions"><button class="button" @click="removeTarget = null">取消</button><button class="button danger" @click="remove">确认移除</button></div>
  </ModalShell>
</template>
