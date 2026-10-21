<script setup lang="ts">
import { computed } from 'vue'
import type { NamedSeries } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'

const emit = defineEmits<{ select: [payload: { dataIndex: number; seriesName: string; name: string; value: unknown }] }>()
import { groupedOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ series: NamedSeries[]; unit: string; colors?: string[]; height?: number; showLegend?: boolean }>(), { colors: () => [], height: 240, showLegend: true })
const ui = useUiStore()
const option = computed(() => {
  const t = chartTheme(ui.isDark)
  return groupedOption(props.series, props.unit, props.colors.length ? props.colors : t.series, t, props.showLegend && props.series.length > 1, props.height < 140)
})
</script>

<template>
  <EChart :option="option" :height="height" @select="(payload) => emit('select', payload)" />
</template>
