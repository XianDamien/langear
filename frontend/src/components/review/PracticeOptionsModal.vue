<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, X } from 'lucide-vue-next'
import RetroButton from '@/components/ui/RetroButton.vue'
import { fetchPracticeOptions, type PracticeOption, type ReviewTemplate } from '@/services/review'
import { resourceError } from '@/services/content'

const props = defineProps<{
  open: boolean
  deckId: string
  deckName?: string
  initialTemplate?: ReviewTemplate
}>()

const emit = defineEmits<{
  close: []
  confirm: [value: { template: ReviewTemplate }]
}>()

const META: Record<ReviewTemplate, { label: string; description: string; unit: string }> = {
  sentence_retelling: { label: '复述', description: '听原句，口头复述并获取反馈', unit: '句' },
  sentence_translation: { label: '翻译', description: '看中文，输入英文译文', unit: '句' },
  sentence_dictation: { label: '听写', description: '听原句，写出英文', unit: '句' },
  vocabulary_english_to_chinese: { label: '英译中', description: '看单词，回忆中文释义', unit: '个' },
  vocabulary_chinese_to_english: { label: '中译英', description: '看释义，输入英文单词', unit: '个' },
}
const ORDER: ReviewTemplate[] = [
  'sentence_retelling',
  'sentence_translation',
  'sentence_dictation',
  'vocabulary_english_to_chinese',
  'vocabulary_chinese_to_english',
]

const options = ref<PracticeOption[]>([])
const selected = ref<ReviewTemplate>()
const loading = ref(false)
const error = ref('')

const available = computed(() =>
  ORDER.filter(key => options.value.some(option => option.key === key)),
)
const counts = computed(() =>
  Object.fromEntries(options.value.map(option => [option.key, option.count])),
)

async function load() {
  if (!props.open || !props.deckId) return
  loading.value = true
  error.value = ''
  try {
    options.value = await fetchPracticeOptions(props.deckId)
    selected.value = props.initialTemplate && available.value.includes(props.initialTemplate)
      ? props.initialTemplate
      : available.value[0]
  } catch (cause) {
    error.value = resourceError(cause)
  } finally {
    loading.value = false
  }
}

watch(() => [props.open, props.deckId], load, { immediate: true })

function choose(key: ReviewTemplate) {
  selected.value = key
}

function confirm() {
  if (!selected.value || loading.value || error.value) return
  emit('confirm', { template: selected.value })
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/60 p-4 sm:p-8"
    role="dialog"
    aria-modal="true"
    aria-labelledby="practice-options-title"
    data-testid="practice-options"
    @click.self="emit('close')"
  >
    <div class="w-full max-w-2xl border-2 border-slate-300 bg-brand-panel shadow-mech">
      <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
        <div>
          <p class="font-pixel text-xs uppercase tracking-widest text-slate-500">
            练习设置
          </p>
          <h2
            id="practice-options-title"
            class="mt-1 text-2xl font-bold uppercase text-brand-accent"
          >
            {{ deckName || '选择练习方式' }}
          </h2>
          <p class="mt-2 text-sm text-slate-600">
            怎么练？
          </p>
        </div>
        <button
          type="button"
          class="rounded border border-slate-200 p-1.5 text-slate-400 transition hover:border-brand-accent hover:text-brand-accent"
          aria-label="关闭练习设置"
          @click="emit('close')"
        >
          <X :size="18" />
        </button>
      </header>

      <div class="space-y-6 px-6 py-5">
        <div
          v-if="loading"
          class="py-8 text-center text-sm text-slate-500"
          role="status"
        >
          正在读取可用练习…
        </div>
        <div
          v-else-if="error"
          class="border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800"
          role="alert"
        >
          {{ error }}
          <button
            type="button"
            class="ml-2 underline"
            @click="load"
          >
            重试
          </button>
        </div>
        <p
          v-else-if="!available.length"
          class="py-8 text-center text-sm text-slate-500"
        >
          这个牌组还没有可练习的卡片。
        </p>

        <section v-else>
          <h3 class="mb-3 text-sm font-bold uppercase tracking-wide text-slate-600">
            练习类型
          </h3>
          <div class="grid gap-2">
            <button
              v-for="key in available"
              :key="key"
              type="button"
              class="flex items-center justify-between gap-4 border-2 px-4 py-3 text-left transition"
              :class="selected === key
                ? 'border-brand-accent bg-brand-accent/10'
                : 'border-slate-200 bg-white hover:border-brand-accent'"
              :aria-pressed="selected === key"
              :data-testid="`practice-option-${key}`"
              @click="choose(key)"
            >
              <span class="min-w-0">
                <span class="block font-bold uppercase text-slate-800">
                  {{ META[key].label }}
                </span>
                <span class="mt-1 block text-sm text-slate-500">
                  {{ META[key].description }}
                </span>
              </span>
              <span class="flex shrink-0 items-center gap-3">
                <span class="text-xs text-slate-500">{{ counts[key] }} {{ META[key].unit }}</span>
                <Check
                  v-if="selected === key"
                  :size="20"
                  class="text-brand-accent"
                />
              </span>
            </button>
          </div>
        </section>
      </div>

      <footer class="border-t border-slate-200 px-6 py-5">
        <RetroButton
          variant="primary"
          size="lg"
          class="w-full"
          :disabled="loading || !!error || !selected"
          data-testid="practice-confirm"
          @click="confirm"
        >
          开始练习
        </RetroButton>
      </footer>
    </div>
  </div>
</template>
