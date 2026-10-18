import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReviewSessionView from '@/views/ReviewSessionView.vue'
import { libraryContent } from '@/services/libraryContent'
import type { ReviewNext } from '@/services/review'

vi.mock('@/services/libraryContent', () => ({ libraryContent: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
const options = ['again', 'hard', 'good', 'easy'].map(rating => ({ rating, display_interval: '15m' }))
const card = { id: 'a', deck_id: 'deck-a', note_id: 'n1', card_template_key: 'vocabulary_english_to_chinese', front: { word: 'journey' }, card_schedule_revision: 0, input_requirement: { type: 'none', required: false } }
const counts = { new_remaining: 1, review_remaining: 0, learning_remaining: 0, can_undo: false, next_due_at: null, empty_reason: null }
let current: Record<string, unknown>
let attempt: Record<string, unknown>
const httpGet = vi.mocked(libraryContent.get)
const httpPost = vi.mocked(libraryContent.post)
const httpPut = vi.mocked(libraryContent.put)
async function start() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/review/:deckId', component: ReviewSessionView },
    { path: '/library', component: { template: '<div>Library</div>' } },
  ] })
  await router.push('/review/deck-a')
  const wrapper = mount(ReviewSessionView, { global: { plugins: [router] } })
  await flushPromises()
  const click = async (text: string) => {
    await wrapper.findAll('button').find(b => b.text() === text)!.trigger('click')
    await flushPromises()
  }
  return { wrapper, router, click }
}
beforeEach(() => {
  sessionStorage.clear()
  current = { ...counts, queue_id: 'q', review_token: 'token', card: { ...card } }
  attempt = { id: 'attempt', card_id: 'a', review_token: 'token', front_snapshot: card.front,
    back_snapshot: { word: 'journey', meaning: '旅程', mnemonic: '记忆联想', note: '常用搭配' }, input_snapshot: { type: 'none' },
    asr_status: 'skipped', ai_status: 'skipped', rating: null, media_asset_id: null, deterministic_result: null }
  httpGet.mockImplementation(async path => ({ data: path.startsWith('/decks/') ? { id: path.split('/')[2], name: 'Practice' } : path.startsWith('/media-assets') ? { url: '/reference.wav' } : current }))
  httpPost.mockImplementation(async (path, body) => {
    if (path === '/review/queues') return { data: { ...counts, queue_id: 'q', current: null } }
    if (path.endsWith('/flip')) {
      attempt.input_snapshot = (body as { input: unknown }).input
      current = { ...current, attempt, card_schedule_revision: 0, rating_options: options, can_undo: false }
      return { data: { attempt, card_schedule_revision: 0, rating_options: options } }
    }
    if (path.endsWith('/undo')) {
      current = { ...counts, queue_id: 'q', review_token: 'token', card, attempt, card_schedule_revision: 2, rating_options: options }
      return { data: { attempt, card_schedule_revision: 2, rating_options: options } }
    }
    return { data: {} }
  })
  httpPut.mockImplementation(async () => {
    current = { ...counts, queue_id: 'q', review_token: null, card: null, new_remaining: 0, can_undo: true, empty_reason: 'waiting', next_due_at: '2026-10-17T10:15:00Z' }
    return { data: { attempt_id: 'attempt', rating: 'good' } }
  })
})
describe('server-backed review', () => {
  it('keeps retelling counts in the header through reveal, rating, and undo', async () => {
    const remaining = { new_remaining: 3, learning_remaining: 2, review_remaining: 4 }
    current = { ...current, ...remaining, card: { ...card, card_template_key: 'sentence_retelling', front: { reference_audio: 'audio' } } }
    attempt = { ...attempt, front_snapshot: { reference_audio: 'audio' }, back_snapshot: { english: 'Hello' }, input_snapshot: { type: 'audio', temporary_media_asset_id: 'recording' }, media_asset_id: 'recording' }
    const { wrapper } = await start()
    const headerCounts = () => wrapper.get('header [aria-label="剩余卡片"]')
    const expectCounts = (values: number[]) => {
      expect(headerCounts().findAll('dt').map(label => label.text())).toEqual(['未学习', '学习中', '待复习'])
      expect(headerCounts().findAll('dd').map(value => Number(value.text()))).toEqual(values)
      expect(wrapper.findAll('[aria-label="剩余卡片"]')).toHaveLength(1)
    }
    expectCounts([3, 2, 4])
    wrapper.unmount()

    // A recovered recording restores the answer without hiding queue progress.
    current = { ...current, attempt, rating_options: options, card_schedule_revision: 0 }
    const recovered = await start()
    const values = () => recovered.wrapper.get('header [aria-label="剩余卡片"]').findAll('dd').map(value => Number(value.text()))
    expect(values()).toEqual([3, 2, 4])
    httpPut.mockImplementationOnce(async () => {
      current = { ...current, attempt: undefined, review_token: 'next-token', new_remaining: 2, learning_remaining: 3, can_undo: true }
      return { data: { attempt_id: 'attempt', rating: 'again' } }
    })
    await recovered.wrapper.get('[data-testid="rate-again"]').trigger('click')
    await flushPromises()
    expect(values()).toEqual([2, 3, 4])
    expect(recovered.wrapper.find('[data-testid="rate-again"]').exists()).toBe(false)
    httpPost.mockImplementationOnce(async () => {
      current = { ...current, ...remaining, attempt, card_schedule_revision: 2, rating_options: options, can_undo: false }
      return { data: { attempt, card_schedule_revision: 2, rating_options: options } }
    })
    await recovered.click('撤回上一张')
    expect(values()).toEqual([3, 2, 4])
    expect(recovered.wrapper.get('[data-testid="rate-again"]').exists()).toBe(true)
    recovered.wrapper.unmount()
  })
  it('loads only the front, reveals snapshots, rates and undoes without local navigation', async () => {
    const { wrapper, click } = await start()
    expect(httpGet).not.toHaveBeenCalledWith('/cards', expect.anything())
    expect(wrapper.text()).not.toContain('记忆联想')
    await click('显示答案')
    expect(wrapper.text()).toContain('记忆联想')
    expect(wrapper.text()).toContain('旅程')
    expect(wrapper.get('[data-testid="rate-good"]').text()).toContain('15m')
    await wrapper.get('[data-testid="rate-good"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="review-empty"]').text()).toContain('下一张')
    expect(httpPut).toHaveBeenCalledWith('/review/queues/q/attempts/attempt/rating', { rating: 'good', card_schedule_revision: 0 }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.stringMatching(/^[0-9a-f-]{14}7/) } }))
    await click('撤回上一张')
    expect(wrapper.text()).toContain('记忆联想')
    expect(wrapper.get('[data-testid="rate-easy"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it.each(['vocabulary_english_to_chinese', 'vocabulary_chinese_to_english', 'sentence_retelling', 'sentence_translation', 'sentence_dictation'])('returns %s to its saved back after undo, including refresh', async template => {
    const savedCard = { ...card, card_template_key: template, front: template === 'vocabulary_english_to_chinese' ? { word: 'journey' } : template === 'vocabulary_chinese_to_english' ? { meaning: '旅程' } : template === 'sentence_translation' ? { chinese: '你好' } : { reference_audio: 'audio' } }
    attempt = { ...attempt, front_snapshot: savedCard.front, back_snapshot: { word: 'journey', meaning: '旅程', english: 'Saved answer' }, input_snapshot: template === 'sentence_retelling' ? { type: 'audio', temporary_media_asset_id: 'recording' } : template.startsWith('sentence_') ? { type: 'text', text: '  Saved input  ' } : { type: 'none' }, media_asset_id: template === 'sentence_retelling' ? 'recording' : null }
    current = { ...current, card: { ...savedCard, id: 'next-card' }, can_undo: true }
    httpPost.mockImplementationOnce(async () => ({ data: { ...counts, queue_id: 'q', current: null } }))
    const view = await start()
    httpPost.mockImplementationOnce(async () => {
      current = { ...counts, queue_id: 'q', review_token: 'saved-token', card: savedCard, attempt, card_schedule_revision: 2, rating_options: options }
      return { data: { attempt, card_schedule_revision: 2, rating_options: options } }
    })
    const actions = view.wrapper.get('[aria-label="卡片操作"]')
    expect(actions.text()).toContain('今日跳过')
    expect(actions.text()).toContain('暂停此卡')
    await view.click('撤回上一张')
    expect(view.wrapper.find('[data-testid="card-back-container"]').exists()).toBe(true)
    expect(view.wrapper.get('[data-testid="rate-good"]').exists()).toBe(true)
    view.wrapper.unmount()
    const recovered = await start()
    expect(recovered.wrapper.find('[data-testid="card-back-container"]').exists()).toBe(true)
    if (template === 'sentence_retelling') {
      expect(recovered.wrapper.findAll('audio').some(audio => audio.attributes('src') === '/reference.wav')).toBe(true)
      expect(recovered.wrapper.find('[data-testid="record-toggle"]').exists()).toBe(false)
    } else if (template.startsWith('sentence_')) {
      expect(recovered.wrapper.text()).toContain('Saved input')
      expect(recovered.wrapper.find('[aria-label="我的译文"], [aria-label="我的听写"]').exists()).toBe(false)
    }
    expect(recovered.wrapper.get('[data-testid="rate-good"]').attributes('disabled')).toBeUndefined()
    expect(httpPost.mock.calls.filter(([path]) => path.endsWith('/flip'))).toHaveLength(0)
    await recovered.wrapper.get('[data-testid="rate-good"]').trigger('click')
    await flushPromises()
    expect(httpPut).toHaveBeenCalledWith('/review/queues/q/attempts/attempt/rating', { rating: 'good', card_schedule_revision: 2 }, expect.anything())
    recovered.wrapper.unmount()
  })
  it.each(['vocabulary_english_to_chinese', 'vocabulary_chinese_to_english', 'sentence_retelling', 'sentence_translation', 'sentence_dictation'])('offers server-backed skip and suspend on %s', async template => {
    current.card = { ...card, card_template_key: template }
    const view = await start()
    await view.click('今日跳过')
    expect(httpPost).toHaveBeenCalledWith('/cards/a/schedule', { action: 'bury', card_schedule_revision: 0 })
    await view.click('暂停此卡')
    expect(httpPost).toHaveBeenCalledWith('/cards/a/schedule', { action: 'suspend', card_schedule_revision: 0 })
    expect(view.wrapper.find('[data-testid="card-front-container"]').exists()).toBe(true)
    view.wrapper.unmount()
  })
  it('preserves raw translation text and restores it from the saved Attempt after refresh', async () => {
    current.card = { ...card, card_template_key: 'sentence_translation', front: { chinese: '你好' }, input_requirement: { type: 'text', required: true } }
    attempt.front_snapshot = { chinese: '你好' }
    attempt.back_snapshot = { english: 'Hello', reference_audio: 'audio' }
    const { wrapper, click } = await start()
    expect(wrapper.text()).not.toContain('Hello')
    expect(wrapper.find('audio').exists()).toBe(false)
    await wrapper.get('textarea').setValue('  Hi  ')
    await click('显示答案')
    expect(httpPost).toHaveBeenCalledWith('/review/queues/q/flip', expect.objectContaining({ input: { type: 'text', text: '  Hi  ' } }), expect.anything())
    expect(wrapper.text()).toContain('Hello')
    expect(wrapper.text()).toContain('Hi')
    expect(wrapper.get('audio').attributes('src')).toBe('/reference.wav')
    wrapper.unmount()
    const recovered = await start()
    expect(recovered.wrapper.text()).toContain('Hi')
    expect(recovered.wrapper.find('textarea').exists()).toBe(false)
    expect(recovered.wrapper.get('[data-testid="rate-good"]').attributes('disabled')).toBeUndefined()
    recovered.wrapper.unmount()
  })
  it('replays a lost rating response with the identical key, even after remounting', async () => {
    const { wrapper, click } = await start()
    await click('显示答案')
    const success = httpPut.getMockImplementation()!
    httpPut.mockImplementationOnce(async (...args) => {
      await success(...args)
      throw new Error('offline after commit')
    })
    await wrapper.get('[data-testid="rate-good"]').trigger('click')
    await flushPromises()
    const original = httpPut.mock.calls[0]
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    wrapper.unmount()
    const recovered = await start()
    expect(httpPut.mock.calls[1]).toEqual(original)
    expect(recovered.wrapper.get('[data-testid="review-empty"]').text()).toContain('下一张')
    expect(sessionStorage.length).toBe(0)
    recovered.wrapper.unmount()
  })
  it('uses authoritative normalized dictation differences rather than a second frontend diff', async () => {
    current.card = { ...card, card_template_key: 'sentence_dictation', front: { reference_audio: 'audio' } }
    attempt.front_snapshot = { reference_audio: 'audio' }
    attempt.back_snapshot = { english: '“Hello”', chinese: '你好' }
    attempt.deterministic_result = { kind: 'dictation_text_diff', exact_match: true, normalized_expected: '"Hello"', normalized_actual: '"Hello"', differences: [] }
    const { wrapper, click } = await start()
    expect(wrapper.text()).not.toContain('Hello')
    await wrapper.get('textarea').setValue('"Hello"')
    await click('显示答案')
    expect(wrapper.get('[data-testid="text-difference-count"]').text()).toBe('0 处差异')
    wrapper.unmount()
  })
  it('shows recovered audio and allows rating independently of pending processing', async () => {
    current.card = { ...card, card_template_key: 'sentence_retelling', front: { reference_audio: 'audio' } }
    attempt = { ...attempt, front_snapshot: { reference_audio: 'audio' }, back_snapshot: { english: 'Hello' }, input_snapshot: { type: 'audio', temporary_media_asset_id: 'recording' }, media_asset_id: 'recording', asr_status: 'pending', ai_status: 'pending' }
    current = { ...current, attempt, rating_options: options, card_schedule_revision: 0 }
    const { wrapper } = await start()
    expect(httpGet).toHaveBeenCalledWith('/media-assets/recording/url')
    expect(wrapper.text()).toContain('转写：等待处理')
    expect(wrapper.get('[data-testid="rate-good"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('blocks revealing a retelling answer without a recording', async () => {
    current.card = { ...card, card_template_key: 'sentence_retelling', front: { reference_audio: 'audio' } }
    const { wrapper } = await start()
    expect(wrapper.get('[data-testid="flip-button"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('recovers an expired queue and ignores stale deck responses', async () => {
    const { wrapper, click, router } = await start()
    httpPost.mockRejectedValueOnce({ isAxiosError: true, response: { data: { error: { code: 'QUEUE_EXPIRED' } } } })
    await click('显示答案')
    await click('恢复队列')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    let release!: (value: { data: ReviewNext }) => void
    httpGet.mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
    await router.push('/review/deck-b')
    await router.push('/review/deck-c')
    await flushPromises()
    release({ data: { ...counts, queue_id: 'old', card: null, review_token: null, empty_reason: 'no_cards' } })
    await flushPromises()
    expect(wrapper.text()).toContain('journey')
    wrapper.unmount()
  })
})
