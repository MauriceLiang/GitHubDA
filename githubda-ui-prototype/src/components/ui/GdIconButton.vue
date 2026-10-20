<script setup lang="ts">
withDefaults(defineProps<{ label: string; disabled?: boolean }>(), { disabled: false })
</script>

<template>
  <button
    :aria-label="label"
    :title="label"
    :disabled="disabled"
    class="grid size-[30px] shrink-0 place-items-center rounded-md text-muted transition-colors hover:bg-track hover:text-ink"
  >
    <slot />
  </button>
</template>
