<template>
  <div
    class="rounded-xl border overflow-hidden transition-shadow"
    :style="{
      background: 'var(--color-card)',
      borderColor: severityBorderColor,
      borderLeftWidth: '3px',
    }"
  >
    <!-- Header row -->
    <div class="flex items-start justify-between px-4 pt-4 pb-3 gap-3">
      <!-- Left: severity + type -->
      <div class="flex items-start gap-3 min-w-0">
        <SmellBadge :severity="smell.severity" :show-dot="true" class="flex-shrink-0 mt-0.5" />
        <div class="min-w-0">
          <p class="text-sm font-semibold" style="color: var(--color-text)">
            {{ formatSmellType(smell.smell_type) }}
          </p>
          <p class="text-xs mt-0.5 font-mono truncate" style="color: var(--color-text-muted)">
            {{ smell.smell_type }}
          </p>
        </div>
      </div>
      <!-- Right: confidence + dismiss -->
      <div class="flex items-center gap-3 flex-shrink-0">
        <div class="text-right">
          <p class="text-xs" style="color: var(--color-text-muted)">Confidence</p>
          <p
            class="text-sm font-bold"
            :style="{ color: confidenceColor }"
          >
            {{ Math.round(smell.confidence * 100) }}%
          </p>
        </div>
        <div v-if="smell.dismissed" class="text-xs px-2 py-0.5 rounded" style="background: var(--color-elevated); color: var(--color-text-muted)">
          Dismissed
        </div>
        <button
          v-else
          @click="showDismissModal = true"
          class="text-xs px-2 py-1 rounded-md border transition-colors"
          :style="{
            borderColor: 'var(--color-border)',
            color: 'var(--color-text-muted)',
            background: 'transparent',
          }"
        >
          Dismiss
        </button>
      </div>
    </div>

    <!-- Description -->
    <div class="px-4 pb-3">
      <p class="text-sm leading-relaxed" style="color: var(--color-text-secondary)">
        {{ smell.description }}
      </p>
    </div>

    <!-- Affected nodes chips -->
    <div v-if="smell.affected_nodes.length" class="px-4 pb-3">
      <p class="text-xs font-medium mb-1.5" style="color: var(--color-text-muted)">Affected nodes</p>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="node in smell.affected_nodes"
          :key="node.node_id"
          @click="$emit('nodeClick', node.node_id)"
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono transition-colors"
          :style="{
            background: 'var(--color-elevated)',
            color: 'var(--color-primary)',
            border: '1px solid var(--color-border)',
          }"
          :title="node.qualified_name"
        >
          <span
            class="w-1.5 h-1.5 rounded-full flex-shrink-0"
            :style="{ background: nodeTypeColor(node.node_type) }"
          />
          {{ shortName(node.qualified_name) }}
        </button>
      </div>
    </div>

    <!-- Expandable: LLM rationale + evidence -->
    <div
      class="border-t"
      :style="{ borderColor: 'var(--color-border)' }"
    >
      <button
        @click="expanded = !expanded"
        class="flex items-center justify-between w-full px-4 py-2.5 text-xs transition-colors"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        <span>{{ expanded ? 'Hide details' : 'Show details' }}</span>
        <svg
          class="w-3.5 h-3.5 transition-transform"
          :class="expanded ? 'rotate-180' : ''"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      <div v-if="expanded" class="px-4 pb-4 space-y-3">
        <!-- LLM rationale -->
        <div v-if="smell.llm_rationale">
          <p class="text-xs font-medium mb-1" style="color: var(--color-text-muted)">AI Rationale</p>
          <p
            class="text-xs leading-relaxed p-3 rounded-md italic"
            :style="{
              background: 'var(--color-elevated)',
              color: 'var(--color-text-secondary)',
              borderLeft: '2px solid var(--color-primary)',
            }"
          >
            {{ smell.llm_rationale }}
          </p>
        </div>

        <!-- Evidence table -->
        <div v-if="evidenceEntries.length">
          <p class="text-xs font-medium mb-1" style="color: var(--color-text-muted)">Evidence</p>
          <table class="w-full text-xs">
            <tbody>
              <tr
                v-for="[key, val] in evidenceEntries"
                :key="key"
                class="border-b last:border-0"
                :style="{ borderColor: 'var(--color-border)' }"
              >
                <td class="py-1 pr-3 font-mono" style="color: var(--color-text-muted)">{{ key }}</td>
                <td class="py-1 font-semibold" style="color: var(--color-text)">{{ val }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Dismiss modal -->
    <BaseModal
      :open="showDismissModal"
      title="Dismiss Smell"
      size="sm"
      @close="showDismissModal = false"
    >
      <div class="space-y-3">
        <p class="text-sm" style="color: var(--color-text-secondary)">
          Provide a reason for dismissing this smell. It will be marked as a known/acceptable issue.
        </p>
        <textarea
          v-model="dismissReason"
          rows="3"
          placeholder="e.g. This complexity is intentional and managed by the team."
          class="w-full px-3 py-2 text-sm rounded-md border resize-none focus:outline-none"
          :style="{
            background: 'var(--color-elevated)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text)',
          }"
        />
      </div>
      <template #footer>
        <button
          @click="showDismissModal = false"
          class="px-4 py-2 text-sm rounded-md border transition-colors"
          :style="{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }"
        >
          Cancel
        </button>
        <button
          @click="confirmDismiss"
          :disabled="!dismissReason.trim()"
          class="px-4 py-2 text-sm rounded-md transition-colors disabled:opacity-50"
          style="background: var(--color-primary); color: white"
        >
          Dismiss Smell
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import SmellBadge from './SmellBadge.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import type { NodeType, SmellDetail, SmellType } from '@/types'

