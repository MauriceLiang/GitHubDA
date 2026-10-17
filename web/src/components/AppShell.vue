<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { ChartBar, FolderGit2, LayoutDashboard, ListTodo, Menu, Moon, RotateCcw, Search, Settings2, Sun, X } from '@lucide/vue'
import ModalShell from './ModalShell.vue'
import { useAppStore } from '@/stores/app'
import { dataMode, services } from '@/services'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const settingsOpen = ref(false)
const resetOpen = ref(false)
const searchText = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
const mobileMenu = ref<HTMLButtonElement | null>(null)
const mobileClose = ref<HTMLButtonElement | null>(null)
const nav = [
  { label: '总览', to: '/', icon: LayoutDashboard },
  { label: '仓库', to: '/repositories?tab=saved', icon: FolderGit2 },
  { label: '研究', to: '/research', icon: ChartBar },
  { label: '任务', to: '/tasks', icon: ListTodo },
]
const currentTitle = computed(() => route.path.startsWith('/repositories/') ? '仓库详情' : route.path === '/compare' ? '仓库比较' : nav.find((item) => route.path === item.to.split('?')[0])?.label ?? '总览')
watch(() => store.theme, (theme) => { document.documentElement.dataset.theme = theme }, { immediate: true })
watch(() => store.searchOpen, (open) => { if (open) window.setTimeout(() => searchInput.value?.focus(), 40) })
watch(() => store.mobileNavOpen, (open) => { void nextTick(() => (open ? mobileClose.value : mobileMenu.value)?.focus()) })

function onKey(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === 'k') { event.preventDefault(); store.searchOpen = true }
  if (event.key === 'Escape') { store.searchOpen = false; settingsOpen.value = false; resetOpen.value = false; store.mobileNavOpen = false }
}
async function analyzeFromSearch() {
  if (!searchText.value.trim()) return
  try {
    const result = await services.addAndAnalyze(searchText.value)
    store.searchOpen = false; searchText.value = ''
    if (result.existing) store.flash('仓库已在个人库中，已打开原有详情')
    else store.flash('已加入分析队列')
    router.push(`/repositories/${result.repositoryId}`)
  } catch (error) { store.flash(error instanceof Error ? error.message : '无法解析仓库地址') }
}
function resetMock() {
  services.resetMock?.()
  store.clearSelected()
  resetOpen.value = false
  store.flash('演示数据已恢复')
  router.push('/')
}
onMounted(() => { window.addEventListener('keydown', onKey) })
onUnmounted(() => { window.removeEventListener('keydown', onKey) })
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar" :class="{ 'sidebar-open': store.mobileNavOpen }" aria-label="主导航">
      <div class="brand">
        <div class="brand-mark">G</div><div><div class="brand-name">GitHubDA</div><div class="brand-sub">仓库分析</div></div>
        <button ref="mobileClose" class="icon-button mobile-close" aria-label="关闭导航" @click="store.mobileNavOpen = false"><X :size="17" /></button>
      </div>
      <nav class="nav-list">
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to" class="nav-item" :class="{ active: route.path === item.to.split('?')[0] && (item.to.includes('tab=') ? route.query.tab !== 'discover' : true) }" @click="store.mobileNavOpen = false">
          <component :is="item.icon" :size="17" :stroke-width="1.8" /><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-spacer" />
      <div class="sidebar-bottom">
        <p class="sidebar-caption">设置</p>
        <button class="nav-item" @click="settingsOpen = true"><Settings2 :size="17" /><span>界面设置</span></button>
        <button v-if="dataMode === 'mock'" class="nav-item" @click="resetOpen = true"><RotateCcw :size="17" /><span>重置演示数据</span></button>
        <p class="local-status"><i />{{ dataMode === 'mock' ? '仅供演示 · 数据保存在本地' : '本机工作区 · 真实 API' }}</p>
      </div>
    </aside>
    <button v-if="store.mobileNavOpen" class="mobile-scrim" aria-label="关闭导航" @click="store.mobileNavOpen = false" />

    <main class="main-area">
      <header class="topbar">
        <div class="topbar-left">
          <button ref="mobileMenu" class="icon-button mobile-menu" aria-label="打开导航" @click="store.mobileNavOpen = true"><Menu :size="19" /></button>
          <span class="current-title">{{ currentTitle }}</span>
        </div>
        <div class="topbar-actions">
          <button class="search-trigger" aria-label="搜索仓库" @click="store.searchOpen = true"><Search :size="15" /><span>搜索仓库</span><kbd>⌘ K</kbd></button>
          <span v-if="dataMode === 'mock'" class="demo-pill">演示数据</span>
          <button class="icon-button" :aria-label="store.theme === 'light' ? '切换深色主题' : '切换浅色主题'" @click="store.toggleTheme()"><Moon v-if="store.theme === 'light'" :size="18" /><Sun v-else :size="18" /></button>
        </div>
      </header>
      <RouterView />
    </main>
    <div v-if="store.toast" class="toast" role="status" aria-live="polite">{{ store.toast }}</div>

    <ModalShell v-model:open="store.searchOpen" title="搜索仓库" description="输入 owner/repo 或 GitHub 仓库链接，直接开始分析。">
      <form class="dialog-search" @submit.prevent="analyzeFromSearch">
        <input ref="searchInput" v-model="searchText" class="field" aria-label="仓库地址" placeholder="例如 vuejs/core" />
        <button class="button primary" type="submit">开始分析</button>
      </form>
      <p class="muted small">快捷键 ⌘ K / Ctrl K 打开，Escape 关闭。</p>
    </ModalShell>
    <ModalShell v-model:open="settingsOpen" title="界面设置" description="调整主题显示。">
      <div class="setting-row"><div><strong>界面主题</strong><p class="muted small">亮色或深色</p></div><div class="segmented"><button :class="{ active: store.theme === 'light' }" @click="store.setTheme('light')">浅色</button><button :class="{ active: store.theme === 'dark' }" @click="store.setTheme('dark')">深色</button></div></div>
      <p v-if="dataMode === 'mock'" class="muted small">演示任务和仓库仅保存在当前浏览器的本地存储中。</p>
    </ModalShell>
    <ModalShell v-model:open="resetOpen" title="重置演示数据" description="这会恢复初始仓库与任务样例，并清除当前的演示操作。">
      <div class="dialog-actions"><button class="button" @click="resetOpen = false">取消</button><button class="button primary" @click="resetMock">确认重置</button></div>
    </ModalShell>
  </div>
</template>
