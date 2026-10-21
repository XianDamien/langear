import { onBeforeUnmount, ref, type InjectionKey } from 'vue'
import { createRecordingSession, type RecordingSession } from '@/adapters/browser/recording'
import { dialogueApi, dialogueError, dialogueSocketUrl, type DialogueEntry, type DialogueSession, type DialogueTurn } from '@/services/dialogue'

type Status = 'preparing' | 'preview' | 'connecting' | 'speaking' | 'ready' | 'recording' | 'thinking' | 'reviewing' | 'complete' | 'failed'
export const dialogueControllerKey: InjectionKey<typeof useDialogue> = Symbol('dialogueController')

export function useDialogue(entry: DialogueEntry) {
  const session = ref<DialogueSession>()
  const status = ref<Status>('preparing')
  const error = ref('')
  const notice = ref('')
  const partial = ref('')
  const userPartial = ref('')
  // Remaining seconds in this voice connection; the server closes the dialogue at zero.
  const remaining = ref(0)
  let socket: WebSocket | null = null
  let recorder: RecordingSession | null = null
  let playback: AudioContext | null = null
  let playUntil = 0
  const sources = new Set<AudioBufferSourceNode>()
  let timer: ReturnType<typeof setTimeout> | undefined
  let recordingTimer: ReturnType<typeof setTimeout> | undefined
  let connectionTimer: ReturnType<typeof setTimeout> | undefined
  let clock: ReturnType<typeof setInterval> | undefined
  let disposed = false
  let generation = 0
  let finishing = false

  function stopRecording() {
    clearTimeout(recordingTimer)
    recorder?.dispose(); recorder = null
  }
  function clearPlayback() {
    clearTimeout(timer)
    for (const source of sources) { try { source.stop() } catch { /* already ended */ } }
    sources.clear(); playUntil = 0
  }
  function stopClock() {
    clearInterval(clock); clock = undefined
  }
  function startClock(seconds: number) {
    stopClock()
    remaining.value = Math.max(0, Math.round(seconds))
    clock = setInterval(() => { if (remaining.value > 0) remaining.value -= 1 }, 1000)
  }
  function disconnect() {
    generation++
    clearTimeout(connectionTimer)
    stopClock(); stopRecording(); clearPlayback()
    if (socket) { socket.onclose = null; socket.onmessage = null; socket.close(); socket = null }
  }
  function fail(message: string) {
    error.value = message; notice.value = ''; status.value = 'failed'; partial.value = ''; userPartial.value = ''
    disconnect()
  }
  async function prepare() {
    status.value = 'preparing'; error.value = ''
    try {
      const result = await dialogueApi.create(entry)
      if (disposed) return
      session.value = result
      status.value = result.status === 'finished' ? 'complete' : 'preview'
    } catch (cause) { if (!disposed) fail(dialogueError(cause)) }
  }
  function audio(data: string) {
    if (!playback) return
    const binary = atob(data)
    const bytes = Uint8Array.from(binary, c => c.charCodeAt(0))
    const view = new DataView(bytes.buffer)
    const buffer = playback.createBuffer(1, bytes.length / 2, 24000)
    const samples = buffer.getChannelData(0)
    for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768
    const source = playback.createBufferSource()
    source.buffer = buffer; source.connect(playback.destination)
    source.onended = () => sources.delete(source)
    sources.add(source)
    const start = Math.max(playback.currentTime + 0.02, playUntil)
    source.start(start); playUntil = start + buffer.duration
  }
  function afterPlayback(action: () => void) {
    clearTimeout(timer)
    timer = setTimeout(action, Math.max(0, playUntil - (playback?.currentTime || 0)) * 1000)
  }
  function addTurn(turn: DialogueTurn, count: number) {
    if (!session.value) return
    notice.value = ''; userPartial.value = ''
    if (!session.value.turns.some(t => t.id === turn.id)) session.value.turns.push(turn)
    session.value.user_turns = count
    partial.value = ''
  }
  async function connect() {
    if (!session.value || disposed) return
    disconnect()
    const request = generation
    status.value = 'connecting'; error.value = ''; partial.value = ''; userPartial.value = ''
    try {
      // Resume on the user's click so browsers allow synthesized speech playback.
      playback ??= new AudioContext()
      await playback.resume()
      const current = await dialogueApi.get(session.value.id)
      if (disposed || request !== generation) return
      session.value = current
      if (current.status === 'finished') { status.value = 'complete'; return }
      socket = new WebSocket(dialogueSocketUrl(current.id))
      connectionTimer = setTimeout(() => fail('连接超时，请重新连接。'), 20000)
      socket.onmessage = ({ data }) => {
        if (disposed || request !== generation) return
        try {
          const event = JSON.parse(data)
          if (event.type === 'connected') {
            clearTimeout(connectionTimer)
            session.value = event.session
            startClock(event.session.time_limit_seconds ?? 600)
            status.value = 'thinking'
          } else if (event.type === 'audio') { status.value = 'speaking'; audio(event.data) }
          else if (event.type === 'message_delta') partial.value += event.text
          else if (event.type === 'transcript_partial') userPartial.value = event.text || ''
          else if (event.type === 'turn') addTurn(event.turn, event.user_turns)
          else if (event.type === 'ready') afterPlayback(() => { if (!disposed) status.value = 'ready' })
          else if (event.type === 'notice') { notice.value = event.text || ''; userPartial.value = '' }
          else if (event.type === 'ended') {
            clearTimeout(connectionTimer)
            stopClock()
            stopRecording()
            status.value = 'speaking'
            // The server has durably ended the session; normal socket close is expected.
            if (socket) socket.onclose = null
            afterPlayback(() => { void finishAndReview(false) })
          } else if (event.type === 'error') fail(event.message || '对话连接中断，请重新连接。')
        } catch { fail('对话消息未能读取，请重新连接。') }
      }
      socket.onerror = () => fail('对话连接失败，请重新连接。')
      socket.onclose = () => { if (!disposed && status.value !== 'complete' && status.value !== 'reviewing') fail('连接已断开，可重新连接继续对话。') }
    } catch (cause) { if (!disposed) fail(dialogueError(cause)) }
  }
  async function record() {
    if (status.value !== 'ready' || !socket || socket.readyState !== WebSocket.OPEN) return
    const request = generation
    notice.value = ''
    userPartial.value = ''
    status.value = 'connecting'
    try {
      const recording = await createRecordingSession({ onRealtimePcmChunk: data => {
        if (status.value === 'recording' && socket?.readyState === WebSocket.OPEN) {
          if (socket.bufferedAmount > 256 * 1024) { fail('网络较慢，请重新连接后再试。'); return }
          socket.send(JSON.stringify({ type: 'audio', data }))
        }
      } })
      if (disposed || request !== generation) { recording.dispose(); return }
      recorder = recording
      socket!.send(JSON.stringify({ type: 'audio_begin' }))
      recorder.start()
      status.value = 'recording'
      // The realtime provider rejects input buffers longer than 30 seconds.
      recordingTimer = setTimeout(sendRecording, 28000)
    } catch { if (!disposed && request === generation) { status.value = 'ready'; error.value = '无法使用麦克风，请检查浏览器权限后重试。' } }
  }
  function sendRecording() {
    if (status.value !== 'recording') return
    stopRecording()
    status.value = 'thinking'; error.value = ''
    socket?.send(JSON.stringify({ type: 'commit' }))
  }
  function sendText(text: string) {
    if (status.value !== 'ready' || socket?.readyState !== WebSocket.OPEN || !text.trim()) return
    notice.value = ''; userPartial.value = ''
    status.value = 'thinking'; error.value = ''
    socket.send(JSON.stringify({ type: 'text', text: text.trim() }))
  }
  async function finishAndReview(review = true) {
    if (finishing || disposed || !session.value) return
    finishing = true
    disconnect()
    status.value = 'reviewing'; error.value = ''
    try {
      let result = await dialogueApi.get(session.value.id)
      if (result.status !== 'finished') result = await dialogueApi.finish(result.id)
      // Realtime already delivers the natural closing. Structured evidence review is optional.
      if (review) result = await dialogueApi.review(result.id)
      if (!disposed) { session.value = result; status.value = 'complete' }
    } catch (cause) { if (!disposed) { status.value = 'failed'; error.value = dialogueError(cause) } }
    finally { finishing = false }
  }
  function end() {
    stopRecording(); clearPlayback()
    if (socket?.readyState === WebSocket.OPEN) {
      status.value = 'thinking'
      socket.send(JSON.stringify({ type: 'end' }))
      clearTimeout(connectionTimer)
      // Finish may await the current 60s response, then a separate 60s spoken closing.
      connectionTimer = setTimeout(() => fail('结束请求未完成，请重新连接后重试。'), 135000)
    } else { void finishAndReview(false) }
  }
  onBeforeUnmount(() => { disposed = true; stopClock(); disconnect(); void playback?.close() })
  return { session, status, error, notice, partial, userPartial, remaining, prepare, connect, record, sendRecording, sendText, end, finishAndReview }
}
