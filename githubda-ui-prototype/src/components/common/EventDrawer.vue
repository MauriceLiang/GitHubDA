<script setup lang="ts">
import { computed } from 'vue'
import GdButton from '@/components/ui/GdButton.vue'
import GdDrawer from '@/components/ui/GdDrawer.vue'
import { DEFINITIONS } from '@/services/definitions'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const payload = computed(() => ui.drawerPayload ?? {})
const definition = computed(() => DEFINITIONS[payload.value.metric ?? 'M01'] ?? DEFINITIONS.M01)
const title = computed(() => {
  switch (ui.drawerKind) {
    case 'commits': return 'Commit 周聚合'
    case 'definitions': return '数据与口径'
    case 'release': return payload.value.identifierType === 'release_id' ? `Release #${payload.value.tag ?? '—'}` : payload.value.tag ?? 'Release'
    case 'issue': return payload.value.title ?? 'Issue'
    case 'pr': return payload.value.title ?? 'Pull Request'
    default: return ''
  }
})
const subtitle = computed(() => ui.drawerKind === 'commits'
  ? `${payload.value.weekLabel ?? ''} · ${payload.value.count ?? '—'} 次提交`
  : ui.drawerKind === 'definitions' ? '指标来源与解释' : '')
</script>

<template>
  <GdDrawer :open="ui.drawerKind !== null" :title="title" :subtitle="subtitle" @update:open="(open) => !open && ui.closeDrawer()">
    <template v-if="ui.drawerKind === 'commits'">
      <div class="rounded-md bg-warnbg px-3 py-2.5 text-[12px] leading-relaxed text-warnfg">
        当前浏览器 API 只提供周聚合结果，没有逐条 Commit 明细，因此不能从此图表打开单条提交记录。
      </div>
    </template>

    <template v-else-if="ui.drawerKind === 'definitions'">
      <div class="text-[13px] font-semibold">{{ definition.title }}</div>
      <dl class="mt-1 divide-y divide-line text-[12.5px]">
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">计算口径</dt><dd class="m-0">{{ definition.definition }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">数据来源</dt><dd class="m-0">{{ definition.source }}</dd></div>
        <div class="grid grid-cols-[92px_1fr] gap-2.5 py-2.5"><dt class="text-muted">限制</dt><dd class="m-0">{{ definition.limitation }}</dd></div>
      </dl>
      <p class="mt-2 text-[11px] text-muted">实际时间范围、样本量和覆盖状态显示在当前图表旁。</p>
    </template>

    <template v-else-if="ui.drawerKind === 'release'">
      <dl class="divide-y divide-line text-[12.5px]">
        <div class="grid grid-cols-[110px_1fr] gap-2.5 py-2.5"><dt class="text-muted">发布时间</dt><dd class="m-0">{{ payload.date ?? '—' }}</dd></div>
        <div class="grid grid-cols-[110px_1fr] gap-2.5 py-2.5"><dt class="text-muted">类型</dt><dd class="m-0">{{ payload.type ?? '正式发布' }}</dd></div>
        <div class="grid grid-cols-[110px_1fr] gap-2.5 py-2.5"><dt class="text-muted">相邻间隔</dt><dd class="m-0">{{ payload.interval ?? '—' }}</dd></div>
      </dl>
    </template>

    <template #footer>
      <GdButton variant="outline" class="flex-1" @click="ui.closeDrawer()">关闭</GdButton>
    </template>
  </GdDrawer>
</template>
