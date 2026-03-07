<template>
  <div class="p-6 max-w-3xl mx-auto space-y-6">
    <div>
      <h1 class="text-2xl font-bold" style="color: var(--color-text)">Settings</h1>
      <p class="mt-0.5 text-sm" style="color: var(--color-text-secondary)">
        Configure VCS providers, integrations, and LLM model settings.
      </p>
    </div>

    <!-- Tab switcher -->
    <div class="flex gap-1 p-1 rounded-lg w-fit" style="background: var(--color-elevated)">
      <button
        @click="activeTab = 'vcs'"
        class="px-4 py-1.5 text-sm rounded-md font-medium transition-all"
        :style="activeTab === 'vcs'
          ? 'background: var(--color-card); color: var(--color-text); box-shadow: 0 1px 3px rgba(0,0,0,0.3)'
          : 'color: var(--color-text-muted)'"
      >VCS Providers</button>
      <button
        @click="onActivateLLMTab"
        class="px-4 py-1.5 text-sm rounded-md font-medium transition-all"
        :style="activeTab === 'llm'
          ? 'background: var(--color-card); color: var(--color-text); box-shadow: 0 1px 3px rgba(0,0,0,0.3)'
          : 'color: var(--color-text-muted)'"
      >LLM Model</button>
    </div>

    <!-- ── VCS Providers tab ────────────────────────────────────────────── -->
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
            <div class="flex items-center gap-2">
              <p class="text-sm font-semibold truncate" style="color: var(--color-text)">{{ p.name }}</p>
              <!-- Verified badge -->
              <span
                v-if="verifiedMap.has(p.id)"
                class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium flex-shrink-0"
                :style="verifiedMap.get(p.id)
                  ? 'background: rgba(34,197,94,0.15); color: #86efac'
                  : 'background: rgba(239,68,68,0.15); color: #fca5a5'"
              >
                {{ verifiedMap.get(p.id) ? '&#x2713; Verified' : '&#x2715; Unverified' }}
              </span>
            </div>
            <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">
              {{ p.provider }}
              <template v-if="p.base_url"> · {{ p.base_url }}</template>
              <template v-if="p.username"> · {{ p.username }}</template>
              · token: <span class="font-mono">{{ p.token_hint }}</span>
            </p>
          </div>

          <!-- Actions -->
          <div class="flex gap-2 flex-shrink-0">
            <BaseButton variant="ghost" size="xs" @click="openVerifyModal(p)">Verify</BaseButton>
            <BaseButton variant="ghost" size="xs" @click="openEditModal(p)">Edit</BaseButton>
            <BaseButton variant="danger" size="xs" @click="deleteProvider(p.id)">Delete</BaseButton>
          </div>
        </div>
      </div>
    </template>

    <!-- ── LLM Model tab ───────────────────────────────────────────────── -->
    <template v-if="activeTab === 'llm'">
      <div
        class="rounded-xl border p-5 space-y-5"
        :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }"
      >
        <!-- Loading -->
        <div v-if="llmLoading" class="space-y-3">
          <div v-for="i in 3" :key="i" class="h-10 rounded-md animate-pulse" style="background: var(--color-elevated)" />
        </div>

        <template v-else-if="llmSettings">
          <!-- Provider (read-only) -->
          <div>
            <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">Provider</label>
            <div
              class="px-3 py-2 rounded-md border text-sm"
              :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }"
            >
              {{ llmSettings.provider }}
            </div>
            <p class="text-xs mt-1" style="color: var(--color-text-muted)">
              Provider is configured via environment variables.
            </p>
          </div>

          <!-- Model dropdown -->
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-xs font-medium" style="color: var(--color-text-secondary)">Model</label>
              <button
                class="text-xs"
                style="color: var(--color-text-muted)"
                :disabled="llmLoading"
                @click="loadLLMSettings"
              >↻ Refresh</button>
            </div>
            <select
              v-model="llmForm.model"
              class="w-full px-3 py-2 text-sm rounded-md border"
              :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
            >
              <option
                v-for="m in llmSettings.available_models"
                :key="m"
                :value="m"
              >{{ m }}</option>
            </select>

            <!-- Add custom model -->
            <div class="mt-2 flex gap-2">
              <input
                v-model="newModelInput"
                type="text"
                placeholder="e.g. gpt-4o-mini"
                class="flex-1 px-3 py-2 text-sm rounded-md border"
                :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
                :disabled="addModelLoading"
                @keydown.enter="addCustomModel"
              />
              <BaseButton
                variant="secondary"
                size="sm"
                :loading="addModelLoading"
                :disabled="!newModelInput.trim()"
                @click="addCustomModel"
              >
                Add
              </BaseButton>
            </div>
            <p v-if="addModelError" class="mt-1.5 text-xs" style="color: var(--color-error)">
              {{ addModelError }}
            </p>
          </div>

          <!-- Embedding Model dropdown -->
          <div>
            <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
              Embedding Model
            </label>
            <select
              v-model="llmForm.embed_model"
              class="w-full px-3 py-2 text-sm rounded-md border"
              :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
            >
              <option v-for="m in llmSettings.available_models" :key="m" :value="m">{{ m }}</option>
            </select>
            <p class="text-xs mt-1" style="color: var(--color-text-muted)">
              Model used for code embeddings and vector search.
            </p>
          </div>

          <!-- Base URL -->
          <div>
            <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
              Base URL <span style="color: var(--color-text-muted)">(for self-hosted / proxy)</span>
            </label>
            <input
              v-model="llmForm.base_url"
              type="url"
              placeholder="https://api.openai.com (leave blank for default)"
              class="w-full px-3 py-2 text-sm rounded-md border"
              :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
            />
          </div>

          <!-- Test Connection result -->
          <div
            v-if="llmTestResult"
            class="flex items-start gap-2 px-3 py-2 rounded-md text-sm"
            :style="llmTestResult.ok
              ? 'background: rgba(34,197,94,0.1); color: #86efac'
              : 'background: rgba(239,68,68,0.1); color: #fca5a5'"
          >
            <span class="flex-shrink-0 font-semibold">{{ llmTestResult.ok ? '&#x2713;' : '&#x2715;' }}</span>
            <span v-if="llmTestResult.ok">
              <span class="font-medium">{{ llmTestResult.model }}</span>
              <span v-if="llmTestResult.response" class="ml-1 opacity-80">— {{ llmTestResult.response }}</span>
            </span>
            <span v-else>{{ llmTestResult.error }}</span>
          </div>

          <!-- Save result message -->
          <div
            v-if="llmSaveResult"
            class="px-3 py-2 rounded-md text-sm font-medium"
            :style="llmSaveResult.ok
              ? 'background: rgba(34,197,94,0.1); color: #86efac'
              : 'background: rgba(239,68,68,0.1); color: #fca5a5'"
          >
            {{ llmSaveResult.message }}
          </div>

          <!-- Action buttons -->
          <div class="flex items-center justify-between">
            <BaseButton
              variant="secondary"
              size="sm"
              :loading="llmTesting"
              :disabled="llmSaving"
              @click="testLLMConnection"
            >
              Test Connection
            </BaseButton>
            <BaseButton variant="primary" size="sm" :loading="llmSaving" :disabled="llmTesting" @click="saveLLMSettings">
              Save
            </BaseButton>
          </div>
        </template>

        <!-- Load error -->
        <div v-else class="py-6 text-center">
          <p class="text-sm" style="color: var(--color-text-muted)">Failed to load LLM settings.</p>
          <BaseButton variant="ghost" size="sm" class="mt-3" @click="loadLLMSettings">Retry</BaseButton>
        </div>
      </div>
    </template>

    <!-- ── Add/Edit Modal ───────────────────────────────────────────────── -->
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
            {{ tokenLabel }}
            <span v-if="formModal.editId" style="color: var(--color-text-muted)">(leave blank to keep existing)</span>
          </label>
          <input
            v-model="form.token"
            type="password"
            :placeholder="tokenPlaceholder"
            class="w-full px-3 py-2 text-sm rounded-md border font-mono"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
          <p class="text-xs mt-1" style="color: var(--color-text-muted)">{{ tokenHelperText }}</p>
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

        <!-- Test & Save inline result -->
        <div
          v-if="formModal.testResult"
          class="px-3 py-2 rounded-md text-sm"
          :style="formModal.testResult.success
            ? 'background: rgba(34,197,94,0.1); color: #86efac'
            : 'background: rgba(239,68,68,0.1); color: #fca5a5'"
        >
          {{ formModal.testResult.success ? '&#x2713; Connection verified' : '&#x2715; ' + formModal.testResult.message }}
        </div>
      </div>

      <template #footer>
        <BaseButton variant="secondary" size="sm" @click="closeFormModal">Cancel</BaseButton>
        <!-- Test & Save (add mode only) -->
        <BaseButton
          v-if="!formModal.editId"
          variant="primary"
          size="sm"
          :loading="formModal.testLoading || isSaving"
          :disabled="!form.name || !form.token"
          @click="testAndSave"
        >
          Test &amp; Save
        </BaseButton>
        <!-- Plain Save (edit mode) -->
        <BaseButton
          v-else
          variant="primary"
          size="sm"
          :loading="isSaving"
          :disabled="!form.name"
          @click="saveProvider"
        >
          Save Changes
        </BaseButton>
      </template>
    </BaseModal>

    <!-- Verify modal (renamed from Test) -->
    <BaseModal :open="verifyModal.open" title="Verify Connection" size="sm" @close="verifyModal.open = false">
      <div class="space-y-4">
        <p class="text-sm" style="color: var(--color-text-secondary)">
          Verify the connection for <span class="font-semibold" style="color: var(--color-text)">{{ verifyModal.providerName }}</span>.
          Enter your token to check credentials.
        </p>

        <!-- Token input -->
        <div v-if="!verifyModal.result">
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
            Personal Access Token <span style="color: var(--color-error)">*</span>
          </label>
          <input
            v-model="verifyModal.testToken"
            type="password"
            placeholder="ghp_..."
            :disabled="verifyModal.loading"
            class="w-full px-3 py-2 text-sm rounded-md border font-mono"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
          <p class="text-xs mt-1" style="color: var(--color-text-muted)">Token is not stored — used only for this verification.</p>
        </div>

        <!-- Loading spinner -->
        <div v-if="verifyModal.loading" class="flex items-center gap-2 text-sm" style="color: var(--color-text-muted)">
          <svg class="w-4 h-4 animate-spin" style="color: var(--color-primary)" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Connecting...
        </div>

        <!-- Result -->
        <div v-else-if="verifyModal.result">
          <div
            class="flex items-start gap-2 p-3 rounded-lg"
            :style="{ background: verifyModal.result.success ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)' }"
          >
            <span
              class="text-sm font-semibold"
              :style="{ color: verifyModal.result.success ? '#22c55e' : '#ef4444' }"
            >
              {{ verifyModal.result.success ? '&#x2713; Connected' : '&#x2715; Failed' }}
            </span>
          </div>
          <p class="text-xs mt-2" style="color: var(--color-text-secondary)">{{ verifyModal.result.message }}</p>
        </div>
      </div>

      <template #footer>
        <BaseButton variant="secondary" size="sm" @click="verifyModal.open = false">
          {{ verifyModal.result ? 'Close' : 'Cancel' }}
        </BaseButton>
        <BaseButton
          v-if="!verifyModal.result"
          variant="primary"
          size="sm"
          :loading="verifyModal.loading"
          :disabled="!verifyModal.testToken.trim()"
          @click="runVerify"
        >
          Verify
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { settingsApi, vcsApi } from '@/api/endpoints'
import { useUIStore } from '@/stores/ui'
import type { LLMSettings, VCSProvider, VCSProviderType } from '@/types'

