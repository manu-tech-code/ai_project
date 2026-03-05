/**
 * ALM Frontend — Application entry point.
 *
 * Initializes Vue, Pinia, Vue Router, and mounts the root App component.
 */

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'

// Global CSS (Tailwind entry point)
import './style.css'

// Seed API key from build-time env if not already stored
const _envKey = import.meta.env.VITE_API_KEY as string | undefined
if (_envKey && !localStorage.getItem('alm_api_key')) {
  localStorage.setItem('alm_api_key', _envKey)
}

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
