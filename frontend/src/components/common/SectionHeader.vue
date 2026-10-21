<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <div class="flex items-start justify-between gap-4">
    <div>
      <h3 class="m-0 text-[15.5px] font-semibold">{{ title }}</h3>
      <p v-if="subtitle" class="mt-0.5 text-[12px] text-muted">{{ subtitle }}</p>
    </div>
    <slot name="right" />
  </div>
</template>
