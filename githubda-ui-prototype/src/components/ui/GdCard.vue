<script setup lang="ts">
withDefaults(defineProps<{ padding?: 'none' | 'sm' | 'md'; gap?: boolean }>(), { padding: 'md', gap: true })
</script>

<template>
  <section
    class="gd-card"
    :class="[padding === 'md' && 'p-[18px]', padding === 'sm' && 'p-3.5', padding === 'none' && 'p-0', gap ? 'gap-3.5' : 'gap-0']"
  >
    <slot />
  </section>
</template>
