<script setup lang="ts">
import type { Observation } from '@/services/types'
defineProps<{ observations: Observation[]; compact?: boolean }>()
</script>

<template>
  <div class="flex flex-col gap-3">
    <div v-for="(item, index) in observations" :key="item.id" class="flex items-start gap-2.5">
      <span class="w-0.5 self-stretch rounded-sm" :class="index % 2 === 0 ? 'bg-s1' : 'bg-s3'" />
      <div>
        <p class="m-0 text-[12.5px] leading-relaxed">{{ item.text }}</p>
        <span class="mt-1 inline-block text-[11px] text-muted">{{ item.evidence }}</span>
      </div>
    </div>
    <p v-if="!observations.length" class="text-[12px] text-muted">当前没有满足完整窗口与有效样本要求的主要数据观察。</p>
  </div>
</template>
