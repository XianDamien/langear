<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useDashboardStore } from '@/stores/dashboard'
import { useDecksStore } from '@/stores/decks'
import type { DeckView } from '@/stores/decks'
import StatsCards from '@/components/dashboard/StatsCards.vue'
import ActivityChart from '@/components/dashboard/ActivityChart.vue'
import RecentDecks from '@/components/dashboard/RecentDecks.vue'
import Leaderboard from '@/components/dashboard/Leaderboard.vue'
import ReviewLessonPicker, { type ReviewLessonOption } from '@/components/review/ReviewLessonPicker.vue'

const router = useRouter()
const dashboardStore = useDashboardStore()
const decksStore = useDecksStore()
const { stats, weeklyTrend, leaderboard, loading, error } = storeToRefs(dashboardStore)
const { myCourses, myCoursesTree } = storeToRefs(decksStore)
const coursesLoading = ref(true)
const coursesError = ref<string | null>(null)
const showReviewPicker = ref(false)

function collectLeafDecks(nodes: DeckView[]): DeckView[] {
  return nodes.flatMap(node =>
    node.children.length ? collectLeafDecks(node.children) : [node],
  )
}

const reviewLessons = computed<ReviewLessonOption[]>(() => {
  const rowsById = new Map(decksStore.rows.map(row => [row.id, row]))
  return collectLeafDecks(myCoursesTree.value)
    .map(deck => {
      const row = rowsById.get(deck.id)
      const parents = (row?.path ?? [])
        .slice(0, -1)
        .map(id => rowsById.get(id)?.name)
        .filter((name): name is string => Boolean(name))
      return {
        id: deck.id,
        name: deck.name,
        path: parents.length ? parents.join(' / ') : '我的课程',
        due: row?.stats.review_cards ?? 0,
      }
    })
    .filter(lesson => lesson.due > 0)
    .sort((left, right) =>
      right.due - left.due || left.name.localeCompare(right.name, 'zh-CN'),
    )
})

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = null
  try {
    await decksStore.load()
  } catch {
    coursesError.value = '课程加载失败，请重试'
  } finally {
    coursesLoading.value = false
  }
}

onMounted(() => {
  void dashboardStore.load()
  void loadCourses()
})

function handlePlayDeck(deckId: string) {
  if (coursesLoading.value || coursesError.value) return
  void router.push({ name: 'DeckReview', params: { deckId } })
}

function handleReviewAll() {
  showReviewPicker.value = true
}

function startLessonReview(deckId: string) {
  showReviewPicker.value = false
  void router.push({ name: 'DeckReview', params: { deckId } })
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
      <StatsCards
        :stats="stats"
        @review-all="handleReviewAll"
      />
      <ActivityChart :data="weeklyTrend" />
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <RecentDecks
          :decks="myCourses"
          :loading="coursesLoading"
          :error="coursesError"
          @play="handlePlayDeck"
          @retry="loadCourses"
        />
        <Leaderboard :entries="leaderboard" />
      </div>
      <ReviewLessonPicker
        :open="showReviewPicker"
        :lessons="reviewLessons"
        :loading="coursesLoading"
        :error="coursesError"
        @close="showReviewPicker = false"
        @select="startLessonReview"
        @retry="loadCourses"
      />
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
