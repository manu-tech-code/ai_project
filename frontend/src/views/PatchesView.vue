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
        <BaseButton v-if="patches.length > 0" variant="primary" size="sm" @click="openPushModal">
          Push to Repo
        </BaseButton>
        <BaseButton v-if="patches.length > 0" variant="secondary" size="sm" @click="exportZip">
          Export ZIP
        </BaseButton>
        <BaseButton variant="ghost" size="sm" :loading="isLoading" @click="() => reload(true)">
          Refresh
        </BaseButton>
      </div>
    </div>

    <!-- Error banner (shared, always rendered when generateError is set) -->
    <div
      v-if="generateError"
      class="p-3 rounded-lg text-sm"
      style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.3); color: var(--color-error)"
    >
      {{ generateError }}
    </div>

    <!-- Loading skeleton -->
    <div v-if="isLoading && patches.length === 0" class="space-y-3">
      <div v-for="i in 5" :key="i" class="h-14 rounded-lg animate-pulse" style="background: var(--color-card)" />
    </div>

    <!-- Generate Patches panel (no patches yet, job complete) -->
    <template v-else-if="patches.length === 0 && job?.status === 'complete'">
      <div
        class="rounded-xl border p-5 space-y-4"
        :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }"
      >
        <!-- Panel header -->
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold" style="color: var(--color-text)">Generate Patches</h2>
            <p class="text-sm mt-0.5" style="color: var(--color-text-secondary)">
              Select tasks to generate code patches for. Each patch is an LLM-generated unified diff.
            </p>
          </div>
          <div class="flex items-center gap-2">
            <BaseButton
              variant="secondary"
              size="sm"
              :disabled="selectedTaskIds.size === 0 || isGenerating"
              :loading="isGenerating && generateMode === 'selected'"
              @click="generateSelected"
            >
              Generate Selected ({{ selectedTaskIds.size }})
            </BaseButton>
            <BaseButton
              variant="primary"
              size="sm"
              :disabled="planTasks.length === 0 || isGenerating"
              :loading="isGenerating && generateMode === 'all'"
              @click="generateAll"
            >
              Generate All
            </BaseButton>
          </div>
        </div>

        <!-- Tasks loading -->
        <div v-if="isLoadingTasks" class="space-y-2">
          <div v-for="i in 4" :key="i" class="h-10 rounded animate-pulse" style="background: var(--color-elevated)" />
        </div>

        <!-- Tasks table -->
        <div
          v-else-if="planTasks.length > 0"
          class="rounded-lg border overflow-hidden"
          :style="{ borderColor: 'var(--color-border)' }"
        >
          <table class="w-full text-sm">
            <thead>
              <tr :style="{ background: 'var(--color-elevated)', borderBottom: '1px solid var(--color-border)' }">
                <th class="px-3 py-2.5 text-left w-8">
                  <input
                    type="checkbox"
                    class="w-4 h-4 rounded accent-indigo-500"
                    :checked="selectedTaskIds.size === planTasks.length && planTasks.length > 0"
                    @change="toggleSelectAll"
                  />
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)">Task</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)">Pattern</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)">Files</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)">Est.</th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)"></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="task in planTasks"
                :key="task.task_id"
                class="transition-colors"
                :style="{
                  borderBottom: '1px solid var(--color-border)',
                  background: selectedTaskIds.has(task.task_id) ? 'rgba(99,102,241,0.05)' : 'transparent',
                }"
              >
                <td class="px-3 py-2.5">
                  <input
                    type="checkbox"
                    class="w-4 h-4 rounded accent-indigo-500"
                    :checked="selectedTaskIds.has(task.task_id)"
                    @change="toggleTask(task.task_id)"
                  />
                </td>
                <td class="px-3 py-2.5 max-w-xs">
                  <p class="text-xs font-medium truncate" style="color: var(--color-text)" :title="task.title">
                    {{ task.title }}
                  </p>
                  <p class="text-xs truncate mt-0.5" style="color: var(--color-text-muted)" :title="task.description">
                    {{ task.description }}
                  </p>
                </td>
                <td class="px-3 py-2.5">
                  <span
                    class="inline-block px-1.5 py-0.5 text-xs rounded font-mono"
                    style="background: rgba(99,102,241,0.12); color: #a5b4fc"
                  >
                    {{ task.refactor_pattern }}
                  </span>
                </td>
                <td class="px-3 py-2.5 text-xs" style="color: var(--color-text-muted)">
                  {{ task.affected_files.length }} file{{ task.affected_files.length !== 1 ? 's' : '' }}
                </td>
                <td class="px-3 py-2.5 text-xs" style="color: var(--color-text-muted)">
                  {{ task.estimated_hours != null ? `${task.estimated_hours}h` : '—' }}
                </td>
                <td class="px-3 py-2.5">
                  <BaseButton
                    variant="ghost"
                    size="xs"
                    :loading="generatingTaskId === task.task_id"
                    :disabled="isGenerating"
                    @click="generateForTask(task.task_id)"
                  >
                    Generate
                  </BaseButton>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- No automated tasks -->
        <div v-else class="text-center py-8" style="color: var(--color-text-muted)">
          <p class="text-sm">No automated tasks found for this job.</p>
        </div>
      </div>
    </template>

    <!-- Patches exist: filter bar + table + optional "Generate More" -->
    <template v-else-if="patches.length > 0">
      <!-- Filter bar -->
      <div
        class="flex flex-wrap items-center gap-3 p-3 rounded-lg border"
        :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }"
      >
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
        <select
          v-model="langFilter"
          class="px-2 py-1.5 text-xs rounded-md border ml-auto"
          :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
        >
          <option value="">All languages</option>
          <option v-for="l in availableLangs" :key="l" :value="l">{{ l }}</option>
        </select>
        <select
          v-model="validationFilter"
          class="px-2 py-1.5 text-xs rounded-md border"
          :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
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

      <!-- Empty (filter-based) -->
      <div v-if="filteredPatches.length === 0" class="text-center py-16">
        <p class="text-sm" style="color: var(--color-text-muted)">No patches match the current filter.</p>
      </div>

      <!-- Patches table -->
      <div
        v-else
        class="rounded-xl border overflow-hidden"
        :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }"
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
                <td class="px-4 py-3 max-w-xs">
                  <p class="text-xs font-mono truncate" style="color: var(--color-text)" :title="patch.file_path">
                    {{ patch.file_path.split('/').pop() }}
                  </p>
                  <p class="text-xs font-mono truncate mt-0.5" style="color: var(--color-text-muted)" :title="patch.file_path">
                    {{ patch.file_path }}
                  </p>
                </td>
                <td class="px-4 py-3">
                  <BaseBadge :label="patch.patch_type" :color="patchTypeColor(patch.patch_type)" />
                </td>
                <td class="px-4 py-3">
                  <BaseBadge :label="patch.language" color="blue" />
                </td>
                <td class="px-4 py-3">
                  <StatusBadge :status="patch.status" />
                </td>
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
                <td class="px-4 py-3 text-xs" style="color: var(--color-text-muted)">
                  {{ patch.model_used ? patch.model_used.split('-').slice(0, 3).join('-') : '—' }}
                </td>
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

      <!-- Generate More (collapsible, for tasks without patches) -->
      <div
        v-if="tasksWithoutPatches.length > 0 && job?.status === 'complete'"
        class="rounded-xl border overflow-hidden"
        :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }"
      >
        <button
          class="w-full flex items-center justify-between px-5 py-3 text-sm font-medium transition-colors"
          :style="{ color: 'var(--color-text)', background: 'transparent' }"
          @click="generateMoreExpanded = !generateMoreExpanded"
        >
          <span>Generate More Patches ({{ tasksWithoutPatches.length }} tasks remaining)</span>
          <svg
            class="w-4 h-4 transition-transform"
            :class="generateMoreExpanded ? 'rotate-180' : ''"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
            style="color: var(--color-text-muted)"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        <div v-if="generateMoreExpanded" :style="{ borderTop: '1px solid var(--color-border)' }">
          <div class="p-4 space-y-3">
            <div class="flex items-center justify-between">
              <p class="text-xs" style="color: var(--color-text-muted)">
                {{ selectedMoreTaskIds.size }} selected
              </p>
              <div class="flex gap-2">
                <BaseButton
                  variant="secondary"
                  size="sm"
                  :disabled="selectedMoreTaskIds.size === 0 || isGenerating"
                  :loading="isGenerating && generateMode === 'more-selected'"
                  @click="generateMoreSelected"
                >
                  Generate Selected
                </BaseButton>
                <BaseButton
                  variant="primary"
                  size="sm"
                  :disabled="isGenerating"
                  :loading="isGenerating && generateMode === 'more-all'"
                  @click="generateMoreAll"
                >
                  Generate All Remaining
                </BaseButton>
              </div>
            </div>

            <div class="rounded-lg border overflow-hidden" :style="{ borderColor: 'var(--color-border)' }">
              <table class="w-full text-sm">
                <thead>
                  <tr :style="{ background: 'var(--color-elevated)', borderBottom: '1px solid var(--color-border)' }">
                    <th class="px-3 py-2 text-left w-8">
                      <input
                        type="checkbox"
                        class="w-4 h-4 rounded accent-indigo-500"
                        :checked="selectedMoreTaskIds.size === tasksWithoutPatches.length && tasksWithoutPatches.length > 0"
                        @change="toggleSelectAllMore"
                      />
                    </th>
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)">Task</th>
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)">Pattern</th>
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="task in tasksWithoutPatches"
                    :key="task.task_id"
                    :style="{ borderBottom: '1px solid var(--color-border)' }"
                  >
                    <td class="px-3 py-2">
                      <input
                        type="checkbox"
                        class="w-4 h-4 rounded accent-indigo-500"
                        :checked="selectedMoreTaskIds.has(task.task_id)"
                        @change="toggleMoreTask(task.task_id)"
                      />
                    </td>
                    <td class="px-3 py-2 max-w-xs">
                      <p class="text-xs font-medium truncate" style="color: var(--color-text)">{{ task.title }}</p>
                    </td>
                    <td class="px-3 py-2">
                      <span class="text-xs font-mono" style="color: var(--color-text-muted)">{{ task.refactor_pattern }}</span>
                    </td>
                    <td class="px-3 py-2">
                      <BaseButton
                        variant="ghost"
                        size="xs"
                        :loading="generatingTaskId === task.task_id"
                        :disabled="isGenerating"
                        @click="generateForTask(task.task_id)"
                      >
                        Generate
                      </BaseButton>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- No patches and job not complete -->
    <div v-else-if="!isLoading" class="text-center py-16">
      <p class="text-sm" style="color: var(--color-text-muted)">
        {{ job?.status === 'failed' ? 'Job failed — no patches available.' : 'No patches available yet.' }}
      </p>
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
        <div class="flex flex-wrap gap-3 mb-4 text-xs" style="color: var(--color-text-muted); align-items: center">
          <span>File: <span class="font-mono" style="color: var(--color-text)">{{ diffModal.patch.file_path }}</span></span>
          <span>Language: <span style="color: var(--color-text)">{{ diffModal.patch.language }}</span></span>
          <span v-if="diffModal.patch.tokens_used">
            Tokens: <span style="color: var(--color-text)">{{ diffModal.patch.tokens_used.toLocaleString() }}</span>
          </span>
          <button
            v-if="diffModal.patch.prompt"
            @click="diffModal.showPrompt = !diffModal.showPrompt"
            class="ml-auto underline hover:opacity-80 transition-opacity"
            style="color: var(--color-primary)"
          >
            {{ diffModal.showPrompt ? 'Hide Prompt' : 'View Prompt' }}
          </button>
        </div>
        <div
          v-if="diffModal.showPrompt && diffModal.patch.prompt"
          class="mb-4 rounded-lg overflow-auto text-xs font-mono p-4"
          style="max-height: 300px; background: #0a0c12; border: 1px solid var(--color-border); white-space: pre-wrap; color: var(--color-text-muted)"
        >
          {{ diffModal.patch.prompt }}
        </div>
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
        <BaseButton variant="secondary" size="sm" @click="diffModal.open = false">Close</BaseButton>
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
    <BaseModal :open="revertModal.open" title="Revert Patch" size="sm" @close="revertModal.open = false">
      <div class="space-y-3">
        <p class="text-sm" style="color: var(--color-text-secondary)">
          Provide a reason for reverting this patch.
        </p>
        <textarea
          v-model="revertModal.reason"
          rows="3"
          placeholder="e.g. Caused integration test failures in CI."
          class="w-full px-3 py-2 text-sm rounded-md border resize-none"
          :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
        />
      </div>
      <template #footer>
        <BaseButton variant="secondary" size="sm" @click="revertModal.open = false">Cancel</BaseButton>
        <BaseButton variant="danger" size="sm" :disabled="!revertModal.reason.trim()" @click="confirmRevert">
          Revert Patch
        </BaseButton>
      </template>
    </BaseModal>

    <!-- Push to repo modal -->
    <BaseModal :open="pushModal.open" title="Push Patches to Repo" size="sm" @close="pushModal.open = false">
      <div v-if="pushModal.result" class="space-y-3">
        <div class="p-3 rounded-lg" style="background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.25)">
          <p class="text-sm font-semibold" style="color: #22c55e">
            &#x2713; {{ pushModal.result.patches_applied }} file(s) pushed to
            <span class="font-mono">{{ pushModal.result.branch }}</span>
          </p>
          <p class="text-xs mt-1" style="color: var(--color-text-secondary)">{{ pushModal.result.message }}</p>
        </div>
        <a
          v-if="pushModal.result.pr_url"
          :href="pushModal.result.pr_url"
          target="_blank"
          rel="noopener noreferrer"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium"
          style="background: rgba(99,102,241,0.15); color: #a5b4fc"
        >
          Open Pull Request &#x2192;
        </a>
        <p v-else class="text-xs" style="color: var(--color-text-muted)">
          No PR created (non-GitHub/GitLab provider or creation skipped).
        </p>
      </div>
      <div v-else-if="pushModal.error" class="space-y-3">
        <div class="p-3 rounded-lg" style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.3)">
          <p class="text-sm font-semibold mb-1" style="color: var(--color-error)">Push failed</p>
          <p class="text-xs font-mono" style="color: var(--color-text-secondary)">{{ pushModal.error }}</p>
        </div>
        <BaseButton variant="ghost" size="sm" @click="pushModal.error = null">Try again</BaseButton>
      </div>
      <div v-else class="space-y-4">
        <div>
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">Branch name</label>
          <input
            v-model="pushModal.branchName"
            type="text"
            class="w-full px-3 py-2 text-sm rounded-md border font-mono"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
        </div>
        <div>
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">Provider</label>
          <select
            v-model="pushModal.providerId"
            class="w-full px-3 py-2 text-sm rounded-md border"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          >
            <option value="">No saved provider — enter token manually</option>
            <option v-for="p in vcsProviders" :key="p.id" :value="p.id">{{ p.name }} ({{ p.provider }})</option>
          </select>
        </div>
        <div v-if="!pushModal.providerId">
          <label class="block text-xs font-medium mb-1.5" style="color: var(--color-text-secondary)">
            Token <span style="color: var(--color-error)">*</span>
          </label>
          <input
            v-model="pushModal.token"
            type="password"
            placeholder="ghp_..."
            class="w-full px-3 py-2 text-sm rounded-md border font-mono"
            :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }"
          />
        </div>
        <label class="flex items-center gap-3 cursor-pointer">
          <input v-model="pushModal.createPr" type="checkbox" class="w-4 h-4 rounded accent-indigo-500" />
          <span class="text-sm" style="color: var(--color-text)">Create pull request (GitHub / GitLab)</span>
        </label>
        <div>
          <label class="block text-xs font-medium mb-2" style="color: var(--color-text-secondary)">Scope</label>
          <div class="space-y-2">
            <label class="flex items-center gap-2.5 cursor-pointer">
              <input v-model="pushModal.scope" type="radio" value="all" class="accent-indigo-500" />
              <span class="text-sm" style="color: var(--color-text)">All patches</span>
              <span class="text-xs" style="color: var(--color-text-muted)">({{ patches.length }})</span>
            </label>
            <label class="flex items-center gap-2.5 cursor-pointer">
              <input v-model="pushModal.scope" type="radio" value="applied" class="accent-indigo-500" />
              <span class="text-sm" style="color: var(--color-text)">Applied patches only</span>
              <span class="text-xs" style="color: var(--color-text-muted)">({{ appliedPatchCount }})</span>
            </label>
          </div>
        </div>
      </div>
      <template #footer>
        <BaseButton variant="secondary" size="sm" @click="pushModal.open = false">
          {{ pushModal.result ? 'Close' : 'Cancel' }}
        </BaseButton>
        <BaseButton
          v-if="!pushModal.result && !pushModal.error"
          variant="primary"
          size="sm"
          :loading="pushModal.loading"
          @click="confirmPush"
        >
          Push
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
import { analyzeApi, patchesApi, planApi, vcsApi } from '@/api/endpoints'
import { useUIStore } from '@/stores/ui'
import type { Job, PatchDetail, PatchStatus, PatchSummary, PatchType, PlanTask, VCSProvider, VCSPushResult } from '@/types'

