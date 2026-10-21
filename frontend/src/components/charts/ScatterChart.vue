<script setup lang="ts">
import { computed } from 'vue'
import type { ResearchScatterPoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { scatterOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ points: ResearchScatterPoint[]; groups: string[]; colors?: string[]; height?: number }>(), { colors: () => [], height: 300 })
const ui = useUiStore()
const option = computed(() => {
  const t = chartTheme(ui.isDark)
  return scatterOption(props.points, props.groups, props.colors.length ? props.colors : [t.series[0], t.series[2], t.series[3]], t)
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
