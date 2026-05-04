<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import RetroCard from '@/components/ui/RetroCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import type { LessonSelectionItem } from '@/utils/deckSelection'

const props = defineProps<{
  open: boolean
  title: string
  lessons: LessonSelectionItem[]
  selectedLessonIds: number[]
  saving?: boolean
}>()

const emit = defineEmits<{
  close: []
  save: [lessonIds: number[]]
}>()

const draftLessonIds = ref<number[]>([])

watch(
  () => [props.open, props.selectedLessonIds, props.lessons] as const,
  () => {
    if (!props.open) return
    const visibleLessonIds = new Set(props.lessons.map((lesson) => lesson.lessonId))
    draftLessonIds.value = props.selectedLessonIds.filter((lessonId) => visibleLessonIds.has(lessonId))
  },
  { immediate: true },
)

const draftLessonIdSet = computed(() => new Set(draftLessonIds.value))
const allSelected = computed(
  () => props.lessons.length > 0 && props.lessons.every((lesson) => draftLessonIdSet.value.has(lesson.lessonId)),
)

function toggleLesson(lessonId: number) {
  if (draftLessonIdSet.value.has(lessonId)) {
    draftLessonIds.value = draftLessonIds.value.filter((candidate) => candidate !== lessonId)
    return
  }

  draftLessonIds.value = [...draftLessonIds.value, lessonId].sort((left, right) => left - right)
}

function toggleAll() {
  draftLessonIds.value = allSelected.value ? [] : props.lessons.map((lesson) => lesson.lessonId)
}

function save() {
  emit('save', draftLessonIds.value)
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
  >
    <RetroCard class="w-full max-w-3xl bg-white border-brand-accent">
      <div class="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 class="text-xl font-bold text-brand-accent">
            {{ title }}
          </h3>
        </div>
        <RetroButton
          variant="secondary"
          size="sm"
          @click="toggleAll"
        >
          {{ allSelected ? '清空' : '全选' }}
        </RetroButton>
      </div>

      <div class="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
        <label
          v-for="lesson in lessons"
          :key="lesson.lessonId"
          class="flex cursor-pointer items-start gap-3 border border-slate-200 bg-slate-50 p-3 transition-colors hover:border-brand-accent hover:bg-red-50/40"
        >
          <input
            :checked="draftLessonIdSet.has(lesson.lessonId)"
            type="checkbox"
            class="mt-1 h-4 w-4 accent-red-500"
            @change="toggleLesson(lesson.lessonId)"
          >
          <div class="min-w-0">
            <div class="font-bold text-slate-900">
              {{ lesson.lessonId }} · {{ lesson.lessonTitle }}
            </div>
            <div class="text-xs text-slate-500">
              {{ lesson.sourceTitle }} / {{ lesson.unitTitle }}
            </div>
          </div>
        </label>
      </div>

      <div class="mt-4 flex justify-end gap-2">
        <RetroButton
          variant="secondary"
          size="sm"
          @click="emit('close')"
        >
          关闭
        </RetroButton>
        <RetroButton
          variant="primary"
          size="sm"
          :disabled="saving"
          @click="save"
        >
          确定
        </RetroButton>
      </div>
    </RetroCard>
  </div>
</template>
