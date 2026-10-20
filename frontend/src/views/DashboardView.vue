<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useDashboardStore } from '@/stores/dashboard'
import { useDecksStore } from '@/stores/decks'
import StatsCards from '@/components/dashboard/StatsCards.vue'
import ActivityChart from '@/components/dashboard/ActivityChart.vue'
import RecentDecks from '@/components/dashboard/RecentDecks.vue'
import Leaderboard from '@/components/dashboard/Leaderboard.vue'

const router = useRouter()
const dashboardStore = useDashboardStore()
const decksStore = useDecksStore()
const { stats, weeklyTrend, leaderboard, loading, error } = storeToRefs(dashboardStore)
const { myCourses } = storeToRefs(decksStore)
const coursesLoading = ref(true)
const coursesError = ref<string | null>(null)

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
          :decks="myCourses"
          :loading="coursesLoading"
          :error="coursesError"
          @play="handlePlayDeck"
          @retry="loadCourses"
        />
        <Leaderboard :entries="leaderboard" />
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
