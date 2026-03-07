<template>
  <div class="flex h-screen overflow-hidden" style="background: var(--color-bg); color: var(--color-text)">
    <!-- Sidebar -->
    <AppSidebar />

    <!-- Main content area -->
    <div class="flex flex-col flex-1 min-w-0 overflow-hidden">
      <AppHeader />
      <main class="flex-1 overflow-auto" style="background: var(--color-bg)">
        <RouterView v-slot="{ Component, route }">
          <KeepAlive :max="10">
            <component :is="Component" :key="route.fullPath" v-if="route.meta.keepAlive" />
          </KeepAlive>
          <component :is="Component" :key="route.fullPath" v-if="!route.meta.keepAlive" />
        </RouterView>
      </main>
    </div>

    <!-- Toast Notification Stack -->
    <div class="fixed top-4 right-4 z-50 flex flex-col gap-2 w-80 pointer-events-none">
      <TransitionGroup name="toast">
        <div
          v-for="notification in uiStore.notifications"
          :key="notification.id"
          class="pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 shadow-xl"
          :style="notificationStyle(notification.type)"
        >
          <!-- Icon -->
          <span class="mt-0.5 flex-shrink-0 text-base">
            {{ notificationIcon(notification.type) }}
          </span>
          <!-- Content -->
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold leading-tight" style="color: var(--color-text)">
              {{ notification.title }}
            </p>
            <p v-if="notification.message" class="mt-0.5 text-xs" style="color: var(--color-text-secondary)">
              {{ notification.message }}
            </p>
          </div>
          <!-- Dismiss -->
          <button
            class="flex-shrink-0 ml-1 opacity-60 hover:opacity-100 transition-opacity text-base leading-none"
            style="color: var(--color-text)"
            @click="uiStore.dismissNotification(notification.id)"
          >
            &times;
          </button>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<script setup lang="ts">
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import { useUIStore } from '@/stores/ui'

const uiStore = useUIStore()

type NotifType = 'success' | 'error' | 'warning' | 'info'

function notificationStyle(type: NotifType): string {
  const map: Record<NotifType, string> = {
    success: `background:var(--color-card); border-color:#16a34a`,
    error:   `background:var(--color-card); border-color:#dc2626`,
    warning: `background:var(--color-card); border-color:#d97706`,
    info:    `background:var(--color-card); border-color:#2563eb`,
  }
  return map[type]
}

function notificationIcon(type: NotifType): string {
  const map: Record<NotifType, string> = {
    success: '✓',
    error:   '✕',
    warning: '⚠',
    info:    'ℹ',
  }
  return map[type]
}
</script>
