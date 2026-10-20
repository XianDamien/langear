import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchDashboard, type DashboardLeaderboardEntry, type DashboardResponse } from '@/services/content'

export const useDashboardStore = defineStore('dashboard', () => {
  const stats = ref<DashboardResponse['stats'] | null>(null)
  const weeklyTrend = ref<{ name: string; sentences: number }[]>([])
  const heatmap = ref<{ date: string; count: number }[]>([])
  const leaderboard = ref<DashboardLeaderboardEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      const data = await fetchDashboard()
      stats.value = data.stats
      weeklyTrend.value = data.weeklyTrend
      heatmap.value = data.heatmap
      leaderboard.value = data.leaderboard || []
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载首页数据失败'
      stats.value = null
      weeklyTrend.value = []
      heatmap.value = []
      leaderboard.value = []
    } finally {
      loading.value = false
    }
  }

  return { stats, weeklyTrend, heatmap, leaderboard, loading, error, load }
})
