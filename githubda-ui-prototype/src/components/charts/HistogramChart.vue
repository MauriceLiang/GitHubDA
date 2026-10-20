<script setup lang="ts">
import { computed } from 'vue'
import type { HistogramBucket } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { histogramOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ buckets: HistogramBucket[]; color?: string; unit?: string; height?: number }>(), { color: '', unit: '条记录', height: 200 })
const ui = useUiStore()
const option = computed(() => {
  const t = chartTheme(ui.isDark)
  return histogramOption(props.buckets, props.color || t.series[1], t, props.unit)
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
