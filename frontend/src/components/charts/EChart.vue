<script setup lang="ts">
import * as echarts from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import { CalendarComponent, DataZoomComponent, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

echarts.use([BarChart, LineChart, ScatterChart, HeatmapChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, CalendarComponent, DataZoomComponent, CanvasRenderer])

const props = withDefaults(defineProps<{ option: EChartsOption; height?: number }>(), { height: 240 })
const emit = defineEmits<{ select: [payload: { dataIndex: number; seriesName: string; name: string; value: unknown }] }>()
const el = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value, undefined, { renderer: 'canvas' })
  chart.setOption(props.option)
  chart.on('click', (params) => {
    if (typeof params.dataIndex !== 'number') return
    emit('select', { dataIndex: params.dataIndex, seriesName: String(params.seriesName ?? ''), name: String(params.name ?? ''), value: params.value })
  })
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(el.value)
})

watch(() => props.option, (option) => chart?.setOption(option, true), { deep: true })
watch(() => props.height, () => chart?.resize())

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})

defineExpose({ chart })
</script>

<template>
  <div ref="el" :style="{ height: `${height}px`, width: '100%' }" />
</template>
