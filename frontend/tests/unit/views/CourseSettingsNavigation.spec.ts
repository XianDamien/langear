import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { flushPromises } from '@vue/test-utils'
import { mountWithApp } from '../../helpers/mountWithApp'
import MyCoursesView from '@/views/MyCoursesView.vue'
import LibraryView from '@/views/LibraryView.vue'
import DeckTreeItem from '@/components/library/DeckTreeItem.vue'
import appRouter from '@/router'
import { setAccessToken } from '@/services/authToken'

vi.mock('@/services/reviewNavigation', () => ({ legacyReviewLocation: vi.fn(async (id: string) => ({ name: 'DeckReview', params: { deckId: `core-${id}` } })) }))
vi.mock('@/components/library/LibraryContentEditor.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/services/libraryContent', async importOriginal => ({
  ...await importOriginal<typeof import('@/services/libraryContent')>(),
  libraryEditorEnabled: true,
}))

const coreDeckId = '01900000-0000-7000-8000-000000000001'

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
      { path: '/review/:deckId', name: 'DeckReview', component: { template: '<div />' } },
      { path: '/settings', name: 'Settings', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  const wrapper = mountWithApp(component, {
    pinia: { initialState: { deck: { deckTree: [lesson] }, userCourses: { selectedLessonIds: [18] }, contentDecks: { decks: [{ id: coreDeckId, name: '自建词汇', kind: 'standard', parent_id: null, in_my_courses: true }] } } },
    global: { plugins: [router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('personal course settings navigation', () => {
  it('starts a legacy lesson at its resolved Review URL', async () => {
    const { wrapper, router } = await mountCoursePage(MyCoursesView, '/my-courses')
    const row = wrapper.findAllComponents(DeckTreeItem).find(row => row.props('deck').id === '18')!
    await row.findAll('button').find(button => button.text() === '开始')!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/review/core-18')
    wrapper.unmount()
  })

  it('opens the existing settings page with the selected course', async () => {
    const { wrapper, router } = await mountCoursePage(MyCoursesView, '/my-courses')
    await wrapper.get('button[aria-label="Lesson one 设置"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/settings?deck_id=18')
    wrapper.unmount()
  })

  it('keeps all library decks on the page while keeping settings in my courses', async () => {
    const { wrapper, router } = await mountCoursePage(LibraryView, '/library')
    expect(wrapper.findAll('button[aria-label$=" 设置"]')).toHaveLength(0)
    expect(wrapper.findAll('button').some(button => /^(复习|开始)$/.test(button.text()))).toBe(false)
    for (const deck of wrapper.findAllComponents(DeckTreeItem)) {
      await deck.get('.mb-2').trigger('click')
    }
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/library')
    wrapper.unmount()
  })

  it('starts a joined core deck through the shared course row', async () => {
    const { wrapper, router } = await mountCoursePage(MyCoursesView, '/my-courses')
    const coreRow = wrapper.findAllComponents(DeckTreeItem).find(row => row.props('deck').id === coreDeckId)!
    expect(coreRow.props('deck').type).toBe('source')
    await coreRow.findAll('button').find(button => button.text() === '开始')!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(`/review/${coreDeckId}`)
    wrapper.unmount()
  })

  it('opens the same settings page for a core deck without starting practice', async () => {
    const { wrapper, router } = await mountCoursePage(MyCoursesView, '/my-courses')
    await wrapper.get('button[aria-label="自建词汇 设置"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`/settings?deck_id=${coreDeckId}`)
    wrapper.unmount()
  })

  it('redirects old deck settings links to the existing page', async () => {
    setAccessToken('test-session-token')
    await appRouter.push('/decks/18/settings')
    expect(appRouter.currentRoute.value.fullPath).toBe('/settings?deck_id=18')
  })
})
