<template>
  <div class="p-6 max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold" style="color: var(--color-text)">Code Patches</h1>
        <p class="mt-0.5 text-sm" style="color: var(--color-text-secondary)">
          {{ patches.length }} patches generated
        </p>
      </div>
      <div class="flex items-center gap-3">
        <BaseButton variant="secondary" size="sm" @click="exportZip">
          Export ZIP
        </BaseButton>
        <BaseButton variant="ghost" size="sm" :loading="isLoading" @click="reload">
          Refresh
        </BaseButton>
      </div>
    </div>

    <!-- Filter bar -->
    <div
      class="flex flex-wrap items-center gap-3 p-3 rounded-lg border"
      :style="{
        background: 'var(--color-card)',
        borderColor: 'var(--color-border)',
      }"
    >
      <!-- Status filters -->
      <div class="flex gap-1.5 flex-wrap">
        <button
          v-for="s in PATCH_STATUSES"
          :key="s.key"
          @click="toggleStatusFilter(s.key)"
          class="px-2.5 py-1 text-xs rounded-full border transition-all font-medium"
          :style="{
            background: activeFilters.includes(s.key) ? s.activeBg : 'var(--color-elevated)',
            borderColor: activeFilters.includes(s.key) ? s.borderColor : 'var(--color-border)',
            color: activeFilters.includes(s.key) ? s.textColor : 'var(--color-text-muted)',
          }"
        >
          {{ s.label }} ({{ countByStatus(s.key) }})
        </button>
      </div>

      <!-- Language filter -->
      <select
        v-model="langFilter"
        class="px-2 py-1.5 text-xs rounded-md border ml-auto"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text)',
        }"
      >
        <option value="">All languages</option>
        <option v-for="l in availableLangs" :key="l" :value="l">{{ l }}</option>
      </select>

      <!-- Validation filter -->
      <select
        v-model="validationFilter"
        class="px-2 py-1.5 text-xs rounded-md border"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text)',
        }"
      >
        <option value="">All validation</option>
        <option value="passed">Passed</option>
        <option value="failed">Failed</option>
        <option value="pending">Not validated</option>
      </select>

      <span class="text-xs" style="color: var(--color-text-muted)">
        {{ filteredPatches.length }} of {{ patches.length }}
      </span>
    </div>

    <!-- Loading skeleton -->
    <div v-if="isLoading" class="space-y-3">
      <div v-for="i in 5" :key="i" class="h-14 rounded-lg animate-pulse" style="background: var(--color-card)" />
    </div>

    <!-- Error -->
    <div v-else-if="loadError" class="text-center py-10">
      <p class="text-sm" style="color: var(--color-error)">{{ loadError }}</p>
    </div>

    <!-- Empty -->
    <div v-else-if="filteredPatches.length === 0" class="text-center py-16">
      <p class="text-sm" style="color: var(--color-text-muted)">No patches match the current filter.</p>
    </div>

    <!-- Patches table -->
    <div
      v-else
      class="rounded-xl border overflow-hidden"
      :style="{
        background: 'var(--color-card)',
        borderColor: 'var(--color-border)',
      }"
    >
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr :style="{ borderBottom: '1px solid var(--color-border)' }">
              <th
                v-for="col in COLUMNS"
                :key="col.key"
                class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                style="color: var(--color-text-muted)"
              >
                {{ col.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="patch in filteredPatches"
              :key="patch.patch_id"
              class="transition-colors"
              :style="{ borderBottom: '1px solid var(--color-border)' }"
            >
              <!-- File path -->
              <td class="px-4 py-3 max-w-xs">
                <p class="text-xs font-mono truncate" style="color: var(--color-text)" :title="patch.file_path">
                  {{ patch.file_path.split('/').pop() }}
                </p>
                <p class="text-xs font-mono truncate mt-0.5" style="color: var(--color-text-muted)" :title="patch.file_path">
                  {{ patch.file_path }}
                </p>
              </td>
              <!-- Type -->
              <td class="px-4 py-3">
                <BaseBadge :label="patch.patch_type" :color="patchTypeColor(patch.patch_type)" />
              </td>
              <!-- Language -->
              <td class="px-4 py-3">
                <BaseBadge :label="patch.language" color="blue" />
              </td>
              <!-- Status -->
              <td class="px-4 py-3">
                <StatusBadge :status="patch.status" />
              </td>
              <!-- Validation -->
              <td class="px-4 py-3">
                <span
                  v-if="patch.validation_passed !== null"
                  class="inline-flex items-center gap-1 text-xs font-medium"
                  :style="{ color: patch.validation_passed ? 'var(--color-success)' : 'var(--color-error)' }"
                >
                  {{ patch.validation_passed ? '✓ Passed' : '✕ Failed' }}
                </span>
                <span v-else class="text-xs" style="color: var(--color-text-muted)">—</span>
              </td>
              <!-- Model -->
              <td class="px-4 py-3 text-xs" style="color: var(--color-text-muted)">
                {{ patch.model_used ? patch.model_used.split('-').slice(0, 3).join('-') : '—' }}
              </td>
              <!-- Actions -->
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <BaseButton variant="ghost" size="xs" @click="viewDiff(patch.patch_id)">
                    View Diff
                  </BaseButton>
                  <BaseButton
                    v-if="patch.status === 'pending'"
                    variant="success"
                    size="xs"
                    @click="applyPatch(patch.patch_id)"
                  >
                    Apply
                  </BaseButton>
                  <BaseButton
                    v-if="patch.status === 'applied'"
                    variant="danger"
                    size="xs"
                    @click="showRevertModal(patch.patch_id)"
                  >
                    Revert
                  </BaseButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Diff viewer modal -->
    <BaseModal
      :open="diffModal.open"
      title="Patch Diff"
      size="xl"
      @close="diffModal.open = false"
    >
      <div v-if="diffModal.loading" class="flex items-center justify-center py-10">
        <svg class="w-6 h-6 animate-spin" style="color: var(--color-primary)" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>

      <div v-else-if="diffModal.patch">
        <!-- Patch meta -->
        <div class="flex flex-wrap gap-3 mb-4 text-xs" style="color: var(--color-text-muted)">
          <span>File: <span class="font-mono" style="color: var(--color-text)">{{ diffModal.patch.file_path }}</span></span>
          <span>Language: <span style="color: var(--color-text)">{{ diffModal.patch.language }}</span></span>
          <span v-if="diffModal.patch.tokens_used">
            Tokens: <span style="color: var(--color-text)">{{ diffModal.patch.tokens_used.toLocaleString() }}</span>
          </span>
        </div>

        <!-- Diff display -->
        <div
          class="rounded-lg overflow-auto text-xs font-mono"
          style="max-height: 500px; background: #0a0c12; border: 1px solid var(--color-border)"
        >
          <div class="p-4 space-y-0">
            <div
              v-for="(line, i) in parsedDiff"
              :key="i"
              :class="['px-1 leading-relaxed', line.type]"
            >
              <span class="select-none mr-3 opacity-40" style="user-select: none">{{ line.prefix }}</span>{{ line.content }}
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <BaseButton variant="secondary" size="sm" @click="diffModal.open = false">
          Close
        </BaseButton>
        <BaseButton
          v-if="diffModal.patch?.status === 'pending'"
          variant="success"
          size="sm"
          @click="applyFromModal"
        >
          Apply Patch
        </BaseButton>
      </template>
    </BaseModal>

    <!-- Revert reason modal -->
    <BaseModal
      :open="revertModal.open"
      title="Revert Patch"
      size="sm"
      @close="revertModal.open = false"
    >
      <div class="space-y-3">
        <p class="text-sm" style="color: var(--color-text-secondary)">
          Provide a reason for reverting this patch.
        </p>
        <textarea
          v-model="revertModal.reason"
          rows="3"
          placeholder="e.g. Caused integration test failures in CI."
          class="w-full px-3 py-2 text-sm rounded-md border resize-none"
          :style="{
            background: 'var(--color-elevated)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text)',
          }"
        />
      </div>
      <template #footer>
        <BaseButton variant="secondary" size="sm" @click="revertModal.open = false">Cancel</BaseButton>
        <BaseButton variant="danger" size="sm" :disabled="!revertModal.reason.trim()" @click="confirmRevert">
          Revert Patch
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { patchesApi } from '@/api/endpoints'
import { useUIStore } from '@/stores/ui'
import type { PatchDetail, PatchStatus, PatchSummary, PatchType } from '@/types'

const route  = useRoute()
const uiStore = useUIStore()
const jobId = route.params.jobId as string

const patches    = ref<PatchSummary[]>([])
const isLoading  = ref(false)
const loadError  = ref<string | null>(null)
const activeFilters    = ref<PatchStatus[]>([])
const langFilter       = ref('')
const validationFilter = ref('')

const COLUMNS = [
  { key: 'file',       label: 'File' },
  { key: 'type',       label: 'Type' },
  { key: 'language',   label: 'Language' },
  { key: 'status',     label: 'Status' },
  { key: 'validation', label: 'Validation' },
  { key: 'model',      label: 'Model' },
  { key: 'actions',    label: '' },
]

const PATCH_STATUSES: { key: PatchStatus; label: string; activeBg: string; borderColor: string; textColor: string }[] = [
  { key: 'pending',  label: 'Pending',  activeBg: 'rgba(148,163,184,0.15)', borderColor: '#64748b', textColor: '#cbd5e1' },
  { key: 'applied',  label: 'Applied',  activeBg: 'rgba(34,197,94,0.15)',  borderColor: '#22c55e', textColor: '#86efac' },
  { key: 'reverted', label: 'Reverted', activeBg: 'rgba(249,115,22,0.15)', borderColor: '#f97316', textColor: '#fdba74' },
  { key: 'failed',   label: 'Failed',   activeBg: 'rgba(239,68,68,0.15)',  borderColor: '#ef4444', textColor: '#fca5a5' },
]

const availableLangs = computed(() => [...new Set(patches.value.map((p) => p.language))].sort())

const filteredPatches = computed(() => {
  return patches.value.filter((p) => {
    if (activeFilters.value.length > 0 && !activeFilters.value.includes(p.status)) return false
    if (langFilter.value && p.language !== langFilter.value) return false
    if (validationFilter.value === 'passed' && p.validation_passed !== true) return false
    if (validationFilter.value === 'failed' && p.validation_passed !== false) return false
    if (validationFilter.value === 'pending' && p.validation_passed !== null) return false
    return true
  })
})

function countByStatus(status: PatchStatus): number {
  return patches.value.filter((p) => p.status === status).length
}

function toggleStatusFilter(status: PatchStatus): void {
  const idx = activeFilters.value.indexOf(status)
  if (idx === -1) activeFilters.value.push(status)
  else activeFilters.value.splice(idx, 1)
}

function patchTypeColor(type: PatchType): 'indigo' | 'green' | 'red' | 'orange' {
  const map: Record<PatchType, 'indigo' | 'green' | 'red' | 'orange'> = {
    modify: 'indigo', create: 'green', delete: 'red', rename: 'orange',
  }
  return map[type] ?? 'indigo'
}

// ── Diff modal ────────────────────────────────────────────────────────────────
interface ParsedLine { type: string; prefix: string; content: string }

const diffModal = reactive<{
  open: boolean
  loading: boolean
  patch: PatchDetail | null
}>({ open: false, loading: false, patch: null })

const parsedDiff = computed<ParsedLine[]>(() => {
  if (!diffModal.patch?.diff) return []
  return diffModal.patch.diff.split('\n').map((line) => {
    if (line.startsWith('+++') || line.startsWith('---'))
      return { type: 'diff-header', prefix: '', content: line }
    if (line.startsWith('@@'))
      return { type: 'diff-header', prefix: '', content: line }
    if (line.startsWith('+'))
      return { type: 'diff-add', prefix: '+', content: line.slice(1) }
    if (line.startsWith('-'))
      return { type: 'diff-remove', prefix: '-', content: line.slice(1) }
    return { type: '', prefix: ' ', content: line.slice(1) }
  })
})

async function viewDiff(patchId: string): Promise<void> {
  diffModal.open = true
  diffModal.loading = true
  diffModal.patch = null
  try {
    const { data } = await patchesApi.getPatch(jobId, patchId)
    diffModal.patch = data
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Failed to load diff', message: String(err), duration: 5000 })
    diffModal.open = false
  } finally {
    diffModal.loading = false
  }
}

// ── Apply ─────────────────────────────────────────────────────────────────────
async function applyPatch(patchId: string): Promise<void> {
  try {
    await patchesApi.applyPatch(jobId, patchId, {})
    const idx = patches.value.findIndex((p) => p.patch_id === patchId)
    if (idx !== -1) patches.value[idx] = { ...patches.value[idx], status: 'applied' }
    if (diffModal.patch?.patch_id === patchId) diffModal.patch = { ...diffModal.patch, status: 'applied' }
    uiStore.notify({ type: 'success', title: 'Patch marked as applied', duration: 3000 })
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Failed to apply patch', message: String(err), duration: 5000 })
  }
}

async function applyFromModal(): Promise<void> {
  if (!diffModal.patch) return
  await applyPatch(diffModal.patch.patch_id)
  diffModal.open = false
}

// ── Revert ────────────────────────────────────────────────────────────────────
const revertModal = reactive({ open: false, patchId: '', reason: '' })

function showRevertModal(patchId: string): void {
  revertModal.patchId = patchId
  revertModal.reason = ''
  revertModal.open = true
}

async function confirmRevert(): Promise<void> {
  try {
    await patchesApi.revertPatch(jobId, revertModal.patchId, { reason: revertModal.reason })
    const idx = patches.value.findIndex((p) => p.patch_id === revertModal.patchId)
    if (idx !== -1) patches.value[idx] = { ...patches.value[idx], status: 'reverted' }
    uiStore.notify({ type: 'success', title: 'Patch reverted', duration: 3000 })
    revertModal.open = false
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Failed to revert patch', message: String(err), duration: 5000 })
  }
}

// ── Export ────────────────────────────────────────────────────────────────────
async function exportZip(): Promise<void> {
  try {
    const { data } = await patchesApi.exportPatches(jobId)
    const url = URL.createObjectURL(data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `alm-patches-${jobId.slice(0, 8)}.zip`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Export failed', message: String(err), duration: 5000 })
  }
}

async function reload(): Promise<void> {
  isLoading.value = true
  loadError.value = null
  try {
    const { data } = await patchesApi.listPatches(jobId, { page_size: 200 } as any)
    patches.value = data.data
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err)
  } finally {
    isLoading.value = false
  }
}

onMounted(reload)
</script>
