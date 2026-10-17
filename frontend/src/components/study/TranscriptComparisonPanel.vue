<script setup lang="ts">
import { computed, ref } from 'vue'
import StudyAudioPlayer from './StudyAudioPlayer.vue'
import { Languages } from 'lucide-vue-next'
import type { DictationResult } from '@/services/review'
import { buildTranscriptDiff, type DiffTokenView } from '@/utils/transcriptDiff'

const props = withDefaults(defineProps<{
  referenceAudioUrl: string | null
  userAudioUrl: string | null
  originalText: string
  transcriptText: string
  translationText: string
  showTranslation: boolean
  translationLoading: boolean
  nouns?: string[]
  verbs?: string[]
  transcriptLabel?: string
  showUserAudio?: boolean
  deterministicResult?: DictationResult
  comparisonMode?: 'retelling' | 'translation' | 'dictation'
}>(), { showUserAudio: true })

const emit = defineEmits<{
  wordClick: [word: string]
  toggleTranslation: []
}>()

const referencePlayer = ref<InstanceType<typeof StudyAudioPlayer> | null>(null)
const userPlayer = ref<InstanceType<typeof StudyAudioPlayer> | null>(null)

async function jumpToUserAudio(timestamp: number) {
  if (!props.userAudioUrl) return
  referencePlayer.value?.pause()
  await userPlayer.value?.jumpTo(timestamp)
}

defineExpose({ jumpToUserAudio })

const strict = computed(() => props.comparisonMode === 'dictation')
const showDiff = computed(() => props.comparisonMode !== 'translation')
const interactive = computed(() => !props.comparisonMode || props.comparisonMode === 'retelling')
const preserveFormatting = computed(() => !interactive.value)
const originalLabel = computed(() => props.comparisonMode === 'translation' ? '参考译文' : strict.value ? '标准答案' : '原文')
const diffRows = computed(() => {
  const result = props.deterministicResult
  if (!result) return buildTranscriptDiff(props.originalText, props.transcriptText, preserveFormatting.value)
  const tokens = (text: string, side: 'expected' | 'actual'): DiffTokenView[] => Array.from(text).map((raw, index) => ({
    raw, normalized: raw, index,
    status: result.differences.some(diff => index >= diff[`${side}_range`].start && index < diff[`${side}_range`].end) ? 'replace' : 'match',
  }))
  return { original: tokens(result.normalized_expected, 'expected'), transcript: tokens(result.normalized_actual, 'actual'), counts: { changed: result.differences.length } }
})

function tokenClasses(token: DiffTokenView, side: 'original' | 'transcript') {
  const classes = [
    'inline rounded py-0.5 text-[15px] leading-7 transition-colors',
  ]
  if (!preserveFormatting.value) classes.push('px-0.5')

  if (!showDiff.value || token.status === 'match') {
    classes.push('text-slate-700')
  } else if (token.status === 'remove') {
    classes.push(
      'bg-rose-50 text-rose-700 line-through decoration-rose-500 decoration-2',
    )
  } else if (token.status === 'add') {
    classes.push('bg-emerald-50 text-emerald-700')
  } else {
    classes.push('bg-amber-50 text-amber-700')
  }

  if (side === 'original') {
    const normalized = token.normalized
    if (props.nouns?.includes(normalized)) {
      classes.push('ring-1 ring-sky-200')
    } else if (props.verbs?.includes(normalized)) {
      classes.push('ring-1 ring-brand-accent/30')
    }
    if (interactive.value) classes.push('cursor-pointer hover:bg-orange-50 hover:text-brand-accent focus-visible:outline-brand-accent')
  }

  return classes
}
</script>

<template>
  <section
    class="rounded-md border border-slate-200 bg-white px-4 sm:px-5"
    data-testid="transcription-result"
  >
    <div class="grid items-start gap-4 py-4 md:grid-cols-2 md:gap-6" data-testid="original-row">
      <div class="min-w-0">
        <h3 class="mb-1.5 text-xs font-semibold text-slate-500">{{ originalLabel }}</h3>
        <div class="break-words" :class="{ 'whitespace-pre-wrap': preserveFormatting }" data-testid="original-text">
          <template v-for="token in diffRows.original" :key="`original-${token.index}-${token.raw}`">
            <button
              v-if="interactive"
              type="button"
              :class="tokenClasses(token, 'original')"
              @click="emit('wordClick', token.raw)"
            >{{ token.raw }}</button><span v-else :class="tokenClasses(token, 'original')">{{ token.raw }}</span>{{ preserveFormatting ? '' : ' ' }}
          </template>
        </div>
        <button
          v-if="translationText || interactive"
          type="button"
          class="mt-2 inline-flex items-center gap-1.5 text-xs text-slate-500 transition hover:text-brand-accent"
          :aria-expanded="showTranslation"
          @click="emit('toggleTranslation')"
        >
          <Languages :size="13" />
          {{ showTranslation ? '隐藏中文' : '显示中文' }}
        </button>
        <p
          v-if="showTranslation"
          class="mt-2 text-sm leading-6 text-slate-500"
          data-testid="original-translation"
        >
          {{ translationLoading ? 'AI 翻译生成中...' : (translationText || '暂无翻译') }}
        </p>
      </div>
      <StudyAudioPlayer
        v-if="referenceAudioUrl || interactive"
        ref="referencePlayer"
        compact
        class="md:mt-5"
        label="原音频"
        :src="referenceAudioUrl"
        @play="userPlayer?.pause()"
      />
    </div>

    <div class="grid items-start gap-4 border-t border-slate-200 py-4 md:grid-cols-2 md:gap-6" data-testid="transcript-row">
      <div class="min-w-0">
        <div class="mb-1.5 flex items-center gap-2">
          <h3 class="text-xs font-semibold text-slate-500">{{ transcriptLabel || '转写' }}</h3>
          <span v-if="showDiff" class="text-xs text-slate-400" data-testid="text-difference-count">{{ diffRows.counts.changed }} 处差异</span>
        </div>
        <div v-if="diffRows.transcript.length > 0" class="break-words" :class="{ 'whitespace-pre-wrap': preserveFormatting }">
          <template v-for="token in diffRows.transcript" :key="`transcript-${token.index}-${token.raw}`">
            <span :class="tokenClasses(token, 'transcript')">{{ token.raw }}</span>{{ preserveFormatting ? '' : ' ' }}
          </template>
        </div>
        <p v-else class="text-sm text-slate-400">{{ transcriptLabel ? '未填写' : '暂无转写' }}</p>
      </div>
      <StudyAudioPlayer
        v-if="showUserAudio !== false"
        ref="userPlayer"
        compact
        class="md:mt-5"
        label="我的录音"
        :src="userAudioUrl"
        @play="referencePlayer?.pause()"
      />
    </div>
  </section>
</template>
