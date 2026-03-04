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

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
