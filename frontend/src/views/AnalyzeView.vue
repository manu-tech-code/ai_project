<template>
  <div class="p-6 max-w-2xl mx-auto">
    <h1 class="text-2xl font-bold" style="color: var(--color-text)">New Analysis</h1>
    <p class="mt-1 text-sm" style="color: var(--color-text-secondary)">
      Upload a .zip, .tar.gz, or .tgz archive of your legacy codebase to begin AI-powered analysis.
    </p>

    <!-- Form card -->
    <BaseCard class="mt-6">
      <div class="space-y-5">
        <!-- Job label -->
        <div>
          <label
            class="block text-xs font-medium mb-1.5"
            style="color: var(--color-text-secondary)"
            for="job-label"
          >
            Job Label <span style="color: var(--color-text-muted)">(optional)</span>
          </label>
          <input
            id="job-label"
            v-model="label"
            type="text"
            placeholder="e.g. Legacy ERP v2.1"
            maxlength="200"
            :disabled="isSubmitting"
            class="w-full px-3 py-2 text-sm rounded-md border focus:outline-none transition-colors"
            :style="{
              background: 'var(--color-elevated)',
              borderColor: 'var(--color-border)',
              color: 'var(--color-text)',
            }"
          />
        </div>

        <!-- File dropzone -->
        <div>
          <label
            class="block text-xs font-medium mb-1.5"
            style="color: var(--color-text-secondary)"
          >
            Source Archive <span style="color: var(--color-error)">*</span>
          </label>
          <div
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onDrop"
            @click="fileInput?.click()"
            class="relative flex flex-col items-center justify-center px-6 py-10 rounded-xl border-2 border-dashed cursor-pointer transition-all"
            :style="{
              borderColor: isDragging
                ? 'var(--color-primary)'
                : selectedFile
                ? 'rgba(34,197,94,0.5)'
                : 'var(--color-border)',
              background: isDragging
                ? 'rgba(99,102,241,0.05)'
                : selectedFile
                ? 'rgba(34,197,94,0.04)'
                : 'var(--color-elevated)',
            }"
          >
            <input
              ref="fileInput"
              type="file"
              accept=".zip,.tar.gz,.tgz"
              class="hidden"
              @change="onFileSelect"
            />
            <!-- File selected state -->
            <template v-if="selectedFile">
              <svg
                class="w-10 h-10 mb-3"
                style="color: var(--color-success)"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p class="text-sm font-medium" style="color: var(--color-text)">
                {{ selectedFile.name }}
              </p>
              <p class="text-xs mt-1" style="color: var(--color-text-muted)">
                {{ formatFileSize(selectedFile.size) }}
              </p>
              <button
                @click.stop="selectedFile = null"
                class="mt-2 text-xs transition-colors"
                style="color: var(--color-text-muted)"
              >
                Remove file
              </button>
            </template>
            <!-- Empty state -->
            <template v-else>
              <svg
                class="w-10 h-10 mb-3"
                :style="{ color: isDragging ? 'var(--color-primary)' : 'var(--color-text-muted)' }"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p class="text-sm font-medium" style="color: var(--color-text)">
                {{ isDragging ? 'Drop to upload' : 'Drop archive here or click to browse' }}
              </p>
              <p class="text-xs mt-1" style="color: var(--color-text-muted)">
                Accepted: .zip, .tar.gz, .tgz — max 500 MB
              </p>
            </template>
          </div>
        </div>

        <!-- Advanced config (collapsible) -->
        <div>
          <button
            @click="showConfig = !showConfig"
            class="flex items-center gap-2 text-xs transition-colors"
            style="color: var(--color-text-muted)"
          >
            <svg
              class="w-3.5 h-3.5 transition-transform"
              :class="showConfig ? 'rotate-180' : ''"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
            Advanced configuration
          </button>

          <div v-if="showConfig" class="mt-3 space-y-3">
            <!-- Severity threshold -->
            <div>
              <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
                Minimum smell severity
              </label>
              <select
                v-model="config.smell_severity_threshold"
                class="w-full px-3 py-2 text-sm rounded-md border focus:outline-none"
                :style="{
                  background: 'var(--color-elevated)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text)',
                }"
              >
                <option value="low">Low (show all)</option>
                <option value="medium">Medium and above</option>
                <option value="high">High and above</option>
                <option value="critical">Critical only</option>
              </select>
            </div>

            <!-- Max patches per task -->
            <div>
              <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
                Max patches per task
              </label>
              <input
                v-model.number="config.max_patches_per_task"
                type="number"
                min="1"
                max="20"
                class="w-full px-3 py-2 text-sm rounded-md border focus:outline-none"
                :style="{
                  background: 'var(--color-elevated)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text)',
                }"
              />
            </div>

            <!-- Extended thinking -->
            <label class="flex items-center gap-3 cursor-pointer">
              <input
                v-model="config.enable_extended_thinking"
                type="checkbox"
                class="w-4 h-4 rounded accent-indigo-500"
              />
              <div>
                <span class="text-sm" style="color: var(--color-text)">Enable extended thinking</span>
                <p class="text-xs" style="color: var(--color-text-muted)">
                  Uses deeper LLM reasoning. Slower but more thorough.
                </p>
              </div>
            </label>
          </div>
        </div>

        <!-- Submit button -->
        <div class="flex items-center justify-between pt-1">
          <p v-if="submitError" class="text-sm" style="color: var(--color-error)">
            {{ submitError }}
          </p>
          <div v-else />
          <BaseButton
            variant="primary"
            size="md"
            :disabled="!selectedFile"
            :loading="isSubmitting"
            type="submit"
            @click="submit"
          >
            {{ isSubmitting ? 'Submitting…' : 'Start Analysis' }}
          </BaseButton>
        </div>
      </div>
    </BaseCard>

    <!-- Progress tracker (shown when job is running) -->
    <BaseCard v-if="currentJob" class="mt-6" title="Analysis Progress">
      <div class="space-y-3">
        <div
          v-for="stage in STAGES"
          :key="stage.key"
          class="flex items-center gap-3"
        >
          <!-- Stage indicator -->
          <div
            class="flex items-center justify-center w-6 h-6 rounded-full flex-shrink-0 text-xs font-bold"
            :style="stageIndicatorStyle(stage.key)"
          >
            <span v-if="getStageStatus(stage.key) === 'complete'">✓</span>
            <span v-else-if="getStageStatus(stage.key) === 'running'">
              <svg class="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </span>
            <span v-else-if="getStageStatus(stage.key) === 'failed'">✕</span>
            <span v-else>{{ stage.order }}</span>
          </div>

          <!-- Stage info -->
          <div class="flex-1">
            <p
              class="text-sm font-medium"
              :style="{ color: getStageStatus(stage.key) === 'pending' ? 'var(--color-text-muted)' : 'var(--color-text)' }"
            >
              {{ stage.label }}
            </p>
          </div>

          <!-- Stage status badge -->
          <span
            class="text-xs"
            :style="{ color: stageTextColor(stage.key) }"
          >
            {{ getStageStatus(stage.key) ?? 'waiting' }}
          </span>
        </div>
      </div>

      <!-- Error message -->
      <p v-if="currentJob.error" class="mt-4 text-sm p-3 rounded-md" style="background: rgba(239,68,68,0.1); color: #fca5a5">
        {{ currentJob.error }}
      </p>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import { useAnalysisStore } from '@/stores/analysis'
