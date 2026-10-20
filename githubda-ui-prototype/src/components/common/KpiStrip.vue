<script setup lang="ts">
import { Info } from 'lucide-vue-next'
import type { Metric } from '@/services/types'

defineProps<{ metrics: Metric[] }>()
</script>

<template>
  <section class="flex flex-col divide-y divide-line rounded-[10px] border border-line bg-panel px-5 py-3.5 sm:flex-row sm:divide-x sm:divide-y-0">
    <div v-for="metric in metrics" :key="metric.id" class="min-w-0 flex-1 px-0 py-3 sm:px-5 sm:py-0 sm:first:pl-0">
      <div class="flex items-center gap-1 text-[12.5px] text-muted">
        {{ metric.label }} <Info v-if="metric.sampleSize !== undefined" :size="12" />
      </div>
      <div class="mt-1 flex items-end gap-1">
        <b class="text-[29px] font-semibold leading-tight tabular-nums">{{ metric.value === null ? '—' : metric.value.toLocaleString('en-US', { maximumFractionDigits: 1 }) }}</b>
        <span class="pb-1 text-[12.5px] text-muted">{{ metric.value === null ? '' : metric.unit }}</span>
      </div>
      <div class="mt-0.5 text-[11.5px] text-muted">{{ metric.note }}</div>
    </div>
  </section>
</template>
