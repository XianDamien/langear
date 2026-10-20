import type { Page } from '@playwright/test'

export const reviewDeckId = '01900000-0000-7000-8000-000000000001'

// State belongs to the API fixture, so navigation/reload exercise server recovery.
export async function installReviewMocks(page: Page) {
  const legacyRequests: string[] = []
  await page.addInitScript((transcript: string) => {
    class MockWebSocket {
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      readyState = MockWebSocket.CONNECTING
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onerror: ((event: Event) => void) | null = null
      onclose: ((event: Event) => void) | null = null

      constructor() {
        window.setTimeout(() => {
          this.readyState = MockWebSocket.OPEN
          this.onopen?.(new Event('open'))
        }, 0)
      }

      send(raw: string) {
        const message = JSON.parse(raw)
        if (message.type === 'session.update') {
          this.onmessage?.({ data: JSON.stringify({ type: 'session.created', realtime_session_id: 'e2e-realtime' }) })
        } else if (message.type === 'input_audio_buffer.append') {
          this.onmessage?.({ data: JSON.stringify({ type: 'transcript.partial', text: transcript }) })
        } else if (message.type === 'input_audio_buffer.commit') {
          this.onmessage?.({ data: JSON.stringify({ type: 'transcript.final', text: transcript }) })
        }
      }

      close() {
        this.readyState = MockWebSocket.CLOSED
        this.onclose?.(new Event('close'))
      }
    }

    Object.defineProperty(window, 'WebSocket', { configurable: true, value: MockWebSocket })
  }, 'The quick brown fox jumps over the lazy dog.')
  page.on('request', request => {
    if (new URL(request.url()).pathname.startsWith('/api/v1/')) legacyRequests.push(request.url())
  })
  let index = 0
  let saved: Record<string, unknown> | undefined
  let previous: Record<string, unknown> | undefined
  const options = ['again', 'hard', 'good', 'easy'].map(rating => ({ rating, display_interval: '15m' }))
  const cardId = () => `01900000-0000-7000-8000-00000000001${index}`
  const current = () => ({
    queue_id: 'q', review_token: `token-${index}`, new_remaining: 2 - index, learning_remaining: 0, review_remaining: 0, can_undo: !!previous && !saved,
    card: index < 2 ? {
      id: cardId(), note_id: `n-${index}`, deck_id: reviewDeckId,
      card_template_key: 'sentence_retelling', front: { reference_audio: 'reference' }, card_schedule_revision: index,
    } : null,
    ...(saved ? { attempt: saved, rating_options: options, card_schedule_revision: index } : {}),
  })
  await page.route('**/api/content/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/content/v1', '')
    let data: unknown
    if (path === '/auth/me') data = {
      user: { id: '01900000-0000-7000-8000-0000000000aa', email: 'e2e@example.invalid', username: 'e2e' },
      collection: { id: '01900000-0000-7000-8000-0000000000bb' },
    }
    else if (path === '/auth/csrf') data = { csrf_token: 'test-csrf' }
    else if (path === `/decks/${reviewDeckId}`) data = { id: reviewDeckId, name: 'Lesson 1', deck_guid: 'legacy:test:deck:1001' }
    else if (path === '/dialogue/availability') data = { enabled: false }
    else if (path === '/review/queues') data = { queue_id: 'q' }
    else if (path.endsWith('/next')) data = current()
    else if (path === '/media-assets/audio-uploads') data = { media_asset_id: 'recording', upload_url: '/e2e-audio-upload', headers: {} }
    else if (path.endsWith('/confirm-upload')) data = {}
    else if (path.startsWith('/media-assets/')) data = { url: `/mock/audio/${index + 2001}-${path.includes('reference') ? 'reference' : 'recording'}.wav` }
    else if (path.endsWith('/flip')) {
      const text = index === 0 ? 'The quick brown fox jumps over the lazy dog.' : 'Learning a language requires practice.'
      saved = { id: `attempt-${index}`, card_id: cardId(), media_asset_id: 'recording', input_snapshot: request.postDataJSON().input,
        front_snapshot: { reference_audio: 'reference' }, back_snapshot: { english: text, chinese: '中文参考译文' },
        asr_status: 'succeeded', asr_result: { text }, ai_status: 'succeeded',
        ai_feedback: { pronunciation: '发音清晰', completeness: '本句转写与原文一致', fluency: '流畅', suggestions: [], issues: [] } }
      data = { attempt: saved, card_schedule_revision: index, rating_options: options }
    } else if (path.endsWith('/rating')) { previous = saved; saved = undefined; index++; data = {} }
    else if (path.endsWith('/undo')) { index--; saved = previous; previous = undefined; data = { attempt: saved, card_schedule_revision: index, rating_options: options } }
    else throw new Error(`Unexpected Review request: ${request.method()} ${path}`)
    await route.fulfill({ json: data })
  })
  await page.route('**/e2e-audio-upload', route => route.fulfill({ status: 200, body: '' }))
  return legacyRequests
}
