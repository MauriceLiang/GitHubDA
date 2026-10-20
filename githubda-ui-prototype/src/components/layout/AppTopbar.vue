<script setup lang="ts">
import { ChevronRight, ListChecks, Moon, Sun } from 'lucide-vue-next'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const ui = useUiStore()
const crumb = computed(() => (route.meta.crumb as string) ?? '工作台')
const current = computed(() => (route.meta.title as string) ?? '')
</script>

<template>
  <header class="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-line bg-bg px-7">
    <div class="flex min-w-0 items-center gap-1.5 text-[12.5px] text-muted">
      <RouterLink to="/" class="hover:text-ink">{{ crumb }}</RouterLink>
      <ChevronRight :size="13" />
      <b class="truncate font-medium text-ink">{{ current }}</b>
    </div>
    <div class="flex items-center gap-2">
      <RouterLink to="/tasks" class="flex h-[30px] items-center gap-1.5 rounded-md bg-track px-2.5 text-[12.5px] hover:bg-soft">
        <ListChecks :size="14" /> 任务
      </RouterLink>
      <button class="grid size-[30px] place-items-center rounded-md text-muted hover:bg-track hover:text-ink" :title="ui.isDark ? '切换到浅色' : '切换到深色'" @click="ui.toggleTheme()">
        <Sun v-if="ui.isDark" :size="16" />
        <Moon v-else :size="16" />
      </button>
    </div>
  </header>
</template>
