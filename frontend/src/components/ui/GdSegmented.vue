<script setup lang="ts">
interface Option { value: string | number; label: string; disabled?: boolean; hint?: string }
withDefaults(defineProps<{ modelValue: string | number; options: Option[]; size?: 'sm' | 'md' }>(), { size: 'md' })
const emit = defineEmits<{ 'update:modelValue': [value: string | number] }>()
</script>

<template>
  <div class="flex shrink-0 gap-0.5 rounded-[7px] bg-track p-[3px]" role="group">
    <button
      v-for="option in options"
      :key="option.value"
      :disabled="option.disabled"
      :title="option.hint"
      :aria-label="option.label"
      :aria-pressed="modelValue === option.value"
      :data-value="option.value"
      class="rounded-[5px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45"
      :class="[
        size === 'sm' ? 'h-6 px-2 text-[11.5px]' : 'h-[26px] px-2.5 text-[12.5px]',
        modelValue === option.value ? 'bg-panel text-ink shadow-sm' : 'text-muted hover:text-ink',
      ]"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>
