<script setup lang="ts">
import { ref, watch } from 'vue'
import { reviewHttp, type ReviewAttempt } from '@/services/review'
import { dialogueError, type DialogueSource } from '@/services/dialogue'
import ReviewAttemptStatus from '@/components/review/ReviewAttemptStatus.vue'
const props = defineProps<{ source: DialogueSource }>()
const attempt = ref<ReviewAttempt>()
const error = ref('')
watch(() => props.source.attempt_id, async id => {
  attempt.value = undefined; error.value = ''
  try {
    const { data } = await reviewHttp.get<ReviewAttempt>(`/attempts/${id}`)
    if (props.source.attempt_id !== id) return
    if (data.card_id !== props.source.card_id) throw new Error('引用与原卡片不一致')
    attempt.value = data
  } catch (cause) { if (props.source.attempt_id === id) error.value = dialogueError(cause) }
}, { immediate: true })
</script>
<template>
  <section
    class="space-y-3 rounded-xl border border-teal-200 p-4"
    aria-label="原卡片与反馈"
  >
    <h3 class="font-semibold">
      原卡片与反馈
    </h3>
    <p
      v-if="error"
      role="alert"
      class="text-sm text-amber-800"
    >
      {{ error }}
    </p>
    <template v-else-if="attempt">
      <p
        v-for="(value, key) in attempt.back_snapshot"
        :key="key"
        class="text-sm"
      >
        {{ value }}
      </p>
      <p
        v-if="attempt.asr_result?.text"
        class="text-sm text-slate-600"
      >
        你的转写：{{ attempt.asr_result.text }}
      </p>
      <p
        v-if="attempt.input_snapshot.type === 'text'"
        class="text-sm text-slate-600"
      >
        你的作答：{{ attempt.input_snapshot.text }}
      </p>
      <ReviewAttemptStatus :attempt="attempt" />
    </template>
    <p
      v-else
      role="status"
      class="text-sm text-slate-500"
    >
      正在读取原练习…
    </p>
  </section>
</template>
