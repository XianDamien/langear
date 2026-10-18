import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudySessionView from '@/views/StudySessionView.vue'
import { libraryContent } from '@/services/libraryContent'

vi.mock('@/services/libraryContent', () => ({ libraryContent: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
const get = vi.mocked(libraryContent.get)
const post = vi.mocked(libraryContent.post)
const put = vi.mocked(libraryContent.put)
const options = ['again', 'hard', 'good', 'easy'].map(rating => ({ rating, display_interval: '15m' }))
let current: Record<string, unknown>
const card = { id: 'core-card', note_id: 'note', deck_id: 'core-deck', card_template_key: 'sentence_retelling', front: { reference_audio: 'reference' }, card_schedule_revision: 1 }
const attempt = { id: 'saved-attempt', media_asset_id: 'recording', front_snapshot: card.front,
  back_snapshot: { english: 'Hello world.', chinese: '你好世界' },
  input_snapshot: { type: 'audio', temporary_media_asset_id: 'recording' },
  asr_status: 'succeeded', asr_result: { text: 'Hello there.' }, ai_status: 'succeeded',
  ai_feedback: { pronunciation: '发音清晰', completeness: '注意内容完整度', fluency: '流畅', issues: [], suggestions: [] } }
async function start() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/study/:lessonId', component: StudySessionView }] })
  await router.push('/study/1001')
  const wrapper = mount(StudySessionView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  current = { queue_id: 'q', review_token: 'token', card, new_remaining: 2, learning_remaining: 1, review_remaining: 3, can_undo: false }
  get.mockImplementation(async path => ({ data: path.startsWith('/review/legacy-lessons/') ? { deck_id: 'core-deck' }
    : path.startsWith('/decks/') ? { id: 'core-deck', name: 'Lesson 1', deck_guid: 'legacy:staging:deck:1001' }
    : path.startsWith('/media-assets/') ? { url: '/test.wav' } : current }))
  post.mockImplementation(async () => ({ data: { queue_id: 'q' } }))
  put.mockImplementation(async () => {
    current = { ...current, card: null, attempt: undefined, can_undo: true, empty_reason: 'done_today' }
    return { data: {} }
  })
})
describe('Study compatibility entry uses Review', () => {
  it('resolves the current user lesson and reads authoritative counts', async () => {
    const view = await start()
    expect(get).toHaveBeenCalledWith('/review/legacy-lessons/1001')
    expect(post).toHaveBeenCalledWith('/review/queues', { scope: { deck_id: 'core-deck', include_descendants: true, exclude_imported: false } })
    expect(view.get('header').text()).toContain('Lesson 1')
    expect(view.get('[aria-label="剩余卡片"]').findAll('dd').map(x => x.text())).toEqual(['2', '1', '3'])
    expect(view.get('[data-testid="record-toggle"]').exists()).toBe(true)
    expect(view.find('[role="progressbar"]').exists()).toBe(false)
    expect([...get.mock.calls, ...post.mock.calls].some(([url]) => url.startsWith('/study'))).toBe(false)
    view.unmount()
  })
  it('restores the original comparison, audio, feedback and notes UI from the Attempt', async () => {
    current = { ...current, attempt, rating_options: options, card_schedule_revision: 1 }
    const view = await start()
    expect(view.get('[data-testid="original-text"]').text()).toContain('Hello world.')
    expect(view.get('[data-testid="transcript-row"]').text()).toContain('Hello there.')
    expect(view.get('[data-testid="feedback-panel"]').text()).toContain('发音清晰')
    expect(view.findAll('audio')).toHaveLength(2)
    expect(view.get('textarea').attributes('placeholder')).toContain('记录易错点')
    await view.get('[data-testid="rate-good"]').trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledWith('/review/queues/q/attempts/saved-attempt/rating', { rating: 'good', card_schedule_revision: 1 }, expect.anything())
    expect(view.get('[data-testid="review-empty"]').exists()).toBe(true)
    view.unmount()
  })
  it('does not silently start a separate study session for an unmigrated lesson', async () => {
    get.mockRejectedValueOnce(new Error('课程尚未迁移'))
    const view = await start()
    expect(view.get('[role="alert"]').text()).toContain('课程尚未迁移')
    expect(post).not.toHaveBeenCalled()
    await view.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(get.mock.calls.filter(([url]) => url === '/review/legacy-lessons/1001')).toHaveLength(2)
    view.unmount()
  })
})
