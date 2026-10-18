<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import FlashcardContainer from '../modules/FlashcardContainer.vue'
import AudioRecorderPanel from '../modules/AudioRecorderPanel.vue'
import AIFeedbackPanel from '../modules/AIFeedbackPanel.vue'
import StudyNotesPanel from '../modules/StudyNotesPanel.vue'
import TranscriptComparisonPanel from '../TranscriptComparisonPanel.vue'
import GradeButtons from '../GradeButtons.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import type { Card, FsrsRating } from '@/types/domain'
import type { PollingResponseCompleted } from '@/types/api'

const props = defineProps<{
  card: Card
  isFlipped: boolean
  
  // Audio/Recording Props
  audioPlaying: boolean
  isRecording: boolean
  liveTranscript: string
  userTranscript: string
  userAudioUrl: string | null
  uploadState?: 'idle' | 'uploading' | 'uploaded' | 'failed'
  uploadProgress?: number
  
  // Feedback Props
  feedback: Pick<PollingResponseCompleted, 'feedback'> | null
  asyncSubmitState: string
  errorCode?: string | null
  errorMessage?: string | null
  
  // Translation Props
  showTranslation: boolean
  translationLoading: boolean
  
  // Notes
  notes: string
  
  // Rating
  ratingDisabled: boolean
  flipDisabled?: boolean
  controlsDisabled?: boolean
}>()

const emit = defineEmits<{
  playReference: []
  toggleRecording: []
  flip: []
  showTranslation: []
  wordClick: [word: string]
  grade: [rating: FsrsRating]
  'update:notes': [value: string]
}>()

const audioPlayerRef = ref<InstanceType<typeof TranscriptComparisonPanel> | null>(null)

function handleFlipClick() {
  if (props.isRecording) {
    ElMessage.warning('请先停止录音')
    return
  }
  emit('flip')
}

const recordingDisabled = computed(() => props.controlsDisabled || (props.audioPlaying && !props.isRecording))

function handleTimestampClick(timestamp: number) {
  audioPlayerRef.value?.jumpToUserAudio(timestamp)
}
</script>

<template>
  <FlashcardContainer :is-flipped="isFlipped">
    <template #toolbar><slot name="toolbar" /></template>
    <template #front>
      <AudioRecorderPanel
        :audio-playing="audioPlaying"
        :is-recording="isRecording"
        :live-transcript="liveTranscript"
        :user-transcript="userTranscript"
        :upload-state="uploadState"
        :upload-progress="uploadProgress"
        :recording-disabled="recordingDisabled"
        @play-reference="emit('playReference')"
        @toggle-recording="emit('toggleRecording')"
      />
      
      <slot name="front-status" />
      <p
        v-if="audioPlaying && !isRecording"
        data-testid="record-hint"
        class="mt-3 text-center text-sm text-brand-alert"
      >
        建议完整听完原音频之后再录音
      </p>

      <div class="mt-4 flex w-full justify-center border-t border-slate-200 pt-3">
        <RetroButton
          variant="primary"
          class="w-full max-w-md rounded-md"
          :disabled="flipDisabled || uploadState === 'uploading'"
          data-testid="flip-button"
          @click="handleFlipClick"
        >
          翻面复盘
        </RetroButton>
      </div>
    </template>

    <template #back>
      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1"
        data-testid="study-card-content">
        <TranscriptComparisonPanel
          ref="audioPlayerRef"
          :reference-audio-url="card.frontAudio || null"
          :user-audio-url="userAudioUrl"
          :original-text="card.backText"
          :transcript-text="userTranscript"
          :translation-text="card.backTranslation || ''"
          :show-translation="showTranslation"
          :translation-loading="translationLoading"
          :nouns="card.grammarInfo?.nouns"
          :verbs="card.grammarInfo?.verbs"
          @word-click="emit('wordClick', $event)"
          @toggle-translation="emit('showTranslation')"
        />

        <slot name="processing" />
        <slot name="feedback"><AIFeedbackPanel
          :feedback="feedback"
          :loading="asyncSubmitState === 'processing' || asyncSubmitState === 'submitting'"
          :error-code="errorCode"
          :error-message="errorMessage"
          @timestamp-click="handleTimestampClick"
        /></slot>

        <StudyNotesPanel
          :notes="notes"
          @update:notes="emit('update:notes', $event)"
        />
      </div>

      <div class="mt-3 shrink-0 border-t border-slate-200 pt-3"
        data-testid="study-rating-bar">
        <slot name="rating"><GradeButtons
          :disabled="ratingDisabled"
          @grade="emit('grade', $event)"
        /></slot>
      </div>
    </template>
  </FlashcardContainer>
</template>
