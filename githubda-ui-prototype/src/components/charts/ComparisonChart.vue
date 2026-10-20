<script setup lang="ts">
import { computed } from 'vue'
import type { TimePoint } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { comparisonOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ entries: { label: string; color: string; points: TimePoint[] }[]; height?: number }>(), { height: 280 })
const ui = useUiStore()
const option = computed(() => comparisonOption(props.entries, chartTheme(ui.isDark)))
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
