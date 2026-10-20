<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle, VisuallyHidden } from 'reka-ui'
import GdIconButton from './GdIconButton.vue'

/**
 * Accessible right-side drawer built on Reka UI primitives
 * (focus trap, Esc, scroll lock) — same conventions as shadcn-vue's Sheet.
 */
defineProps<{ open: boolean; title?: string; subtitle?: string }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
</script>

<template>
  <DialogRoot :open="open" @update:open="(value) => emit('update:open', value)">
    <DialogPortal>
      <DialogOverlay class="gd-overlay fixed inset-0 z-40 bg-black/32" />
      <DialogContent class="gd-drawer fixed inset-y-0 right-0 z-50 flex w-[460px] max-w-[92vw] flex-col border-l border-line bg-panel shadow-[-12px_0_32px_rgb(0_0_0/0.10)]">
        <header class="flex items-start justify-between gap-3 border-b border-line px-5 py-[18px]">
          <div>
            <DialogTitle class="m-0 text-[17px] font-semibold leading-snug">{{ title }}</DialogTitle>
            <DialogDescription v-if="subtitle" class="mt-1 text-[12px] text-muted">{{ subtitle }}</DialogDescription>
            <VisuallyHidden v-else>详情面板</VisuallyHidden>
          </div>
          <DialogClose as-child>
            <GdIconButton label="关闭"><X :size="18" /></GdIconButton>
          </DialogClose>
        </header>
        <div class="flex-1 overflow-auto px-5 py-4">
          <slot />
        </div>
        <footer v-if="$slots.footer" class="flex gap-2 border-t border-line px-5 py-3.5">
          <slot name="footer" />
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.gd-overlay[data-state='open'] { animation: gd-fade-in 0.18s ease; }
.gd-overlay[data-state='closed'] { animation: gd-fade-out 0.16s ease; }
.gd-drawer[data-state='open'] { animation: gd-slide-in 0.2s cubic-bezier(0.2, 0.7, 0.3, 1); }
.gd-drawer[data-state='closed'] { animation: gd-slide-out 0.16s ease; }
@keyframes gd-fade-in { from { opacity: 0 } to { opacity: 1 } }
@keyframes gd-fade-out { from { opacity: 1 } to { opacity: 0 } }
@keyframes gd-slide-in { from { transform: translateX(102%) } to { transform: none } }
@keyframes gd-slide-out { from { transform: none } to { transform: translateX(102%) } }
</style>
