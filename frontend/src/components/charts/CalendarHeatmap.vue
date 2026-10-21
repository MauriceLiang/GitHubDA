<script setup lang="ts">
import { computed } from 'vue'
import type { TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { calendarOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ points: TimePoint[]; height?: number }>(), { height: 200 })
const ui = useUiStore()
const option = computed(() => calendarOption(props.points, chartTheme(ui.isDark)))
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
