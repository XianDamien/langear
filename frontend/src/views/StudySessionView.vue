<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { useStudyStore } from '@/stores/study'
import { useStudyTasksStore } from '@/stores/studyTasks'
import { useRecorder } from '@/composables/useRecorder'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useRealtimeAsr } from '@/composables/useRealtimeAsr'
import RetroButton from '@/components/ui/RetroButton.vue'
import RetellingCard from '@/components/study/cards/RetellingCard.vue'
import StudyTaskNav from '@/components/study/StudyTaskNav.vue'
import WordExplanation from '@/components/study/WordExplanation.vue'
import SummaryModal from '@/components/summary/SummaryModal.vue'
import type { SubmissionDisplayError } from '@/types/api'
import type { FsrsRating } from '@/types/domain'
import { parseNumericIdOrThrow } from '@/utils/ids'

const route = useRoute()
const router = useRouter()
const studyStore = useStudyStore()
const studyTasksStore = useStudyTasksStore()

const {
  cards,
  currentIndex,
  currentCard,
  isFlipped,
  userTranscript,
  liveTranscript,
  userAudioUrl,
  notes,
  showTranslation,
  selectedWord,
  wordExplanation,
  loading,
  lessonName,
  audioPlaying,
  uploadState,
  asyncSubmitState,
  lastFeedback,
} = storeToRefs(studyStore)
const { taskMap } = storeToRefs(studyTasksStore)

const recorder = useRecorder()
const audioPlayer = useAudioPlayer()
const realtimeAsr = useRealtimeAsr()

const isSummaryOpen = ref(false)
const summaryText = ref<string | null>(null)
const isSummaryLoading = ref(false)
const isTranslationLoading = ref(false)

function toSubmissionDisplayError(error: unknown): SubmissionDisplayError {
  if (
    typeof error === 'object' &&
    error !== null &&
    'errorMessage' in error &&
    typeof error.errorMessage === 'string'
  ) {
    return {
      errorCode:
        'errorCode' in error && typeof error.errorCode === 'string'
          ? error.errorCode
          : null,
      errorMessage: error.errorMessage,
      requestId:
        'requestId' in error && typeof error.requestId === 'string'
          ? error.requestId
          : null,
    }
  }

  return {
    errorCode: null,
    errorMessage: error instanceof Error ? error.message : '提交失败，请重试',
  }
}

const sessionTitle = computed(() => lessonName.value || '学习任务')

const ratingDisabled = computed(() =>
  studyStore.submitState === 'submitting' ||
    studyStore.asyncSubmitState === 'processing' ||
    studyStore.asyncSubmitState === 'submitting' ||
    studyStore.asyncSubmitState === 'failed' ||
    studyStore.asyncSubmitState === 'idle'
)

const currentTask = computed(() => studyTasksStore.getTask(currentCard.value?.id))

function shouldKeepCardBackVisible() {
  const task = currentTask.value
  if (!task) return false

  return (
    task.reviewStatus === 'submitting' ||
    task.reviewStatus === 'processing' ||
    task.reviewStatus === 'completed' ||
    task.reviewStatus === 'failed' ||
    Boolean(task.submissionId)
  )
}

async function waitForRecordingBlob(timeoutMs = 2500): Promise<boolean> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (recorder.recordingBlob.value && recorder.audioUrl.value) return true
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  return false
}

async function waitForRealtimeSessionId(timeoutMs = 1200): Promise<boolean> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (realtimeAsr.realtimeSessionId.value) return true
    await new Promise((resolve) => setTimeout(resolve, 30))
  }
  return Boolean(realtimeAsr.realtimeSessionId.value)
}

function playCurrentAudio() {
  if (!currentCard.value) return
  if (currentCard.value.frontAudio) {
    audioPlayer.play(currentCard.value.frontAudio)
  } else {
    audioPlayer.speakText(currentCard.value.backText)
  }
}

function clearCardSession() {
  audioPlayer.stop()
  studyStore.audioPlaying = false
  studyStore.resetTimestampAudio()
  realtimeAsr.endSession()
  realtimeAsr.reset()
  recorder.reset()
}

