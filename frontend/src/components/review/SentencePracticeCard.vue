<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Mic, Square } from 'lucide-vue-next'
import FlashcardContainer from '@/components/study/modules/FlashcardContainer.vue'
import StudyAudioPlayer from '@/components/study/StudyAudioPlayer.vue'
import ReviewRatingButtons from './ReviewRatingButtons.vue'
import SentenceTextPracticeCard from './SentenceTextPracticeCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import { useRecorder } from '@/composables/useRecorder'
import { reviewHttp, type PracticeInput, type ReviewAttempt } from '@/services/review'
import type { ResourceCard } from '@/services/contentCore'

const props = defineProps<{ card: ResourceCard; isFlipped: boolean; busy?: boolean; attempt?: ReviewAttempt }>()
const emit = defineEmits<{ flip: [input: PracticeInput] }>()
const recorder = useRecorder()
const audioUrl = ref<string | null>(null)
const audioError = ref(false)
const savedRecordingUrl = ref<string | null>(null)
const referencePlayer = ref<InstanceType<typeof StudyAudioPlayer>>()
const recordingPlayer = ref<InstanceType<typeof StudyAudioPlayer>>()
const retelling = computed(() => props.card.card_template_key === 'sentence_retelling')
let generation = 0
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
onBeforeUnmount(() => { generation++ })
async function toggleRecording() {
  referencePlayer.value?.pause()
  recordingPlayer.value?.pause()
  if (recorder.isRecording.value) recorder.stopRecording()
  else await recorder.startRecording()
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
    <template #rating>
      <slot name="rating">
        <ReviewRatingButtons />
      </slot>
    </template>
    <template #feedback>
      <slot name="feedback" />
    </template>
  </SentenceTextPracticeCard>
  <FlashcardContainer
    v-else
    :is-flipped="isFlipped"
    class="h-full min-h-0 w-full"
  >
    <template #front>
      <div class="mx-auto w-full max-w-xl space-y-5 text-left">
        <StudyAudioPlayer
          ref="referencePlayer"
          compact
          label="原音频"
          :src="audioUrl"
          @play="recordingPlayer?.pause()"
        />
        <p
          v-if="audioError"
          role="alert"
          class="text-sm text-amber-700"
        >
          音频加载失败 <button
            type="button"
            class="underline"
            @click="loadAudio"
          >
            重试
          </button>
        </p>
        <template v-if="retelling">
          <p class="text-center text-sm text-slate-500">
            听音后录音复述，翻面后对照原文。
          </p>
          <RetroButton
            :variant="recorder.isRecording.value ? 'danger' : 'secondary'"
            class="w-full rounded-md"
            data-testid="sentence-record-toggle"
            :disabled="busy"
            @click="toggleRecording"
          >
            <Square
              v-if="recorder.isRecording.value"
              :size="18"
              class="mr-2"
            />
            <Mic
              v-else
              :size="18"
              class="mr-2"
            />
            {{ recorder.isRecording.value ? '停止录音' : '录音' }}
          </RetroButton>
          <StudyAudioPlayer
            v-if="recorder.audioUrl.value && !recorder.isRecording.value"
            ref="recordingPlayer"
            compact
            label="我的录音"
            :src="recorder.audioUrl.value || savedRecordingUrl"
            @play="referencePlayer?.pause()"
          />
        </template>
        <RetroButton
          class="w-full rounded-md"
          :disabled="busy || recorder.isRecording.value || !recorder.recordingBlob.value"
          @click="recorder.recordingBlob.value && emit('flip', { type: 'audio', blob: recorder.recordingBlob.value })"
        >
          显示答案
        </RetroButton>
      </div>
    </template>
    <template #back>
      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1">
        <template v-if="retelling">
          <section class="grid gap-4 rounded-md border border-slate-200 bg-white p-4 md:grid-cols-2">
            <div>
              <h3 class="mb-2 text-xs font-semibold text-slate-500">
                原文
              </h3>
              <p class="whitespace-pre-wrap text-base leading-7">
                {{ card.back.english }}
              </p>
              <p
                v-if="card.back.chinese"
                class="mt-2 text-sm leading-6 text-slate-500"
              >
                {{ card.back.chinese }}
              </p>
            </div>
            <StudyAudioPlayer
              ref="referencePlayer"
              compact
              label="原音频"
              :src="audioUrl"
              @play="recordingPlayer?.pause()"
            />
          </section>
          <StudyAudioPlayer
            ref="recordingPlayer"
            compact
            label="我的录音"
            :src="recorder.audioUrl.value || savedRecordingUrl"
            @play="referencePlayer?.pause()"
          />
          <p class="text-xs text-slate-500">
            录音已保存到本次作答。
          </p>
          <slot name="feedback" />
        </template>
        <section
          v-if="card.back.note"
          class="rounded-md border border-slate-200 bg-white p-3"
        >
          <h3 class="mb-2 text-xs font-bold text-slate-500">
            笔记
          </h3>
          <p class="whitespace-pre-wrap text-sm leading-6">
            {{ card.back.note }}
          </p>
        </section>
      </div>
      <div class="mt-3 shrink-0 border-t border-slate-200 pt-3">
        <slot name="rating">
          <ReviewRatingButtons />
        </slot>
      </div>
    </template>
  </FlashcardContainer>
</template>
