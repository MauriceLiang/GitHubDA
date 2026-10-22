<script setup lang="ts">
import { LoaderCircle } from 'lucide-vue-next'

withDefaults(defineProps<{ variant?: 'primary' | 'outline' | 'ghost' | 'danger'; size?: 'sm' | 'md'; disabled?: boolean; loading?: boolean }>(), {
  variant: 'primary', size: 'md', disabled: false, loading: false,
})
</script>

<template>
  <button
    :disabled="disabled || loading"
    :aria-busy="loading"
    class="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-[7px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45"
    :class="[
      size === 'sm' ? 'h-7 px-2.5 text-[12px]' : 'h-[34px] px-3.5 text-[13px]',
      variant === 'primary' && 'bg-ink text-bg hover:opacity-90',
      variant === 'outline' && 'border border-line bg-panel hover:bg-soft',
      variant === 'ghost' && 'text-muted hover:bg-track hover:text-ink',
      variant === 'danger' && 'border border-danger/30 bg-warnbg text-danger hover:opacity-80',
    ]"
  >
    <LoaderCircle v-if="loading" :size="14" class="shrink-0 animate-spin" aria-hidden="true" />
    <slot />
  </button>
</template>