watch(
  () => route.params.lessonId,
  async (lessonId) => {
    if (typeof lessonId !== 'string' || !lessonId) return
    clearCardSession()
    await studyStore.loadStudySession(lessonId)
    studyTasksStore.initializeLesson(lessonId, cards.value)
    try {
      await studyTasksStore.restoreLessonHistory(lessonId, cards.value)
    } catch (error) {
      console.error('Failed to restore study submission history:', error)
      ElMessage.warning('任务历史加载失败，请确认后端实例和数据库是否正确')
    }
  },
  { immediate: true },
)

watch(cards, (nextCards) => {
  const lessonId = route.params.lessonId
  if (typeof lessonId !== 'string' || !lessonId) return
  studyTasksStore.initializeLesson(lessonId, nextCards)
})

watch(currentIndex, () => {
  clearCardSession()
})

watch(
  () => audioPlayer.isPlaying.value,
  (isPlaying) => {
    studyStore.audioPlaying = isPlaying
  },
  { immediate: true },
)

watch(
  currentTask,
  async (task) => {
    studyStore.submissionId = task?.submissionId ?? null
    studyStore.uploadState = task?.uploadState ?? 'idle'
    studyStore.asyncSubmitState =
      task?.reviewStatus === 'submitting' ||
      task?.reviewStatus === 'processing' ||
      task?.reviewStatus === 'completed' ||
      task?.reviewStatus === 'failed'
        ? task.reviewStatus
        : 'idle'
    studyStore.lastFeedback = task?.result ?? null
    studyStore.isFlipped = shouldKeepCardBackVisible()

    if (task?.result?.transcription.text) {
      studyStore.userTranscript = task.result.transcription.text
      studyStore.liveTranscript = task.result.transcription.text
    }

    if (task?.signedAudioUrl) {
      studyStore.userAudioUrl = task.signedAudioUrl
    } else if (task?.result?.oss_audio_path && currentCard.value) {
      const signedAudioUrl = await studyTasksStore.ensureSignedAudioUrl(
        currentCard.value.id,
        currentIndex.value,
      )
      if (signedAudioUrl) {
        studyStore.userAudioUrl = signedAudioUrl
      }
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  clearCardSession()
  studyStore.resetTimestampAudio()
  audioPlayer.stop()
  studyTasksStore.teardown()
})

function beginRecording() {
  realtimeAsr.finalTranscript.value = ''
  studyStore.recordingState = 'recording'
  studyStore.userTranscript = ''
  studyStore.liveTranscript = ''
  studyStore.uploadState = 'idle'
  studyStore.asyncSubmitState = 'idle'
}

function syncStoppedRecordingState() {
  studyStore.userAudioUrl = recorder.audioUrl.value
  studyStore.recordingState = 'stopped'
}

async function uploadRecordingForCard(cardId: string, cardIndex: number, recordingBlob: Blob) {
  studyStore.uploadState = 'uploading'
  studyTasksStore.setUploadState(cardId, cardIndex, 'uploading')
  const ossPath = await recorder.uploadToOSS(cardId, recordingBlob)

  if (ossPath) {
    studyStore.uploadState = 'uploaded'
    studyTasksStore.setUploadState(cardId, cardIndex, 'uploaded')
    ElMessage.success('录音上传成功')
    return ossPath
  }

  studyStore.uploadState = 'failed'
  studyTasksStore.setUploadState(cardId, cardIndex, 'failed')
}

async function handleStopRecordingFlow() {
  syncStoppedRecordingState()
  const committed = await realtimeAsr.commit()
  if (!committed || !realtimeAsr.finalTranscript.value.trim()) {
    ElMessage.warning('未获得实时转写结果，暂无法翻面')
    return
  }

  studyStore.liveTranscript = realtimeAsr.finalTranscript.value
  studyStore.userTranscript = realtimeAsr.finalTranscript.value
  studyStore.uploadState = 'idle'
}

async function startRealtimeForCurrentCard(): Promise<boolean> {
  if (!currentCard.value) return false

  try {
    const lessonId = parseNumericIdOrThrow(route.params.lessonId as string, '课程 ID')
    const cardId = parseNumericIdOrThrow(currentCard.value.id, '卡片 ID')
    const connected = await realtimeAsr.connect(lessonId, cardId)
    const hasSessionId = connected ? await waitForRealtimeSessionId() : false
    if (!connected || !hasSessionId) {
      ElMessage.error('实时识别连接失败，请重试录音')
      return false
    }
    return true
  } catch (error) {
    const message = error instanceof Error ? error.message : '无法开始录音'
    ElMessage.error(message)
    return false
  }
}

function handleRealtimePcmChunk(chunkBase64: string) {
  if (!chunkBase64) return
  if (realtimeAsr.status.value === 'failed') return
  realtimeAsr.appendAudioChunk(chunkBase64)
}

async function toggleRecording() {
  if (recorder.isRecording.value) {
    recorder.stopRecording()
    const hasBlob = await waitForRecordingBlob()
    if (!hasBlob) {
      ElMessage.error('录音处理失败，请重试')
      return
    }
    await handleStopRecordingFlow()
  } else {
    if (audioPlayer.isPlaying.value || audioPlaying.value) {
      ElMessage.warning('建议完整听完原音频之后再录音')
      return
    }

    realtimeAsr.endSession()
    realtimeAsr.reset()
    const connected = await startRealtimeForCurrentCard()
    if (!connected) return

    const started = await recorder.startRecording(handleRealtimePcmChunk)
    if (!started) {
      realtimeAsr.endSession()
      realtimeAsr.reset()
      studyStore.recordingState = 'idle'
      return
    }

    beginRecording()
  }
}

async function handleGrade(rating: FsrsRating) {
  if (!studyStore.submissionId) {
    ElMessage.warning('请先翻面等待 AI 反馈任务创建')
    return
  }

  if (asyncSubmitState.value !== 'completed') {
    ElMessage.info('AI 评测中，请稍候完成后再评分')
    return
  }

  try {
    const result = await studyStore.submitCardRating(rating)
    if (result === 'summary') {
      isSummaryOpen.value = true
    } else {
      studyStore.goNextCard()
    }
  } catch {
    ElMessage.error('评分提交失败，请重试')
  }
}

async function handleFlip() {
  if (recorder.isRecording.value) {
    ElMessage.warning('请先停止录音')
    return
  }

  if (!recorder.recordingBlob.value) {
    ElMessage.warning('请先完成录音后再翻面')
    return
  }

  if (!realtimeAsr.realtimeSessionId.value || !realtimeAsr.finalTranscript.value.trim()) {
    ElMessage.warning('未获得实时转写结果，暂无法翻面')
    return
  }

  if (realtimeAsr.status.value === 'failed') {
    ElMessage.error('实时识别连接失败，请重试录音')
    return
  }

  if (!currentCard.value) return

  const activeCard = currentCard.value
  const activeCardIndex = currentIndex.value
  const recordingBlob = recorder.recordingBlob.value
  const realtimeSessionId = realtimeAsr.realtimeSessionId.value

  studyStore.userTranscript = realtimeAsr.finalTranscript.value
  studyStore.liveTranscript = realtimeAsr.finalTranscript.value

  audioPlayer.stop()
  studyStore.audioPlaying = false

  await studyStore.flip()
  realtimeAsr.endSession()

  void (async () => {
    if (studyStore.uploadState === 'uploading') return

    try {
      const ossPath = await uploadRecordingForCard(activeCard.id, activeCardIndex, recordingBlob)

      if (!ossPath || studyStore.uploadState !== 'uploaded') {
        studyStore.asyncSubmitState = 'failed'
        studyTasksStore.setSubmissionFailed(activeCard.id, activeCardIndex, null, '上传失败')
        return
      }

      studyStore.asyncSubmitState = 'submitting'
      studyTasksStore.setSubmissionPending(activeCard.id, activeCardIndex)
      const submissionId = await studyStore.createFeedbackSubmission(
        ossPath,
        realtimeSessionId,
      )
      studyTasksStore.registerSubmission(activeCard.id, activeCardIndex, submissionId)
      ElMessage.info('AI 评测中，请稍候...')
    } catch (error) {
      const submissionError = toSubmissionDisplayError(error)
      studyStore.uploadState = 'failed'
      studyStore.asyncSubmitState = 'failed'
      studyTasksStore.setSubmissionFailed(
        activeCard.id,
        activeCardIndex,
        submissionError.errorCode,
        submissionError.errorMessage,
      )
      ElMessage.error(
        submissionError.errorCode
          ? `${submissionError.errorCode}: ${submissionError.errorMessage}`
          : submissionError.errorMessage,
      )
    }
  })()
}

function handleSelectCard(index: number) {
  if (index === currentIndex.value) return
  studyStore.selectCard(index)
}

watch(asyncSubmitState, (newState) => {
  if (newState === 'completed' && studyStore.isLastCard) {
    setTimeout(() => {
      isSummaryOpen.value = true
    }, 1000)
  }
})

watch(
  () => realtimeAsr.partialTranscript.value,
  (text) => {
    if (!text) return
    studyStore.liveTranscript = text
  },
)

watch(
  () => realtimeAsr.finalTranscript.value,
  (text) => {
    if (!text) return
    studyStore.liveTranscript = text
    studyStore.userTranscript = text
  },
)

function handleWordClick(word: string) {
  studyStore.selectedWord = word
  studyStore.wordExplanation = '正在加载 AI 解析...'
  setTimeout(() => {
    studyStore.wordExplanation = `"${word}" 是本句中的关键词。在此语境下表示...（AI 解析示例）`
  }, 800)
}

function handleShowTranslation() {
  studyStore.showTranslation = true
  if (currentCard.value?.backTranslation) return
  isTranslationLoading.value = true
  setTimeout(() => {
    isTranslationLoading.value = false
  }, 1000)
}

function handleSummary() {
  isSummaryLoading.value = true
  summaryText.value = null
  setTimeout(() => {
    summaryText.value = '本课已完成。建议重点关注发音连读与动词时态变化，并回听不顺畅的句子。'
    isSummaryLoading.value = false
  }, 1200)
}

function exitSummary() {
  isSummaryOpen.value = false
  const lessonId = route.params.lessonId as string
  router.push(`/summary/${lessonId}`)
}

function exitStudy() {
  router.push('/library')
}
</script>

<template>
  <div
    class="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-4 sm:px-6 sm:py-6"
    data-testid="study-session-view"
  >
    <div class="mb-4 grid grid-cols-[minmax(5rem,1fr)_auto_minmax(5rem,1fr)] items-center gap-3 sm:mb-6">
      <div class="flex min-w-[5rem]">
        <RetroButton
          variant="ghost"
          size="sm"
          class="w-[5rem] justify-center"
          @click="exitStudy"
        >
          退出
        </RetroButton>
      </div>
      <div
        class="min-w-0 text-center text-lg font-bold uppercase text-brand-accent sm:text-xl"
        data-testid="study-lesson-title"
      >
        {{ sessionTitle }}
        <span class="font-pixel">{{ currentIndex + 1 }}</span>
        /
        <span class="font-pixel">{{ cards.length }}</span>
      </div>
      <div
        class="min-w-[5rem]"
        aria-hidden="true"
      />
    </div>

    <StudyTaskNav
      v-if="cards.length > 0"
      :cards="cards"
      :current-index="currentIndex"
      :task-map="taskMap"
      @select="handleSelectCard"
    />

    <div
      v-if="loading"
      class="flex-1 flex items-center justify-center text-slate-500"
      data-testid="study-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="currentCard"
      class="relative flex flex-1 min-h-0 flex-col pb-4"
      data-testid="study-card"
    >
      <RetellingCard
        :card="currentCard"
        :is-flipped="isFlipped"
        :audio-playing="audioPlaying"
        :is-recording="recorder.isRecording.value"
        :live-transcript="liveTranscript"
        :user-transcript="userTranscript"
        :user-audio-url="userAudioUrl"
        :upload-state="uploadState"
        :upload-progress="recorder.uploadProgress.value"
        :feedback="lastFeedback"
        :async-submit-state="asyncSubmitState"
        :error-code="currentTask?.errorCode"
        :error-message="currentTask?.errorMessage"
        :show-translation="showTranslation"
        :translation-loading="isTranslationLoading"
        :notes="notes"
        :rating-disabled="ratingDisabled"
        @play-reference="playCurrentAudio"
        @toggle-recording="toggleRecording"
        @flip="handleFlip"
        @show-translation="handleShowTranslation"
        @word-click="handleWordClick"
        @grade="handleGrade"
        @update:notes="studyStore.notes = $event"
      />

      <WordExplanation
        v-if="selectedWord"
        :word="selectedWord"
        :explanation="wordExplanation"
        @close="studyStore.selectedWord = null"
      />

      <SummaryModal
        v-if="isSummaryOpen"
        :loading="isSummaryLoading"
        :summary-text="summaryText"
        @generate="handleSummary"
        @exit="exitSummary"
      />
    </div>
  </div>
</template>
