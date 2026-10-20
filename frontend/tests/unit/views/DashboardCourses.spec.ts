import { describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import RecentDecks from '@/components/dashboard/RecentDecks.vue'
import { mountWithApp } from '../../helpers/mountWithApp'

vi.mock('@/components/dashboard/ActivityChart.vue', () => ({ default: { template: '<div />' } }))

const joinedId = '01900000-0000-7000-8000-000000000001'
const otherId = '01900000-0000-7000-8000-000000000002'
const stats = {
  points: 10, reviewsPending: 4, streakDays: 3, dailyGoal: 20,
  dailyDone: 10, todayNew: 4, todayReview: 6, todayDone: 10,
}

function row(id: string, name: string, joined: boolean) {
  return {
    id, name, parent_id: null, kind: 'standard' as const, in_my_courses: joined,
    depth: 0, path: [id],
    stats: { total_cards: 5, selected_cards: 5, new_cards: 2, learning_cards: 1, review_cards: 2, completed_cards: 1, due_cards: 5 },
  }
}

async function mountDashboard(rows = [row(joinedId, '已加入的牌组', true), row(otherId, '未加入的牌组', false)]) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard', component: DashboardView },
      { path: '/review/:deckId', name: 'DeckReview', component: { template: '<div />' } },
      { path: '/library', component: { template: '<div />' } },
    ],
  })
  await router.push('/dashboard')
  const wrapper = mountWithApp(DashboardView, {
    pinia: {
      initialState: {
        dashboard: { stats, weeklyTrend: [], heatmap: [], leaderboard: [], loading: false, error: null },
        decks: { rows, tree: [], cardsByDeck: {}, loading: false, saving: false, error: null },
      },
    },
    global: { plugins: [router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('dashboard courses', () => {
  it('shows only joined core decks and starts their UUID review', async () => {
    const { wrapper, router } = await mountDashboard()
    const recent = wrapper.getComponent(RecentDecks)
    expect(recent.text()).toContain('已加入的牌组')
    expect(recent.text()).not.toContain('未加入的牌组')
    expect(recent.props('decks')).toMatchObject([{ id: joinedId, newCards: 2, reviewCards: 3, totalCards: 5 }])
    await recent.get('.group').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(`/review/${joinedId}`)
    wrapper.unmount()
  })

  it('shows the empty state with a library entry point', async () => {
    const { wrapper } = await mountDashboard([])
    const recent = wrapper.getComponent(RecentDecks)
    expect(recent.findAll('.group')).toHaveLength(0)
    expect(recent.text()).toContain('还没有加入课程')
    expect(recent.get('a').attributes('href')).toBe('/library')
    wrapper.unmount()
  })
})
