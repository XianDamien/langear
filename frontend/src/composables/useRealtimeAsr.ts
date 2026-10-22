import { ref } from 'vue'

export type RealtimeAsrStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'finalizing'
  | 'ready'
  | 'failed'

interface RealtimeErrorPayload {
  code?: string
  message?: string
  retryable?: boolean
}

type CommitResolver = ((ok: boolean) => void) | null

const realtimeAsrModel =
  import.meta.env.VITE_REALTIME_ASR_MODEL || 'qwen3-asr-flash-realtime'

export function useRealtimeAsr() {
  const status = ref<RealtimeAsrStatus>('idle')
  const partialTranscript = ref('')
  const finalTranscript = ref('')
  const realtimeSessionId = ref<string | null>(null)
  const errorCode = ref<string | null>(null)
  const errorMessage = ref<string | null>(null)

  let socket: WebSocket | null = null
  let seq = 0
  let startTs = 0
  let commitResolver: CommitResolver = null
  let commitTimer: number | null = null
  let endingSession = false

  function clearCommitTimer() {
    if (commitTimer) {
      window.clearTimeout(commitTimer)
      commitTimer = null
    }
  }

  function resolveCommit(ok: boolean) {
    if (!commitResolver) return
    const resolver = commitResolver
    commitResolver = null
    clearCommitTimer()
    resolver(ok)
  }

  function closeSocket() {
    if (!socket) return
    socket.onopen = null
    socket.onmessage = null
    socket.onerror = null
    socket.onclose = null
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close()
    }
    socket = null
  }

  function handleError(payload: RealtimeErrorPayload) {
    status.value = 'failed'
    errorCode.value = payload.code ?? 'REALTIME_SESSION_FAILED'
    errorMessage.value = payload.message ?? 'Realtime ASR failed'
    resolveCommit(false)
  }

  function attachSocketHandlers(ws: WebSocket, onConnectFail?: () => void) {
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        const messageType = payload?.type

        if (messageType === 'session.created') {
          const backendSessionId = payload.realtime_session_id
          if (backendSessionId) {
            // Backend-generated session id is attached to the Attempt.
            realtimeSessionId.value = backendSessionId
          } else if (!realtimeSessionId.value && payload.session?.id) {
            realtimeSessionId.value = payload.session.id
          }
          return
        }

        if (
          messageType === 'transcript.partial' ||
          messageType === 'conversation.item.input_audio_transcription.text'
        ) {
          partialTranscript.value = payload.text || ''
          if (status.value === 'connecting') status.value = 'streaming'
          return
        }

        if (
          messageType === 'transcript.final' ||
          messageType === 'conversation.item.input_audio_transcription.completed'
        ) {
          finalTranscript.value = payload.text || payload.transcript || ''
          partialTranscript.value = finalTranscript.value
          status.value = 'ready'
          resolveCommit(true)
          return
        }

        if (messageType === 'error') {
          onConnectFail?.()
          handleError(payload)
          return
        }

        if (messageType === 'session.closed') {
          closeSocket()
          if (endingSession) {
            endingSession = false
            if (status.value !== 'failed') status.value = 'idle'
          }
        }
      } catch {
        handleError({
          code: 'REALTIME_SESSION_FAILED',
          message: 'Invalid realtime message payload',
        })
      }
    }

    ws.onerror = () => {
      handleError({
        code: 'REALTIME_SESSION_FAILED',
        message: 'Realtime websocket error',
      })
      onConnectFail?.()
    }

    ws.onclose = () => {
      closeSocket()
      onConnectFail?.()
      if (!endingSession && status.value !== 'ready' && status.value !== 'idle') {
        handleError({
          code: 'REALTIME_SESSION_FAILED',
          message: 'Realtime websocket disconnected',
        })
      }
      endingSession = false
    }
  }

  async function connect(cardId: string, baseURL: string): Promise<boolean> {
    reset()
    status.value = 'connecting'
    errorCode.value = null
    errorMessage.value = null
    seq = 0
    startTs = Date.now()

    return await new Promise((resolve) => {
      const url = new URL(`${baseURL.replace(/\/$/, '')}/review/realtime/asr/ws`, window.location.origin)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      url.searchParams.set('card_id', cardId)
      const ws = new WebSocket(url.toString())
      socket = ws
      let connectResolved = false
      let timeout: number | null = null
      const settleConnect = (ok: boolean) => {
        if (connectResolved) return
        connectResolved = true
        resolve(ok)
      }
      attachSocketHandlers(ws, () => {
        if (timeout) window.clearTimeout(timeout)
        settleConnect(false)
      })

      timeout = window.setTimeout(() => {
        if (status.value === 'connecting') {
          handleError({
            code: 'REALTIME_SESSION_FAILED',
            message: 'Realtime connection timeout',
          })
          settleConnect(false)
        }
      }, 8000)

      ws.onopen = () => {
        if (timeout) window.clearTimeout(timeout)
        status.value = 'streaming'
        ws.send(
          JSON.stringify({
            type: 'session.update',
            session: {
              modalities: ['text'],
              input_audio_transcription: {
                model: realtimeAsrModel,
                language: 'en',
              },
              input_audio_format: 'pcm',
              sample_rate: 16000,
            },
          }),
        )
        settleConnect(true)
      }
    })
  }

  function appendAudioChunk(chunkBase64: string) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return
    if (status.value === 'failed') return

    seq += 1
    const tsMs = Date.now() - startTs
    socket.send(
      JSON.stringify({
        type: 'input_audio_buffer.append',
        audio: chunkBase64,
        seq,
        ts_ms: tsMs,
      }),
    )
  }

  async function commit(): Promise<boolean> {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      handleError({
        code: 'REALTIME_SESSION_FAILED',
        message: 'Realtime connection is not available',
      })
      return false
    }

    if (finalTranscript.value) {
      status.value = 'ready'
      return true
    }

    status.value = 'finalizing'
    socket.send(JSON.stringify({ type: 'input_audio_buffer.commit' }))

    return await new Promise((resolve) => {
      commitResolver = resolve
      commitTimer = window.setTimeout(() => {
        handleError({
          code: 'REALTIME_TRANSCRIPT_NOT_READY',
          message: 'Realtime final transcript timeout',
        })
        resolveCommit(false)
      }, 20000)
    })
  }

  function endSession() {
    endingSession = true
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'session.end' }))
      window.setTimeout(() => {
        closeSocket()
        if (status.value !== 'failed') status.value = 'idle'
        endingSession = false
      }, 300)
      return
    }
    closeSocket()
    if (status.value !== 'failed') status.value = 'idle'
    endingSession = false
  }

  function clearTranscript() {
    partialTranscript.value = ''
    finalTranscript.value = ''
  }

  function reset() {
    resolveCommit(false)
    clearCommitTimer()
    endingSession = false
    closeSocket()
    status.value = 'idle'
    partialTranscript.value = ''
    finalTranscript.value = ''
    realtimeSessionId.value = null
    errorCode.value = null
    errorMessage.value = null
    seq = 0
    startTs = 0
  }

  return {
    status,
    partialTranscript,
    finalTranscript,
    realtimeSessionId,
    errorCode,
    errorMessage,
    connectReview: (cardId: string, baseURL: string) => connect(cardId, baseURL),
    appendAudioChunk,
    commit,
    endSession,
    clearTranscript,
    reset,
  }
}
