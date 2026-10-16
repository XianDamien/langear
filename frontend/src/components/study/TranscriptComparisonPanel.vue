<script setup lang="ts">
import { computed, ref } from 'vue'
import StudyAudioPlayer from './StudyAudioPlayer.vue'
import { Languages } from 'lucide-vue-next'
import { buildTranscriptDiff, type DiffTokenView } from '@/utils/transcriptDiff'

const props = defineProps<{
  referenceAudioUrl: string | null
  userAudioUrl: string | null
  originalText: string
  transcriptText: string
  translationText: string
  showTranslation: boolean
  translationLoading: boolean
  nouns?: string[]
  verbs?: string[]
}>()

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

const diffRows = computed(() => buildTranscriptDiff(props.originalText, props.transcriptText))

function tokenClasses(token: DiffTokenView, side: 'original' | 'transcript') {
  const classes = [
    'inline rounded px-0.5 py-0.5 text-[15px] leading-7 transition-colors',
  ]

  if (token.status === 'match') {
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
    classes.push('cursor-pointer hover:bg-orange-50 hover:text-brand-accent focus-visible:outline-brand-accent')
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
        <h3 class="mb-1.5 text-xs font-semibold text-slate-500">原文</h3>
        <div class="break-words" data-testid="original-text">
          <template v-for="token in diffRows.original" :key="`original-${token.index}-${token.raw}`">
            <button
              type="button"
              :class="tokenClasses(token, 'original')"
              @click="emit('wordClick', token.raw)"
            >{{ token.raw }}</button>{{ ' ' }}
          </template>
        </div>
        <button
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
          <h3 class="text-xs font-semibold text-slate-500">转写</h3>
          <span class="text-xs text-slate-400">{{ diffRows.counts.changed }} 处差异</span>
        </div>
        <div v-if="diffRows.transcript.length > 0" class="break-words">
          <template v-for="token in diffRows.transcript" :key="`transcript-${token.index}-${token.raw}`">
            <span :class="tokenClasses(token, 'transcript')">{{ token.raw }}</span>{{ ' ' }}
          </template>
        </div>
        <p v-else class="text-sm text-slate-400">暂无转写</p>
      </div>
      <StudyAudioPlayer
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
