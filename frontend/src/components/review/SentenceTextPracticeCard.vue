<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import FlashcardContainer from '@/components/study/modules/FlashcardContainer.vue'
import StudyAudioPlayer from '@/components/study/StudyAudioPlayer.vue'
import TranscriptComparisonPanel from '@/components/study/TranscriptComparisonPanel.vue'
import RetroButton from '@/components/ui/RetroButton.vue'
import ReviewRatingButtons from './ReviewRatingButtons.vue'
import type { ResourceCard } from '@/services/contentCore'

const props = defineProps<{
  card: ResourceCard
  isFlipped: boolean
  audioUrl: string | null
  audioError: boolean
}>()
const emit = defineEmits<{ flip: []; retryAudio: [] }>()
const answer = ref('')
const showTranslation = ref(false)
const translation = computed(() => props.card.card_template_key === 'sentence_translation')
const inputLabel = computed(() => translation.value ? '我的译文' : '我的听写')
const hasAnswer = computed(() => answer.value.trim().length > 0)
watch(() => props.card.id, () => { answer.value = ''; showTranslation.value = false })
</script>

<template>
  <FlashcardContainer :is-flipped="isFlipped" class="h-full min-h-0 w-full" :data-testid="translation ? 'sentence-translation-card' : 'sentence-dictation-card'">
    <template #front>
      <div class="mx-auto w-full max-w-md space-y-5 text-left">
        <section v-if="translation" class="space-y-2" aria-label="中文原文">
          <h3 class="text-xs font-semibold text-slate-500">中文原文</h3>
          <p class="whitespace-pre-wrap break-words text-xl leading-relaxed text-slate-900" data-testid="translation-prompt">{{ card.front.chinese }}</p>
        </section>
        <template v-else>
          <StudyAudioPlayer prominent label="原音频" :src="audioUrl" />
          <p v-if="audioError" role="alert" class="text-center text-sm text-amber-700">
            音频加载失败 <button type="button" class="underline" @click="emit('retryAudio')">重试</button>
          </p>
        </template>
        <label class="block text-sm font-semibold text-slate-500">
          {{ inputLabel }}
          <textarea
            v-model="answer"
            :aria-label="inputLabel"
            rows="4"
            maxlength="10000"
            required
            :spellcheck="translation"
            autocapitalize="off"
            autocorrect="off"
            class="mt-2 w-full resize-y rounded border border-slate-200 bg-white p-3 text-base font-normal leading-7 text-slate-900 focus:border-brand-accent focus:outline-none focus:ring-2 focus:ring-brand-accent/20"
            :placeholder="translation ? '把上面的中文译成英文…' : '输入听到的英文…'"
          />
        </label>
        <p class="text-xs leading-5 text-slate-500">{{ translation ? '完成英文译文后，翻面对照参考表达。' : '可以重复播放；翻面后检查单词、大小写、标点和空格。' }}</p>
      </div>
    </template>
    <template v-if="!isFlipped" #actions>
      <div class="flex w-full justify-center">
        <RetroButton class="w-full max-w-md rounded-md" :disabled="!hasAnswer" @click="emit('flip')">显示答案</RetroButton>
      </div>
    </template>
    <template #back>
      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain pr-1" data-testid="study-card-content">
        <section v-if="translation" class="rounded-md border border-slate-200 bg-white p-4">
          <h3 class="mb-2 text-xs font-semibold text-slate-500">中文原文</h3>
          <p class="whitespace-pre-wrap break-words text-base leading-7 text-slate-900">{{ card.front.chinese }}</p>
        </section>
        <p v-if="audioError" role="alert" class="text-sm text-amber-700">
          音频加载失败 <button type="button" class="underline" @click="emit('retryAudio')">重试</button>
        </p>
        <TranscriptComparisonPanel
          :comparison-mode="translation ? 'translation' : 'dictation'"
          :reference-audio-url="audioUrl"
          :user-audio-url="null"
          :original-text="card.back.english || ''"
          :transcript-text="answer"
          :translation-text="translation ? '' : card.back.chinese || ''"
          :show-translation="showTranslation"
          :translation-loading="false"
          :transcript-label="inputLabel"
          :show-user-audio="false"
          @toggle-translation="showTranslation = !showTranslation"
        />
        <p class="px-1 text-xs leading-5 text-slate-500">{{ translation ? '译文可以有不同表达，参考译文供对照。' : '对照包含大小写、标点和空格。' }}</p>
        <section v-if="card.back.note" class="rounded-md border border-slate-200 bg-white p-3">
          <h3 class="mb-2 text-xs font-bold text-slate-500">学习笔记</h3>
          <p class="whitespace-pre-wrap break-words text-sm leading-6">{{ card.back.note }}</p>
        </section>
      </div>
      <div class="mt-3 shrink-0 border-t border-slate-200 pt-3" data-testid="study-rating-bar"><ReviewRatingButtons /></div>
    </template>
  </FlashcardContainer>
</template>
