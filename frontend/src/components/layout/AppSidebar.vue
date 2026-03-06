<template>
  <aside
    class="flex flex-col flex-shrink-0 transition-all duration-200 border-r overflow-hidden"
    :style="{
      width: uiStore.sidebarCollapsed ? '60px' : '224px',
      background: 'var(--color-card)',
      borderColor: 'var(--color-border)',
    }"
  >
    <!-- Brand -->
    <div
      class="flex items-center gap-3 px-4 h-14 border-b flex-shrink-0"
      :style="{ borderColor: 'var(--color-border)' }"
    >
      <!-- Logo mark -->
      <div
        class="flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0 font-bold text-sm text-white"
        style="background: var(--color-primary)"
      >
        A
      </div>
      <Transition name="fade-slide">
        <span
          v-if="!uiStore.sidebarCollapsed"
          class="font-semibold tracking-tight whitespace-nowrap overflow-hidden text-sm"
          style="color: var(--color-text)"
        >
          ALM Platform
        </span>
      </Transition>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
      <!-- Primary nav -->
      <NavItem to="/" icon="⌂" label="Dashboard" :collapsed="uiStore.sidebarCollapsed" />
      <NavItem to="/analyze" icon="+" label="New Analysis" :collapsed="uiStore.sidebarCollapsed" />
      <NavItem to="/settings" icon="&#x2699;" label="Settings" :collapsed="uiStore.sidebarCollapsed" />

      <!-- Job-scoped section -->
      <template v-if="analysisStore.activeJobId">
        <div
          v-if="!uiStore.sidebarCollapsed"
          class="pt-4 pb-1 px-2 text-xs font-semibold uppercase tracking-widest"
          style="color: var(--color-text-muted)"
        >
          Current Job
        </div>
        <div v-else class="my-2 border-t" :style="{ borderColor: 'var(--color-border)' }" />

        <!-- Active job label -->
        <div
          v-if="!uiStore.sidebarCollapsed && analysisStore.activeJob"
          class="mx-2 mb-2 px-2 py-1.5 rounded-md text-xs truncate"
          :style="{ background: 'var(--color-elevated)', color: 'var(--color-text-secondary)' }"
        >
          <span class="font-mono">{{ shortJobId(analysisStore.activeJob.job_id) }}</span>
          <span
            v-if="analysisStore.activeJob.label"
            class="ml-1 truncate block font-medium"
            style="color: var(--color-text)"
          >
            {{ analysisStore.activeJob.label }}
          </span>
          <!-- Pulse for running jobs -->
          <span v-if="analysisStore.isJobRunning" class="flex items-center gap-1 mt-1">
            <span
              class="inline-block w-1.5 h-1.5 rounded-full animate-pulse-dot"
              style="background: var(--color-warning)"
            />
            <span style="color: var(--color-warning)">{{ analysisStore.activeJob.status }}</span>
          </span>
        </div>

        <NavItem :to="`/jobs/${analysisStore.activeJobId}/graph`"   icon="◎" label="Graph"   :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/smells`"  icon="⚠" label="Smells"  :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/plan`"    icon="✦" label="Plan"    :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/patches`"  icon="⊞" label="Patches"    :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/validate`" icon="✔" label="Validation" :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/report`"   icon="≡" label="Report"     :collapsed="uiStore.sidebarCollapsed" />
      </template>
    </nav>

    <!-- AI Model section -->
    <div
      class="px-2 pb-2 flex-shrink-0 border-t"
      :style="{ borderColor: 'var(--color-border)' }"
    >
      <!-- Collapsed: just an icon -->
      <div v-if="uiStore.sidebarCollapsed" class="pt-2 flex justify-center">
        <button
          @click="uiStore.sidebarCollapsed = false"
          class="w-8 h-8 rounded-md flex items-center justify-center text-base transition-colors"
          :style="{ color: llm.available_models.length ? '#a5b4fc' : 'var(--color-text-muted)' }"
          title="AI Model"
        >⬡</button>
      </div>

      <!-- Expanded -->
      <template v-else>
        <div class="pt-3 pb-1 px-2 flex items-center justify-between">
          <span class="text-xs font-semibold uppercase tracking-widest" style="color: var(--color-text-muted)">AI Model</span>
          <span
            class="inline-block w-1.5 h-1.5 rounded-full"
            :style="{ background: llm.available_models.length ? '#22c55e' : '#ef4444' }"
            :title="llm.available_models.length ? 'Connected' : 'No models found'"
          />
        </div>

        <!-- Provider badge -->
        <div class="px-2 mb-1.5 flex items-center gap-1.5">
          <span
            class="text-xs px-1.5 py-0.5 rounded font-mono font-semibold"
            style="background: rgba(99,102,241,0.15); color: #a5b4fc"
          >{{ llm.provider }}</span>
          <span v-if="llm.loading" class="text-xs" style="color: var(--color-text-muted)">loading…</span>
        </div>

        <!-- Model selector -->
        <div class="px-2">
          <select
            :value="llm.model"
            @change="switchModel(($event.target as HTMLSelectElement).value)"
            class="w-full text-xs rounded-md px-2 py-1.5 border truncate"
            :style="{
              background: 'var(--color-elevated)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }"
            :disabled="llm.loading || !llm.available_models.length"
          >
            <!-- Current model always present even if not in list -->
            <option v-if="!llm.available_models.includes(llm.model)" :value="llm.model">
              {{ llm.model }}
            </option>
            <option v-for="m in llm.available_models" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
      </template>
    </div>

    <!-- Collapse toggle -->
    <div class="px-2 pb-3 flex-shrink-0">
      <button
        @click="uiStore.sidebarCollapsed = !uiStore.sidebarCollapsed"
        class="flex items-center justify-center w-full h-8 rounded-md text-xs transition-colors"
        :style="{ color: 'var(--color-text-muted)', background: 'transparent' }"
        :title="uiStore.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      >
        <span class="select-none text-base">{{ uiStore.sidebarCollapsed ? '→' : '←' }}</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive } from 'vue'
