import { ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createRecordingSession,
  RecordingStartError,
  type RecordingSession,
} from '@/adapters/browser/recording'

/** Records the learner's microphone locally. Upload is owned by Review, not OSS. */
export function useRecorder() {
  const isRecording = ref(false)
  const recordingBlob = ref<Blob | null>(null)
  const audioUrl = ref<string | null>(null)

  let recordingSession: RecordingSession | null = null
  let chunks: BlobPart[] = []

  function releaseRecordingSession() {
    recordingSession?.dispose()
    recordingSession = null
  }

  function resolveRecordingErrorMessage(error: unknown): string {
    if (error instanceof RecordingStartError) {
      switch (error.code) {
        case 'permission-denied':
          return '麦克风权限被拒绝'
        case 'unsupported':
          return '当前环境不支持录音'
        default:
          return '录音启动失败，请重试'
      }
    }
    return '录音启动失败，请重试'
  }

  async function startRecording(onRealtimePcmChunk?: (pcmBase64: string) => void): Promise<boolean> {
    try {
      releaseRecordingSession()
      const session = await createRecordingSession({ onRealtimePcmChunk })
      recordingSession = session
      chunks = []

      // A new take always overwrites the cached recording.
      recordingBlob.value = null
      if (audioUrl.value) {
        URL.revokeObjectURL(audioUrl.value)
        audioUrl.value = null
      }

      session.setOnDataAvailable((chunk) => {
        chunks.push(chunk)
      })

      session.setOnStop(() => {
        const blob = new Blob(chunks, { type: 'audio/webm' })
        recordingBlob.value = blob
        if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
        audioUrl.value = URL.createObjectURL(blob)
        if (recordingSession === session) recordingSession = null
      })

      session.start(250)
      isRecording.value = true
      return true
    } catch (error) {
      releaseRecordingSession()
      ElMessage.error(resolveRecordingErrorMessage(error))
      return false
    }
  }

  function stopRecording() {
    if (recordingSession && recordingSession.getState() !== 'inactive') {
      recordingSession.stop()
      isRecording.value = false
    }
  }

  function reset() {
    if (audioUrl.value) {
      URL.revokeObjectURL(audioUrl.value)
      audioUrl.value = null
    }
    recordingBlob.value = null
    isRecording.value = false
    releaseRecordingSession()
  }

  onUnmounted(() => {
    releaseRecordingSession()
    if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  })

  return { isRecording, recordingBlob, audioUrl, startRecording, stopRecording, reset }
}
