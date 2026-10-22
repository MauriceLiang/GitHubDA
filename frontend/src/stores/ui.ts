import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark'
export type DrawerKind = 'commits' | 'definitions' | 'release' | 'issue' | 'pr' | null

export interface Toast {
  id: number
  message: string
}

const stored = (typeof localStorage !== 'undefined' && (localStorage.getItem('repovantage-theme') ?? localStorage.getItem('githubda-theme'))) as ThemeMode | null

export const useUiStore = defineStore('ui', () => {
  const theme = ref<ThemeMode>(stored ?? (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'))
  const isDark = computed(() => theme.value === 'dark')
  const drawerKind = ref<DrawerKind>(null)
  const drawerPayload = ref<Record<string, string> | null>(null)
  const toasts = ref<Toast[]>([])
  let toastId = 0

  function applyTheme() {
    document.documentElement.classList.toggle('dark', isDark.value)
    localStorage.setItem('repovantage-theme', theme.value)
    localStorage.removeItem('githubda-theme')
  }
  watch(theme, applyTheme, { immediate: true })

  function toggleTheme() {
    theme.value = isDark.value ? 'light' : 'dark'
  }

  function openDrawer(kind: DrawerKind, payload: Record<string, string> = {}) {
    drawerKind.value = kind
    drawerPayload.value = payload
  }
  function closeDrawer() {
    drawerKind.value = null
    drawerPayload.value = null
  }

  function toast(message: string) {
    const id = ++toastId
    toasts.value.push({ id, message })
    window.setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, 2600)
  }

  return { theme, isDark, toggleTheme, drawerKind, drawerPayload, openDrawer, closeDrawer, toasts, toast }
})
