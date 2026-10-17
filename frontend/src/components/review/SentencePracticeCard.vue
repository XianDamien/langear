<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Mic, Square } from 'lucide-vue-next'
import FlashcardContainer from '@/components/study/modules/FlashcardContainer.vue'
import StudyAudioPlayer from '@/components/study/StudyAudioPlayer.vue'
import ReviewRatingButtons from './ReviewRatingButtons.vue'
import SentenceTextPracticeCard from './SentenceTextPracticeCard.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import { useRecorder } from '@/composables/useRecorder'
import { libraryContent } from '@/services/libraryContent'
import type { ResourceCard } from '@/services/contentCore'

const props = defineProps<{ card: ResourceCard; isFlipped: boolean }>()
const emit = defineEmits<{ flip: [] }>()
const recorder = useRecorder()
const audioUrl = ref<string | null>(null)
const audioError = ref(false)
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
    const { data } = await libraryContent.get<{ url: string }>(`/media-assets/${id}/url`)
    if (request === generation) audioUrl.value = data.url
  } catch { if (request === generation) audioError.value = true }
}
watch(() => props.card.id, () => {
  recorder.reset()
  void loadAudio()
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
    @retry-audio="loadAudio"
    @flip="emit('flip')"
  />
  <FlashcardContainer v-else :is-flipped="isFlipped" class="h-full min-h-0 w-full">
    <template #front>
      <div class="mx-auto w-full max-w-xl space-y-5 text-left">
        <StudyAudioPlayer
          ref="referencePlayer"
          compact
          label="原音频"
          :src="audioUrl"
          @play="recordingPlayer?.pause()"
        />
        <p v-if="audioError" role="alert" class="text-sm text-amber-700">
          音频加载失败 <button type="button" class="underline" @click="loadAudio">重试</button>
        </p>
        <template v-if="retelling">
          <p class="text-center text-sm text-slate-500">听音后录音复述，翻面后对照原文。</p>
          <RetroButton
            :variant="recorder.isRecording.value ? 'danger' : 'secondary'"
            class="w-full rounded-md"
            data-testid="sentence-record-toggle"
            @click="toggleRecording"
          >
            <Square v-if="recorder.isRecording.value" :size="18" class="mr-2" />
            <Mic v-else :size="18" class="mr-2" />
            {{ recorder.isRecording.value ? '停止录音' : '录音' }}
          </RetroButton>
          <StudyAudioPlayer
            v-if="recorder.audioUrl.value && !recorder.isRecording.value"
            ref="recordingPlayer"
            compact
            label="我的录音"
            :src="recorder.audioUrl.value"
            @play="referencePlayer?.pause()"
          />
        </template>
        <RetroButton class="w-full rounded-md" :disabled="recorder.isRecording.value" @click="emit('flip')">
          显示答案
        </RetroButton>
      </div>
    </template>
    <template #back>
      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1">
        <template v-if="retelling">
          <section class="grid gap-4 rounded-md border border-slate-200 bg-white p-4 md:grid-cols-2">
            <div>
              <h3 class="mb-2 text-xs font-semibold text-slate-500">原文</h3>
              <p class="whitespace-pre-wrap text-base leading-7">{{ card.back.english }}</p>
              <p v-if="card.back.chinese" class="mt-2 text-sm leading-6 text-slate-500">{{ card.back.chinese }}</p>
            </div>
            <StudyAudioPlayer ref="referencePlayer" compact label="原音频" :src="audioUrl" @play="recordingPlayer?.pause()" />
          </section>
          <StudyAudioPlayer ref="recordingPlayer" compact label="我的录音" :src="recorder.audioUrl.value" @play="referencePlayer?.pause()" />
          <p class="text-xs text-slate-500">录音仅在本次练习中保留；自动转写与 AI 反馈尚未接入。</p>
        </template>
        <section v-if="card.back.note" class="rounded-md border border-slate-200 bg-white p-3">
          <h3 class="mb-2 text-xs font-bold text-slate-500">笔记</h3>
          <p class="whitespace-pre-wrap text-sm leading-6">{{ card.back.note }}</p>
        </section>
      </div>
      <div class="mt-3 shrink-0 border-t border-slate-200 pt-3">
        <ReviewRatingButtons />
      </div>
    </template>
  </FlashcardContainer>
</template>
