<template>
  <div class="flex flex-col items-center justify-center min-h-[60vh] text-center px-6">
    <div
      class="text-8xl font-bold tabular-nums mb-4 select-none"
      style="color: var(--color-border)"
    >
      404
    </div>
    <h1 class="text-2xl font-semibold mb-2" style="color: var(--color-text)">
      Page not found
    </h1>
    <p class="text-sm mb-8 max-w-sm" style="color: var(--color-text-secondary)">
      The page you're looking for doesn't exist or has been moved.
    </p>
    <RouterLink
      to="/"
      class="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
      style="background: rgba(99,102,241,0.15); color: #a5b4fc; border: 1px solid rgba(99,102,241,0.3)"
    >
      ← Back to Dashboard
    </RouterLink>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>