import { RouterLink, useLink } from 'vue-router'
import { settingsApi } from '@/api/endpoints'
import { useAnalysisStore } from '@/stores/analysis'
import { useUIStore } from '@/stores/ui'

const uiStore = useUIStore()
const analysisStore = useAnalysisStore()

function shortJobId(id: string): string {
  return id.slice(0, 8) + '…'
}

// ── LLM model state ────────────────────────────────────────────────────────

/**
 * Module-level cache so the LLM settings survive route navigation without
 * re-fetching. The sidebar is always mounted so onMounted fires on every
 * page load — the TTL guard prevents a network request on each navigation.
 */
const LLM_SETTINGS_TTL_MS = 30_000
let _llmLastFetchedAt = 0

const llm = reactive({
  provider: 'ollama',
  model: '',
  available_models: [] as string[],
  loading: false,
})

async function loadLLMSettings(force = false): Promise<void> {
  const now = Date.now()
  if (!force && llm.model !== '' && now - _llmLastFetchedAt < LLM_SETTINGS_TTL_MS) {
    // Still within TTL and we have data — skip the network round-trip.
    return
  }
  llm.loading = true
  try {
    const { data } = await settingsApi.getLLM()
    llm.provider = data.provider
    llm.model = data.model
    llm.available_models = data.available_models
    _llmLastFetchedAt = Date.now()
  } catch {
    // silently fail — sidebar is not critical
  } finally {
    llm.loading = false
  }
}

async function switchModel(model: string): Promise<void> {
  llm.loading = true
  try {
    const { data } = await settingsApi.patchLLM({ model })
    llm.model = data.model
    llm.available_models = data.available_models
    // A successful model switch counts as a fresh fetch — reset TTL.
    _llmLastFetchedAt = Date.now()
  } catch {
    // revert on error
  } finally {
    llm.loading = false
  }
}

onMounted(() => loadLLMSettings())

// ── NavItem ────────────────────────────────────────────────────────────────
// Uses computed(() => props.to) for reactive route tracking.
// Uses isExactActive so the root "/" is only highlighted on the home page.

const NavItem = defineComponent({
  name: 'NavItem',
  props: {
    to: { type: String, required: true },
    icon: { type: String, required: true },
    label: { type: String, required: true },
    collapsed: { type: Boolean, default: false },
  },
  setup(props) {
    const { isExactActive } = useLink({ to: computed(() => props.to) })
    return () => {
      const active = isExactActive.value
      const activeStyle = active
        ? 'background: rgba(99,102,241,0.15); color: #a5b4fc;'
        : 'color: var(--color-text-secondary);'

      return h(RouterLink, {
        to: props.to,
        class: 'flex items-center gap-2.5 px-2 py-2 rounded-md text-sm transition-colors w-full',
        style: activeStyle,
        title: props.collapsed ? props.label : undefined,
      }, () => [
        h('span', {
          class: 'flex-shrink-0 w-5 text-center text-base leading-none select-none',
          style: active ? 'color: var(--color-primary)' : '',
        }, props.icon),
        !props.collapsed
          ? h('span', { class: 'truncate font-medium' }, props.label)
          : null,
      ])
    }
  },
})
</script>

<style scoped>
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(-6px);
}
</style>