const uiStore = useUIStore()

// ── Tab state ────────────────────────────────────────────────────────────────

const activeTab = ref<'vcs' | 'llm'>('vcs')

// ── VCS Providers ────────────────────────────────────────────────────────────

const providers = ref<VCSProvider[]>([])
const isLoading = ref(false)
// Map of provider_id → verified boolean (populated after verify/test-and-save)
const verifiedMap = reactive(new Map<string, boolean>())

async function loadProviders(): Promise<void> {
  isLoading.value = true
  try {
    const { data } = await vcsApi.listProviders()
    providers.value = data
  } catch {
    // silent
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

// Per-provider token helper text
const tokenLabel = computed((): string => {
  if (form.provider === 'github') return 'Personal Access Token'
  if (form.provider === 'gitlab') return 'Access Token'
  if (form.provider === 'bitbucket') return 'App Password'
  return 'Access Token'
})

const tokenPlaceholder = computed((): string => {
  if (form.provider === 'github') return 'ghp_...'
  if (form.provider === 'gitlab') return 'glpat-...'
  if (form.provider === 'bitbucket') return 'App password'
  return 'token...'
})

const tokenHelperText = computed((): string => {
  if (form.provider === 'github') return 'Personal Access Token (requires repo scope)'
  if (form.provider === 'gitlab') return 'Project or Group Access Token (requires api scope)'
  if (form.provider === 'bitbucket') return 'Bitbucket App Password (requires repo read/write)'
  return 'Token or password used for authentication'
})

// ── Form modal ───────────────────────────────────────────────────────────────

const formModal = reactive({
  open: false,
  editId: null as string | null,
  testLoading: false,
  testResult: null as { success: boolean; message: string } | null,
})
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
  formModal.testResult = null
  Object.assign(form, { name: '', provider: 'github', base_url: '', token: '', username: '' })
  formModal.open = true
}

function openEditModal(p: VCSProvider): void {
  formModal.editId = p.id
  formModal.testResult = null
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

/**
 * Test & Save: runs connection test first, saves on success.
 * Only available in add mode.
 */
async function testAndSave(): Promise<void> {
  if (!form.token.trim()) return
  formModal.testLoading = true
  formModal.testResult = null
  try {
    const { data: testData } = await vcsApi.testConnection({
      provider: form.provider,
      base_url: form.base_url || null,
      token: form.token.trim(),
    })
    formModal.testResult = testData
    if (!testData.success) {
      formModal.testLoading = false
      return
    }
    // Connection verified — proceed to save
    isSaving.value = true
    const { data } = await vcsApi.createProvider({
      name: form.name,
      provider: form.provider,
      base_url: form.base_url || null,
      token: form.token,
      username: form.username || null,
    })
    providers.value.push(data)
    verifiedMap.set(data.id, true)
    uiStore.notify({ type: 'success', title: 'Provider added and verified', duration: 3000 })
    formModal.open = false
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Failed to save provider', message: err instanceof Error ? err.message : String(err), duration: 6000 })
  } finally {
    formModal.testLoading = false
    isSaving.value = false
  }
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
    verifiedMap.delete(id)
    uiStore.notify({ type: 'success', title: 'Provider removed', duration: 3000 })
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Delete failed', message: String(err), duration: 5000 })
  }
}

// ── Verify modal ─────────────────────────────────────────────────────────────

const verifyModal = reactive({
  open: false,
  loading: false,
  providerName: '',
  provider: null as VCSProvider | null,
  testToken: '',
  result: null as { success: boolean; message: string } | null,
})

function openVerifyModal(p: VCSProvider): void {
  verifyModal.provider = p
  verifyModal.providerName = p.name
  verifyModal.result = null
  verifyModal.testToken = ''
  verifyModal.loading = false
  verifyModal.open = true
}

async function runVerify(): Promise<void> {
  if (!verifyModal.provider || !verifyModal.testToken.trim()) return
  verifyModal.loading = true
  verifyModal.result = null
  try {
    const { data } = await vcsApi.testConnection({
      provider: verifyModal.provider.provider,
      base_url: verifyModal.provider.base_url,
      token: verifyModal.testToken.trim(),
    })
    verifyModal.result = data
    // Update the verified badge on the card
    if (verifyModal.provider) {
      verifiedMap.set(verifyModal.provider.id, data.success)
    }
  } catch (err) {
    verifyModal.result = { success: false, message: err instanceof Error ? err.message : String(err) }
    if (verifyModal.provider) {
      verifiedMap.set(verifyModal.provider.id, false)
    }
  } finally {
    verifyModal.loading = false
  }
}

// ── LLM Settings ─────────────────────────────────────────────────────────────

const llmSettings = ref<LLMSettings | null>(null)
const llmLoading = ref(false)
const llmSaving = ref(false)
const llmSaveResult = ref<{ ok: boolean; message: string } | null>(null)
const llmForm = reactive({ model: '', embed_model: '', base_url: '' })

const newModelInput = ref('')
const addModelLoading = ref(false)
const addModelError = ref<string | null>(null)

// ── LLM Test Connection ───────────────────────────────────────────────────────

interface LLMTestResult {
  ok: boolean
  model?: string
  response?: string
  error?: string
}

const llmTesting = ref(false)
const llmTestResult = ref<LLMTestResult | null>(null)

async function testLLMConnection(): Promise<void> {
  llmTesting.value = true
  llmTestResult.value = null
  try {
    const { data } = await settingsApi.testLLM()
    llmTestResult.value = data
  } catch (err) {
    llmTestResult.value = { ok: false, error: err instanceof Error ? err.message : String(err) }
  } finally {
    llmTesting.value = false
  }
}

async function addCustomModel(): Promise<void> {
  const name = newModelInput.value.trim()
  if (!name || !llmSettings.value) return
  if (llmSettings.value.available_models.includes(name)) {
    newModelInput.value = ''
    llmForm.model = name   // just select it
    return
  }
  addModelLoading.value = true
  addModelError.value = null
  try {
    const updated = [...llmSettings.value.available_models, name]
    const { data } = await settingsApi.patchLLM({ available_models: updated })
    llmSettings.value = data
    llmForm.model = name
    newModelInput.value = ''
  } catch (err) {
    addModelError.value = err instanceof Error ? err.message : String(err)
  } finally {
    addModelLoading.value = false
  }
}

async function loadLLMSettings(): Promise<void> {
  llmLoading.value = true
  llmSaveResult.value = null
  try {
    const { data } = await settingsApi.getLLM()
    llmSettings.value = data
    llmForm.model = data.model
    llmForm.embed_model = data.embed_model
    llmForm.base_url = data.base_url ?? ''
  } catch {
    llmSettings.value = null
  } finally {
    llmLoading.value = false
  }
}

function onActivateLLMTab(): void {
  activeTab.value = 'llm'
  if (!llmSettings.value && !llmLoading.value) {
    void loadLLMSettings()
  }
}

async function saveLLMSettings(): Promise<void> {
  llmSaving.value = true
  llmSaveResult.value = null
  try {
    const { data } = await settingsApi.patchLLM({
      model: llmForm.model,
      embed_model: llmForm.embed_model,
      base_url: llmForm.base_url || null,
    })
    llmSettings.value = data
    llmForm.model = data.model
    llmForm.embed_model = data.embed_model
    llmForm.base_url = data.base_url ?? ''
    llmSaveResult.value = { ok: true, message: 'Model settings saved.' }
    uiStore.notify({ type: 'success', title: 'LLM settings saved', duration: 3000 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    llmSaveResult.value = { ok: false, message: msg }
    uiStore.notify({ type: 'error', title: 'Failed to save LLM settings', message: msg, duration: 6000 })
  } finally {
    llmSaving.value = false
  }
}
</script>
