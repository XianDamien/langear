<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import RetellingCard from '@/components/study/cards/RetellingCard.vue'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useRealtimeAsr } from '@/composables/useRealtimeAsr'
import type { PollingResponseCompleted } from '@/types/api'
import ReviewRatingButtons from './ReviewRatingButtons.vue'
import SentenceTextPracticeCard from './SentenceTextPracticeCard.vue'
import { useRecorder } from '@/composables/useRecorder'
import { reviewHttp, type PracticeInput, type ReviewAttempt } from '@/services/review'
import type { ResourceCard } from '@/services/content'

const props = defineProps<{ card: ResourceCard; isFlipped: boolean; busy?: boolean; attempt?: ReviewAttempt }>()
const emit = defineEmits<{ flip: [input: PracticeInput] }>()
const recorder = useRecorder()
const audioUrl = ref<string | null>(null)
const audioError = ref(false)
const savedRecordingUrl = ref<string | null>(null)
const player = useAudioPlayer()
const realtime = useRealtimeAsr()
const recordingBusy = ref(false)
const notes = ref('')
const showTranslation = ref(false)
const userTranscript = computed(() => props.attempt?.asr_result?.text || realtime.finalTranscript.value)
const legacyCard = computed(() => ({
  id: props.card.id, frontAudio: audioUrl.value || undefined,
  backText: props.card.back.english || '', backTranslation: props.card.back.chinese || '', difficulty: 0,
}))
const feedback = computed<Pick<PollingResponseCompleted, 'feedback'> | null>(() => props.attempt?.ai_feedback ? {
  feedback: { ...props.attempt.ai_feedback, issues: props.attempt.ai_feedback.issues || [] },
} : null)
watch(() => props.card.id, id => {
  try { notes.value = sessionStorage.getItem(`langear:review-notes:${id}`) || '' }
  catch { notes.value = '' }
}, { immediate: true })
watch(notes, value => {
  try { sessionStorage.setItem(`langear:review-notes:${props.card.id}`, value) } catch { /* Optional local notes. */ }
})
const retelling = computed(() => props.card.card_template_key === 'sentence_retelling')
let generation = 0
let disposed = false
async function loadAudio() {
  const request = ++generation
  audioUrl.value = null
  audioError.value = false
  const id = props.card.front.reference_audio || props.card.back.reference_audio
  if (!id) return
  try {
    const { data } = await reviewHttp.get<{ url: string }>(`/media-assets/${id}/url`)
    if (request === generation) audioUrl.value = data.url
  } catch { if (request === generation) audioError.value = true }
}
watch(() => `${props.card.id}:${props.card.front.reference_audio || ''}:${props.card.back.reference_audio || ''}`, () => {
  void loadAudio()
}, { immediate: true })
watch(() => props.attempt?.media_asset_id, async id => {
  const request = generation
  savedRecordingUrl.value = null
  if (!id || recorder.audioUrl.value) return
  try {
    const { data } = await reviewHttp.get<{ url: string }>(`/media-assets/${id}/url`)
    if (request === generation) savedRecordingUrl.value = data.url
  } catch { audioError.value = true }
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; generation++; player.stop(); realtime.reset() })
watch(() => props.isFlipped, flipped => { if (flipped) player.stop() })
function playReference() {
  // Replaying the reference must not leave the previous take's transcript on screen.
  realtime.clearTranscript()
  if (audioUrl.value) player.play(audioUrl.value)
}
async function toggleRecording() {
  if (recordingBusy.value || props.busy) return
  player.stop()
  if (recorder.isRecording.value) {
    recorder.stopRecording()
    recordingBusy.value = true
    try { if (realtime.status.value === 'streaming') await realtime.commit() }
    finally { recordingBusy.value = false }
  } else {
    recordingBusy.value = true
    try {
      // A new take replaces the previous one; its transcript must not stay on the card.
      realtime.reset()
      await realtime.connectReview(props.card.id, reviewHttp.defaults.baseURL || '/api/v1')
      if (disposed) { realtime.reset(); return }
      await recorder.startRecording(chunk => realtime.appendAudioChunk(chunk))
    } finally { recordingBusy.value = false }
  }
}
function flipRecording() {
  if (!recorder.recordingBlob.value || recorder.isRecording.value || recordingBusy.value) return
  player.stop()
  emit('flip', { type: 'audio', blob: recorder.recordingBlob.value,
    ...(realtime.status.value === 'ready' && realtime.realtimeSessionId.value ? { realtimeSessionId: realtime.realtimeSessionId.value } : {}),
  })
}
</script>

<template>
  <SentenceTextPracticeCard
    v-if="!retelling"
    :card="card"
    :is-flipped="isFlipped"
    :audio-url="audioUrl"
    :audio-error="audioError"
    :busy="busy"
    :attempt="attempt"
    @retry-audio="loadAudio"
    @flip="emit('flip', $event)"
  >
    <template #toolbar>
      <slot name="toolbar" />
    </template>
    <template #rating>
      <slot name="rating">
        <ReviewRatingButtons />
      </slot>
    </template>
    <template #feedback>
      <slot name="feedback" />
    </template>
  </SentenceTextPracticeCard>
  <RetellingCard
    v-else
    :card="legacyCard"
    :is-flipped="isFlipped"
    :audio-playing="player.isPlaying.value"
    :is-recording="recorder.isRecording.value"
    :live-transcript="realtime.partialTranscript.value"
    :user-transcript="userTranscript"
    :front-transcript="realtime.finalTranscript.value"
    :user-audio-url="recorder.audioUrl.value || savedRecordingUrl"
    :feedback="feedback"
    :async-submit-state="['pending', 'processing'].includes(attempt?.ai_status || '') ? 'processing' : attempt?.ai_status || 'idle'"
    :error-message="attempt?.ai_status === 'failed' ? '反馈处理失败，作答和录音已保存，仍可评分。' : null"
    :show-translation="showTranslation"
    :translation-loading="false"
    :notes="notes"
    :rating-disabled="busy || false"
    :controls-disabled="busy || recordingBusy"
    :flip-disabled="busy || recordingBusy || recorder.isRecording.value || !recorder.recordingBlob.value"
    class="h-full min-h-0 w-full"
    @play-reference="playReference"
    @toggle-recording="toggleRecording"
    @flip="flipRecording"
    @show-translation="showTranslation = !showTranslation"
    @update:notes="notes = $event"
  >
    <template #toolbar>
      <slot name="toolbar" />
    </template>
    <template #front-status>
      <p
        v-if="audioError"
        role="alert"
        class="mt-2 text-sm text-amber-700"
      >
        音频加载失败 <button
          type="button"
          class="underline"
          @click="loadAudio"
        >
          重试
        </button>
      </p>
      <p
        v-if="realtime.status.value === 'failed'"
        role="status"
        class="mt-2 text-xs text-slate-500"
      >
        实时转写暂不可用，录音会在保存后转写。
      </p>
    </template>
    <template #processing>
      <p
        v-if="attempt && ['pending', 'processing', 'failed'].includes(attempt.asr_status)"
        role="status"
        class="text-xs text-slate-500"
      >
        转写：{{ attempt.asr_status === 'failed' ? '处理失败，录音已保留' : '等待处理' }}
      </p>
    </template>
    <template #rating>
      <slot name="rating">
        <ReviewRatingButtons />
      </slot>
    </template>
  </RetellingCard>
</template>
