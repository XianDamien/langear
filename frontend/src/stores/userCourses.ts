import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchMyCourseLessons, updateMyCourseLessons } from '@/services/api/decks'
import { normalizeLessonIds } from '@/utils/deckSelection'

export const useUserCoursesStore = defineStore('userCourses', () => {
  const selectedLessonIds = ref<number[]>([])
  const loading = ref(false)
  const saving = ref(false)

  const selectedLessonIdSet = computed(() => new Set(selectedLessonIds.value))

  async function load() {
    loading.value = true
    try {
      const { data } = await fetchMyCourseLessons()
      const normalized = normalizeLessonIds(data.lesson_ids)
      selectedLessonIds.value = normalized
      return normalized
    } finally {
      loading.value = false
    }
  }

  async function replaceLessons(lessonIds: number[]) {
    saving.value = true
    try {
      const normalized = normalizeLessonIds(lessonIds)
      const { data } = await updateMyCourseLessons(normalized)
      const updatedLessonIds = normalizeLessonIds(data.lesson_ids)
      selectedLessonIds.value = updatedLessonIds
      return updatedLessonIds
    } finally {
      saving.value = false
    }
  }

  async function addLessons(lessonIds: number[]) {
    return replaceLessons([...selectedLessonIds.value, ...lessonIds])
  }

  async function removeLessons(lessonIds: number[]) {
    const lessonIdSet = new Set(lessonIds)
    return replaceLessons(
      selectedLessonIds.value.filter((lessonId) => !lessonIdSet.has(lessonId)),
    )
  }

  return {
    selectedLessonIds,
    selectedLessonIdSet,
    loading,
    saving,
    load,
    replaceLessons,
    addLessons,
    removeLessons,
  }
})
