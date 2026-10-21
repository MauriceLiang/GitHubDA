<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'default' | 'warn' | 'plain' | 'danger' }>(), { variant: 'default' })
const styles: Record<string, string> = {
  default: 'bg-soft text-ink/70',
  warn: 'bg-warnbg text-warnfg',
  plain: 'bg-soft text-muted',
  danger: 'bg-warnbg text-danger',
}
</script>

<template>
  <span class="inline-flex items-center gap-1.5 rounded-[4px] px-1.5 py-0.5 text-[11px] font-medium" :class="styles[variant]">
    <slot />
  </span>
</template>
