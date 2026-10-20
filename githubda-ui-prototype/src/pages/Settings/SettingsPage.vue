<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Check, LoaderCircle, Save, Settings2 } from 'lucide-vue-next'
import GdButton from '@/components/ui/GdButton.vue'
import GdCard from '@/components/ui/GdCard.vue'
import { useDataSource } from '@/composables/useDataSource'

const dataSource = useDataSource()
const pageLimit = ref<number | null>(10)
const savedPageLimit = ref(10)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)

const valid = computed(() => Number.isInteger(pageLimit.value) && (pageLimit.value ?? 0) >= 1 && (pageLimit.value ?? 0) <= 100)
const dirty = computed(() => pageLimit.value !== savedPageLimit.value)
const maxRecords = computed(() => valid.value && pageLimit.value ? pageLimit.value * 100 : 0)

async function loadSettings() {
  loading.value = true
  error.value = ''
  try {
    const settings = await dataSource.getCollectionSettings()
    pageLimit.value = settings.githubMaxPages
    savedPageLimit.value = settings.githubMaxPages
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '读取设置失败'
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  if (!valid.value || pageLimit.value === null) return
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    const settings = await dataSource.saveCollectionSettings({ githubMaxPages: pageLimit.value })
    pageLimit.value = settings.githubMaxPages
    savedPageLimit.value = settings.githubMaxPages
    saved.value = true
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '保存设置失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <main class="space-y-5 px-7 py-6">
    <header>
      <div class="flex items-center gap-2 text-[12px] text-muted"><Settings2 :size="14" /> 应用偏好</div>
      <h1 class="mt-1 text-[22px] font-semibold tracking-tight">设置</h1>
      <p class="mt-1 text-[13px] text-muted">调整采集范围，控制数据覆盖、耗时与 GitHub API 请求量。</p>
    </header>

    <GdCard>
      <div class="flex items-start gap-3">
        <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-soft text-ink"><Settings2 :size="17" /></span>
        <div>
          <h2 class="text-[14px] font-semibold">GitHub 深度采集</h2>
          <p class="mt-1 text-[12.5px] leading-5 text-muted">页数上限分别应用于 Commit、Issue、PR 和 Release 接口。</p>
        </div>
      </div>

      <div class="mt-5 flex flex-col gap-4 border-t border-line pt-4 sm:flex-row sm:items-end sm:justify-between">
        <div class="max-w-xl">
          <label for="github-max-pages" class="block text-[13px] font-medium">每个接口最多采集页数</label>
          <p id="github-max-pages-help" class="mt-1 text-[12px] leading-5 text-muted">
            每页最多 100 条。当前上限对应每个接口最多约 {{ maxRecords.toLocaleString() }} 条；实际数量取决于仓库数据量。
          </p>
          <p class="mt-1 text-[12px] leading-5 text-muted">达到设定页数即按该标准完成；GitHub 请求失败或事件校验异常时仍会部分完成。提高上限会增加采集时间和 API 请求；保存后对新启动的任务生效。</p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <input
            id="github-max-pages"
            v-model.number="pageLimit"
            type="number"
            min="1"
            max="100"
            step="1"
            :disabled="loading || saving"
            aria-describedby="github-max-pages-help"
            class="h-9 w-24 rounded-md border border-line bg-panel px-3 text-[13px] outline-none focus:border-ink/30 disabled:opacity-50"
          >
          <span class="text-[12px] text-muted">页 / 接口</span>
        </div>
      </div>

      <div class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <p v-if="error" role="alert" class="text-[12px] text-danger">{{ error }}</p>
        <p v-else-if="saved" role="status" class="flex items-center gap-1 text-[12px] text-s4"><Check :size="14" /> 设置已保存</p>
        <p v-else class="text-[12px] text-muted">可设置 1–100 页，默认 10 页。</p>
        <GdButton :disabled="loading || saving || !dirty || !valid" @click="saveSettings">
          <LoaderCircle v-if="saving || loading" :size="14" class="animate-spin" />
          <Save v-else :size="14" />
          {{ loading ? '读取中' : saving ? '保存中' : '保存设置' }}
        </GdButton>
      </div>
      <p v-if="!valid && !loading" class="mt-2 text-[12px] text-danger">请输入 1 到 100 之间的整数。</p>
    </GdCard>
  </main>
</template>