const _patchesCache = new Map<string, PatchSummary[]>()
const _patchesInFlight = new Map<string, Promise<void>>()

const route = useRoute()
const uiStore = useUIStore()
const jobId = route.params.jobId as string

const job = ref<Job | null>(null)
const patches = ref<PatchSummary[]>([])
const planTasks = ref<PlanTask[]>([])
const isLoading = ref(false)
const isLoadingTasks = ref(false)
const loadError = ref<string | null>(null)
const activeFilters = ref<PatchStatus[]>([])
const langFilter = ref('')
const validationFilter = ref('')
const vcsProviders = ref<VCSProvider[]>([])

// Generate state
const selectedTaskIds = ref(new Set<string>())
const selectedMoreTaskIds = ref(new Set<string>())
const isGenerating = ref(false)
const generateMode = ref<'selected' | 'all' | 'single' | 'more-selected' | 'more-all' | null>(null)
const generatingTaskId = ref<string | null>(null)
const generateError = ref<string | null>(null)
const generateMoreExpanded = ref(false)

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

// Tasks that don't yet have a patch (for "Generate More" section)
const tasksWithoutPatches = computed(() => {
  const taskIdsWithPatches = new Set(patches.value.map((p) => p.task_id))
  return planTasks.value.filter((t) => !taskIdsWithPatches.has(t.task_id))
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

// ── Task selection ─────────────────────────────────────────────────────────────
function toggleTask(taskId: string): void {
  if (selectedTaskIds.value.has(taskId)) selectedTaskIds.value.delete(taskId)
  else selectedTaskIds.value.add(taskId)
}

function toggleSelectAll(e: Event): void {
  const checked = (e.target as HTMLInputElement).checked
  if (checked) planTasks.value.forEach((t) => selectedTaskIds.value.add(t.task_id))
  else selectedTaskIds.value.clear()
}

function toggleMoreTask(taskId: string): void {
  if (selectedMoreTaskIds.value.has(taskId)) selectedMoreTaskIds.value.delete(taskId)
  else selectedMoreTaskIds.value.add(taskId)
}

function toggleSelectAllMore(e: Event): void {
  const checked = (e.target as HTMLInputElement).checked
  if (checked) tasksWithoutPatches.value.forEach((t) => selectedMoreTaskIds.value.add(t.task_id))
  else selectedMoreTaskIds.value.clear()
}

// ── Generate actions ───────────────────────────────────────────────────────────
async function generateForTask(taskId: string): Promise<void> {
  isGenerating.value = true
  generateMode.value = 'single'
  generatingTaskId.value = taskId
  generateError.value = null
  try {
    await patchesApi.generatePatches(jobId, [taskId])
    await reload(true)
    uiStore.notify({ type: 'success', title: 'Patch generated', duration: 3000 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    generateError.value = msg
    uiStore.notify({ type: 'error', title: 'Generation failed', message: msg, duration: 5000 })
  } finally {
    isGenerating.value = false
    generateMode.value = null
    generatingTaskId.value = null
  }
}

async function generateSelected(): Promise<void> {
  if (selectedTaskIds.value.size === 0) return
  isGenerating.value = true
  generateMode.value = 'selected'
  generateError.value = null
  try {
    await patchesApi.generatePatches(jobId, [...selectedTaskIds.value])
    await reload(true)
    selectedTaskIds.value.clear()
    uiStore.notify({ type: 'success', title: 'Patches generated', duration: 3000 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    generateError.value = msg
    uiStore.notify({ type: 'error', title: 'Generation failed', message: msg, duration: 5000 })
  } finally {
    isGenerating.value = false
    generateMode.value = null
  }
}

async function generateAll(): Promise<void> {
  isGenerating.value = true
  generateMode.value = 'all'
  generateError.value = null
  try {
    await patchesApi.generatePatches(jobId, null)
    await reload(true)
    selectedTaskIds.value.clear()
    uiStore.notify({ type: 'success', title: 'All patches generated', duration: 3000 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    generateError.value = msg
    uiStore.notify({ type: 'error', title: 'Generation failed', message: msg, duration: 5000 })
  } finally {
    isGenerating.value = false
    generateMode.value = null
  }
}

async function generateMoreSelected(): Promise<void> {
  if (selectedMoreTaskIds.value.size === 0) return
  isGenerating.value = true
  generateMode.value = 'more-selected'
  generateError.value = null
  try {
    await patchesApi.generatePatches(jobId, [...selectedMoreTaskIds.value])
    await reload(true)
    selectedMoreTaskIds.value.clear()
    uiStore.notify({ type: 'success', title: 'Patches generated', duration: 3000 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    generateError.value = msg
    uiStore.notify({ type: 'error', title: 'Generation failed', message: msg, duration: 5000 })
  } finally {
    isGenerating.value = false
    generateMode.value = null
  }
}

async function generateMoreAll(): Promise<void> {
  isGenerating.value = true
  generateMode.value = 'more-all'
  generateError.value = null
  const ids = tasksWithoutPatches.value.map((t) => t.task_id)
  try {
    await patchesApi.generatePatches(jobId, ids)
    await reload(true)
    selectedMoreTaskIds.value.clear()
    uiStore.notify({ type: 'success', title: 'All remaining patches generated', duration: 3000 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    generateError.value = msg
    uiStore.notify({ type: 'error', title: 'Generation failed', message: msg, duration: 5000 })
  } finally {
    isGenerating.value = false
    generateMode.value = null
  }
}

// ── Diff modal ─────────────────────────────────────────────────────────────────
interface ParsedLine { type: string; prefix: string; content: string }

const diffModal = reactive<{ open: boolean; loading: boolean; patch: PatchDetail | null; showPrompt: boolean }>({
  open: false,
  loading: false,
  patch: null,
  showPrompt: false,
})

const parsedDiff = computed<ParsedLine[]>(() => {
  if (!diffModal.patch?.diff) return []
  return diffModal.patch.diff.split('\n').map((line) => {
    if (line.startsWith('+++') || line.startsWith('---')) return { type: 'diff-header', prefix: '', content: line }
    if (line.startsWith('@@')) return { type: 'diff-header', prefix: '', content: line }
    if (line.startsWith('+')) return { type: 'diff-add', prefix: '+', content: line.slice(1) }
    if (line.startsWith('-')) return { type: 'diff-remove', prefix: '-', content: line.slice(1) }
    return { type: '', prefix: ' ', content: line.slice(1) }
  })
})

async function viewDiff(patchId: string): Promise<void> {
  diffModal.open = true
  diffModal.loading = true
  diffModal.patch = null
  diffModal.showPrompt = false
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

// ── Apply ──────────────────────────────────────────────────────────────────────
async function applyPatch(patchId: string): Promise<void> {
  try {
    await patchesApi.applyPatch(jobId, patchId, {})
    const idx = patches.value.findIndex((p) => p.patch_id === patchId)
    if (idx !== -1) patches.value[idx] = { ...patches.value[idx], status: 'applied' }
    if (diffModal.patch?.patch_id === patchId) diffModal.patch = { ...diffModal.patch, status: 'applied' }
    _patchesCache.delete(jobId)
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

// ── Revert ─────────────────────────────────────────────────────────────────────
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
    _patchesCache.delete(jobId)
    uiStore.notify({ type: 'success', title: 'Patch reverted', duration: 3000 })
    revertModal.open = false
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Failed to revert patch', message: String(err), duration: 5000 })
  }
}

// ── Export ─────────────────────────────────────────────────────────────────────
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

// ── Data loading ───────────────────────────────────────────────────────────────
async function reload(force = false): Promise<void> {
  if (!force && _patchesCache.has(jobId)) {
    patches.value = _patchesCache.get(jobId)!
    return
  }
  const inflight = _patchesInFlight.get(jobId)
  if (inflight) {
    await inflight
    patches.value = _patchesCache.get(jobId) ?? []
    return
  }
  isLoading.value = true
  loadError.value = null
  const promise = patchesApi.listPatches(jobId, { page_size: 200 })
    .then(({ data }) => {
      patches.value = data.data
      _patchesCache.set(jobId, data.data)
    })
    .catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      loadError.value = msg
      uiStore.notify({ type: 'error', title: 'Failed to load patches', message: msg, duration: 6000 })
    })
    .finally(() => {
      isLoading.value = false
      _patchesInFlight.delete(jobId)
    })
  _patchesInFlight.set(jobId, promise)
  await promise
}

async function loadJob(): Promise<void> {
  try {
    const { data } = await analyzeApi.getJob(jobId)
    job.value = data
  } catch {
    // silent
  }
}

async function loadPlanTasks(): Promise<void> {
  isLoadingTasks.value = true
  try {
    const { data } = await planApi.listTasks(jobId, { automated: true, page_size: 100 })
    planTasks.value = data.data
  } catch {
    // silent — UI still works, just no tasks shown
  } finally {
    isLoadingTasks.value = false
  }
}

// ── Push to repo ───────────────────────────────────────────────────────────────
const pushModal = reactive({
  open: false,
  branchName: `fix/alm-${jobId.slice(0, 8)}`,
  providerId: '',
  token: '',
  createPr: true,
  scope: 'all' as 'all' | 'applied',
  loading: false,
  result: null as VCSPushResult | null,
  error: null as string | null,
})

const appliedPatchCount = computed(() => patches.value.filter((p) => p.status === 'applied').length)

async function openPushModal(): Promise<void> {
  pushModal.branchName = `fix/alm-${jobId.slice(0, 8)}`
  pushModal.providerId = ''
  pushModal.token = ''
  pushModal.createPr = true
  pushModal.scope = 'all'
  pushModal.result = null
  pushModal.error = null
  pushModal.open = true
  try {
    const { data } = await vcsApi.listProviders()
    vcsProviders.value = data
  } catch {
    // silent
  }
}

async function confirmPush(): Promise<void> {
  pushModal.loading = true
  pushModal.error = null
  try {
    const patchIds = pushModal.scope === 'applied'
      ? patches.value.filter((p) => p.status === 'applied').map((p) => p.patch_id)
      : patches.value.map((p) => p.patch_id)
    const { data } = await patchesApi.pushToRepo(jobId, {
      branch_name: pushModal.branchName,
      provider_id: pushModal.providerId || null,
      token: pushModal.token || null,
      create_pr: pushModal.createPr,
      patch_ids: patchIds.length > 0 ? patchIds : null,
    })
    pushModal.result = data
    if (data.pr_url) uiStore.notify({ type: 'success', title: 'Pushed and PR created', message: data.message, duration: 6000 })
    else uiStore.notify({ type: 'success', title: 'Pushed to repo', message: data.message, duration: 5000 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    pushModal.error = msg
    uiStore.notify({ type: 'error', title: 'Push failed', message: msg, duration: 6000 })
  } finally {
    pushModal.loading = false
  }
}

onMounted(async () => {
  await Promise.all([reload(), loadJob()])
  // Load plan tasks always (needed for "Generate More" section when patches exist)
  void loadPlanTasks()
})
</script>
