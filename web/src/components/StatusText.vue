<script setup lang="ts">
import type { AnalysisStatus, TaskStatus } from '@/services/domain'
import { analysisLabel, taskLabel } from '@/lib/format'

const props = defineProps<{ status: AnalysisStatus | TaskStatus }>()
const label = () => props.status in ({ queued: 1, running: 1, succeeded: 1, partial: 1, failed: 1, cancelled: 1 }) ? taskLabel(props.status as TaskStatus) : analysisLabel(props.status as AnalysisStatus)
</script>

<template><span class="status-text" :class="`status-${status}`"><i />{{ label() }}</span></template>
