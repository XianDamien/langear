import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  fetchStudySessionWithScope,
  submitReviewAsync,
  submitRating,
  getOSSSignedUrl,
} from '@/services/api/study'
import { extractApiError } from '@/services/http'
import type { Card, FsrsRating, FsrsState } from '@/types/domain'
import type {
  PollingResponseCompleted,
  SubmissionDisplayError,
  SubmitReviewResponseAsync,
  StudySessionCardResponse,
  StudySessionQuota,
  StudySessionScope,
  StudySessionSummary,
  SubmitRatingResponse,
} from '@/types/api'
import { parseNumericIdOrThrow } from '@/utils/ids'
import { formatBusinessIso } from '@/utils/businessTime'

export type RecordingState = 'idle' | 'recording' | 'stopped'
export type SubmitState = 'idle' | 'submitting' | 'success' | 'failed'
export type AsyncSubmitState = 'idle' | 'submitting' | 'processing' | 'completed' | 'failed'
export type UploadState = 'idle' | 'uploading' | 'uploaded' | 'failed'
export type StudySessionMode = 'lesson' | 'userDeck'

function resolveDueAt(payload: { due_at?: string | null; due?: string | null }): string | null {
  return payload.due_at ?? payload.due ?? null
}

function deriveIsNewCard(payload: {
  is_new_card?: boolean
  card_state?: FsrsState
  last_review_at?: string | null
}): boolean {
  if (payload.is_new_card != null) return payload.is_new_card
  return payload.last_review_at === null
}

function mapStudySessionCardToDomain(raw: StudySessionCardResponse): Card {
  return {
    id: String(raw.id),
    lessonId: String(raw.lesson_id),
    cardIndex: raw.card_index,
    frontText: raw.front_text,
    backText: raw.front_text,
    backTranslation: raw.back_text,
    frontAudio: raw.audio_path ?? '',
    difficulty: 0,
    ossAudioPath: raw.oss_audio_path ?? null,
    cardState: raw.card_state,
    dueAt: resolveDueAt(raw),
    isNewCard: deriveIsNewCard(raw),
    lastReviewAt: raw.last_review_at ?? null,
  }
}

