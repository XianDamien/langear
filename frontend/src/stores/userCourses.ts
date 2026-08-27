import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchUserDecks, updateUserDeckSelection } from '@/services/api/decks'
import type { UserDeckSummary } from '@/types/api'
import type { Deck } from '@/types/domain'
import {
  compressLessonSelectionToOriginDeckIds,
  expandUserDecksToLessonIds,
  normalizeLessonIds,
} from '@/utils/deckSelection'

export const useUserCoursesStore = defineStore('userCourses', () => {
  const userDecks = ref<UserDeckSummary[]>([])
  const selectedLessonIds = ref<number[]>([])
  const loading = ref(false)
  const saving = ref(false)

  const selectedLessonIdSet = computed(() => new Set(selectedLessonIds.value))

  function syncSelectedLessons(deckTree: Deck[] = []) {
    selectedLessonIds.value = deckTree.length
      ? expandUserDecksToLessonIds(deckTree, userDecks.value)
      : []
    return selectedLessonIds.value
  }

  async function load(deckTree: Deck[] = []) {
    loading.value = true
    try {
      const { data } = await fetchUserDecks()
      userDecks.value = data.user_decks
      return syncSelectedLessons(deckTree)
    } finally {
      loading.value = false
    }
  }

  async function replaceLessons(deckTree: Deck[], lessonIds: number[]) {
    saving.value = true
    try {
      const normalizedLessonIds = normalizeLessonIds(lessonIds)
      const originDeckIds = compressLessonSelectionToOriginDeckIds(
        deckTree,
        normalizedLessonIds,
      )
      const { data } = await updateUserDeckSelection(originDeckIds)
      userDecks.value = data.user_decks
      selectedLessonIds.value = expandUserDecksToLessonIds(deckTree, data.user_decks)
      return selectedLessonIds.value
    } finally {
      saving.value = false
    }
  }

  async function addLessons(deckTree: Deck[], lessonIds: number[]) {
    return replaceLessons(deckTree, [...selectedLessonIds.value, ...lessonIds])
  }

  async function removeLessons(deckTree: Deck[], lessonIds: number[]) {
    const lessonIdSet = new Set(lessonIds)
    return replaceLessons(
      deckTree,
      selectedLessonIds.value.filter((lessonId) => !lessonIdSet.has(lessonId)),
    )
  }

  return {
    userDecks,
    selectedLessonIds,
    selectedLessonIdSet,
    loading,
    saving,
    load,
    replaceLessons,
    addLessons,
    removeLessons,
    syncSelectedLessons,
  }
})