import { useUIStore } from '@/stores/ui'
import type { Job, JobConfig } from '@/types'

const store = useAnalysisStore()
const ui = useUIStore()
const router = useRouter()

const fileInput  = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const label = ref('')
const isDragging = ref(false)
const isSubmitting = ref(false)
const submitError = ref<string | null>(null)
const showConfig = ref(false)

const config = ref<Partial<JobConfig>>({
  smell_severity_threshold: 'medium',
  max_patches_per_task: 5,
  enable_extended_thinking: false,
})

const currentJob = computed<Job | null>(() => store.activeJob)

const STAGES = [
  { key: 'detecting',    label: 'Language Detection',  order: 1 },
  { key: 'mapping',      label: 'UCG Construction',     order: 2 },
  { key: 'analyzing',    label: 'Smell Detection',      order: 3 },
  { key: 'planning',     label: 'Refactor Planning',    order: 4 },
  { key: 'transforming', label: 'Patch Generation',     order: 5 },
  { key: 'validating',   label: 'Validation',           order: 6 },
]

function getStageStatus(stageKey: string): string | null {
  return currentJob.value?.stage_progress?.[stageKey] ?? null
}

function stageIndicatorStyle(stageKey: string): string {
  const s = getStageStatus(stageKey)
  const base = 'border '
  if (s === 'complete')  return base + 'background: rgba(34,197,94,0.15); border-color: #22c55e; color: #86efac'
  if (s === 'running')   return base + 'background: rgba(99,102,241,0.15); border-color: #6366f1; color: #a5b4fc'
  if (s === 'failed')    return base + 'background: rgba(239,68,68,0.15); border-color: #ef4444; color: #fca5a5'
  return base + 'background: var(--color-elevated); border-color: var(--color-border); color: var(--color-text-muted)'
}

function stageTextColor(stageKey: string): string {
  const s = getStageStatus(stageKey)
  if (s === 'complete')  return 'var(--color-success)'
  if (s === 'running')   return 'var(--color-primary)'
  if (s === 'failed')    return 'var(--color-error)'
  return 'var(--color-text-muted)'
}

function onFileSelect(evt: Event): void {
  const input = evt.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

function onDrop(evt: DragEvent): void {
  isDragging.value = false
  const file = evt.dataTransfer?.files?.[0]
  if (file) selectedFile.value = file
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function submit(): Promise<void> {
  if (!selectedFile.value) return
  isSubmitting.value = true
  submitError.value = null
  try {
    const job = await store.submitJob(
      selectedFile.value,
      label.value || undefined,
      config.value,
    )
    store.startPolling(job.job_id)
    ui.notify({ type: 'info', title: 'Analysis started', message: 'Monitoring pipeline progress…', duration: 4000 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    submitError.value = msg
    ui.notify({ type: 'error', title: 'Submission failed', message: msg, duration: 6000 })
  } finally {
    isSubmitting.value = false
  }
}

// Auto-navigate when analysis completes
watch(
  () => store.activeJob?.status,
  (status) => {
    if (status === 'complete' && store.activeJobId) {
      ui.notify({ type: 'success', title: 'Analysis complete', message: 'Navigating to results…', duration: 4000 })
      router.push({ name: 'graph', params: { jobId: store.activeJobId } })
    } else if (status === 'failed') {
      ui.notify({ type: 'error', title: 'Analysis failed', message: store.activeJob?.error ?? 'An error occurred during analysis.', duration: 0 })
    }
  },
)
</script>