export const useStudyStore = defineStore('study', () => {
  const lessonId = ref<string | null>(null)
  const userDeckId = ref<string | null>(null)
  const sessionMode = ref<StudySessionMode>('lesson')
  const lessonName = ref('')
  const cards = ref<Card[]>([])
  const currentIndex = ref(0)
  const isFlipped = ref(false)
  const recordingState = ref<RecordingState>('idle')
  const submitState = ref<SubmitState>('idle')
  const userTranscript = ref('')
  const liveTranscript = ref('')
  const userAudioUrl = ref<string | null>(null)
  const userAudioBase64 = ref<string | null>(null)
  const notes = ref('')
  const showTranslation = ref(false)
  const audioPlaying = ref(false)
  const selectedWord = ref<string | null>(null)
  const wordExplanation = ref('')
  const loading = ref(false)

  const uploadState = ref<UploadState>('idle')
  const asyncSubmitState = ref<AsyncSubmitState>('idle')
  const submissionId = ref<number | null>(null)
  const currentAudioElement = ref<HTMLAudioElement | null>(null)
  const lastFeedback = ref<PollingResponseCompleted | null>(null)
  const lastRatingResponse = ref<SubmitRatingResponse | null>(null)
  const sessionServerTime = ref('')
  const sessionDate = ref('')
  const sessionScope = ref<StudySessionScope>({})
  const sessionQuota = ref<StudySessionQuota>({})
  const sessionSummary = ref<StudySessionSummary | null>(null)

  const currentCard = computed(() => cards.value[currentIndex.value])
  const isLastCard = computed(() => currentIndex.value >= cards.value.length - 1)
  const progress = computed(() =>
    cards.value.length > 0 ? ((currentIndex.value + 1) / cards.value.length) * 100 : 0,
  )

  function resetTimestampAudio() {
    if (!currentAudioElement.value) return
    currentAudioElement.value.pause()
    currentAudioElement.value.currentTime = 0
    currentAudioElement.value = null
  }

  async function loadStudySession(id: string) {
    return loadLessonStudySession(id)
  }

  async function loadLessonStudySession(id: string) {
    loading.value = true
    lessonId.value = id
    userDeckId.value = null
    sessionMode.value = 'lesson'
    try {
      const parsedLessonId = parseNumericIdOrThrow(id, '课程 ID')
      const { data } = await fetchStudySessionWithScope({ lessonId: parsedLessonId })
      cards.value = data.cards.map(mapStudySessionCardToDomain)
      lessonName.value = data.lesson_name ?? data.lessonName ?? '学习任务'
      sessionServerTime.value = data.server_time
      sessionDate.value = data.session_date
      sessionScope.value = data.scope
      sessionQuota.value = data.quota
      sessionSummary.value = data.summary
      currentIndex.value = 0
      resetCardState()
    } finally {
      loading.value = false
    }
  }

  async function loadUserDeckStudySession(id: string) {
    loading.value = true
    lessonId.value = null
    userDeckId.value = id
    sessionMode.value = 'userDeck'
    try {
      const parsedUserDeckId = parseNumericIdOrThrow(id, '用户牌组 ID')
      const { data } = await fetchStudySessionWithScope({ userDeckId: parsedUserDeckId })
      cards.value = data.cards.map(mapStudySessionCardToDomain)
      lessonName.value = data.lesson_name ?? data.lessonName ?? '学习任务'
      sessionServerTime.value = data.server_time
      sessionDate.value = data.session_date
      sessionScope.value = data.scope
      sessionQuota.value = data.quota
      sessionSummary.value = data.summary
      currentIndex.value = 0
      resetCardState()
    } finally {
      loading.value = false
    }
  }

  function resetCardState() {
    isFlipped.value = false
    recordingState.value = 'idle'
    submitState.value = 'idle'
    userTranscript.value = ''
    liveTranscript.value = ''
    notes.value = ''
    showTranslation.value = false
    selectedWord.value = null
    wordExplanation.value = ''
    audioPlaying.value = false

    if (userAudioUrl.value) {
      if (userAudioUrl.value.startsWith('blob:')) {
        URL.revokeObjectURL(userAudioUrl.value)
      }
      userAudioUrl.value = null
    }

    userAudioBase64.value = null
    uploadState.value = 'idle'
    asyncSubmitState.value = 'idle'
    submissionId.value = null
    lastFeedback.value = null
    lastRatingResponse.value = null
    resetTimestampAudio()
  }

  async function createFeedbackSubmission(
    ossAudioPath: string,
    realtimeSessionId: string,
  ): Promise<number> {
    if (!currentCard.value) {
      throw new Error('No active lesson')
    }

    const parsedLessonId = parseNumericIdOrThrow(currentCard.value.lessonId, '课程 ID')
    const parsedCardId = parseNumericIdOrThrow(currentCard.value.id, '卡片 ID')
    const parsedUserDeckId = userDeckId.value
      ? parseNumericIdOrThrow(userDeckId.value, '用户牌组 ID')
      : null

    asyncSubmitState.value = 'submitting'

    try {
      const transcriptionText = userTranscript.value.trim() || liveTranscript.value.trim()
      const response = await submitReviewAsync({
        lesson_id: parsedLessonId,
        card_id: parsedCardId,
        oss_audio_path: ossAudioPath,
        realtime_session_id: realtimeSessionId,
        ...(sessionMode.value === 'userDeck' && parsedUserDeckId != null
          ? { user_deck_id: parsedUserDeckId }
          : {}),
        ...(transcriptionText ? { transcription_text: transcriptionText } : {}),
      })
      const data = response.data as SubmitReviewResponseAsync

      submissionId.value = data.submission_id
      asyncSubmitState.value = 'processing'
      return data.submission_id
    } catch (error) {
      const apiError = extractApiError(error)
      asyncSubmitState.value = 'failed'
      const submissionError: SubmissionDisplayError = {
        errorCode: apiError.code || null,
        errorMessage: apiError.message,
        requestId: apiError.request_id,
      }
      throw submissionError
    }
  }

  async function submitCardRating(rating: FsrsRating): Promise<'next' | 'summary'> {
    if (!submissionId.value) {
      throw new Error('No active submission')
    }

    submitState.value = 'submitting'
    try {
      const { data } = await submitRating(submissionId.value, { rating })
      lastRatingResponse.value = data

      if (currentCard.value) {
        const nextCards = [...cards.value]
        nextCards[currentIndex.value] = {
          ...currentCard.value,
          cardState: data.srs.state,
          dueAt: resolveDueAt(data.srs),
          isNewCard: data.srs.is_new_card ?? false,
          lastReviewAt:
            data.srs.last_review_at ?? currentCard.value.lastReviewAt ?? formatBusinessIso(new Date()),
        }
        cards.value = nextCards
      }

      submitState.value = 'success'
      if (isLastCard.value) {
        return 'summary'
      }
      return 'next'
    } catch {
      submitState.value = 'failed'
      throw new Error('评分提交失败，请重试')
    }
  }

  function jumpToTimestamp(timestamp: number) {
    if (!userAudioUrl.value) return

    if (!currentAudioElement.value || currentAudioElement.value.src !== userAudioUrl.value) {
      resetTimestampAudio()
      currentAudioElement.value = new Audio(userAudioUrl.value)
    }

    currentAudioElement.value.currentTime = timestamp
    void currentAudioElement.value.play().catch((error) => {
      console.warn('Failed to play timestamp audio:', error)
    })
  }

  function selectCard(index: number) {
    if (index < 0 || index >= cards.value.length) return
    currentIndex.value = index
    resetCardState()
  }

  function goNextCard() {
    if (!isLastCard.value) {
      selectCard(currentIndex.value + 1)
    }
  }

  async function flip() {
    isFlipped.value = true

    if (!userAudioUrl.value && currentCard.value?.ossAudioPath) {
      try {
        userAudioUrl.value = await getOSSSignedUrl(currentCard.value.ossAudioPath)
      } catch (error) {
        console.warn('Failed to get signed URL for recording:', error)
      }
    }
  }

  watch(userAudioUrl, (nextUrl, previousUrl) => {
    if (nextUrl !== previousUrl) {
      resetTimestampAudio()
    }
  })

  const loadLessonCards = loadStudySession

  return {
    lessonId,
    userDeckId,
    sessionMode,
    lessonName,
    cards,
    sessionServerTime,
    sessionDate,
    sessionScope,
    sessionQuota,
    sessionSummary,
    currentIndex,
    isFlipped,
    recordingState,
    submitState,
    userTranscript,
    liveTranscript,
    userAudioUrl,
    userAudioBase64,
    notes,
    showTranslation,
    audioPlaying,
    selectedWord,
    wordExplanation,
    loading,
    currentCard,
    isLastCard,
    progress,
    loadLessonCards,
    resetCardState,
    selectCard,
    goNextCard,
    flip,
    uploadState,
    asyncSubmitState,
    submissionId,
    lastFeedback,
    lastRatingResponse,
    createFeedbackSubmission,
    submitCardRating,
    jumpToTimestamp,
    resetTimestampAudio,
    loadStudySession,
    loadLessonStudySession,
    loadUserDeckStudySession,
  }
})
