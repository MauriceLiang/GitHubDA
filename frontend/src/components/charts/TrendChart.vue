<script setup lang="ts">
import { computed } from 'vue'
import type { TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'

const emit = defineEmits<{ select: [payload: { dataIndex: number; seriesName: string; name: string; value: unknown }] }>()
import { timeSeriesOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ points: TimePoint[]; unit: string; color?: string; height?: number }>(), { color: '', height: 260 })
const ui = useUiStore()
const option = computed(() => {
  const t = chartTheme(ui.isDark)
  return timeSeriesOption(props.points, props.unit, props.color || t.series[0], t, props.points.length > 40)
})
</script>

<template>
  <EChart :option="option" :height="height" @select="(payload) => emit('select', payload)" />
</template>
