<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { use } from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { init, type EChartsType } from 'echarts/core'
import { useAppStore } from '@/stores/app'

use([LineChart, BarChart, GridComponent, TooltipComponent, SVGRenderer])
const props = defineProps<{ labels: string[]; values: Array<number | null>; seriesName?: string; kind?: 'line' | 'bar'; label: string }>()
const store = useAppStore()
const root = ref<HTMLDivElement | null>(null)
let chart: EChartsType | null = null
let resizeObserver: ResizeObserver | null = null
const colors = computed(() => store.theme === 'dark' ? { text: '#9ca8a0', line: '#303a33', accent: '#a0d2b0' } : { text: '#77807a', line: '#e7eae5', accent: '#245944' })

function render() {
  if (!root.value || !chart) return
  const palette = colors.value
  chart.setOption({
    animation: false,
    grid: { left: 12, right: 14, top: 18, bottom: 12, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: store.theme === 'dark' ? '#1a201d' : '#fff', borderColor: palette.line, textStyle: { color: palette.text } },
    xAxis: { type: 'category', data: props.labels, axisLabel: { color: palette.text }, axisLine: { lineStyle: { color: palette.line } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: palette.text, formatter: (value: number) => new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(value) }, splitLine: { lineStyle: { color: palette.line } } },
    series: [{ name: props.seriesName ?? '数值', type: props.kind ?? 'line', data: props.values, smooth: false, symbol: 'circle', symbolSize: 6, lineStyle: { color: palette.accent, width: 2 }, itemStyle: { color: palette.accent }, areaStyle: props.kind === 'bar' ? undefined : { color: palette.accent, opacity: 0.08 }, barMaxWidth: 34 }],
  }, true)
}
onMounted(async () => { await nextTick(); if (!root.value) return; chart = init(root.value, undefined, { renderer: 'svg' }); resizeObserver = new ResizeObserver(() => chart?.resize()); resizeObserver.observe(root.value); render() })
watch(() => [props.labels, props.values, props.kind, store.theme], render, { deep: true })
onUnmounted(() => { resizeObserver?.disconnect(); chart?.dispose(); chart = null })
</script>

<template><div ref="root" class="chart" role="img" :aria-label="label" /></template>
