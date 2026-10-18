<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useDashboardStore } from '@/stores/dashboard'
import { useDeckStore } from '@/stores/deck'
import { useUserCoursesStore } from '@/stores/userCourses'
import { legacyReviewLocation } from '@/services/reviewNavigation'
import { reviewError } from '@/services/review'
import { buildSelectedTree, findDeckById, findFirstSelectedLessonId } from '@/utils/deckSelection'
import StatsCards from '@/components/dashboard/StatsCards.vue'
import ActivityChart from '@/components/dashboard/ActivityChart.vue'
import RecentDecks from '@/components/dashboard/RecentDecks.vue'
import Leaderboard from '@/components/dashboard/Leaderboard.vue'

const router = useRouter()
const dashboardStore = useDashboardStore()
const deckStore = useDeckStore()
const userCoursesStore = useUserCoursesStore()
const { stats, weeklyTrend, loading, error } = storeToRefs(dashboardStore)
const { deckTree } = storeToRefs(deckStore)
const { selectedLessonIdSet } = storeToRefs(userCoursesStore)
const myCourseTree = computed(() => buildSelectedTree(deckTree.value, selectedLessonIdSet.value))
const coursesLoading = ref(true)
const coursesError = ref<string | null>(null)

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = null
  try {
    await Promise.all([deckStore.load(), userCoursesStore.load()])
  } catch {
    coursesError.value = '课程加载失败，请重试'
  } finally {
    coursesLoading.value = false
  }
}

onMounted(() => {
  dashboardStore.load()
  loadCourses()
})

async function handlePlayDeck(deckId: string) {
  if (coursesLoading.value || coursesError.value) return
  const deck = findDeckById(myCourseTree.value, deckId)
  if (!deck) return
  const lessonId = findFirstSelectedLessonId(deck, selectedLessonIdSet.value)
  if (lessonId) {
    deckStore.selectLesson(lessonId)
    try { await router.push(await legacyReviewLocation(lessonId)) }
    catch (error) { coursesError.value = reviewError(error) }
  }
}
</script>

<template>
  <div class="space-y-6 animate-fadeIn">
    <div
      v-if="loading"
      class="text-center text-slate-500 py-20"
    >
      加载中...
    </div>
    <div
      v-else-if="error"
      class="rounded border border-red-200 bg-red-50 p-6 text-center text-red-700"
    >
      首页数据加载失败：{{ error }}
    </div>
    <template v-else-if="stats">
      <StatsCards :stats="stats" />
      <ActivityChart :data="weeklyTrend" />
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <RecentDecks
          :decks="myCourseTree"
          :loading="coursesLoading"
          :error="coursesError"
          @play="handlePlayDeck"
          @retry="loadCourses"
        />
        <Leaderboard />
      </div>
    </template>
    <div
      v-else-if="coursesLoading"
      class="text-center text-slate-500 py-20"
    >
      加载中...
    </div>
    <div
      v-else
      class="rounded border border-slate-200 bg-brand-panel/90 p-6 text-center text-slate-600"
    >
      暂无首页数据
    </div>
  </div>
</template>
