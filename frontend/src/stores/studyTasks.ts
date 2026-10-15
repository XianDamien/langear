import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getOSSSignedUrl, listStudySubmissions, pollSubmissionResult } from '@/services/api/study'
import type {
  PollingResponseCompleted,
  ProgressState,
  StudySubmissionListItem,
} from '@/types/api'
import type { Card } from '@/types/domain'
import { parseNumericIdOrThrow } from '@/utils/ids'
import { formatBusinessIso } from '@/utils/businessTime'
import type { UploadState } from './study'

export type TaskReviewStatus = 'idle' | 'submitting' | 'processing' | 'completed' | 'failed'

export interface StudyTaskEntry {
  cardId: string
  cardIndex: number
  submissionId: number | null
  uploadState: UploadState
  reviewStatus: TaskReviewStatus
  progress: ProgressState | null
  result: PollingResponseCompleted | null
  signedAudioUrl: string | null
  errorCode: string | null
  errorMessage: string | null
  createdAt: string | null
  updatedAt: number | null
}

function createEmptyTask(cardId: string, cardIndex: number): StudyTaskEntry {
  return {
    cardId,
    cardIndex,
    submissionId: null,
    uploadState: 'idle',
    reviewStatus: 'idle',
    progress: null,
    result: null,
    signedAudioUrl: null,
    errorCode: null,
    errorMessage: null,
    createdAt: null,
    updatedAt: null,
  }
}

