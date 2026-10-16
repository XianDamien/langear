import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { flushPromises } from '@vue/test-utils'
import { mountWithApp } from '../../helpers/mountWithApp'
import MyCoursesView from '@/views/MyCoursesView.vue'
import LibraryView from '@/views/LibraryView.vue'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import appRouter from '@/router'
import { setAccessToken } from '@/services/authToken'

vi.mock('@/components/library/PersonalCardsPanel.vue', () => ({ default: { template: '<div />' } }))

const lesson = {
  id: '18', name: 'Lesson one', description: '', type: 'lesson',
  totalCards: 4, newCards: 4, reviewCards: 0, completedCards: 0,
}

async function mountCoursePage(component: typeof MyCoursesView | typeof LibraryView, path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/my-courses', component: MyCoursesView },
      { path: '/library', component: LibraryView },
      { path: '/study/:lessonId', component: { template: '<div />' } },
      { path: '/settings', name: 'Settings', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  const wrapper = mountWithApp(component, {
    pinia: { initialState: { deck: { deckTree: [lesson] }, userCourses: { selectedLessonIds: [18] } } },
    global: { plugins: [router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('personal course settings navigation', () => {
  it('opens the existing settings page with the selected course', async () => {
    const { wrapper, router } = await mountCoursePage(MyCoursesView, '/my-courses')
    await wrapper.get('button[aria-label="Lesson one 设置"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/settings?deck_id=18')
    wrapper.unmount()
  })

  it('opens a leaf deck from library while keeping settings in my courses', async () => {
    const { wrapper, router } = await mountCoursePage(LibraryView, '/library')
    expect(wrapper.find('button[aria-label="Lesson one 设置"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some(button => /^(复习|开始)$/.test(button.text()))).toBe(false)
    await wrapper.getComponent(DeckTreeItem).get('.truncate').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/study/18')
    wrapper.unmount()
  })

  it('redirects old deck settings links to the existing page', async () => {
    setAccessToken('test-session-token')
    await appRouter.push('/decks/18/settings')
    expect(appRouter.currentRoute.value.fullPath).toBe('/settings?deck_id=18')
  })
})
