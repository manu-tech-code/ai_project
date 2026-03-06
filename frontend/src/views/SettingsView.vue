<template>
  <div class="p-6 max-w-3xl mx-auto space-y-6">
    <div>
      <h1 class="text-2xl font-bold" style="color: var(--color-text)">Settings</h1>
      <p class="mt-0.5 text-sm" style="color: var(--color-text-secondary)">
        Configure VCS providers and integrations.
      </p>
    </div>

    <!-- Tab bar -->
    <div class="flex gap-1 p-1 rounded-lg w-fit" style="background: var(--color-elevated)">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        @click="activeTab = tab.key"
        class="px-4 py-1.5 text-sm rounded-md font-medium transition-all"
        :style="activeTab === tab.key
          ? 'background: var(--color-card); color: var(--color-text); box-shadow: 0 1px 3px rgba(0,0,0,0.3)'
          : 'color: var(--color-text-muted)'"
      >{{ tab.label }}</button>
    </div>

    <!-- VCS Providers tab -->
    <template v-if="activeTab === 'vcs'">
      <!-- Add button -->
      <div class="flex items-center justify-between">
        <p class="text-sm" style="color: var(--color-text-secondary)">
          Connect version control providers to enable repo analysis and automated patch delivery.
        </p>
        <BaseButton variant="primary" size="sm" @click="openAddModal">
          + Add Provider
        </BaseButton>
      </div>

      <!-- Loading -->
      <div v-if="isLoading" class="space-y-3">
        <div v-for="i in 2" :key="i" class="h-16 rounded-xl animate-pulse" style="background: var(--color-card)" />
      </div>

      <!-- Empty -->
      <div
        v-else-if="providers.length === 0"
        class="flex flex-col items-center justify-center py-14 rounded-xl border border-dashed"
        :style="{ borderColor: 'var(--color-border)', background: 'var(--color-card)' }"
      >
        <span class="text-3xl mb-3">&#x2B21;</span>
        <p class="text-sm font-medium" style="color: var(--color-text)">No VCS providers configured</p>
        <p class="text-xs mt-1" style="color: var(--color-text-muted)">Add a GitHub, GitLab, or Bitbucket token to get started.</p>
      </div>

      <!-- Provider cards -->
      <div v-else class="space-y-3">
        <div
          v-for="p in providers"
          :key="p.id"
          class="flex items-center gap-4 p-4 rounded-xl border"
          :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }"
        >
          <!-- Provider icon -->
          <div
            class="flex items-center justify-center w-10 h-10 rounded-lg flex-shrink-0 text-lg"
            :style="{ background: providerBg(p.provider) }"
          >{{ providerIcon(p.provider) }}</div>

          <!-- Info -->
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold truncate" style="color: var(--color-text)">{{ p.name }}</p>
            <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">
              {{ p.provider }}
              <template v-if="p.base_url"> · {{ p.base_url }}</template>
              <template v-if="p.username"> · {{ p.username }}</template>
              · token: <span class="font-mono">{{ p.token_hint }}</span>
            </p>
          </div>

          <!-- Actions -->
          <div class="flex gap-2 flex-shrink-0">
            <BaseButton variant="ghost" size="xs" @click="openTestModal(p)">Test</BaseButton>
            <BaseButton variant="ghost" size="xs" @click="openEditModal(p)">Edit</BaseButton>
            <BaseButton variant="danger" size="xs" @click="deleteProvider(p.id)">Delete</BaseButton>
          </div>
        </div>
      </div>
    </template>

    <!-- LLM tab -->
    <template v-else-if="activeTab === 'llm'">
      <div class="p-5 rounded-xl border" :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }">
        <p class="text-sm" style="color: var(--color-text)">LLM model selection is available in the sidebar panel at the bottom left.</p>
        <p class="text-xs mt-2" style="color: var(--color-text-muted)">Change the active model or provider without restarting the backend.</p>
      </div>
    </template>

    <!-- Add/Edit Modal -->
    <BaseModal
      :open="formModal.open"
      :title="formModal.editId ? 'Edit Provider' : 'Add VCS Provider'"
      size="sm"
      @close="closeFormModal"
    >
      <div class="space-y-4">
        <!-- Name -->
        <div>
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">Label</label>
          <input
            v-model="form.name"
            type="text"
            placeholder="e.g. My GitHub Account"
            class="w-full px-3 py-2 text-sm rounded-md border"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
        </div>

        <!-- Provider (add only) -->
        <div v-if="!formModal.editId">
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">Provider</label>
          <select
            v-model="form.provider"
            class="w-full px-3 py-2 text-sm rounded-md border"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          >
            <option value="github">GitHub</option>
            <option value="gitlab">GitLab</option>
            <option value="bitbucket">Bitbucket</option>
            <option value="other">Other (generic git)</option>
          </select>
        </div>

        <!-- Base URL (self-hosted — GitLab and Other only) -->
        <div v-if="form.provider !== 'github' && form.provider !== 'bitbucket'">
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
            Base URL <span style="color: var(--color-text-muted)">(for self-hosted)</span>
          </label>
          <input
            v-model="form.base_url"
            type="url"
            placeholder="https://gitlab.mycompany.com"
            class="w-full px-3 py-2 text-sm rounded-md border"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
        </div>

        <!-- Token -->
        <div>
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
            Personal Access Token
            <span v-if="formModal.editId" style="color: var(--color-text-muted)">(leave blank to keep existing)</span>
          </label>
          <input
            v-model="form.token"
            type="password"
            placeholder="ghp_..."
            class="w-full px-3 py-2 text-sm rounded-md border font-mono"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
        </div>

        <!-- Username -->
        <div>
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
            Username <span style="color: var(--color-text-muted)">(optional)</span>
          </label>
          <input
            v-model="form.username"
            type="text"
            placeholder="Optional"
            class="w-full px-3 py-2 text-sm rounded-md border"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
        </div>

      </div>

      <template #footer>
        <BaseButton variant="secondary" size="sm" @click="closeFormModal">Cancel</BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          :loading="isSaving"
          :disabled="!form.name || (!formModal.editId && !form.token)"
          @click="saveProvider"
        >
          {{ formModal.editId ? 'Save Changes' : 'Add Provider' }}
        </BaseButton>
      </template>
    </BaseModal>

    <!-- Test modal -->
    <BaseModal :open="testModal.open" title="Test Connection" size="sm" @close="testModal.open = false">
      <div class="space-y-4">
        <p class="text-sm" style="color: var(--color-text-secondary)">
          Test the connection for <span class="font-semibold" style="color: var(--color-text)">{{ testModal.providerName }}</span>.
          Enter your token to verify credentials.
        </p>

        <!-- Token input -->
        <div v-if="!testModal.result">
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
            Personal Access Token <span style="color: var(--color-error)">*</span>
          </label>
          <input
            v-model="testModal.testToken"
            type="password"
            placeholder="ghp_..."
            :disabled="testModal.loading"
            class="w-full px-3 py-2 text-sm rounded-md border font-mono"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
          <p class="text-xs mt-1" style="color: var(--color-text-muted)">Token is not stored — used only for this test.</p>
        </div>

        <!-- Loading spinner -->
        <div v-if="testModal.loading" class="flex items-center gap-2 text-sm" style="color: var(--color-text-muted)">
          <svg class="w-4 h-4 animate-spin" style="color: var(--color-primary)" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Connecting...
        </div>

        <!-- Result -->
        <div v-else-if="testModal.result">
          <div
            class="flex items-start gap-2 p-3 rounded-lg"
            :style="{ background: testModal.result.success ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)' }"
          >
            <span
              class="text-sm font-semibold"
              :style="{ color: testModal.result.success ? '#22c55e' : '#ef4444' }"
            >
              {{ testModal.result.success ? '&#x2713; Connected' : '&#x2715; Failed' }}
            </span>
          </div>
          <p class="text-xs mt-2" style="color: var(--color-text-secondary)">{{ testModal.result.message }}</p>
        </div>
      </div>

      <template #footer>
        <BaseButton variant="secondary" size="sm" @click="testModal.open = false">
          {{ testModal.result ? 'Close' : 'Cancel' }}
        </BaseButton>
        <BaseButton
          v-if="!testModal.result"
          variant="primary"
          size="sm"
          :loading="testModal.loading"
          :disabled="!testModal.testToken.trim()"
          @click="runTest"
        >
          Run Test
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { vcsApi } from '@/api/endpoints'
import { useUIStore } from '@/stores/ui'
import type { VCSProvider, VCSProviderType } from '@/types'

