/**
 * Unit tests for the UI Pinia store.
 *
 * Tests sidebar, modal, notification, and dark mode state management.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUIStore } from '@/stores/ui'

describe('useUIStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  // --- Initial state ---

  it('initializes with sidebarOpen true', () => {
    const store = useUIStore()
    expect(store.sidebarOpen).toBe(true)
  })

  it('initializes with sidebarCollapsed false', () => {
    const store = useUIStore()
    expect(store.sidebarCollapsed).toBe(false)
  })

  it('initializes with null activeModal', () => {
    const store = useUIStore()
    expect(store.activeModal).toBeNull()
  })

  it('initializes with empty modalProps', () => {
    const store = useUIStore()
    expect(store.modalProps).toEqual({})
  })

  it('initializes with empty notifications array', () => {
    const store = useUIStore()
    expect(store.notifications).toEqual([])
  })

  // --- toggleSidebar ---

  it('toggleSidebar closes an open sidebar', () => {
    const store = useUIStore()
    expect(store.sidebarOpen).toBe(true)
    store.toggleSidebar()
    expect(store.sidebarOpen).toBe(false)
  })

  it('toggleSidebar opens a closed sidebar', () => {
    const store = useUIStore()
    store.toggleSidebar() // close
    store.toggleSidebar() // open
    expect(store.sidebarOpen).toBe(true)
  })

  it('toggleSidebar alternates state repeatedly', () => {
    const store = useUIStore()
    const initial = store.sidebarOpen
    store.toggleSidebar()
    expect(store.sidebarOpen).toBe(!initial)
    store.toggleSidebar()
    expect(store.sidebarOpen).toBe(initial)
  })

  // --- openModal / closeModal ---

  it('openModal sets activeModal', () => {
    const store = useUIStore()
    store.openModal('upload-dialog')
    expect(store.activeModal).toBe('upload-dialog')
  })

  it('openModal sets modalProps', () => {
    const store = useUIStore()
    store.openModal('confirm', { message: 'Are you sure?' })
    expect(store.modalProps).toEqual({ message: 'Are you sure?' })
  })

  it('closeModal clears activeModal', () => {
    const store = useUIStore()
    store.openModal('some-modal')
    store.closeModal()
    expect(store.activeModal).toBeNull()
  })

  it('closeModal clears modalProps', () => {
    const store = useUIStore()
    store.openModal('modal', { key: 'value' })
    store.closeModal()
    expect(store.modalProps).toEqual({})
  })

  it('openModal with no props defaults to empty object', () => {
    const store = useUIStore()
    store.openModal('simple')
    expect(store.modalProps).toEqual({})
  })

  // --- notify ---

  it('notify adds a notification to the list', () => {
    const store = useUIStore()
    store.notify({ type: 'success', title: 'Done!', duration: 0 })
    expect(store.notifications).toHaveLength(1)
  })

  it('notify sets the correct type', () => {
    const store = useUIStore()
    store.notify({ type: 'error', title: 'Error occurred', duration: 0 })
    expect(store.notifications[0].type).toBe('error')
  })

  it('notify sets the correct title', () => {
    const store = useUIStore()
    store.notify({ type: 'info', title: 'Information', duration: 0 })
    expect(store.notifications[0].title).toBe('Information')
  })

  it('notify sets an id on the notification', () => {
    const store = useUIStore()
    store.notify({ type: 'warning', title: 'Warning', duration: 0 })
    expect(store.notifications[0].id).toBeTruthy()
    expect(typeof store.notifications[0].id).toBe('string')
  })

  it('notify sets a timestamp', () => {
    const store = useUIStore()
    store.notify({ type: 'success', title: 'OK', duration: 0 })
    expect(store.notifications[0].timestamp).toBeGreaterThan(0)
  })

  it('notify with duration > 0 auto-dismisses', () => {
    const store = useUIStore()
    store.notify({ type: 'info', title: 'Auto-dismiss', duration: 1000 })
    expect(store.notifications).toHaveLength(1)

    vi.advanceTimersByTime(1001)
    expect(store.notifications).toHaveLength(0)
  })

  it('notify with duration 0 does not auto-dismiss', () => {
    const store = useUIStore()
    store.notify({ type: 'error', title: 'Persistent', duration: 0 })

    vi.advanceTimersByTime(60000)
    expect(store.notifications).toHaveLength(1)
  })

  it('multiple notifications can coexist', () => {
    const store = useUIStore()
    store.notify({ type: 'success', title: 'First', duration: 0 })
    store.notify({ type: 'error', title: 'Second', duration: 0 })
    expect(store.notifications).toHaveLength(2)
  })

  it('notify ids are unique per notification', () => {
    const store = useUIStore()
    store.notify({ type: 'info', title: 'N1', duration: 0 })
    store.notify({ type: 'info', title: 'N2', duration: 0 })

    const ids = store.notifications.map((n) => n.id)
    expect(new Set(ids).size).toBe(2)
  })

  // --- dismissNotification ---

  it('dismissNotification removes the notification by id', () => {
    const store = useUIStore()
    store.notify({ type: 'info', title: 'To dismiss', duration: 0 })
    const id = store.notifications[0].id

    store.dismissNotification(id)
    expect(store.notifications).toHaveLength(0)
  })

  it('dismissNotification removes only the target notification', () => {
    const store = useUIStore()
    store.notify({ type: 'success', title: 'Keep', duration: 0 })
    store.notify({ type: 'error', title: 'Remove', duration: 0 })

    const idToRemove = store.notifications[1].id
    store.dismissNotification(idToRemove)

    expect(store.notifications).toHaveLength(1)
    expect(store.notifications[0].title).toBe('Keep')
  })

  it('dismissNotification with invalid id does nothing', () => {
    const store = useUIStore()
    store.notify({ type: 'info', title: 'Stays', duration: 0 })
    store.dismissNotification('non-existent-id')
    expect(store.notifications).toHaveLength(1)
  })

  // --- setDarkMode ---

  it('setDarkMode changes the isDarkMode value', () => {
    const store = useUIStore()
    store.setDarkMode(true)
    expect(store.isDarkMode).toBe(true)
  })

  it('setDarkMode can be toggled off', () => {
    const store = useUIStore()
    store.setDarkMode(true)
    store.setDarkMode(false)
    expect(store.isDarkMode).toBe(false)
  })
})
