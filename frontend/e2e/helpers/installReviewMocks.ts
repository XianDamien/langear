import type { Page } from '@playwright/test'

// State belongs to the API fixture, so navigation/reload exercise server recovery.
export async function installReviewMocks(page: Page) {
  await page.addInitScript(() => localStorage.setItem('langear_access_token', 'test-token'))
  const requests: string[] = []
  page.on('request', request => { if (/\/(?:content-api|api)\/v1\/study(?:\/|\?)/.test(request.url())) requests.push(request.url()) })
  let index = 0
  let saved: Record<string, unknown> | undefined
  let previous: Record<string, unknown> | undefined
  const options = ['again', 'hard', 'good', 'easy'].map(rating => ({ rating, display_interval: '15m' }))
  const current = () => ({
    queue_id: 'q', review_token: `token-${index}`, new_remaining: 2 - index, learning_remaining: 0, review_remaining: 0, can_undo: !!previous && !saved,
    card: index < 2 ? { id: String(index + 2001), note_id: `n-${index}`, deck_id: 'core-deck', card_template_key: 'sentence_retelling', front: { reference_audio: 'reference' }, card_schedule_revision: index } : null,
    ...(saved ? { attempt: saved, rating_options: options, card_schedule_revision: index } : {}),
  })
  await page.route('**/content-api/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/content-api/v1', '')
    let data: unknown
    if (path === '/auth/legacy') data = { csrf_token: 'test-csrf' }
    else if (path === '/review/legacy-lessons/1001') data = { deck_id: 'core-deck' }
    else if (path === '/decks/core-deck') data = { id: 'core-deck', name: 'Lesson 1', deck_guid: 'legacy:test:deck:1001' }
    else if (path === '/review/queues') data = { queue_id: 'q' }
    else if (path.endsWith('/next')) data = current()
    else if (path === '/media-assets/audio-uploads') data = { media_asset_id: 'recording', upload_url: '/e2e-audio-upload', headers: {} }
    else if (path.endsWith('/confirm-upload')) data = {}
    else if (path.startsWith('/media-assets/')) data = { url: `/mock/audio/${index + 2001}-${path.includes('reference') ? 'reference' : 'recording'}.wav` }
    else if (path.endsWith('/flip')) {
      const text = index === 0 ? 'The quick brown fox jumps over the lazy dog.' : 'Learning a language requires practice.'
      saved = { id: `attempt-${index}`, card_id: String(index + 2001), media_asset_id: 'recording', input_snapshot: request.postDataJSON().input,
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
  return requests
}
