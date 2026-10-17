import { ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import OSS from 'ali-oss'
import {
  createRecordingSession,
  RecordingStartError,
  type RecordingSession,
} from '@/adapters/browser/recording'
import { getSTSToken } from '@/services/api/study'
import { normalizeOssRegion } from '@/services/ossRegion'
import { buildE2EOssAudioPath, isE2EMode } from '@/utils/e2e'
import { formatBusinessDateStamp } from '@/utils/businessTime'

export function useRecorder() {
  const isRecording = ref(false)
  const recordingBlob = ref<Blob | null>(null)
  const audioUrl = ref<string | null>(null)
  const audioBase64 = ref<string | null>(null)

  const uploadState = ref<'idle' | 'uploading' | 'uploaded' | 'failed'>('idle')
  const ossAudioPath = ref<string | null>(null)
  const uploadProgress = ref(0)
  type OssPutOptions = NonNullable<Parameters<InstanceType<typeof OSS>['put']>[2]>

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

  async function startRecording(onRealtimePcmChunk?: (pcmBase64: string) => void, demoCardId?: string): Promise<boolean> {
    if (isE2EMode) {
      if (!demoCardId) return false
      const { getMockRecording } = await import('@/services/mock/study')
      const response = await fetch(getMockRecording(demoCardId).audioUrl)
      if (!response.ok) return false
      const blob = await response.blob()
      recordingBlob.value = blob
      if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
      audioUrl.value = URL.createObjectURL(blob)
      isRecording.value = true
      uploadState.value = 'idle'
      uploadProgress.value = 0

      if (onRealtimePcmChunk) {
        window.setTimeout(() => {
          if (isRecording.value) onRealtimePcmChunk('ZTItdGVzdC1wY20=')
        }, 50)
      }

      return true
    }

    try {
      releaseRecordingSession()
      const session = await createRecordingSession({ onRealtimePcmChunk })
      recordingSession = session
      chunks = []

      session.setOnDataAvailable((chunk) => {
        chunks.push(chunk)
      })

      session.setOnStop(() => {
        const blob = new Blob(chunks, { type: 'audio/webm' })
        recordingBlob.value = blob

        if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
        audioUrl.value = URL.createObjectURL(blob)
        if (recordingSession === session) {
          recordingSession = null
        }
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
    if (isE2EMode) {
      isRecording.value = false
      return
    }

    if (recordingSession && recordingSession.getState() !== 'inactive') {
      recordingSession.stop()
      isRecording.value = false
    }
  }

  /**
   * 上传音频到 OSS
   */
  async function uploadToOSS(cardId: string, blobOverride?: Blob): Promise<string | null> {
    const blobToUpload = blobOverride ?? recordingBlob.value
    if (!blobToUpload) {
      ElMessage.error('没有录音数据')
      return null
    }

    if (isE2EMode) {
      uploadState.value = 'uploading'
      uploadProgress.value = 100
      const path = buildE2EOssAudioPath(cardId)
      ossAudioPath.value = path
      uploadState.value = 'uploaded'
      return path
    }

    uploadState.value = 'uploading'
    uploadProgress.value = 0

    try {
      const { data: stsToken } = await getSTSToken()

      const client = new OSS({
        region: normalizeOssRegion(stsToken.region),
        accessKeyId: stsToken.access_key_id,
        accessKeySecret: stsToken.access_key_secret,
        stsToken: stsToken.security_token,
        bucket: stsToken.bucket,
        secure: true,
        refreshSTSToken: async () => {
          const { data: newToken } = await getSTSToken()
          return {
            accessKeyId: newToken.access_key_id,
            accessKeySecret: newToken.access_key_secret,
            stsToken: newToken.security_token
          }
        }
      })

      const timestamp = Date.now()
      const dateStr = formatBusinessDateStamp(new Date())
      const filename = `${cardId}_${timestamp}.webm`
      const uploadPrefix = (stsToken.upload_prefix || 'recordings').replace(/^\/+|\/+$/g, '')
      const path = `${uploadPrefix}/${dateStr}/${filename}`

      const result = await client.put(path, blobToUpload, {
        progress: (p: number) => {
          uploadProgress.value = Math.round(p * 100)
        }
      } as OssPutOptions)

      if (result?.res?.status === 200) {
        ossAudioPath.value = path
        uploadState.value = 'uploaded'
        return path
      } else {
        throw new Error(`Upload failed with status ${result?.res?.status ?? 'unknown'}`)
      }
    } catch (error) {
      console.error('OSS upload failed:', error)
      uploadState.value = 'failed'

      const origin = typeof window !== 'undefined' ? window.location.origin : ''
      const rawMessage = error instanceof Error ? error.message : String(error)
      const isLikelyCors = /CORS|Access-Control-Allow-Origin|preflight|ERR_FAILED/i.test(rawMessage)
      if (isLikelyCors && origin) {
        ElMessage.error(`音频上传失败：OSS CORS 未放行（请在 OSS 控制台允许 ${origin}）`)
      } else {
        ElMessage.error('音频上传失败，请重试')
      }
      return null
    }
  }

  function reset() {
    if (audioUrl.value) {
      URL.revokeObjectURL(audioUrl.value)
      audioUrl.value = null
    }
    recordingBlob.value = null
    audioBase64.value = null
    isRecording.value = false

    uploadState.value = 'idle'
    ossAudioPath.value = null
    uploadProgress.value = 0
    releaseRecordingSession()
  }

  onUnmounted(() => {
    releaseRecordingSession()
    if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  })

  return {
    isRecording,
    recordingBlob,
    audioUrl,
    audioBase64,
    startRecording,
    stopRecording,
    reset,
    uploadState,
    ossAudioPath,
    uploadProgress,
    uploadToOSS
  }
}
