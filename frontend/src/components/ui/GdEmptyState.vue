<script setup lang="ts">
withDefaults(defineProps<{ title: string; description?: string; compact?: boolean }>(), { description: '', compact: false })
</script>

<template>
  <div
    class="flex flex-col items-center gap-2 rounded-lg border border-dashed border-line bg-panel/50 text-center"
    :class="compact ? 'px-4 py-5' : 'px-5 py-8'"
  >
    <slot name="icon" />
    <p class="text-[13px] font-medium">{{ title }}</p>
    <p v-if="description" class="max-w-[380px] text-[11.5px] leading-relaxed text-muted">{{ description }}</p>
    <slot name="action" />
  </div>
</template>
