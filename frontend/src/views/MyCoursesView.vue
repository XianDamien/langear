<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import { useDeckStore } from '@/stores/deck'
import { useUserCoursesStore } from '@/stores/userCourses'
import {
  buildSelectedTree,
  findDeckById,
  findFirstSelectedLessonId,
} from '@/utils/deckSelection'

const router = useRouter()
const deckStore = useDeckStore()
const userCoursesStore = useUserCoursesStore()
const { deckTree, loading } = storeToRefs(deckStore)
const {
  selectedLessonIdSet,
  loading: coursesLoading,
} = storeToRefs(userCoursesStore)

const myCourseTree = computed(() => buildSelectedTree(deckTree.value, selectedLessonIdSet.value))
const pageLoading = computed(() => loading.value || coursesLoading.value)

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

function handlePlayDeck(deckId: string) {
  const deck = findDeckById(myCourseTree.value, deckId)
  if (!deck) return

  const lessonId = findFirstSelectedLessonId(deck, selectedLessonIdSet.value)
  if (lessonId) {
    deckStore.selectLesson(lessonId)
    router.push(`/study/${lessonId}`)
  }
}
</script>

<template>
  <div class="animate-fadeIn">
    <h2 class="mb-6 text-3xl font-bold uppercase text-brand-accent">
      我的课程
    </h2>

    <div
      v-if="pageLoading"
      class="py-20 text-center text-slate-500"
    >
      加载中...
    </div>

    <div
      v-else-if="!myCourseTree.length"
      class="border-2 border-dashed border-slate-200 p-8 text-center"
    >
      <p class="mb-4 text-slate-500">
        你还没有加入任何课程。去题库挑选一些 lesson 吧。
      </p>
      <RetroButton
        variant="primary"
        size="sm"
        @click="router.push('/library')"
      >
        去题库添加课程
      </RetroButton>
    </div>

    <div
      v-else
      class="space-y-2"
    >
      <DeckTreeItem
        v-for="deck in myCourseTree"
        :key="deck.id"
        :deck="deck"
        mode="my-courses"
        :selected-lesson-id-set="selectedLessonIdSet"
        :depth="0"
        @select-lesson="handleSelectLesson"
        @play-deck="handlePlayDeck"
      />
    </div>
  </div>
</template>
