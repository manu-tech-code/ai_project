<template>
  <!-- Root component: renders the active route inside AppLayout -->
  <RouterView />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { generateAndSaveApiKey, getApiKey } from '@/api/client'

// Bootstrap an API key on first visit if none is stored
onMounted(async () => {
  if (!getApiKey()) {
    try {
      await generateAndSaveApiKey()
    } catch {
      // Silently fail — the header's "Generate Key" button serves as manual fallback
    }
  }
})
</script>
