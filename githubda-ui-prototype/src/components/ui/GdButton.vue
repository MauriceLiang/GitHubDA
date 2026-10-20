<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'primary' | 'outline' | 'ghost'; size?: 'sm' | 'md'; disabled?: boolean }>(), {
  variant: 'primary', size: 'md', disabled: false,
})
</script>

<template>
  <button
    :disabled="disabled"
    class="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-[7px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45"
    :class="[
      size === 'sm' ? 'h-7 px-2.5 text-[12px]' : 'h-[34px] px-3.5 text-[13px]',
      variant === 'primary' && 'bg-ink text-bg hover:opacity-90',
      variant === 'outline' && 'border border-line bg-panel hover:bg-soft',
      variant === 'ghost' && 'text-muted hover:bg-track hover:text-ink',
    ]"
  >
    <slot />
  </button>
</template>