export const useStudyTasksStore = defineStore('studyTasks', () => {
  const lessonId = ref<string | null>(null)
  const taskMap = ref<Record<string, StudyTaskEntry>>({})
  const pollingTimers = new Map<string, number>()

  const orderedTasks = computed(() =>
    Object.values(taskMap.value).sort((left, right) => left.cardIndex - right.cardIndex),
  )

  function ensureTask(cardId: string, cardIndex: number): StudyTaskEntry {
    const existing = taskMap.value[cardId]
    if (existing) {
      existing.cardIndex = cardIndex
      return existing
    }

    const nextTask = createEmptyTask(cardId, cardIndex)
    taskMap.value = {
      ...taskMap.value,
      [cardId]: nextTask,
    }
    return nextTask
  }

  function patchTask(cardId: string, cardIndex: number, patch: Partial<StudyTaskEntry>) {
    const current = ensureTask(cardId, cardIndex)
    taskMap.value = {
      ...taskMap.value,
      [cardId]: {
        ...current,
        ...patch,
        updatedAt: Date.now(),
      },
    }
  }

  function initializeLesson(nextLessonId: string, cards: Card[]) {
    if (lessonId.value !== nextLessonId) {
      teardown()
      lessonId.value = nextLessonId
    }

    const nextTaskMap: Record<string, StudyTaskEntry> = {}
    cards.forEach((card, index) => {
      nextTaskMap[card.id] = taskMap.value[card.id] ?? createEmptyTask(card.id, index)
      nextTaskMap[card.id]!.cardIndex = index
    })
    taskMap.value = nextTaskMap
  }

  function setUploadState(cardId: string, cardIndex: number, uploadState: UploadState) {
    patchTask(cardId, cardIndex, {
      uploadState,
      ...(uploadState === 'failed'
        ? { reviewStatus: 'failed', errorCode: null, errorMessage: '上传失败' }
        : {}),
    })
  }

  function setSubmissionPending(cardId: string, cardIndex: number) {
    patchTask(cardId, cardIndex, {
      uploadState: 'uploaded',
      reviewStatus: 'submitting',
      errorCode: null,
      errorMessage: null,
      createdAt: ensureTask(cardId, cardIndex).createdAt ?? formatBusinessIso(new Date()),
    })
  }

  function setSubmissionFailed(
    cardId: string,
    cardIndex: number,
    errorCode: string | null,
    errorMessage: string,
  ) {
    patchTask(cardId, cardIndex, {
      reviewStatus: 'failed',
      errorCode,
      errorMessage,
    })
  }

  function stopPolling(cardId: string) {
    const timer = pollingTimers.get(cardId)
    if (!timer) return
    window.clearInterval(timer)
    pollingTimers.delete(cardId)
  }

  async function handleCompleted(cardId: string, cardIndex: number, data: PollingResponseCompleted) {
    stopPolling(cardId)

    const current = ensureTask(cardId, cardIndex)
    let signedAudioUrl = current.signedAudioUrl
    if (data.oss_audio_path && !signedAudioUrl) {
      try {
        signedAudioUrl = await getOSSSignedUrl(data.oss_audio_path)
      } catch (error) {
        console.warn('Failed to get task signed audio URL:', error)
      }
    }

    patchTask(cardId, cardIndex, {
      reviewStatus: 'completed',
      progress: null,
      result: data,
      signedAudioUrl: signedAudioUrl ?? null,
      errorCode: null,
      errorMessage: null,
      createdAt: current.createdAt ?? formatBusinessIso(new Date()),
    })
  }

  function handleFailed(cardId: string, cardIndex: number, errorCode: string | null, errorMessage: string) {
    stopPolling(cardId)
    patchTask(cardId, cardIndex, {
      reviewStatus: 'failed',
      progress: null,
      errorCode,
      errorMessage,
      createdAt: ensureTask(cardId, cardIndex).createdAt ?? formatBusinessIso(new Date()),
    })
  }

  function startPolling(cardId: string, cardIndex: number, submissionId: number) {
    stopPolling(cardId)

    const pollInterval = Number(import.meta.env.VITE_POLLING_INTERVAL) || 1500
    const timeout = Number(import.meta.env.VITE_POLLING_TIMEOUT) || 30000
    const startTime = Date.now()

    const timer = window.setInterval(async () => {
      if (Date.now() - startTime > timeout) {
        handleFailed(cardId, cardIndex, 'POLLING_TIMEOUT', '处理超时，请稍后查看')
        return
      }

      try {
        const { data } = await pollSubmissionResult(submissionId)
        if (data.status === 'completed') {
          await handleCompleted(cardId, cardIndex, data)
          return
        }

        if (data.status === 'failed') {
          handleFailed(cardId, cardIndex, data.error_code, data.error_message)
          return
        }

        patchTask(cardId, cardIndex, {
          reviewStatus: 'processing',
          progress: data.progress ?? null,
        })
      } catch (error) {
        console.error('Task polling error:', error)
      }
    }, pollInterval)

    pollingTimers.set(cardId, timer)
  }

  function registerSubmission(cardId: string, cardIndex: number, submissionId: number) {
    patchTask(cardId, cardIndex, {
      submissionId,
      uploadState: 'uploaded',
      reviewStatus: 'processing',
      progress: null,
      errorCode: null,
      errorMessage: null,
      createdAt: ensureTask(cardId, cardIndex).createdAt ?? formatBusinessIso(new Date()),
    })
    startPolling(cardId, cardIndex, submissionId)
  }

  async function ensureSignedAudioUrl(cardId: string, cardIndex: number) {
    const task = ensureTask(cardId, cardIndex)
    if (task.signedAudioUrl || !task.result?.oss_audio_path) return task.signedAudioUrl

    try {
      const signedAudioUrl = await getOSSSignedUrl(task.result.oss_audio_path)
      patchTask(cardId, cardIndex, { signedAudioUrl })
      return signedAudioUrl
    } catch (error) {
      console.warn('Failed to get task signed audio URL:', error)
      return null
    }
  }

  function buildCompletedResult(item: StudySubmissionListItem): PollingResponseCompleted | null {
    if (item.status !== 'completed' || !item.transcription || !item.feedback) {
      return null
    }

    return {
      submission_id: item.submission_id,
      status: 'completed',
      result_type: 'single',
      transcription: item.transcription,
      feedback: item.feedback,
      oss_audio_path: item.oss_audio_path,
    }
  }

  function mergeHistoryItem(cardId: string, cardIndex: number, item: StudySubmissionListItem) {
    const result = buildCompletedResult(item)
    patchTask(cardId, cardIndex, {
      submissionId: item.submission_id,
      uploadState: 'uploaded',
      reviewStatus: item.status,
      progress: null,
      result,
      signedAudioUrl: null,
      errorCode: item.error_code,
      errorMessage: item.error_message,
      createdAt: item.created_at,
    })

    if (item.status === 'processing') {
      startPolling(cardId, cardIndex, item.submission_id)
      return
    }

    stopPolling(cardId)
  }

  async function restoreLessonHistory(nextLessonId: string, cards: Card[]) {
    const parsedLessonId = parseNumericIdOrThrow(nextLessonId, '课程 ID')
    const { data } = await listStudySubmissions({ lesson_id: parsedLessonId })

    const latestByCardId = new Map<string, StudySubmissionListItem>()
    for (const item of data) {
      if (item.card_id == null) continue
      const cardId = String(item.card_id)
      if (!latestByCardId.has(cardId)) {
        latestByCardId.set(cardId, item)
      }
    }

    cards.forEach((card, index) => {
      const history = latestByCardId.get(card.id)
      if (!history) {
        stopPolling(card.id)
        return
      }
      mergeHistoryItem(card.id, index, history)
    })
  }

  function getTask(cardId: string | null | undefined): StudyTaskEntry | null {
    if (!cardId) return null
    return taskMap.value[cardId] ?? null
  }

  function teardown() {
    pollingTimers.forEach((timer) => window.clearInterval(timer))
    pollingTimers.clear()
    taskMap.value = {}
    lessonId.value = null
  }

  return {
    lessonId,
    taskMap,
    orderedTasks,
    initializeLesson,
    setUploadState,
    setSubmissionPending,
    setSubmissionFailed,
    registerSubmission,
    restoreLessonHistory,
    ensureSignedAudioUrl,
    getTask,
    stopPolling,
    teardown,
  }
})
