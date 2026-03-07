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
      <NavItem to="/settings" icon="&#x2699;" label="Settings" :collapsed="uiStore.sidebarCollapsed" />

      <!-- Job-scoped section -->
      <template v-if="analysisStore.activeJobId && onJobRoute">
        <div
          v-if="!uiStore.sidebarCollapsed"
          class="pt-4 pb-1 px-2 text-xs font-semibold uppercase tracking-widest"
          style="color: var(--color-text-muted)"
        >
          Current Job
        </div>
        <div v-else class="my-2 border-t" :style="{ borderColor: 'var(--color-border)' }" />

        <!-- Active job label — clicking navigates to the progress view -->
        <RouterLink
          v-if="!uiStore.sidebarCollapsed && analysisStore.activeJob"
          :to="`/jobs/${analysisStore.activeJobId}/progress`"
          class="mx-2 mb-2 px-2 py-1.5 rounded-md text-xs truncate block hover:bg-white/10 transition-colors"
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
        </RouterLink>

        <NavItem :to="`/jobs/${analysisStore.activeJobId}/progress`" icon="▶" label="Progress" :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/graph`"   icon="◎" label="Graph"   :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/smells`"  icon="⚠" label="Smells"  :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/plan`"    icon="✦" label="Plan"    :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/patches`"  icon="⊞" label="Patches"    :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/validate`" icon="✔" label="Validation" :collapsed="uiStore.sidebarCollapsed" />
        <NavItem :to="`/jobs/${analysisStore.activeJobId}/report`"   icon="≡" label="Report"     :collapsed="uiStore.sidebarCollapsed" />
      </template>
    </nav>

    <!-- Active model pill -->
    <div v-if="activeModelName" class="px-2 pb-2 flex-shrink-0">
      <button
        @click="router.push('/settings')"
        class="flex items-center gap-1.5 w-full px-2 py-1.5 rounded-md text-xs transition-colors truncate"
        :style="{
          background: 'rgba(99,102,241,0.1)',
          color: 'var(--color-text-muted)',
          border: '1px solid rgba(99,102,241,0.2)',
        }"
        :title="uiStore.sidebarCollapsed ? activeModelName : undefined"
      >
        <span class="flex-shrink-0 select-none">&#x2726;</span>
        <span v-if="!uiStore.sidebarCollapsed" class="truncate font-mono" style="color: var(--color-primary)">
          {{ activeModelName }}
        </span>
      </button>
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
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { RouterLink, useLink, useRoute, useRouter } from 'vue-router'
import { useAnalysisStore } from '@/stores/analysis'
import { useUIStore } from '@/stores/ui'
import { settingsApi } from '@/api/endpoints'

const uiStore = useUIStore()
const analysisStore = useAnalysisStore()
const route = useRoute()
const router = useRouter()

const onJobRoute = computed(() => route.path.startsWith('/jobs/'))

// Active model pill
const activeModelName = ref<string | null>(null)
onMounted(async () => {
  try {
    const { data } = await settingsApi.getLLM()
    activeModelName.value = data.model
  } catch {
    // silent — not critical
  }
})

function shortJobId(id: string): string {
  return id.slice(0, 8) + '…'
}

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
