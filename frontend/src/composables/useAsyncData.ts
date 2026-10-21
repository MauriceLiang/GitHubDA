import { ref, shallowRef, watch, type WatchSource } from 'vue'

/**
 * Minimal async-data helper used by pages: exposes loading / error / data and a
 * manual reload. Keeps pages free of repetitive try/catch blocks.
 */
export function useAsyncData<T>(loader: () => Promise<T>, source?: WatchSource) {
  const data = shallowRef<T | null>(null)
  const loading = ref(true)
  const error = ref<string | null>(null)
  let requestId = 0

  async function run() {
    const id = ++requestId
    loading.value = true
    error.value = null
    try {
      const result = await loader()
      if (id === requestId) data.value = result as T
    } catch (e) {
      if (id === requestId) {
        error.value = e instanceof Error ? e.message : '未知错误'
        data.value = null
      }
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  if (source) watch(source, () => void run(), { immediate: true })
  else void run()

  return { data, loading, error, reload: run }
}
