<script setup lang="ts">
import type { Coverage } from '@/services/types'
defineProps<{ coverage: Coverage; compact?: boolean }>()
</script>

<template>
  <span class="inline-flex items-center gap-1.5" :class="compact ? 'text-[11px]' : 'text-[12px]'">
    <span
      class="size-1.5 rounded-full"
      :class="coverage.state === 'complete' ? 'bg-ink/60' : coverage.state === 'partial' ? 'bg-warnfg' : 'bg-muted'"
    />
    <span :class="coverage.state === 'partial' ? 'font-medium text-warnfg' : 'text-muted'">{{ coverage.label }}</span>
    <span v-if="coverage.detail && !compact" class="text-muted">· {{ coverage.detail }}</span>
  </span>
</template>
