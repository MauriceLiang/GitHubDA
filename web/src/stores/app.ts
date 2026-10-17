import { defineStore } from 'pinia'

type Theme = 'light' | 'dark'
const PREFS_KEY = 'githubda.v5.preferences'

function initialPreferences() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(PREFS_KEY) ?? '{}') as { theme?: Theme; selected?: number[] }
    return { theme: stored.theme === 'dark' ? 'dark' as Theme : 'light' as Theme, selected: Array.isArray(stored.selected) ? stored.selected.slice(0, 5) : [] }
  } catch { return { theme: 'light' as Theme, selected: [] as number[] } }
}

export const useAppStore = defineStore('app', {
  state: () => ({ ...initialPreferences(), mobileNavOpen: false, searchOpen: false, toast: '' }),
  actions: {
    persist() { window.localStorage.setItem(PREFS_KEY, JSON.stringify({ theme: this.theme, selected: this.selected })) },
    setTheme(theme: Theme) { this.theme = theme; document.documentElement.dataset.theme = theme; this.persist() },
    toggleTheme() { this.setTheme(this.theme === 'light' ? 'dark' : 'light') },
    toggleSelected(id: number) {
      if (this.selected.includes(id)) this.selected = this.selected.filter((selectedId) => selectedId !== id)
      else if (this.selected.length < 5) this.selected = [...this.selected, id]
      else this.flash('最多选择 5 个仓库')
      this.persist()
    },
    clearSelected() { this.selected = []; this.persist() },
    flash(message: string) { this.toast = message; window.setTimeout(() => { if (this.toast === message) this.toast = '' }, 3400) },
  },
})
