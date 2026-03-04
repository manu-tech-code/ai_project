/**
 * UI Pinia store.
 *
 * Manages global UI state: sidebar, notifications, modals, theme.
 * See docs/frontend-spec.md section 3.3 for the full store definition.
 */

import { useStorage } from '@vueuse/core'
import { defineStore } from 'pinia'
import { ref } from 'vue'

interface Notification {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  message?: string
  duration: number  // ms, 0 = persistent
  timestamp: number
}

export const useUIStore = defineStore('ui', () => {
  // --- State ---
  const sidebarOpen = ref(true)
  const sidebarCollapsed = ref(false)
  const activeModal = ref<string | null>(null)
  const modalProps = ref<Record<string, unknown>>({})
  const notifications = ref<Notification[]>([])

  // Persisted to localStorage via @vueuse/core
  const isDarkMode = useStorage('alm_dark_mode', false)

  // --- Actions ---
  function toggleSidebar(): void {
    sidebarOpen.value = !sidebarOpen.value
  }

  function openModal(name: string, props: Record<string, unknown> = {}): void {
    activeModal.value = name
    modalProps.value = props
  }

  function closeModal(): void {
    activeModal.value = null
    modalProps.value = {}
  }

  function notify(notification: Omit<Notification, 'id' | 'timestamp'>): void {
    const n: Notification = {
      ...notification,
      id: Math.random().toString(36).slice(2),
      timestamp: Date.now(),
    }
    notifications.value.push(n)

    if (n.duration > 0) {
      setTimeout(() => dismissNotification(n.id), n.duration)
    }
  }

  function dismissNotification(id: string): void {
    const idx = notifications.value.findIndex((n) => n.id === id)
    if (idx !== -1) notifications.value.splice(idx, 1)
  }

  function setDarkMode(value: boolean): void {
    isDarkMode.value = value
  }

  return {
    sidebarOpen,
    sidebarCollapsed,
    activeModal,
    modalProps,
    notifications,
    isDarkMode,
    toggleSidebar,
    openModal,
    closeModal,
    notify,
    dismissNotification,
    setDarkMode,
  }
})
