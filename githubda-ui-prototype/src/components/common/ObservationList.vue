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
        <button class="mt-1 text-[11px] text-muted underline underline-offset-2 hover:text-ink">{{ item.evidence }}</button>
      </div>
    </div>
    <p v-if="!observations.length" class="text-[12px] text-muted">当前数据不足以生成可解释的变化观察。</p>
  </div>
</template>
