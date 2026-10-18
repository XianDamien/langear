import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'
import RecentDecks from '@/components/dashboard/RecentDecks.vue'
import { useUserCoursesStore } from '@/stores/userCourses'
import { useDeckStore } from '@/stores/deck'
import type { Deck } from '@/types/domain'
import { mountWithApp } from '../../helpers/mountWithApp'

const { fetchDeckTree, fetchMyCourseLessons, updateMyCourseLessons } = vi.hoisted(() => ({
  fetchDeckTree: vi.fn(), fetchMyCourseLessons: vi.fn(), updateMyCourseLessons: vi.fn(),
}))
vi.mock('@/services/api/decks', () => ({ fetchDeckTree, fetchMyCourseLessons, updateMyCourseLessons }))
vi.mock('@/services/reviewNavigation', () => ({ legacyReviewLocation: vi.fn(async (id: string) => ({ name: 'DeckReview', params: { deckId: `core-${id}` } })) }))
vi.mock('@/components/dashboard/ActivityChart.vue', () => ({ default: { template: '<div />' } }))

const lesson = (id: string, newCards: number): Deck => ({
  id, name: 'Lesson ' + id, type: 'lesson', description: '',
  totalCards: newCards + 2, newCards, reviewCards: 2, completedCards: 0,
})
const tree: Deck[] = [
  { ...lesson('1', 99), name: '已选教材', type: 'source', children: [lesson('11', 80), lesson('12', 3)] },
  { ...lesson('2', 50), name: '未选教材', type: 'source', children: [lesson('21', 50)] },
]

async function mountDashboard() {
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
      stubActions: false,
      initialState: { dashboard: { stats: {} } },
    },
    global: { plugins: [router], stubs: { StatsCards: true, Leaderboard: true } },
  })
  return { wrapper, router }
}

vi.mock('@/services/api/dashboard', () => ({ fetchDashboard: vi.fn().mockResolvedValue({
  data: { stats: {}, weeklyTrend: [], heatmap: [] },
}) }))

describe('首页学习中与我的课程一致', () => {
  beforeEach(() => {
    fetchDeckTree.mockResolvedValue({ data: { tree } })
    fetchMyCourseLessons.mockResolvedValue({ data: { lesson_ids: [12] } })
  })

  it('只展示已选牌组，并只统计已选课时', async () => {
    const { wrapper } = await mountDashboard()
    await flushPromises()
    const recent = wrapper.getComponent(RecentDecks)
    expect(recent.text()).toContain('已选教材')
    expect(recent.text()).not.toContain('未选教材')
    expect(recent.props('decks')).toMatchObject([{ id: '1', newCards: 3, reviewCards: 2, totalCards: 5 }])
    expect(fetchMyCourseLessons).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('从已选课时开始学习，跳过同牌组中未加入的第一课', async () => {
    const { wrapper, router } = await mountDashboard()
    await flushPromises()
    await wrapper.getComponent(RecentDecks).get('.group').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/review/core-12')
    expect(useDeckStore().selectedLessonId).toBe('12')
    wrapper.unmount()
  })

  it('未加入课程时显示添加入口，并同步移除后的空状态', async () => {
    const { wrapper } = await mountDashboard()
    await flushPromises()
    updateMyCourseLessons.mockResolvedValue({ data: { lesson_ids: [] } })
    await useUserCoursesStore().removeLessons([12])
    await flushPromises()
    const recent = wrapper.getComponent(RecentDecks)
    expect(recent.findAll('.group')).toHaveLength(0)
    expect(recent.text()).toContain('还没有加入课程')
    expect(recent.get('a').attributes('href')).toBe('/library')
    wrapper.unmount()
  })

  it('等待已选课程加载完成后再显示牌组', async () => {
    let resolve!: (value: { data: { lesson_ids: number[] } }) => void
    fetchMyCourseLessons.mockReturnValueOnce(new Promise(done => { resolve = done }))
    const { wrapper } = await mountDashboard()
    await flushPromises()
    const recent = wrapper.getComponent(RecentDecks)
    expect(recent.get('[role="status"]').text()).toContain('加载中')
    expect(recent.findAll('.group')).toHaveLength(0)
    resolve({ data: { lesson_ids: [12] } })
    await flushPromises()
    expect(recent.findAll('.group')).toHaveLength(1)
    wrapper.unmount()
  })

  it.each(['tree', 'selection'])('%s 请求失败时不显示旧牌组，支持重试', async failed => {
    const fetch = failed === 'tree' ? fetchDeckTree : fetchMyCourseLessons
    fetch.mockRejectedValueOnce(new Error('unavailable'))
    const { wrapper } = await mountDashboard()
    await flushPromises()
    const recent = wrapper.getComponent(RecentDecks)
    expect(recent.get('[role="alert"]').text()).toContain('课程加载失败')
    expect(recent.findAll('.group')).toHaveLength(0)
    await recent.get('button').trigger('click')
    await flushPromises()
    expect(recent.find('[role="alert"]').exists()).toBe(false)
    expect(recent.findAll('.group')).toHaveLength(1)
    wrapper.unmount()
  })
})
