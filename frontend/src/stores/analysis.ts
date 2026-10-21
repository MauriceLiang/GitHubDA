import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Granularity, TimeWindow } from '@/services/types'

/** Cross-page analysis preferences (shared by header, tabs and comparison). */
export const useAnalysisStore = defineStore('analysis', () => {
  const timeWindow = ref<TimeWindow>(90)
  const granularity = ref<Granularity>('week')
  const compareIds = ref<string[]>([])
  const recentIds = ref<string[]>([])

  function setWindow(value: TimeWindow) {
    timeWindow.value = value
  }
  function setGranularity(value: Granularity) {
    granularity.value = value
  }
  function toggleCompare(id: string) {
    const exists = compareIds.value.includes(id)
    if (exists) compareIds.value = compareIds.value.filter((x) => x !== id)
    else if (compareIds.value.length < 5) compareIds.value = [...compareIds.value, id]
  }
  function setCompare(ids: string[]) {
    compareIds.value = ids.slice(0, 5)
  }
  function remember(id: string) {
    recentIds.value = [id, ...recentIds.value.filter((x) => x !== id)].slice(0, 6)
  }

  return { timeWindow, granularity, compareIds, recentIds, setWindow, setGranularity, toggleCompare, setCompare, remember }
})
