<template>
  <Teleport to="#modal-root">
    <Transition name="modal">
      <div
        v-if="open"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        @keydown.escape.stop="$emit('close')"
      >
        <!-- Backdrop -->
        <div
          class="absolute inset-0 backdrop-blur-sm"
          style="background: rgba(0,0,0,0.7)"
          @click="$emit('close')"
        />

        <!-- Dialog panel -->
        <div
          ref="panelRef"
          class="modal-panel relative z-10 w-full rounded-xl border flex flex-col max-h-[90vh]"
          :class="sizeClass"
          :style="{
            background: 'var(--color-card)',
            borderColor: 'var(--color-border)',
            boxShadow: '0 25px 50px rgba(0,0,0,0.6)',
          }"
          tabindex="-1"
          @click.stop
        >
          <!-- Header -->
          <div
            class="flex items-center justify-between px-5 py-4 border-b flex-shrink-0"
            :style="{ borderColor: 'var(--color-border)' }"
          >
            <h2
              :id="titleId"
              class="text-base font-semibold"
              :style="{ color: 'var(--color-text)' }"
            >
              {{ title }}
            </h2>
            <button
              @click="$emit('close')"
              class="flex items-center justify-center w-7 h-7 rounded-md transition-colors"
              :style="{ color: 'var(--color-text-muted)' }"
              aria-label="Close dialog"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Content -->
          <div class="overflow-y-auto flex-1 px-5 py-4">
            <slot />
          </div>

          <!-- Footer -->
          <div
            v-if="$slots.footer"
            class="px-5 py-4 border-t flex items-center justify-end gap-3 flex-shrink-0"
            :style="{
              borderColor: 'var(--color-border)',
              background: 'var(--color-elevated)',
            }"
          >
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type Size = 'sm' | 'md' | 'lg' | 'xl' | 'fullscreen'

const props = withDefaults(
  defineProps<{ open: boolean; title: string; size?: Size }>(),
  { size: 'md' },
)

defineEmits<{ close: [] }>()

const panelRef = ref<HTMLElement | null>(null)
const titleId = computed(() => `modal-title-${Math.random().toString(36).slice(2, 9)}`)

const sizeClass = computed(() => {
  const map: Record<Size, string> = {
    sm: 'max-w-sm',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    fullscreen: 'max-w-full m-0',
  }
  return map[props.size]
})

// Focus the panel when opened
watch(
  () => props.open,
  (val) => {
    if (val) {
      setTimeout(() => panelRef.value?.focus(), 50)
    }
  },
)
</script>