const props = defineProps<{ smell: SmellDetail; expanded?: boolean }>()
const emit = defineEmits<{
  dismiss: [smellId: string, reason: string]
  nodeClick: [nodeId: string]
}>()

const expanded = ref(props.expanded ?? false)
const showDismissModal = ref(false)
const dismissReason = ref('')

// ── Severity left-border color ───────────────────────────────────────────────
const SEV_BORDER: Record<string, string> = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#f59e0b',
  low:      '#22c55e',
}
const severityBorderColor = computed(() => SEV_BORDER[props.smell.severity] ?? '#2d3148')
const confidenceColor = computed(() => {
  const c = props.smell.confidence
  if (c >= 0.85) return 'var(--color-success)'
  if (c >= 0.6)  return 'var(--color-warning)'
  return 'var(--color-text-muted)'
})

// ── Smell type → readable label ──────────────────────────────────────────────
function formatSmellType(type: SmellType): string {
  return type
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

// ── Node type colors ─────────────────────────────────────────────────────────
const NODE_COLORS: Partial<Record<NodeType, string>> = {
  CLASS:    '#6366f1',
  METHOD:   '#22c55e',
  FUNCTION: '#22c55e',
  FILE:     '#a855f7',
  MODULE:   '#a855f7',
}
function nodeTypeColor(type: NodeType): string {
  return NODE_COLORS[type] ?? '#6b7280'
}

function shortName(qualifiedName: string): string {
  return qualifiedName.split('.').pop() ?? qualifiedName
}

// ── Evidence entries ─────────────────────────────────────────────────────────
const evidenceEntries = computed(() =>
  Object.entries(props.smell.evidence)
    .filter(([, v]) => v !== null && v !== undefined)
    .slice(0, 8),
)

// ── Dismiss ──────────────────────────────────────────────────────────────────
function confirmDismiss(): void {
  if (!dismissReason.value.trim()) return
  emit('dismiss', props.smell.smell_id, dismissReason.value)
  showDismissModal.value = false
  dismissReason.value = ''
}
</script>
