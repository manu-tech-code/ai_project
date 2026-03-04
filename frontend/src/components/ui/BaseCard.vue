<template>
  <div
    :class="['rounded-xl border overflow-hidden', className]"
    :style="{
      background: 'var(--color-card)',
      borderColor: 'var(--color-border)',
    }"
  >
    <!-- Optional header slot -->
    <div
      v-if="$slots.header || title"
      class="flex items-center justify-between px-5 py-3.5 border-b"
      :style="{ borderColor: 'var(--color-border)' }"
    >
      <div class="flex items-center gap-2">
        <h3
          v-if="title"
          class="text-sm font-semibold"
          :style="{ color: 'var(--color-text)' }"
        >
          {{ title }}
        </h3>
        <slot name="header" />
      </div>
      <slot name="header-actions" />
    </div>

    <!-- Body -->
    <div :class="noPadding ? '' : 'px-5 py-4'">
      <slot />
    </div>

    <!-- Optional footer slot -->
    <div
      v-if="$slots.footer"
      class="px-5 py-3 border-t"
      :style="{
        borderColor: 'var(--color-border)',
        background: 'var(--color-elevated)',
      }"
    >
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    className?: string
    noPadding?: boolean
  }>(),
  { noPadding: false },
)
</script>
