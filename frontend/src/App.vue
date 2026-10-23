<script setup lang="ts">
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppTopbar from '@/components/layout/AppTopbar.vue'
import EventDrawer from '@/components/common/EventDrawer.vue'
import GdToastHost from '@/components/ui/GdToastHost.vue'
const dataMode = import.meta.env.VITE_DATA_MODE === 'mock' ? 'mock' : 'http'
</script>

<template>
  <div class="flex min-h-screen" data-testid="app" :data-mode="dataMode">
    <AppSidebar />
    <div class="flex min-w-0 flex-1 flex-col">
      <AppTopbar />
      <div class="mx-auto w-full max-w-[1360px]">
        <RouterView />
      </div>
    </div>
  </div>
  <EventDrawer />
  <GdToastHost />
</template>
