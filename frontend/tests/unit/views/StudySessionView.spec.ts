import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudySessionView from '@/views/StudySessionView.vue'
import ReviewSessionView from '@/views/ReviewSessionView.vue'
import { libraryContent } from '@/services/libraryContent'

vi.mock('@/services/libraryContent', () => ({ libraryContent: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
const get = vi.mocked(libraryContent.get)
const post = vi.mocked(libraryContent.post)
async function start() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/study/:lessonId', component: StudySessionView },
    { path: '/review/:deckId', name: 'DeckReview', component: ReviewSessionView },
  ] })
  await router.push('/study/1001')
  const wrapper = mount(RouterView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}
beforeEach(() => {
  sessionStorage.clear()
  get.mockImplementation(async path => ({ data: path.startsWith('/review/legacy-lessons/') ? { deck_id: 'core-deck' }
    : path.startsWith('/decks/') ? { id: 'core-deck', name: 'Lesson 1', deck_guid: 'legacy:staging:deck:1001' }
    : path.startsWith('/media-assets/') ? { url: '/test.wav' }
    : { queue_id: 'q', review_token: 'token', card: { id: 'a', card_template_key: 'sentence_retelling', front: { reference_audio: 'reference' } }, new_remaining: 2, learning_remaining: 1, review_remaining: 3, can_undo: false } }))
  post.mockResolvedValue({ data: { queue_id: 'q' } })
})
describe('Study compatibility redirect', () => {
  it('replaces the old URL with the current user Review deck and defaults to retelling', async () => {
    const { wrapper, router } = await start()
    expect(router.currentRoute.value.path).toBe('/review/core-deck')
    expect(get).toHaveBeenCalledWith('/review/legacy-lessons/1001')
    expect(post).toHaveBeenCalledWith('/review/queues', { scope: { deck_id: 'core-deck', include_descendants: true, exclude_imported: false, card_template_keys: ['sentence_retelling'] } })
    expect(wrapper.get('[data-testid="record-toggle"]').exists()).toBe(true)
    expect(wrapper.get('[aria-label="剩余卡片"]').findAll('dd').map(x => x.text())).toEqual(['2', '1', '3'])
    expect([...get.mock.calls, ...post.mock.calls].some(([url]) => url.startsWith('/study'))).toBe(false)
    wrapper.unmount()
  })
  it('keeps unmigrated lessons on an actionable error instead of starting the wrong deck', async () => {
    get.mockRejectedValueOnce(new Error('课程尚未迁移'))
    const { wrapper, router } = await start()
    expect(wrapper.get('[role="alert"]').text()).toContain('课程尚未迁移')
    expect(post).not.toHaveBeenCalled()
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/review/core-deck')
    wrapper.unmount()
  })
})
