<template>
  <div class="relative">
    <!-- Vertical connector line -->
    <div
      v-if="orderedTasks.length > 1"
      class="absolute top-3.5 bottom-3.5 left-[27px] w-px pointer-events-none"
      style="background: var(--color-border)"
    />

    <div class="space-y-3 relative">
      <PlanTaskCard
        v-for="(task, idx) in orderedTasks"
        :key="task.task_id"
        :task="task"
        :all-tasks="tasks"
        :order="idx + 1"
        :readonly="readonly"
        @approve="$emit('approve', $event)"
        @reject="$emit('reject', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import PlanTaskCard from './PlanTask.vue'
import type { PlanTask } from '@/types'

const props = defineProps<{
  tasks: PlanTask[]
  priorityOrder?: string[]
  readonly?: boolean
}>()

defineEmits<{
  approve: [taskId: string]
  reject: [taskId: string]
}>()

const orderedTasks = computed(() => {
  if (!props.priorityOrder?.length) return props.tasks
  const orderMap = new Map(props.priorityOrder.map((id, i) => [id, i]))
  return [...props.tasks].sort(
    (a, b) => (orderMap.get(a.task_id) ?? 9999) - (orderMap.get(b.task_id) ?? 9999),
  )
})
</script>