const uiStore = useUIStore()

const TABS = [
  { key: 'vcs', label: 'VCS Providers' },
  { key: 'llm', label: 'LLM Model' },
]
const activeTab = ref('vcs')

const providers = ref<VCSProvider[]>([])
const isLoading = ref(false)

async function loadProviders(): Promise<void> {
  isLoading.value = true
  try {
    const { data } = await vcsApi.listProviders()
    providers.value = data
  } catch {
    // silent — not critical, providers list is empty by default
  } finally {
    isLoading.value = false
  }
}

onMounted(loadProviders)

function providerIcon(p: VCSProviderType): string {
  const icons: Record<VCSProviderType, string> = {
    github: '\u2B21',
    gitlab: '\u25C8',
    bitbucket: '\u2B21',
    other: '\u229E',
  }
  return icons[p] ?? '\u229E'
}

function providerBg(p: VCSProviderType): string {
  const bgs: Record<VCSProviderType, string> = {
    github: 'rgba(99,102,241,0.15)',
    gitlab: 'rgba(252,115,22,0.15)',
    bitbucket: 'rgba(59,130,246,0.15)',
    other: 'rgba(148,163,184,0.15)',
  }
  return bgs[p] ?? 'rgba(148,163,184,0.15)'
}

// ── Form modal ──────────────────────────────────────────────────────────────

