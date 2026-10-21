<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { MONO, chartTheme } from './theme'

const props = withDefaults(defineProps<{
  items: { label: string; value: number; muted?: boolean; color?: string }[]
  color?: string
  height?: number
  valueSuffix?: string
  maxValue?: number
}>(), { color: '', height: 220, valueSuffix: '', maxValue: 0 })

const ui = useUiStore()
const option = computed<EChartsOption>(() => {
  const t = chartTheme(ui.isDark)
  const fallback = props.color || t.series[0]
  return {
    animation: false,
    grid: { left: 104, right: 52, top: 4, bottom: 4 },
    tooltip: { show: false },
    xAxis: { type: 'value', show: false, max: props.maxValue || undefined },
    yAxis: {
      type: 'category', inverse: true, data: props.items.map((i) => i.label),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 11, fontFamily: MONO, width: 96, overflow: 'truncate' },
    },
    series: [{
      type: 'bar', barWidth: 8,
      data: props.items.map((i) => ({ value: i.value, itemStyle: { color: i.muted ? t.border : i.color || fallback, borderRadius: 4 } })),
      label: { show: true, position: 'right', color: t.muted, fontSize: 10.5, fontFamily: MONO, formatter: `{c}${props.valueSuffix}` },
    }],
  }
})
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
