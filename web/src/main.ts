import { createApp } from 'vue'
import { createPinia } from 'pinia'
import AppShell from '@/components/AppShell.vue'
import { router } from '@/router'
import '@/styles.css'

createApp(AppShell).use(createPinia()).use(router).mount('#app')
