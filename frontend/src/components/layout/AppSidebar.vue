<script setup lang="ts">
import { FlaskConical, FolderGit2, GitCompareArrows, LayoutDashboard } from 'lucide-vue-next'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAnalysisStore } from '@/stores/analysis'
import { useDataSource } from '@/composables/useDataSource'
import { useAsyncData } from '@/composables/useAsyncData'

const route = useRoute()
const analysis = useAnalysisStore()
const { data: repositories } = useAsyncData(() => useDataSource().listRepositories())

const nav = [
  { key: 'overview', label: '总览', to: '/', icon: LayoutDashboard },
  { key: 'repositories', label: '仓库', to: '/repositories', icon: FolderGit2 },
  { key: 'compare', label: '项目比较', to: '/compare', icon: GitCompareArrows },
  { key: 'research', label: '研究分析', to: '/research', icon: FlaskConical },
]
const recent = computed(() =>
  analysis.recentIds
    .map((id) => repositories.value?.find((r) => r.id === id))
    .filter((r): r is NonNullable<typeof r> => Boolean(r))
    .slice(0, 3),
)
</script>

<template>
  <aside class="sticky top-0 hidden h-screen w-[224px] shrink-0 flex-col border-r border-line bg-panel px-3 py-[18px] lg:flex">
    <div class="flex h-[38px] items-center gap-2.5 px-1.5">
      <span class="relative grid size-6 shrink-0 place-items-center overflow-hidden">
        <img
          src="/repovantage-icon.png"
          alt=""
          class="absolute left-1/2 top-1/2 size-11 max-w-none -translate-x-1/2 -translate-y-1/2 object-contain"
        />
      </span>
      <div class="leading-tight">
        <b class="text-[14.5px] font-semibold">RepoVantage</b>
        <span class="block text-[11px] text-muted">开源项目分析</span>
      </div>
    </div>

    <nav class="mt-[18px] flex flex-col gap-0.5">
      <RouterLink
        v-for="item in nav"
        :key="item.key"
        :to="item.to"
        class="flex h-[34px] items-center gap-2.5 rounded-md px-2.5 text-[13.5px] transition-colors"
        :class="route.meta.nav === item.key ? 'bg-soft font-semibold text-ink' : 'text-muted hover:bg-track hover:text-ink'"
      >
        <component :is="item.icon" :size="16" />
        {{ item.label }}
      </RouterLink>
    </nav>

    <div class="mt-6 flex items-center justify-between px-2.5 text-[11.5px] text-muted">
      <span>最近分析</span>
      <RouterLink to="/repositories" class="hover:text-ink">全部</RouterLink>
    </div>
    <div class="mt-1.5 flex flex-col gap-px">
      <RouterLink
        v-for="repo in recent"
        :key="repo.id"
        :to="`/repositories/${repo.id}/overview`"
        class="flex h-8 items-center gap-2 rounded-md px-2.5 text-[12px] transition-colors"
        :class="route.params.id === repo.id ? 'bg-soft font-medium text-ink' : 'text-muted hover:bg-track hover:text-ink'"
      >
        <span class="size-1.5 rounded-full" :class="repo.status === 'partial' ? 'bg-warnfg' : 'bg-ink/70'" />
        {{ repo.fullName.split('/')[1] }}
      </RouterLink>
    </div>

    <div class="mt-auto border-t border-line pt-2.5">
      <div class="mt-2 flex items-center gap-2.5 px-2.5 py-1.5">
        <span class="grid size-[26px] place-items-center rounded-full bg-soft text-[10.5px] font-semibold">DA</span>
        <div class="leading-tight">
          <b class="block text-[12px] font-medium">本机工作区</b>
          <span class="text-[10.5px] text-muted">数据来自本地服务</span>
        </div>
      </div>
    </div>
  </aside>
</template>
