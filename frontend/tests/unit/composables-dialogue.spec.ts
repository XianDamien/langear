import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import { useDialogue } from '@/composables/useDialogue'
import { dialogueApi } from '@/services/dialogue'
vi.mock('@/services/dialogue', () => ({ dialogueApi: { create: vi.fn(), get: vi.fn(), finish: vi.fn(), review: vi.fn() }, dialogueError: () => '请求失败', dialogueSocketUrl: () => 'wss://testserver/dialogue' }))
const recording = { start: vi.fn(), dispose: vi.fn(), stop: vi.fn(), getState: () => 'recording' }
vi.mock('@/adapters/browser/recording', () => ({ createRecordingSession: vi.fn(async () => recording) }))
let api: ReturnType<typeof useDialogue>
const session = { id: 's', status: 'ready', turns: [], user_turns: 0, max_user_turns: 8, scenario: {}, review: null }
class Socket {
  static OPEN = 1
  static current: Socket
  readyState = 1
  bufferedAmount = 0
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  send = vi.fn()
  close = vi.fn()
  constructor() { Socket.current = this }
  event(event: object) { this.onmessage?.({ data: JSON.stringify(event) }) }
}
beforeEach(() => {
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('AudioContext', class { currentTime = 0; resume = vi.fn(); close = vi.fn() })
  vi.mocked(dialogueApi.create).mockResolvedValue(structuredClone(session) as never)
  vi.mocked(dialogueApi.get).mockResolvedValue(structuredClone(session) as never)
})
function start() {
  return mount(defineComponent({ setup() { api = useDialogue({ deck_id: 'd', review_queue_id: 'queue', entry_key: 'key', attempt_ids: ['attempt'] }); return () => null } }))
}
it('connects only after explicit start and closes transport/microphone when unmounted', async () => {
  const wrapper = start()
  await api.prepare()
  expect(api.status.value).toBe('preview')
  await api.connect()
  Socket.current.event({ type: 'connected', session: structuredClone(session) })
  Socket.current.event({ type: 'ready' })
  await new Promise(r => setTimeout(r, 1))
  await api.record()
  expect(api.status.value).toBe('recording')
  expect(Socket.current.send).toHaveBeenCalledWith('{"type":"audio_begin"}')
  api.sendRecording()
  expect(Socket.current.send).toHaveBeenLastCalledWith('{"type":"commit"}')
  expect(recording.dispose).toHaveBeenCalled()
  wrapper.unmount()
  expect(Socket.current.close).toHaveBeenCalled()
})
it('ignores a response that arrives after the dialogue window is closed', async () => {
  let resolve!: (v: unknown) => void
  vi.mocked(dialogueApi.create).mockImplementationOnce(() => new Promise(r => { resolve = r }) as never)
  const wrapper = start()
  const request = api.prepare()
  wrapper.unmount()
  resolve(session)
  await request; await flushPromises()
  expect(api.session.value).toBeUndefined()
})
it('sends typed replies and completes after the spoken closing without a mandatory recap model call', async () => {
  const wrapper = start()
  await api.prepare(); await api.connect()
  Socket.current.event({ type: 'connected', session: structuredClone(session) })
  Socket.current.event({ type: 'ready' })
  await new Promise(r => setTimeout(r, 1))
  api.sendText('I practised buying an apple.')
  expect(Socket.current.send).toHaveBeenLastCalledWith('{"type":"text","text":"I practised buying an apple."}')
  expect(api.status.value).toBe('thinking')
  vi.mocked(dialogueApi.get).mockResolvedValue({ ...structuredClone(session), status: 'finished' } as never)
  Socket.current.event({ type: 'ended', reason: 'task_completed' })
  await new Promise(r => setTimeout(r, 1)); await flushPromises()
  expect(api.status.value).toBe('complete')
  expect(dialogueApi.review).not.toHaveBeenCalled()
  expect(dialogueApi.finish).not.toHaveBeenCalled()
  wrapper.unmount()
})
