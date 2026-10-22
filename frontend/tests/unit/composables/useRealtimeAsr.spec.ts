import { afterEach, describe, expect, it, vi } from 'vitest'
import { useRealtimeAsr } from '@/composables/useRealtimeAsr'

class FakeSocket {
  static instance: FakeSocket
  static OPEN = 1
  static CONNECTING = 0
  readyState = 0
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  send = vi.fn()
  close = vi.fn()
  constructor(public url: string) { FakeSocket.instance = this }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })
describe('Review realtime transport', () => {
  it('uses the authenticated Review proxy and retains the original PCM protocol', async () => {
    vi.stubGlobal('WebSocket', FakeSocket)
    const asr = useRealtimeAsr()
    const connecting = asr.connectReview('card-uuid', '/content-api/v1')
    const socket = FakeSocket.instance
    expect(socket.url).toContain('/content-api/v1/review/realtime/asr/ws?card_id=card-uuid')
    socket.readyState = 1
    socket.onopen!()
    expect(await connecting).toBe(true)
    socket.onmessage!({ data: JSON.stringify({ type: 'session.created', realtime_session_id: 'stream-id' }) })
    asr.appendAudioChunk('cGNt')
    expect(JSON.parse(socket.send.mock.calls.at(-1)![0])).toMatchObject({ type: 'input_audio_buffer.append', audio: 'cGNt' })
    const committed = asr.commit()
    socket.onmessage!({ data: JSON.stringify({ type: 'transcript.final', text: 'Hello' }) })
    expect(await committed).toBe(true)
    expect(asr.realtimeSessionId.value).toBe('stream-id')
    expect(asr.finalTranscript.value).toBe('Hello')
    asr.clearTranscript()
    expect(asr.partialTranscript.value).toBe('')
    expect(asr.finalTranscript.value).toBe('')
    expect(asr.realtimeSessionId.value).toBe('stream-id')
    asr.reset()
  })
  it.each(['onerror', 'onclose'] as const)('settles connection failure on %s so recording can continue', async event => {
    vi.stubGlobal('WebSocket', FakeSocket)
    const asr = useRealtimeAsr()
    const connecting = asr.connectReview('card-uuid', '/api/v1')
    const socket = FakeSocket.instance
    socket[event]!()
    expect(await connecting).toBe(false)
    expect(asr.status.value).toBe('failed')
    asr.reset()
  })
})
