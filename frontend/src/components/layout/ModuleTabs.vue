<script setup lang="ts">
import { Info } from 'lucide-vue-next'
import { useUiStore } from '@/stores/ui'

defineProps<{ repoId: string; active: string }>()
const ui = useUiStore()
const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'activity', label: '开发活动' },
  { key: 'issues', label: 'Issue' },
  { key: 'prs', label: 'PR' },
  { key: 'releases', label: '版本发布' },
]
</script>

<template>
  <div class="sticky top-14 z-20 flex h-11 items-center justify-between border-b border-line bg-bg px-7">
    <nav class="flex h-11 gap-[22px]">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.key"
        :to="`/repositories/${repoId}/${tab.key}`"
        class="flex h-11 items-center border-b-2 border-transparent text-[13px] text-muted hover:text-ink"
        :class="active === tab.key && 'border-ink font-semibold text-ink'"
      >
        {{ tab.label }}
      </RouterLink>
    </nav>
    <button class="flex items-center gap-1 text-[12px] text-muted hover:text-ink" @click="ui.openDrawer('definitions', { metric: 'M01' })">
      <Info :size="13" /> 数据与口径
    </button>
  </div>
</template>