const formModal = reactive({ open: false, editId: null as string | null })
const form = reactive({
  name: '',
  provider: 'github',
  base_url: '',
  token: '',
  username: '',
})
const isSaving = ref(false)

function openAddModal(): void {
  formModal.editId = null
  Object.assign(form, { name: '', provider: 'github', base_url: '', token: '', username: '' })
  formModal.open = true
}

function openEditModal(p: VCSProvider): void {
  formModal.editId = p.id
  Object.assign(form, {
    name: p.name,
    provider: p.provider,
    base_url: p.base_url ?? '',
    token: '',
    username: p.username ?? '',
  })
  formModal.open = true
}

function closeFormModal(): void {
  formModal.open = false
}

async function saveProvider(): Promise<void> {
  isSaving.value = true
  try {
    if (formModal.editId) {
      const body: { name: string; base_url: string | null; username: string | null; token?: string } = {
        name: form.name,
        base_url: form.base_url || null,
        username: form.username || null,
      }
      if (form.token) body.token = form.token
      const { data } = await vcsApi.updateProvider(formModal.editId, body)
      const idx = providers.value.findIndex((p) => p.id === formModal.editId)
      if (idx !== -1) providers.value[idx] = data
      uiStore.notify({ type: 'success', title: 'Provider updated', duration: 3000 })
    } else {
      const { data } = await vcsApi.createProvider({
        name: form.name,
        provider: form.provider,
        base_url: form.base_url || null,
        token: form.token,
        username: form.username || null,
      })
      providers.value.push(data)
      uiStore.notify({ type: 'success', title: 'Provider added', duration: 3000 })
    }
    formModal.open = false
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Failed to save provider', message: err instanceof Error ? err.message : String(err), duration: 6000 })
  } finally {
    isSaving.value = false
  }
}

async function deleteProvider(id: string): Promise<void> {
  try {
    await vcsApi.deleteProvider(id)
    providers.value = providers.value.filter((p) => p.id !== id)
    uiStore.notify({ type: 'success', title: 'Provider removed', duration: 3000 })
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Delete failed', message: String(err), duration: 5000 })
  }
}

// ── Test modal ──────────────────────────────────────────────────────────────

const testModal = reactive({
  open: false,
  loading: false,
  providerName: '',
  provider: null as VCSProvider | null,
  testToken: '',
  result: null as { success: boolean; message: string } | null,
})

function openTestModal(p: VCSProvider): void {
  testModal.provider = p
  testModal.providerName = p.name
  testModal.result = null
  testModal.testToken = ''
  testModal.loading = false
  testModal.open = true
}

async function runTest(): Promise<void> {
  if (!testModal.provider || !testModal.testToken.trim()) return
  testModal.loading = true
  testModal.result = null
  try {
    const { data } = await vcsApi.testConnection({
      provider: testModal.provider.provider,
      base_url: testModal.provider.base_url,
      token: testModal.testToken.trim(),
    })
    testModal.result = data
  } catch (err) {
    testModal.result = { success: false, message: err instanceof Error ? err.message : String(err) }
  } finally {
    testModal.loading = false
  }
}
</script>
