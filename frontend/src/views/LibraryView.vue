<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import LessonPickerModal from '@/components/library/LessonPickerModal.vue'
import { useLessonPicker } from '@/composables/useLessonPicker'
import { useDeckStore } from '@/stores/deck'
import { useUserCoursesStore } from '@/stores/userCourses'
import { collectLessonIds, findDeckById, getNodeSelectionStatus } from '@/utils/deckSelection'

const router = useRouter()
const deckStore = useDeckStore()
const userCoursesStore = useUserCoursesStore()
const { deckTree, loading } = storeToRefs(deckStore)
const {
  selectedLessonIds,
  selectedLessonIdSet,
  loading: coursesLoading,
  saving,
} = storeToRefs(userCoursesStore)

const pageLoading = computed(() => loading.value || coursesLoading.value)
const {
  pickerDeck,
  pickerLessons,
  pickerSelectedLessonIds,
  openPicker,
  closePicker,
  savePickerSelection,
} = useLessonPicker({
  deckTree,
  selectedLessonIds,
  replaceLessons: userCoursesStore.replaceLessons,
})

onMounted(() => {
  if (!deckTree.value.length) {
    deckStore.load()
  }
  userCoursesStore.load()
})

function handleSelectLesson(lessonId: string) {
  deckStore.selectLesson(lessonId)
  router.push(`/study/${lessonId}`)
}

async function handleToggleDeckSelection(deckId: string) {
  const deck = findDeckById(deckTree.value, deckId)
  if (!deck) return

  if (deck.type === 'lesson') {
    const lessonId = Number(deck.id)
    if (selectedLessonIdSet.value.has(lessonId)) {
      await userCoursesStore.removeLessons([lessonId])
      ElMessage.success('已从我的课程移除该 lesson')
    } else {
      await userCoursesStore.addLessons([lessonId])
      ElMessage.success('已加入我的课程')
    }
    return
  }

  const status = getNodeSelectionStatus(deck, selectedLessonIdSet.value)
  if (status === 'full') {
    await userCoursesStore.removeLessons(collectLessonIds(deck))
    ElMessage.success('已移除该范围下的所有 lessons')
    return
  }

  openPicker(deckId)
}

async function handlePickerSave(lessonIds: number[]) {
  await savePickerSelection(lessonIds)
  ElMessage.success('我的课程已更新')
}
</script>

<template>
  <div class="animate-fadeIn">
    <h2 class="mb-6 text-3xl font-bold uppercase text-brand-accent">
      题库
    </h2>

    <div
      v-if="pageLoading"
      class="py-20 text-center text-slate-500"
    >
      加载中...
    </div>

    <div
      v-else
      class="space-y-2"
    >
      <DeckTreeItem
        v-for="deck in deckTree"
        :key="deck.id"
        :deck="deck"
        mode="library"
        :selected-lesson-id-set="selectedLessonIdSet"
        :depth="0"
        @select-lesson="handleSelectLesson"
        @toggle-deck-selection="handleToggleDeckSelection"
      />
    </div>

    <LessonPickerModal
      :open="!!pickerDeck"
      :title="pickerDeck ? `${pickerDeck.name} · 选择 lessons` : ''"
      :lessons="pickerLessons"
      :selected-lesson-ids="pickerSelectedLessonIds"
      :saving="saving"
      @close="closePicker"
      @save="handlePickerSave"
    />
  </div>
</template>
