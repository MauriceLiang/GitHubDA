<script setup lang="ts">
import { computed } from 'vue'
import type { ReleaseRecord } from '@/services/types'
import { useUiStore } from '@/stores/ui'
import EChart from './EChart.vue'
import { timelineOption } from './options'
import { chartTheme } from './theme'

const props = withDefaults(defineProps<{ releases: ReleaseRecord[]; height?: number; compact?: boolean }>(), { height: 150, compact: false })
const ui = useUiStore()
const option = computed(() => timelineOption(props.releases, chartTheme(ui.isDark), props.compact))
</script>

<template>
  <EChart :option="option" :height="height" />
</template>
