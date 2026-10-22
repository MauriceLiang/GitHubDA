<script setup lang="ts">
import { ChartNoAxesCombined, Columns2, Folder, Gauge } from 'lucide-vue-next'
import { useRoute } from 'vue-router'

const route = useRoute()

const nav = [
  { key: 'overview', label: '总览', to: '/', icon: Gauge },
  { key: 'repositories', label: '仓库', to: '/repositories', icon: Folder },
  { key: 'compare', label: '项目比较', to: '/compare', icon: Columns2 },
  { key: 'research', label: '研究分析', to: '/research', icon: ChartNoAxesCombined },
]
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
  </aside>
</template>
